"""
Alertas diarias en la plataforma (Fase D4 de docs/PLAN_ESTADISTICAS.md), por tienda.

Decisión del usuario (2026-10-03): dentro de la plataforma (Dashboard, admin).
Se calculan para UN día ya cerrado (el cron de las 9 pm: la tienda vende
hasta ~8 pm) con las facturas y prendas guardadas:

  - low_day (warning): el día vendió menos del LOW_DAY_RATIO del promedio
    del mismo día de la semana en las 8 semanas anteriores (mínimo 4 días
    para comparar).
  - best_sellers_out (warning): de las prendas (con talla) más vendidas en
    los últimos 30 días, las que hoy tienen 0 en stock en Alegra. Marca las
    nuevas respecto a la alerta anterior.
  - goal_pace (warning): la tienda va más de GOAL_PACE_GAP puntos por debajo
    de lo esperado para la meta del mes (Fase D3).
  - high_discounts (info): facturas del día con descuento de
    HIGH_DISCOUNT_PCT o más (en la tienda hay descuentos del 50 % a clientas:
    es informativa, no advertencia).

Cada tipo se calcula aparte: si uno falla (ej. Alegra no responde el
stock), los demás se guardan igual. Si una condición deja de cumplirse al
recalcular el mismo día, su alerta se borra.
"""
import json
import logging
from collections import defaultdict
from datetime import date, datetime, timedelta
from typing import Any, Callable, Dict, List, Optional

from app.models.daily_alert import DailyAlert
from app.models.invoice_fact import InvoiceFact, InvoiceItemFact, InvoiceSyncDay
from app.models.user import db
from app.services.garment_insights import garment_rows, parse_garment, stock_variants

logger = logging.getLogger(__name__)

LOW_DAY_RATIO = 0.6
LOW_DAY_WEEKS = 8
LOW_DAY_MIN_SAMPLES = 4
HIGH_DISCOUNT_PCT = 40
HIGH_DISCOUNT_LIST = 15
BEST_SELLERS_DAYS = 30
BEST_SELLERS_TOP = 30
GOAL_PACE_GAP = 10
WEEKDAYS = ['lunes', 'martes', 'miércoles', 'jueves', 'viernes', 'sábado', 'domingo']


def _cop(value) -> str:
    return '$' + f'{int(round(value or 0)):,}'.replace(',', '.')


def _loaded(store: str, day: date) -> bool:
    return InvoiceSyncDay.query.filter_by(store_code=store, date=day).first() is not None


def _day_sales(store: str, day: date) -> int:
    return int(db.session.query(db.func.coalesce(db.func.sum(InvoiceFact.total), 0)).filter(
        InvoiceFact.store_code == store, InvoiceFact.date == day, InvoiceFact.voided.is_(False)).scalar() or 0)


# ─── Cada alerta: devuelve {severity, title, message, data} o None ──────────

def low_day(store: str, day: date) -> Optional[Dict[str, Any]]:
    if not _loaded(store, day):
        return None
    sales = _day_sales(store, day)
    previous = [day - timedelta(weeks=w) for w in range(1, LOW_DAY_WEEKS + 1)]
    samples = [_day_sales(store, d) for d in previous if _loaded(store, d)]
    samples = [s for s in samples if s > 0]  # días cerrados (ej. festivos sin venta) no cuentan
    if len(samples) < LOW_DAY_MIN_SAMPLES:
        return None
    average = sum(samples) / len(samples)
    if not average or sales >= average * LOW_DAY_RATIO:
        return None
    drop = round((1 - sales / average) * 100)
    weekday = WEEKDAYS[day.weekday()]
    return {
        'severity': 'warning',
        'title': f'Día flojo: se vendió {drop} % menos que un {weekday} normal',
        'message': f'Venta del día {_cop(sales)}; un {weekday} normal (promedio de los últimos {len(samples)}) vende {_cop(average)}.',
        'data': {'sales': sales, 'average': round(average), 'drop_pct': drop, 'samples': len(samples)},
    }


def high_discounts(store: str, day: date) -> Optional[Dict[str, Any]]:
    rows = []
    for f in InvoiceFact.query.filter(InvoiceFact.store_code == store, InvoiceFact.date == day,
                                      InvoiceFact.voided.is_(False), InvoiceFact.discount > 0):
        pct = f.discount * 100 / f.subtotal if f.subtotal else 0
        if pct >= HIGH_DISCOUNT_PCT:
            rows.append({'number': f.number, 'client': f.client_name or 'Consumidor final',
                         'seller': f.seller_name, 'subtotal': f.subtotal, 'discount': f.discount,
                         'total': f.total, 'discount_pct': round(pct, 1)})
    if not rows:
        return None
    rows.sort(key=lambda r: r['discount'], reverse=True)
    total = sum(r['discount'] for r in rows)
    return {
        'severity': 'info',
        'title': f'{len(rows)} {"factura" if len(rows) == 1 else "facturas"} con descuento de {HIGH_DISCOUNT_PCT} % o más',
        'message': f'Descuento total en esas facturas: {_cop(total)}.',
        'data': {'threshold_pct': HIGH_DISCOUNT_PCT, 'total_discount': total, 'invoices': rows[:HIGH_DISCOUNT_LIST],
                 'count': len(rows)},
    }


def best_sellers_out(store: str, day: date, items_loader: Callable[[], List[Dict[str, Any]]],
                     previous: Optional[Dict[str, Any]] = None) -> Optional[Dict[str, Any]]:
    start = day - timedelta(days=BEST_SELLERS_DAYS - 1)
    sold: Dict[str, Dict[str, Any]] = defaultdict(lambda: {'units': 0, 'name': None})
    rows = [{'item_id': r.item_id, 'name': r.name, 'quantity': r.quantity} for r in InvoiceItemFact.query.filter(
        InvoiceItemFact.store_code == store, InvoiceItemFact.date >= start, InvoiceItemFact.date <= day)]
    for r in garment_rows(rows):
        if r['item_id']:
            sold[r['item_id']]['units'] += int(r['quantity'])
            sold[r['item_id']]['name'] = r['name']
    if not sold:
        return None
    top = sorted(sold.items(), key=lambda kv: kv[1]['units'], reverse=True)[:BEST_SELLERS_TOP]
    stock = stock_variants(items_loader())
    before = {i['item_id'] for i in ((previous or {}).get('items') or [])}
    out = []
    for item_id, v in top:
        if item_id in stock and stock[item_id]['stock'] <= 0:
            g = parse_garment(v['name'])
            out.append({'item_id': item_id, 'name': v['name'], 'product': g['product'], 'size': g['size'],
                        'units_30d': v['units'], 'new': item_id not in before})
    if not out:
        return None
    new = sum(1 for o in out if o['new'])
    return {
        'severity': 'warning',
        'title': f'{len(out)} de las {BEST_SELLERS_TOP} prendas más vendidas están agotadas',
        'message': (f'{new} se {"agotó" if new == 1 else "agotaron"} desde el último aviso. ' if previous and new else '')
        + f'Más vendidas de los últimos {BEST_SELLERS_DAYS} días con 0 unidades en Alegra: para pedir.',
        'data': {'items': out, 'new': new, 'days': BEST_SELLERS_DAYS},
    }


def goal_pace(goals_loader: Callable[[], Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    data = goals_loader()
    store, pace = data['store'], data['pace']
    if not store.get('goal') or not pace['is_current'] or store.get('progress_pct') is None:
        return None
    gap = pace['expected_pct'] - store['progress_pct']
    if gap <= GOAL_PACE_GAP:
        return None
    behind = [{'name': s['name'], 'progress_pct': s['progress_pct'], 'goal': s['goal'], 'sales': s['sales']}
              for s in data['sellers'] if s['active'] and s.get('goal') and s.get('progress_pct') is not None
              and s['progress_pct'] < pace['expected_pct'] - GOAL_PACE_GAP]
    return {
        'severity': 'warning',
        'title': f'La meta del mes va atrasada: {store["progress_pct"]:.0f} % de avance, debería ir en {pace["expected_pct"]:.0f} %',
        'message': f'Vendido {_cop(store["sales"])} de {_cop(store["goal"])}. Para llegar se necesitan {_cop(store["needed_per_day"])} por día.',
        'data': {'progress_pct': store['progress_pct'], 'expected_pct': pace['expected_pct'], 'sellers_behind': behind},
    }


# ─── Generar y guardar ──────────────────────────────────────────────────────

def _previous_data(store: str, day: date, kind: str) -> Optional[Dict[str, Any]]:
    row = DailyAlert.query.filter(DailyAlert.store_code == store, DailyAlert.kind == kind,
                                  DailyAlert.date < day).order_by(DailyAlert.date.desc()).first()
    return json.loads(row.data) if row and row.data else None


def _save(store: str, day: date, kind: str, alert: Optional[Dict[str, Any]]) -> None:
    row = DailyAlert.query.filter_by(store_code=store, date=day, kind=kind).first()
    if alert is None:
        if row:
            db.session.delete(row)
        return
    if row is None:
        row = DailyAlert(store_code=store, date=day, kind=kind)
        db.session.add(row)
    row.severity = alert['severity']
    row.title = alert['title'][:200]
    row.message = alert.get('message')
    row.data = json.dumps(alert.get('data') or {}, ensure_ascii=False, default=str)
    row.created_at = datetime.utcnow()  # se conserva dismissed_at si ya se había descartado


def generate(store: str, day: date, items_loader: Callable[[], List[Dict[str, Any]]],
             goals_loader: Callable[[], Dict[str, Any]]) -> Dict[str, Any]:
    """Calcula y guarda las alertas de `day`. Devuelve qué salió y qué falló."""
    checks = {
        'low_day': lambda: low_day(store, day),
        'high_discounts': lambda: high_discounts(store, day),
        'best_sellers_out': lambda: best_sellers_out(store, day, items_loader,
                                                     _previous_data(store, day, 'best_sellers_out')),
        'goal_pace': lambda: goal_pace(goals_loader),
    }
    created, errors = [], {}
    for kind, check in checks.items():
        try:
            alert = check()
        except Exception as e:
            logger.error(f'[{store}] Alerta {kind} del {day}: {e}', exc_info=True)
            errors[kind] = 'No se pudo calcular'
            continue  # si falla, la alerta anterior de ese día queda como estaba
        _save(store, day, kind, alert)
        if alert:
            created.append(kind)
    db.session.commit()
    return {'date': day.isoformat(), 'alerts': created, 'errors': errors}


def to_dict(row: DailyAlert) -> Dict[str, Any]:
    return {
        'id': row.id, 'date': row.date.isoformat(), 'kind': row.kind, 'severity': row.severity,
        'title': row.title, 'message': row.message, 'data': json.loads(row.data) if row.data else {},
        'dismissed': row.dismissed_at is not None,
    }


def active_alerts(store: str, today: date, days: int = 7) -> List[Dict[str, Any]]:
    rows = DailyAlert.query.filter(
        DailyAlert.store_code == store, DailyAlert.date >= today - timedelta(days=days - 1),
        DailyAlert.dismissed_at.is_(None),
    ).order_by(DailyAlert.date.desc(), DailyAlert.severity.desc(), DailyAlert.id).all()
    return [to_dict(r) for r in rows]
