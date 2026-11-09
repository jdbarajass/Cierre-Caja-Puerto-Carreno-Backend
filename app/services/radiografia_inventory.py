"""
Radiografía del inventario (Fase 3 de docs/PLAN_RADIOGRAFIA.md): cuánta plata
hay en ropa, cuántos días alcanza, qué rota y qué está quieto, por tienda.

Solo lee. Datos:
- Stock y precio de lista: ítems activos de Alegra (la misma lista en caché que
  usa Estadísticas → Prendas); variantes con inventario, sin obsoletos (*) ni
  bolsa/tarjetas. Valor a costo = precio de lista × (1 − margen): ESTIMADO.
- Ventas: copia de prendas (InvoiceItemFact), solo días cerrados.
- Llegadas: compras de mercancía guardadas (PurchaseItemFact). Una tienda que
  abrió hace poco (Primavera, 25-oct-2026, mercancía entrada con ajustes y no
  con compras) cuenta todo como llegado el día que abrió: nada es "quieto"
  antes de N días de abierta.
- Rotación con el inventario de HOY (no con el promedio de las fotos de fin
  de mes: en Carreño las fotos antes del 7-oct-2026 están infladas por la
  anulación de 2025). ESTIMADO.
"""
from collections import defaultdict
from datetime import date, timedelta
from typing import Any, Dict, Iterable, List, Optional

from sqlalchemy import func

from app.models.invoice_fact import InvoiceFact, InvoiceItemFact
from app.models.purchase_fact import PurchaseItemFact
from app.models.user import db
from app.services import radiografia as r
from app.services.garment_insights import DEPARTMENT_ORDER, is_excluded, parse_garment

QUIET_OPTIONS = (60, 90, 180)
SALES_WINDOW_DAYS = 90     # ritmo de venta para días de inventario y las tablas
ROTATION_WINDOW_DAYS = 365
COPY_START = date(2026, 1, 1)
QUIET_LIMIT = 300
TOP_LIMIT = 15


def variants(items: Iterable[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    """id → {name, stock, price} de las variantes con inventario (sin obsoletos ni bolsa/tarjetas)."""
    out = {}
    for item in items:
        name = str(item.get('name') or '')
        if item.get('type') != 'variant' or name.strip().startswith('*') or is_excluded(name):
            continue
        inventory = item.get('inventory') or {}
        if not inventory:
            continue
        price = None
        for p in item.get('price') or []:
            if isinstance(p, dict) and (p.get('main') or price is None):
                price = p.get('price')
        out[str(item.get('id'))] = {'name': name, 'stock': int(float(inventory.get('availableQuantity') or 0)),
                                    'price': float(price or 0)}
    return out


def _sales_by_item(store: str, start: date, end: date) -> Dict[str, Dict[str, Any]]:
    """item_id (o nombre) → unidades, precio de lista vendido, venta y última venta."""
    out: Dict[str, Dict[str, Any]] = {}
    if start > end:
        return out
    q = db.session.query(
        InvoiceItemFact.item_id, InvoiceItemFact.name, func.sum(InvoiceItemFact.quantity),
        func.sum(InvoiceItemFact.quantity * InvoiceItemFact.unit_price), func.sum(InvoiceItemFact.total),
        func.max(InvoiceItemFact.date),
    ).filter(InvoiceItemFact.store_code == store, InvoiceItemFact.date >= start, InvoiceItemFact.date <= end,
             InvoiceItemFact.quantity > 0).group_by(InvoiceItemFact.item_id, InvoiceItemFact.name)
    for item_id, name, units, lista, total, last in q:
        if is_excluded(name):
            continue
        key = str(item_id) if item_id else f'name:{name}'
        e = out.setdefault(key, {'name': name, 'units': 0, 'lista': 0.0, 'ventas': 0.0, 'last_sale': None})
        e['units'] += int(units or 0)
        e['lista'] += float(lista or 0)
        e['ventas'] += float(total or 0)
        if last and (e['last_sale'] is None or last > e['last_sale']):
            e['last_sale'] = last
    return out


def _arrivals(store: str) -> Dict[str, date]:
    """item_id → última llegada (compra de mercancía guardada)."""
    q = db.session.query(PurchaseItemFact.item_id, func.max(PurchaseItemFact.date)).filter(
        PurchaseItemFact.store_code == store, PurchaseItemFact.item_id.isnot(None),
        PurchaseItemFact.quantity > 0).group_by(PurchaseItemFact.item_id)
    return {str(i): d for i, d in q}


def _opened(store: str) -> Optional[date]:
    """Primer día con ventas en la copia, si la tienda abrió después de que empezó la copia
    (más de un mes después: Carreño puede no vender el 1-ene, festivo)."""
    first = db.session.query(func.min(InvoiceFact.date)).filter(InvoiceFact.store_code == store).scalar()
    return first if first and first > COPY_START + timedelta(days=31) else None


def _loaded_days(store: str, start: date, end: date) -> int:
    from app.services.invoice_facts import missing_item_days
    if start > end:
        return 0
    return (end - start).days + 1 - len(missing_item_days(store, start, end))


def build_inventory(store: str, today: date, items: List[Dict[str, Any]], quiet_days: int = 90) -> Dict[str, Any]:
    from app.services.finance_settings import get_settings
    margin = get_settings(store)['margin_pct']
    keep = 1 - margin / 100
    yesterday = today - timedelta(days=1)
    opened = _opened(store)
    copy_from = max(COPY_START, opened or COPY_START)
    warnings: List[str] = []

    stock = variants(items)
    in_stock = {k: v for k, v in stock.items() if v['stock'] > 0}
    negative = [v for v in stock.values() if v['stock'] < 0]
    no_price = [v for v in in_stock.values() if not v['price']]
    valor = sum(v['stock'] * v['price'] for v in in_stock.values())
    unidades = sum(v['stock'] for v in in_stock.values())

    # Ritmo de venta: últimos 90 días cerrados (o desde que abrió / desde que empezó la copia)
    w_start = max(today - timedelta(days=SALES_WINDOW_DAYS), copy_from)
    w_days = _loaded_days(store, w_start, yesterday)
    window = _sales_by_item(store, w_start, yesterday)
    w_lista = sum(e['lista'] for e in window.values())
    daily_lista = r.ratio(w_lista, w_days)
    dias_inventario = r.ratio(valor, daily_lista)

    # Rotación: precio de lista vendido en el año (o lo que haya), llevado a 12 meses ÷ inventario de hoy
    y_start = max(today - timedelta(days=ROTATION_WINDOW_DAYS), copy_from)
    y_days = _loaded_days(store, y_start, yesterday)
    year_sales = _sales_by_item(store, y_start, yesterday)
    y_lista = sum(e['lista'] for e in year_sales.values())
    rotacion = r.ratio(y_lista / y_days * 365, valor) if y_days else None

    # Última venta de cada prenda: desde que empezó la copia
    all_sales = _sales_by_item(store, copy_from, yesterday)
    arrivals = _arrivals(store)
    limit_day = today - timedelta(days=quiet_days)

    quiet, quiet_value, quiet_units = [], 0.0, 0
    for item_id, v in in_stock.items():
        sale = all_sales.get(item_id)
        last_sale = sale['last_sale'] if sale else None
        arrived = arrivals.get(item_id)
        if opened and (arrived is None or arrived < opened):
            arrived = opened
        if (last_sale and last_sale > limit_day) or (arrived and arrived > limit_day):
            continue
        parada = v['stock'] * v['price'] * keep
        quiet_value += parada
        quiet_units += v['stock']
        g = parse_garment(v['name'])
        quiet.append({'item_id': item_id, 'name': v['name'], **g, 'stock': v['stock'], 'price': v['price'],
                      'plata_parada': parada, 'last_sale': last_sale.isoformat() if last_sale else None,
                      'last_arrival': arrived.isoformat() if arrived else None})
    quiet.sort(key=lambda q: q['plata_parada'], reverse=True)

    # Por tipo de prenda y por departamento (ventas de la ventana de 90 días + stock de hoy)
    def group_rows(key_fn):
        acc = defaultdict(lambda: {'units': 0, 'lista': 0.0, 'ventas': 0.0, 'stock': 0, 'valor': 0.0, 'parada': 0.0})
        for e in window.values():
            a = acc[key_fn(e['name'])]
            a['units'] += e['units']
            a['lista'] += e['lista']
            a['ventas'] += e['ventas']
        for v in in_stock.values():
            a = acc[key_fn(v['name'])]
            a['stock'] += v['stock']
            a['valor'] += v['stock'] * v['price']
        for q in quiet:
            acc[key_fn(q['name'])]['parada'] += q['plata_parada']
        rows = []
        for name, a in acc.items():
            daily = r.ratio(a['lista'], w_days)
            rows.append({
                'name': name, 'units': a['units'], 'ventas': a['ventas'], 'precio_lista': a['lista'],
                'descuento_pct': r.ratio(a['lista'] - a['ventas'], a['lista']),
                'utilidad_estimada': a['ventas'] - a['lista'] * keep,
                'stock': a['stock'], 'valor_venta': a['valor'], 'valor_costo': a['valor'] * keep,
                'dias_inventario': r.ratio(a['valor'], daily) if daily else None,
                'plata_parada': a['parada'],
            })
        return rows

    by_type = group_rows(lambda n: parse_garment(n)['product'])
    by_type.sort(key=lambda x: (x['ventas'], x['valor_venta']), reverse=True)
    by_dept = group_rows(lambda n: parse_garment(n)['department'])
    by_dept.sort(key=lambda x: DEPARTMENT_ORDER.index(x['name']) if x['name'] in DEPARTMENT_ORDER else 99)

    with_both = [t for t in by_type if t['stock'] > 0 and t['dias_inventario'] is not None]
    fastest = sorted(with_both, key=lambda t: t['dias_inventario'])[:TOP_LIMIT]
    slowest = sorted([t for t in by_type if t['stock'] > 0],
                     key=lambda t: (t['dias_inventario'] is not None, -(t['dias_inventario'] or 0), -t['valor_venta']))[:TOP_LIMIT]

    if opened and (today - opened).days < quiet_days:
        warnings.append(f'La tienda abrió el {opened.strftime("%d/%m/%Y")}: hasta cumplir {quiet_days} días '
                        'abierta ninguna prenda cuenta como quieta (todo es recién llegado).')
    if opened and w_days < 30:
        warnings.append(f'Solo hay {w_days} días de ventas: los días de inventario y la rotación todavía dicen poco.')
    if w_days < (yesterday - w_start).days + 1:
        warnings.append('Faltan días con prendas cargadas en los últimos 90 días: el ritmo de venta puede quedar corto.')
    if no_price:
        warnings.append(f'{len(no_price)} prenda(s) con stock no tienen precio en Alegra: no suman al valor.')
    if negative:
        warnings.append(f'{len(negative)} prenda(s) tienen stock negativo en Alegra ({sum(v["stock"] for v in negative)} '
                        'unidades): no suman, pero conviene revisarlas.')

    from app.models.monthly_summary import InventorySnapshot
    snap = InventorySnapshot.for_store(store).order_by(InventorySnapshot.as_of.desc()).first()

    return {
        'as_of': today.isoformat(),
        'margin_pct': margin,
        'quiet_days': quiet_days,
        'quiet_options': list(QUIET_OPTIONS),
        'sales_window': {'start': w_start.isoformat(), 'end': yesterday.isoformat(), 'loaded_days': w_days},
        'opened': opened.isoformat() if opened else None,
        'totals': {
            'valor_venta': valor, 'valor_costo': valor * keep, 'unidades': unidades,
            'referencias': len(in_stock),
            'vendido_lista_dia': daily_lista,
            'dias_inventario': dias_inventario,
            'rotacion_anual': rotacion,
            'rotation_days_used': y_days,
            'quiet_units': quiet_units, 'quiet_count': len(quiet),
            'plata_parada': quiet_value,
            'plata_parada_pct': r.ratio(quiet_value, valor * keep),
            'negative_count': len(negative), 'no_price_count': len(no_price),
        },
        'alegra_snapshot': {'value': snap.value, 'as_of': snap.as_of.isoformat()} if snap else None,
        'quiet': quiet[:QUIET_LIMIT],
        'quiet_truncated': len(quiet) > QUIET_LIMIT,
        'fastest': fastest,
        'slowest': slowest,
        'by_type': by_type,
        'by_department': by_dept,
        'warnings': warnings,
    }
