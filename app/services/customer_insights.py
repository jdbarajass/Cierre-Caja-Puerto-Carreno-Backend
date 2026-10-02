"""
Dashboard de clientes (por tienda) a partir de los reportes agregados de
Alegra (/api/v1/reports/sales-by-client y sales-by-seller, ver
AlegraDirectClient). Alegra suma el rango en el servidor, así que un año
completo son pocas consultas en vez de una por día.

Indicadores:
  - % de la venta con cliente identificado (total y por vendedora). Las
    ventas sin cliente quedan en "Consumidor final" (NIT 222222222222).
  - Mejores clientes por monto, frecuencia y descuento.
  - Compras del equipo: clientes que son vendedoras (misma cédula, o todos
    los nombres de la vendedora dentro del nombre del cliente). Siguen en
    el ranking, marcadas, y además se resumen aparte.
  - Clientes nuevos vs recurrentes: compraron en el periodo y nunca antes.
  - Clientas inactivas: compraron en el último año pero no en los últimos
    N días; las que más han comprado traen teléfono y última compra.

Todo es por tienda: el cliente de Alegra ya viene con las credenciales de
la tienda del request y la caché lleva la tienda en la clave.
"""
import logging
import re
import unicodedata
from concurrent.futures import ThreadPoolExecutor
from datetime import date, timedelta
from typing import Any, Dict, List, Optional

from app.utils.ttl_cache import TTLCache

logger = logging.getLogger(__name__)

ANONYMOUS_IDENTIFICATION = '222222222222'
# Primer día que se considera "historia" para saber si un cliente es nuevo.
HISTORY_START = date(2015, 1, 1)
INACTIVE_LOOKBACK_DAYS = 365
INACTIVE_ENRICH_LIMIT = 50  # teléfono + última compra: una consulta por clienta
NEW_CLIENTS_LIST_LIMIT = 10

# Un rango ya cerrado casi no cambia; uno que incluye hoy, sí.
CLOSED_RANGE_TTL = 12 * 3600
OPEN_RANGE_TTL = 10 * 60
CONTACT_TTL = 12 * 3600

_cache = TTLCache()


def clear_cache():
    _cache.clear()


def _cached(key: str, ttl: float, loader):
    value = _cache.get(key)
    if value is None:
        value = loader()
        _cache.set(key, value, ttl)
    return value


# ─── Normalización ───────────────────────────────────────────────────────────

def _num(value) -> int:
    try:
        return int(round(float(value or 0)))
    except (TypeError, ValueError):
        return 0


# El mismo reporte trae nombres distintos según el servidor de Alegra:
# reports-api v2 (web / conector) usa afterTaxes; /api/v1 (la plataforma,
# Basic) usa total. Verificado 2026-10-02 en producción: leer solo
# afterTaxes dejaba todos los montos en 0.
AMOUNT_KEYS = ('afterTaxes', 'total')
SUBTOTAL_KEYS = ('subTotal', 'subtotal')
DISCOUNT_KEYS = ('discount', 'totalDiscount')

_warned_missing_amount = False


def _field(row: Dict[str, Any], keys) -> int:
    """Primer campo presente (aunque valga 0) entre los nombres posibles."""
    for key in keys:
        if row.get(key) is not None:
            return _num(row.get(key))
    return 0


def row_amount(row: Dict[str, Any]) -> int:
    """Monto después de impuestos de una fila de sales-by-client / sales-by-seller."""
    global _warned_missing_amount
    if not any(row.get(k) is not None for k in AMOUNT_KEYS) and not _warned_missing_amount:
        _warned_missing_amount = True
        logger.warning(f'Fila de Alegra sin monto ({"/".join(AMOUNT_KEYS)}); campos: {sorted(row)}')
    return _field(row, AMOUNT_KEYS)


def _clean_name(name) -> str:
    return re.sub(r'\s+', ' ', str(name or '')).strip()


def _name_tokens(name) -> set:
    plain = unicodedata.normalize('NFKD', str(name or '')).encode('ascii', 'ignore').decode()
    return set(re.findall(r'[A-Z0-9]+', plain.upper()))


def _pct(part, whole) -> Optional[float]:
    return round(part * 100 / whole, 1) if whole else None


def normalize_client(row: Dict[str, Any]) -> Dict[str, Any]:
    documents = _num(row.get('totalDocuments'))
    subtotal = _field(row, SUBTOTAL_KEYS)
    discount = _field(row, DISCOUNT_KEYS)
    total = row_amount(row)
    return {
        'id': str(row.get('idLocal') or ''),
        'name': _clean_name(row.get('clientName') or row.get('name')),
        'identification': str(row.get('identification') or '').strip(),
        'documents': documents,
        'subtotal': subtotal,
        'discount': discount,
        'discount_pct': _pct(discount, subtotal),
        'total': total,
        'average_ticket': round(total / documents) if documents else 0,
    }


def is_anonymous(client: Dict[str, Any]) -> bool:
    return (client['identification'] == ANONYMOUS_IDENTIFICATION
            or client['name'].lower() == 'consumidor final')


def match_employee(client: Dict[str, Any], sellers: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    """
    Vendedora que corresponde a este cliente, o None. Primero por cédula; si
    no, por nombre: TODAS las palabras del nombre de la vendedora deben estar
    en el del cliente ("MONICA VARGAS" ⊂ "MONICA ALEJANDRA VARGAS"). Nombres
    de una sola palabra ("TATIANA") no se comparan: darían falsos positivos.
    """
    for seller in sellers:
        ident = str(seller.get('identification') or '').strip()
        if ident and ident == client['identification']:
            return seller
    client_tokens = _name_tokens(client['name'])
    for seller in sellers:
        seller_tokens = _name_tokens(seller.get('name'))
        if len(seller_tokens) >= 2 and seller_tokens <= client_tokens:
            return seller
    return None


def whatsapp_number(phone) -> Optional[str]:
    """Celular colombiano en formato internacional para wa.me (573001234567), o None."""
    digits = re.sub(r'\D', '', str(phone or ''))
    if len(digits) == 12 and digits.startswith('573'):
        return digits
    if len(digits) == 10 and digits.startswith('3'):
        return f'57{digits}'
    return None


def contact_phone(contact: Dict[str, Any]) -> Optional[str]:
    """Primer número que sirva para WhatsApp; si ninguno, el primero que haya."""
    phones = [contact.get(k) for k in ('mobile', 'phonePrimary', 'phoneSecondary')]
    phones = [str(p).strip() for p in phones if p and str(p).strip()]
    for phone in phones:
        if whatsapp_number(phone):
            return phone
    return phones[0] if phones else None


# ─── Cálculos puros (sin red) ────────────────────────────────────────────────

def _rank(clients, key, limit):
    return sorted(clients, key=key, reverse=True)[:limit]


def build_summary(
    client_rows: List[Dict[str, Any]],
    seller_rows: List[Dict[str, Any]],
    sellers: List[Dict[str, Any]],
    seller_client_rows: Dict[str, Optional[List[Dict[str, Any]]]],
    history_ids: Optional[set],
    top_limit: int = 25,
) -> Dict[str, Any]:
    """
    client_rows: sales-by-client del periodo. seller_rows: sales-by-seller del
    periodo. sellers: todas las vendedoras. seller_client_rows: sales-by-client
    filtrado por vendedora (None si no se pudo). history_ids: ids de clientes
    con compras ANTES del periodo (None si no se pudo consultar).
    """
    clients = [normalize_client(r) for r in client_rows]
    anonymous = [c for c in clients if is_anonymous(c)]
    identified = [c for c in clients if not is_anonymous(c)]

    for c in identified:
        seller = match_employee(c, sellers)
        c['employee'] = {'seller_id': str(seller.get('id')), 'seller_name': _clean_name(seller.get('name'))} if seller else None

    total_sales = sum(c['total'] for c in clients)
    total_documents = sum(c['documents'] for c in clients)
    anonymous_sales = sum(c['total'] for c in anonymous)
    anonymous_documents = sum(c['documents'] for c in anonymous)
    identified_sales = total_sales - anonymous_sales
    identified_documents = total_documents - anonymous_documents

    employees = sorted((c for c in identified if c['employee']), key=lambda c: c['total'], reverse=True)

    # Por vendedora: su venta y cuánto de ella quedó sin cliente.
    seller_blocks = []
    for row in seller_rows:
        seller_id = str(row.get('idLocal') or '')
        total = row_amount(row)
        documents = _num(row.get('totalDocuments'))
        block = {
            'id': seller_id,
            'name': _clean_name(row.get('sellerName') or row.get('name')),
            'total': total,
            'documents': documents,
            'discount': _field(row, DISCOUNT_KEYS),
            'identified_available': False,
        }
        rows = seller_client_rows.get(seller_id)
        if rows is not None:
            anon = [c for c in (normalize_client(r) for r in rows) if is_anonymous(c)]
            anon_total = sum(c['total'] for c in anon)
            anon_docs = sum(c['documents'] for c in anon)
            block.update({
                'identified_available': True,
                'identified_sales': total - anon_total,
                'identified_documents': documents - anon_docs,
                'identified_pct': _pct(total - anon_total, total),
                'identified_documents_pct': _pct(documents - anon_docs, documents),
            })
        seller_blocks.append(block)
    seller_blocks.sort(key=lambda s: s['total'], reverse=True)
    unassigned_sales = total_sales - sum(s['total'] for s in seller_blocks)

    new_vs_returning = None
    if history_ids is not None:
        new = [c for c in identified if c['id'] not in history_ids]
        returning = [c for c in identified if c['id'] in history_ids]
        new_vs_returning = {
            'new_clients': len(new),
            'new_sales': sum(c['total'] for c in new),
            'returning_clients': len(returning),
            'returning_sales': sum(c['total'] for c in returning),
            'top_new': _rank(new, lambda c: c['total'], NEW_CLIENTS_LIST_LIMIT),
        }

    return {
        'kpis': {
            'total_sales': total_sales,
            'total_documents': total_documents,
            'identified_sales': identified_sales,
            'identified_documents': identified_documents,
            'identified_pct': _pct(identified_sales, total_sales),
            'identified_documents_pct': _pct(identified_documents, total_documents),
            'unique_clients': len(identified),
            'average_per_client': round(identified_sales / len(identified)) if identified else 0,
            'total_discount': sum(c['discount'] for c in clients),
        },
        'anonymous': {
            'total': anonymous_sales,
            'documents': anonymous_documents,
            'discount': sum(c['discount'] for c in anonymous),
        },
        'top_by_amount': _rank(identified, lambda c: (c['total'], c['documents']), top_limit),
        'top_by_frequency': _rank(identified, lambda c: (c['documents'], c['total']), top_limit),
        'top_by_discount': _rank([c for c in identified if c['discount'] > 0],
                                 lambda c: (c['discount'], c['total']), top_limit),
        'employees': {
            'clients': employees,
            'total': sum(c['total'] for c in employees),
            'documents': sum(c['documents'] for c in employees),
            'discount': sum(c['discount'] for c in employees),
            'share_of_discount_pct': _pct(sum(c['discount'] for c in employees),
                                          sum(c['discount'] for c in clients)),
        },
        'sellers': seller_blocks,
        'unassigned_sales': unassigned_sales if unassigned_sales > 0 else 0,
        'new_vs_returning': new_vs_returning,
    }


def build_inactive(before_rows: List[Dict[str, Any]], recent_rows: List[Dict[str, Any]],
                   sellers: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Clientes con compras en `before_rows` y ninguna en `recent_rows`, de mayor a menor compra."""
    recent_ids = {normalize_client(r)['id'] for r in recent_rows}
    inactive = []
    for row in before_rows:
        c = normalize_client(row)
        if is_anonymous(c) or c['id'] in recent_ids:
            continue
        seller = match_employee(c, sellers)
        c['employee'] = {'seller_id': str(seller.get('id')), 'seller_name': _clean_name(seller.get('name'))} if seller else None
        inactive.append(c)
    inactive.sort(key=lambda c: (c['total'], c['documents']), reverse=True)
    return inactive


# ─── Consultas a Alegra (con caché por tienda) ───────────────────────────────

class CustomerInsightsService:
    """Arma el dashboard de clientes de UNA tienda."""

    def __init__(self, client, store_code: str, today: date):
        self.client = client
        self.store = store_code
        self.today = today

    def _ttl(self, end: date) -> float:
        return CLOSED_RANGE_TTL if end < self.today else OPEN_RANGE_TTL

    def _clients(self, start: date, end: date, seller_id: Optional[str] = None):
        key = f'{self.store}:clients:{start}:{end}:{seller_id or ""}'
        return _cached(key, self._ttl(end), lambda: self.client.get_sales_by_client(
            start.isoformat(), end.isoformat(), seller_id))

    def _seller_sales(self, start: date, end: date):
        key = f'{self.store}:seller-sales:{start}:{end}'
        return _cached(key, self._ttl(end), lambda: self.client.get_sales_by_seller(
            start.isoformat(), end.isoformat()))

    def _sellers(self):
        return _cached(f'{self.store}:sellers', CONTACT_TTL, self.client.get_sellers)

    def _seller_clients_checked(self, start, end, seller_row) -> Optional[List[Dict[str, Any]]]:
        """
        sales-by-client filtrado por vendedora, solo si el filtro funcionó: la
        suma debe dar la venta de la vendedora (si Alegra ignorara el filtro
        devolvería la de toda la tienda y el % saldría mal sin avisar).
        """
        seller_id = str(seller_row.get('idLocal') or '')
        if not seller_id:
            return None
        try:
            rows = self._clients(start, end, seller_id)
        except Exception as e:
            logger.warning(f'[{self.store}] Clientes de la vendedora {seller_id}: {e}')
            return None
        expected = row_amount(seller_row)
        got = sum(row_amount(r) for r in rows)
        if abs(got - expected) > max(1, expected * 0.005):
            logger.warning(f'[{self.store}] Filtro por vendedora {seller_id} no cuadra '
                           f'(esperado {expected}, recibido {got}); se omite su % identificado')
            return None
        return rows

    def summary(self, start: date, end: date, top_limit: int = 25) -> Dict[str, Any]:
        history_end = start - timedelta(days=1)
        with ThreadPoolExecutor(max_workers=4) as pool:
            f_clients = pool.submit(self._clients, start, end)
            f_seller_sales = pool.submit(self._seller_sales, start, end)
            f_sellers = pool.submit(self._sellers)
            f_history = pool.submit(self._clients, HISTORY_START, history_end) if history_end >= HISTORY_START else None

            client_rows = f_clients.result()
            seller_rows = f_seller_sales.result()
            # Vendedoras e historia son complementos: si fallan, el resto sale igual.
            try:
                sellers = f_sellers.result()
            except Exception as e:
                logger.warning(f'[{self.store}] No se pudo leer la lista de vendedoras: {e}')
                sellers = []
            history_ids = set()
            if f_history is not None:
                try:
                    history_ids = {normalize_client(r)['id'] for r in f_history.result()}
                except Exception as e:
                    logger.warning(f'[{self.store}] No se pudo leer la historia de clientes: {e}')
                    history_ids = None

            active_sellers = [r for r in seller_rows if _num(r.get('totalDocuments')) > 0]
            futures = {str(r.get('idLocal') or ''): pool.submit(self._seller_clients_checked, start, end, r)
                       for r in active_sellers}
            seller_client_rows = {sid: f.result() for sid, f in futures.items()}

        if client_rows:
            logger.info(f'[{self.store}] Campos de sales-by-client en Alegra: {sorted(client_rows[0])}')
        data = build_summary(client_rows, seller_rows, sellers, seller_client_rows, history_ids, top_limit)
        data['history_since'] = HISTORY_START.isoformat()
        return data

    def _contact_info(self, client_id: str) -> Dict[str, Any]:
        """
        Teléfono y última compra de una clienta. Solo se guarda en caché si
        las dos consultas salieron bien: un error pasajero de Alegra (ej.
        demasiadas consultas seguidas) no debe dejarla "sin celular" 12 h.
        """
        key = f'{self.store}:contact:{client_id}'
        cached = _cache.get(key)
        if cached is not None:
            return cached

        info = {'phone': None, 'whatsapp': None, 'last_purchase': None}
        complete = True
        try:
            phone = contact_phone(self.client.get_contact(client_id) or {})
            info.update({'phone': phone, 'whatsapp': whatsapp_number(phone)})
        except Exception as e:
            complete = False
            logger.warning(f'[{self.store}] Contacto {client_id}: {e}')
        try:
            info['last_purchase'] = self.client.get_last_invoice_date(client_id)
        except Exception as e:
            complete = False
            logger.warning(f'[{self.store}] Última compra de {client_id}: {e}')
        if complete:
            _cache.set(key, info, CONTACT_TTL)
        return info

    def inactive(self, days: int, lookback_days: int = INACTIVE_LOOKBACK_DAYS,
                 enrich_limit: int = INACTIVE_ENRICH_LIMIT) -> Dict[str, Any]:
        recent_start = self.today - timedelta(days=days - 1)
        before_end = recent_start - timedelta(days=1)
        before_start = self.today - timedelta(days=lookback_days)

        with ThreadPoolExecutor(max_workers=3) as pool:
            f_before = pool.submit(self._clients, before_start, before_end)
            f_recent = pool.submit(self._clients, recent_start, self.today)
            f_sellers = pool.submit(self._sellers)
            before_rows, recent_rows = f_before.result(), f_recent.result()
            try:
                sellers = f_sellers.result()
            except Exception:
                sellers = []

        inactive = build_inactive(before_rows, recent_rows, sellers)
        top = inactive[:enrich_limit]
        with ThreadPoolExecutor(max_workers=5) as pool:
            infos = list(pool.map(lambda c: self._contact_info(c['id']), top))
        for c, info in zip(top, infos):
            c.update(info)
            c['days_since_last_purchase'] = (
                (self.today - date.fromisoformat(info['last_purchase'])).days if info['last_purchase'] else None)

        return {
            'days': days,
            'lookback_days': lookback_days,
            'periods': {
                'before': {'start': before_start.isoformat(), 'end': before_end.isoformat()},
                'recent': {'start': recent_start.isoformat(), 'end': self.today.isoformat()},
            },
            'inactive_count': len(inactive),
            'inactive_sales': sum(c['total'] for c in inactive),
            'clients': top,
        }
