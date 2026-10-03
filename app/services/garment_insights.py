"""
Estadísticas → Prendas (Fase C de docs/PLAN_ESTADISTICAS.md), por tienda.

Fuente de ventas: las prendas guardadas en InvoiceItemFact (se cargan con el
resumen de facturas, ver app/services/invoice_facts.py) + las de HOY en vivo
desde Alegra. Fuente de stock: los ítems activos de Alegra
(`AlegraClient.get_active_items`, paginado y cacheado 5 min por tienda).

Indicadores:
  - C2: prendas por factura y precio promedio por prenda, total y por vendedora.
  - C3: más vendidos que están agotados; curva de tallas venta vs. stock.
  - C4: rotación por tipo de prenda (días de inventario al ritmo de venta del periodo).

No cuentan en ningún indicador (decisiones del usuario 2026-10-02): la
"BOLSA PAPEL" y las tarjetas/bonos de regalo (cada tarjeta es un ítem
distinto en Alegra: llenaban "agotados" y no son prendas). Talla, departamento y tipo de prenda se
leen del nombre con SKUParser ("CAMISETA MUJER 49900 / 1052499002").
"""
import logging
from collections import defaultdict
from datetime import date, timedelta
from functools import lru_cache
from typing import Any, Dict, Iterable, List, Optional

from app.models.invoice_fact import InvoiceItemFact
from app.services.invoice_facts import invoice_to_items, missing_item_days
from app.services.sku_parser import SKUParser

logger = logging.getLogger(__name__)

NO_SELLER = 'Sin vendedora'
OTHER_DEPARTMENT = 'OTROS'  # sin género en el nombre (accesorios, blusas sin MUJER...)
DEPARTMENT_ORDER = ['MUJER', 'HOMBRE', 'NIÑA', 'NIÑO', OTHER_DEPARTMENT]
ALPHA_SIZES = ['XS', 'S', 'M', 'L', 'XL', 'XXL']
LOW_STOCK_UNITS = 2       # "por agotarse": 1 o 2 unidades
SLOW_ROTATION_DAYS = 180  # más de 6 meses de inventario al ritmo actual
FAST_ROTATION_DAYS = 15   # se acaba en menos de 2 semanas


EXCLUDED_KEYWORDS = ('BOLSA PAPEL', 'TARJETA REGALO', 'BONO REGALO')

# Prendas de mujer cuyo nombre no dice "MUJER" y cuyo SKU no trae el código de
# departamento (ej. "BLUSA 89900 / 1040899001"): sin esto caían en "Otros".
WOMEN_ONLY_KEYWORDS = ('BLUSA', 'CROPTOP', 'CROP TOP', 'FALDA', 'VESTIDO')


def is_excluded(name: str) -> bool:
    """Bolsa y tarjetas de regalo: se venden, pero no son prendas."""
    upper = str(name or '').upper()
    return any(k in upper for k in EXCLUDED_KEYWORDS)


@lru_cache(maxsize=8192)
def parse_garment(name: str) -> Dict[str, str]:
    """Tipo de prenda, departamento y talla a partir del nombre de Alegra."""
    parsed = SKUParser.extract_size_from_product_name(str(name or ''))
    base = (parsed.get('product_base') or str(name or '')).strip().upper() or 'SIN NOMBRE'
    gender = parsed.get('gender') or 'UNKNOWN'
    size = parsed.get('size') or 'UNKNOWN'
    return {
        'product': base,
        'department': gender if gender in DEPARTMENT_ORDER
        else 'MUJER' if any(k in base for k in WOMEN_ONLY_KEYWORDS) else OTHER_DEPARTMENT,
        'size': size if size != 'UNKNOWN' else 'SIN TALLA',
    }


def size_family(size: str) -> str:
    if size in ALPHA_SIZES:
        return 'Letras'
    if size.isdigit():
        return 'Números'
    if '-' in size:
        return 'Niños'
    return 'Única / sin talla'


def _size_sort_key(size: str):
    if size in ALPHA_SIZES:
        return (0, ALPHA_SIZES.index(size), size)
    if size.isdigit():
        return (1, int(size), size)
    if '-' in size and size.split('-')[0].isdigit():
        return (2, int(size.split('-')[0]), size)
    return (3, 0, size)


def _pct(part: float, whole: float) -> float:
    return round(part * 100 / whole, 1) if whole else 0.0


def garment_rows(rows: Iterable[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Renglones vendidos sin la bolsa y con cantidad positiva."""
    return [r for r in rows if not is_excluded(r.get('name')) and (r.get('quantity') or 0) > 0]


# ─── C2: prendas por factura y precio promedio ──────────────────────────────

def _basket(rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    invoices = {r['invoice_alegra_id'] for r in rows}
    units = sum(int(r['quantity']) for r in rows)
    revenue = sum(int(r['total']) for r in rows)
    return {
        'invoices': len(invoices),
        'units': units,
        'revenue': revenue,
        'units_per_invoice': round(units / len(invoices), 2) if invoices else 0,
        'avg_price_per_unit': round(revenue / units) if units else 0,
    }


def seller_baskets(rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    by_seller: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    names: Dict[str, str] = {}
    for r in rows:
        key = r.get('seller_id') or ''
        by_seller[key].append(r)
        names[key] = r.get('seller_name') or NO_SELLER
    result = [{'id': key or None, 'name': names[key], **_basket(seller_rows)}
              for key, seller_rows in by_seller.items()]
    return sorted(result, key=lambda s: s['revenue'], reverse=True)


def top_products(rows: List[Dict[str, Any]], limit: int = 15) -> List[Dict[str, Any]]:
    acc: Dict[str, Dict[str, Any]] = defaultdict(lambda: {'units': 0, 'revenue': 0})
    for r in rows:
        g = parse_garment(r['name'])
        acc[g['product']]['units'] += int(r['quantity'])
        acc[g['product']]['revenue'] += int(r['total'])
    out = [{'product': p, **v} for p, v in acc.items()]
    return sorted(out, key=lambda p: (p['units'], p['revenue']), reverse=True)[:limit]


# ─── Stock (ítems activos de Alegra) ────────────────────────────────────────

def stock_variants(items: Iterable[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    """id de ítem → {name, stock}. Solo variantes con inventario, sin obsoletos (*) ni la bolsa."""
    out = {}
    for item in items:
        name = str(item.get('name') or '')
        if item.get('type') != 'variant' or name.strip().startswith('*') or is_excluded(name):
            continue
        inventory = item.get('inventory') or {}
        if not inventory:
            continue
        out[str(item.get('id'))] = {'name': name, 'stock': int(inventory.get('availableQuantity') or 0)}
    return out


def _sold_by_item(rows: List[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    acc: Dict[str, Dict[str, Any]] = {}
    for r in rows:
        key = r.get('item_id') or f"name:{r['name']}"
        entry = acc.setdefault(key, {'item_id': r.get('item_id'), 'name': r['name'], 'units': 0, 'revenue': 0})
        entry['units'] += int(r['quantity'])
        entry['revenue'] += int(r['total'])
    return acc


# ─── C3: más vendidos agotados ──────────────────────────────────────────────

def best_sellers_stock(rows: List[Dict[str, Any]], stock: Dict[str, Dict[str, Any]],
                       limit: int = 25) -> Dict[str, Any]:
    """Variantes (prenda + talla) más vendidas con su stock actual."""
    sold = sorted(_sold_by_item(rows).values(), key=lambda v: (v['units'], v['revenue']), reverse=True)
    out_of_stock, low_stock = [], []
    for entry in sold:
        if not entry['item_id'] or entry['item_id'] not in stock:
            continue  # ítem inactivo o borrado en Alegra: sin stock que comparar
        current = stock[entry['item_id']]['stock']
        g = parse_garment(entry['name'])
        row = {**entry, **g, 'stock': current}
        if current <= 0 and len(out_of_stock) < limit:
            out_of_stock.append(row)
        elif 0 < current <= LOW_STOCK_UNITS and len(low_stock) < limit:
            low_stock.append(row)
    return {'out_of_stock': out_of_stock, 'low_stock': low_stock, 'low_stock_units': LOW_STOCK_UNITS}


# ─── C3: curva de tallas venta vs. stock ────────────────────────────────────

def size_curve(rows: List[Dict[str, Any]], stock: Dict[str, Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Por departamento y familia de tallas (letras, números, niños): % de las
    prendas vendidas y % del stock en cada talla. Si una talla se vende más de
    lo que pesa en el stock, se acaba primero.
    """
    groups: Dict[tuple, Dict[str, Dict[str, int]]] = defaultdict(lambda: defaultdict(lambda: {'sold': 0, 'stock': 0}))
    for r in rows:
        g = parse_garment(r['name'])
        groups[(g['department'], size_family(g['size']))][g['size']]['sold'] += int(r['quantity'])
    for variant in stock.values():
        qty = max(variant['stock'], 0)
        if not qty:
            continue
        g = parse_garment(variant['name'])
        groups[(g['department'], size_family(g['size']))][g['size']]['stock'] += qty

    result = []
    for (department, family), sizes in groups.items():
        if family == 'Única / sin talla':
            continue  # sin curva que comparar
        sold_total = sum(v['sold'] for v in sizes.values())
        stock_total = sum(v['stock'] for v in sizes.values())
        if not sold_total:
            continue
        result.append({
            'department': department,
            'family': family,
            'sold_units': sold_total,
            'stock_units': stock_total,
            'sizes': [{
                'size': size,
                'sold_units': v['sold'],
                'sold_pct': _pct(v['sold'], sold_total),
                'stock_units': v['stock'],
                'stock_pct': _pct(v['stock'], stock_total),
            } for size, v in sorted(sizes.items(), key=lambda kv: _size_sort_key(kv[0]))],
        })
    order = {d: i for i, d in enumerate(DEPARTMENT_ORDER)}
    return sorted(result, key=lambda g: (order.get(g['department'], 99), g['family']))


# ─── C4: rotación / días de inventario ──────────────────────────────────────

def rotation(rows: List[Dict[str, Any]], stock: Dict[str, Dict[str, Any]], days: int) -> List[Dict[str, Any]]:
    """
    Por tipo de prenda ("CAMISETA MUJER"): vendidas en el periodo, venta por
    día, stock actual y días de inventario (stock ÷ venta diaria). Sin ventas
    en el periodo → días = None ("sin ventas"). `days` = días CON prendas
    guardadas (no los del rango): si faltan días, dividir por todo el rango
    bajaba la venta diaria e inflaba los días de inventario.
    """
    acc: Dict[str, Dict[str, int]] = defaultdict(lambda: {'sold': 0, 'stock': 0})
    for r in rows:
        acc[parse_garment(r['name'])['product']]['sold'] += int(r['quantity'])
    for variant in stock.values():
        if variant['stock'] > 0:
            acc[parse_garment(variant['name'])['product']]['stock'] += variant['stock']

    out = []
    for product, v in acc.items():
        daily = v['sold'] / days if days else 0
        days_left = round(v['stock'] / daily) if daily else None
        if days_left is None:
            status = 'sin ventas' if v['stock'] else None
        elif v['stock'] == 0:
            status = 'agotado'
        elif days_left > SLOW_ROTATION_DAYS:
            status = 'lenta'
        elif days_left < FAST_ROTATION_DAYS:
            status = 'se agota pronto'
        else:
            status = 'normal'
        if status is None:
            continue
        out.append({'product': product, 'sold_units': v['sold'], 'daily_units': round(daily, 2),
                    'stock_units': v['stock'], 'days_of_inventory': days_left, 'status': status})
    return sorted(out, key=lambda p: (p['sold_units'], p['stock_units']), reverse=True)


# ─── Servicio ───────────────────────────────────────────────────────────────

class GarmentInsightsService:
    def __init__(self, store_code: str, today: date, invoices_client=None):
        self.store_code = store_code
        self.today = today
        self.client = invoices_client  # AlegraClient de la tienda (ventas de hoy y stock)

    def _rows(self, start: date, end: date) -> Dict[str, Any]:
        closed_end = min(end, self.today - timedelta(days=1))
        rows: List[Dict[str, Any]] = []
        missing: List[date] = []
        if start <= closed_end:
            missing = missing_item_days(self.store_code, start, closed_end)
            query = InvoiceItemFact.query.filter(
                InvoiceItemFact.store_code == self.store_code,
                InvoiceItemFact.date >= start,
                InvoiceItemFact.date <= closed_end,
            )
            rows = [{
                'invoice_alegra_id': f.invoice_alegra_id, 'seller_id': f.seller_id, 'seller_name': f.seller_name,
                'item_id': f.item_id, 'name': f.name, 'quantity': f.quantity, 'total': f.total,
            } for f in query]
        closed_rows = garment_rows(rows)
        today_rows: List[Dict[str, Any]] = []
        if end >= self.today and self.client is not None:
            for invoice in self.client.get_invoices_by_date(self.today.isoformat()):
                today_rows.extend(invoice_to_items(invoice))
        today_rows = garment_rows(today_rows)
        days = (end - start).days + 1
        closed_days = (closed_end - start).days + 1 if start <= closed_end else 0
        return {
            'rows': closed_rows + today_rows,
            # Rotación: solo días cerrados (hoy va por la mitad y contarlo como
            # día completo bajaba la venta diaria). Si el periodo es solo hoy, hoy.
            'closed_rows': closed_rows,
            'closed_loaded_days': closed_days - len(missing),
            'today_rows': today_rows,
            'coverage': {
                'days': days,
                'loaded_days': days - len(missing),
                'missing_days': len(missing),
                'first_missing_day': missing[0].isoformat() if missing else None,
                'complete': not missing,
            },
        }

    @staticmethod
    def _rotation(data: Dict[str, Any], stock: Dict[str, Dict[str, Any]]) -> List[Dict[str, Any]]:
        if data['closed_loaded_days']:
            return rotation(data['closed_rows'], stock, data['closed_loaded_days'])
        return rotation(data['today_rows'], stock, 1 if data['today_rows'] else 0)

    def summary(self, start: date, end: date) -> Dict[str, Any]:
        """C2: canasta total y por vendedora + prendas más vendidas (solo base de datos + hoy)."""
        data = self._rows(start, end)
        rows = data['rows']
        return {
            'date_range': {'start': start.isoformat(), 'end': end.isoformat()},
            'coverage': data['coverage'],
            'totals': _basket(rows),
            'sellers': seller_baskets(rows),
            'top_products': top_products(rows),
        }

    def stock_analysis(self, start: date, end: date) -> Dict[str, Any]:
        """C3 y C4: necesita el stock actual de Alegra (primera vez ~1 min, luego caché)."""
        data = self._rows(start, end)
        rows = data['rows']
        stock = stock_variants(self.client.get_active_items())
        return {
            'date_range': {'start': start.isoformat(), 'end': end.isoformat()},
            'coverage': data['coverage'],
            'stock_variants': len(stock),
            'stock_units': sum(max(v['stock'], 0) for v in stock.values()),
            'best_sellers': best_sellers_stock(rows, stock),
            'size_curve': size_curve(rows, stock),
            'rotation': self._rotation(data, stock),
            'thresholds': {'slow_days': SLOW_ROTATION_DAYS, 'fast_days': FAST_ROTATION_DAYS},
        }
