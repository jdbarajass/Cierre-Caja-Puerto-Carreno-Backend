"""
Estadísticas → Llegadas (Fase D1 de docs/PLAN_ESTADISTICAS.md), por tienda.

Carga: las compras de mercancía de Alegra (`/bills`, con sus prendas) desde
el 1-ene-2026 se guardan en PurchaseItemFact. Son pocas: cada carga
reemplaza TODAS las del periodo en una transacción; si Alegra falla, no se
toca nada. Corre junto con la carga de facturas (cron de las 9 pm y botón).

Indicadores: cada llegada (misma fecha y proveedor, aunque sean varias
facturas de compra) con las prendas que llegaron, cuántas se vendieron desde
ese día (prendas guardadas, días cerrados) y el % vendido. Las ventas de una
referencia se asignan primero a la llegada más antigua del periodo
consultado (aproximado: no se sabe cuánto stock había antes). La bolsa y las
tarjetas de regalo no cuentan (como en Prendas).
"""
import logging
from collections import defaultdict
from datetime import date, datetime, timedelta
from typing import Any, Dict, List

from sqlalchemy import func

from app.models.invoice_fact import InvoiceItemFact
from app.models.purchase_fact import PurchaseItemFact
from app.models.user import db
from app.services.garment_insights import is_excluded, parse_garment
from app.services.invoice_facts import missing_item_days
from app.utils.formatters import safe_number

logger = logging.getLogger(__name__)

STALE_DAYS = 30          # una llegada de hace 30 días o más sin ventas = "no se mueve"
STALE_LIST_LIMIT = 40
SKIPPED_STATUSES = ('void', 'draft')


def _str(value, max_len):
    return str(value or '').strip()[:max_len] or None


def bill_to_rows(bill: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Renglones de PurchaseItemFact de una compra de /api/v1/bills (anuladas y borradores: ninguno)."""
    if str(bill.get('status') or '').lower() in SKIPPED_STATUSES:
        return []
    provider = bill.get('provider') or {}
    template = bill.get('numberTemplate') or {}
    day = datetime.strptime(str(bill.get('date'))[:10], '%Y-%m-%d').date()
    items = (bill.get('purchases') or {}).get('items') or []
    rows = []
    for line, item in enumerate(items):
        quantity = int(round(safe_number(item.get('quantity'))))
        if quantity <= 0:
            continue
        rows.append({
            'bill_alegra_id': str(bill.get('id')),
            'bill_number': _str(template.get('fullNumber') or template.get('number'), 40),
            'line': line,
            'date': day,
            'provider_id': _str(provider.get('id'), 30),
            'provider_name': _str(provider.get('name'), 200),
            'item_id': _str(item.get('id'), 30),
            'name': _str(item.get('name'), 200) or 'Sin nombre',
            'quantity': quantity,
            'unit_price': int(round(safe_number(item.get('price')))),
        })
    return rows


def sync_purchases(direct_client, store_code: str, since: date) -> Dict[str, Any]:
    """Reemplaza las compras guardadas desde `since` por las de Alegra. Devuelve cuántas."""
    bills = direct_client.get_bills_since(since.isoformat())  # si falla, no se toca nada
    rows = [r for b in bills for r in bill_to_rows(b)]
    try:
        PurchaseItemFact.query.filter(
            PurchaseItemFact.store_code == store_code, PurchaseItemFact.date >= since,
        ).delete(synchronize_session=False)
        db.session.add_all(PurchaseItemFact(store_code=store_code, **r) for r in rows)
        db.session.commit()
    except Exception:
        db.session.rollback()
        raise
    return {'bills': len({r['bill_alegra_id'] for r in rows}), 'items': len(rows),
            'units': sum(r['quantity'] for r in rows)}


def purchases_status(store_code: str) -> Dict[str, Any]:
    q = PurchaseItemFact.query.filter(PurchaseItemFact.store_code == store_code)
    last_sync, last_date = q.with_entities(func.max(PurchaseItemFact.synced_at), func.max(PurchaseItemFact.date)).one()
    return {
        'bills': q.with_entities(func.count(func.distinct(PurchaseItemFact.bill_alegra_id))).scalar() or 0,
        'last_synced_at': last_sync.isoformat() + 'Z' if last_sync else None,
        'last_purchase_date': last_date.isoformat() if last_date else None,
    }


# ─── Asignación de ventas a llegadas ────────────────────────────────────────

def allocate_sales(arrivals: List[Dict[str, Any]], sales_by_day: Dict[date, int]) -> None:
    """
    Una referencia (item): `arrivals` = renglones de llegada [{date, quantity}]
    y `sales_by_day` = unidades vendidas por día. Asigna cada venta a la
    llegada MÁS ANTIGUA ya recibida ese día que aún tenga unidades. Escribe
    `sold` en cada llegada.
    """
    arrivals.sort(key=lambda a: a['date'])
    for a in arrivals:
        a['sold'] = 0
    for day in sorted(sales_by_day):
        units = sales_by_day[day]
        for a in arrivals:
            if units <= 0:
                break
            if a['date'] > day:
                break
            free = a['quantity'] - a['sold']
            if free > 0:
                take = min(free, units)
                a['sold'] += take
                units -= take


def _pct(part, whole):
    return round(part * 100 / whole, 1) if whole else 0.0


class ArrivalsService:
    def __init__(self, store_code: str, today: date):
        self.store_code = store_code
        self.today = today

    def summary(self, start: date, end: date) -> Dict[str, Any]:
        yesterday = self.today - timedelta(days=1)
        purchases = [r for r in PurchaseItemFact.query.filter(
            PurchaseItemFact.store_code == self.store_code,
            PurchaseItemFact.date >= start, PurchaseItemFact.date <= end,
        ) if not is_excluded(r.name)]

        lines: List[Dict[str, Any]] = [{
            'date': r.date, 'provider': r.provider_name or 'Sin proveedor', 'bill': r.bill_number or r.bill_alegra_id,
            'item_id': r.item_id, 'name': r.name, 'quantity': r.quantity, 'unit_price': r.unit_price,
        } for r in purchases]

        # Ventas (días cerrados con prendas guardadas) de las referencias que llegaron
        item_ids = {l['item_id'] for l in lines if l['item_id']}
        sales: Dict[str, Dict[date, int]] = defaultdict(lambda: defaultdict(int))
        missing: List[date] = []
        if lines and start <= yesterday:
            missing = missing_item_days(self.store_code, start, yesterday)
            rows = db.session.query(InvoiceItemFact.item_id, InvoiceItemFact.date,
                                    func.sum(InvoiceItemFact.quantity)).filter(
                InvoiceItemFact.store_code == self.store_code,
                InvoiceItemFact.date >= start, InvoiceItemFact.date <= yesterday,
                InvoiceItemFact.item_id.in_(item_ids),
            ).group_by(InvoiceItemFact.item_id, InvoiceItemFact.date)
            for item_id, day, qty in rows:
                sales[item_id][day] += int(qty or 0)

        by_item: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
        for l in lines:
            by_item[l['item_id'] or f"name:{l['name']}"].append(l)
        for key, item_lines in by_item.items():
            allocate_sales(item_lines, sales.get(key, {}))

        arrivals = self._arrivals(lines)
        stale = sorted(
            ({**self._line_view(l), 'arrival_date': l['date'].isoformat(), 'provider': l['provider'],
              'days_since_arrival': (self.today - l['date']).days}
             for l in lines if l['sold'] == 0 and (self.today - l['date']).days >= STALE_DAYS),
            key=lambda l: (l['units'], l['days_since_arrival']), reverse=True)[:STALE_LIST_LIMIT]

        units = sum(l['quantity'] for l in lines)
        sold = sum(l['sold'] for l in lines)
        days = (yesterday - start).days + 1 if start <= yesterday else 0
        return {
            'date_range': {'start': start.isoformat(), 'end': end.isoformat()},
            'sales_until': yesterday.isoformat(),
            'coverage': {
                'days': days,
                'missing_days': len(missing),
                'first_missing_day': missing[0].isoformat() if missing else None,
                'complete': not missing,
            },
            'totals': {
                'arrivals': len(arrivals),
                'units': units,
                'sold_units': sold,
                'sell_through_pct': _pct(sold, units),
                'value': sum(l['quantity'] * l['unit_price'] for l in lines),
            },
            'arrivals': arrivals,
            'stale': stale,
            'stale_days': STALE_DAYS,
            'status': purchases_status(self.store_code),
        }

    @staticmethod
    def _line_view(l: Dict[str, Any]) -> Dict[str, Any]:
        g = parse_garment(l['name'])
        return {'item_id': l['item_id'], 'name': l['name'], 'product': g['product'], 'size': g['size'],
                'department': g['department'], 'units': l['quantity'], 'sold_units': l['sold'],
                'unit_price': l['unit_price']}

    def _arrivals(self, lines: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        groups: Dict[tuple, List[Dict[str, Any]]] = defaultdict(list)
        for l in lines:
            groups[(l['date'], l['provider'])].append(l)
        out = []
        for (day, provider), group in groups.items():
            units = sum(l['quantity'] for l in group)
            sold = sum(l['sold'] for l in group)
            # Mismo tipo de prenda en la llegada: una fila por prenda (todas sus tallas)
            products: Dict[str, Dict[str, Any]] = {}
            for l in group:
                view = self._line_view(l)
                p = products.setdefault(view['product'], {'product': view['product'], 'department': view['department'],
                                                          'units': 0, 'sold_units': 0, 'sizes': []})
                p['units'] += view['units']
                p['sold_units'] += view['sold_units']
                p['sizes'].append({'size': view['size'], 'units': view['units'], 'sold_units': view['sold_units'],
                                   'name': view['name'], 'item_id': view['item_id']})
            product_rows = sorted(products.values(), key=lambda p: p['units'], reverse=True)
            for p in product_rows:
                p['sell_through_pct'] = _pct(p['sold_units'], p['units'])
            out.append({
                'date': day.isoformat(),
                'provider': provider,
                'bills': sorted({l['bill'] for l in group}),
                'days_since_arrival': (self.today - day).days,
                'units': units,
                'sold_units': sold,
                'sell_through_pct': _pct(sold, units),
                'value': sum(l['quantity'] * l['unit_price'] for l in group),
                'unsold_references': sum(1 for l in group if l['sold'] == 0),
                'products': product_rows,
            })
        return sorted(out, key=lambda a: a['date'], reverse=True)
