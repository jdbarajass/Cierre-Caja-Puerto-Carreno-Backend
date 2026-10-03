"""
Estadísticas → Día y hora (Fase D2 de docs/PLAN_ESTADISTICAS.md), por tienda.

Ventas por día de la semana y por hora a partir de las facturas guardadas
(InvoiceFact.hour), solo días cerrados (hoy en vivo solo si el periodo es
únicamente hoy). Sin anuladas.

Para comparar días de la semana se usa el PROMEDIO por día (venta del lunes
÷ cuántos lunes cargados hubo en el periodo): un periodo con 5 sábados y 4
lunes no debe hacer ver al sábado mejor solo por tener uno más.
Opcional: una sola vendedora (`seller_id`).
"""
from collections import defaultdict
from datetime import date, timedelta
from typing import Any, Dict, List, Optional

from app.models.invoice_fact import InvoiceFact
from app.services.invoice_facts import invoice_to_fact, outdated_days

WEEKDAYS = ['Lunes', 'Martes', 'Miércoles', 'Jueves', 'Viernes', 'Sábado', 'Domingo']


def _days(start: date, end: date):
    day = start
    while day <= end:
        yield day
        day += timedelta(days=1)


def build_patterns(facts: List[Dict[str, Any]], loaded_days: List[date]) -> Dict[str, Any]:
    """
    facts: facturas activas {date, hour, total, seller_id, seller_name}.
    loaded_days: días del periodo con datos (para el promedio por día de la semana).
    """
    weekday_count = defaultdict(int)
    for d in loaded_days:
        weekday_count[d.weekday()] += 1

    cells: Dict[tuple, Dict[str, int]] = defaultdict(lambda: {'sales': 0, 'invoices': 0})
    by_weekday: Dict[int, Dict[str, int]] = defaultdict(lambda: {'sales': 0, 'invoices': 0})
    by_hour: Dict[int, Dict[str, int]] = defaultdict(lambda: {'sales': 0, 'invoices': 0})
    no_hour = {'sales': 0, 'invoices': 0}
    for f in facts:
        wd = f['date'].weekday()
        by_weekday[wd]['sales'] += f['total']
        by_weekday[wd]['invoices'] += 1
        if f.get('hour') is None:
            no_hour['sales'] += f['total']
            no_hour['invoices'] += 1
            continue
        for acc in (cells[(wd, f['hour'])], by_hour[f['hour']]):
            acc['sales'] += f['total']
            acc['invoices'] += 1

    total_sales = sum(f['total'] for f in facts)
    hours = sorted(by_hour)
    hour_range = list(range(hours[0], hours[-1] + 1)) if hours else []

    def avg(value, wd):
        return round(value / weekday_count[wd]) if weekday_count[wd] else 0

    weekdays = [{
        'weekday': wd, 'name': WEEKDAYS[wd], 'days': weekday_count[wd],
        'sales': by_weekday[wd]['sales'], 'invoices': by_weekday[wd]['invoices'],
        'avg_sales_per_day': avg(by_weekday[wd]['sales'], wd),
        'avg_invoices_per_day': round(by_weekday[wd]['invoices'] / weekday_count[wd], 1) if weekday_count[wd] else 0,
    } for wd in range(7)]

    return {
        'total_sales': total_sales,
        'total_invoices': len(facts),
        'weekdays': weekdays,
        'hours': [{
            'hour': h, 'sales': by_hour[h]['sales'], 'invoices': by_hour[h]['invoices'],
            'share_pct': round(by_hour[h]['sales'] * 100 / total_sales, 1) if total_sales else 0.0,
        } for h in hour_range],
        # Promedio por día de la semana en cada hora (venta y facturas)
        'heatmap': [{
            'weekday': wd, 'name': WEEKDAYS[wd],
            'cells': [{'hour': h, 'avg_sales': avg(cells[(wd, h)]['sales'], wd),
                       'avg_invoices': round(cells[(wd, h)]['invoices'] / weekday_count[wd], 2) if weekday_count[wd] else 0}
                      for h in hour_range],
        } for wd in range(7)],
        'without_hour': no_hour,
    }


class SalesPatternsService:
    def __init__(self, store_code: str, today: date, invoices_client=None):
        self.store_code = store_code
        self.today = today
        self.client = invoices_client  # AlegraClient de la tienda (ventas de hoy)

    def summary(self, start: date, end: date, seller_id: Optional[str] = None) -> Dict[str, Any]:
        closed_end = min(end, self.today - timedelta(days=1))
        facts: List[Dict[str, Any]] = []
        outdated: List[date] = []
        if start <= closed_end:
            outdated = outdated_days(self.store_code, start, closed_end)
            query = InvoiceFact.query.filter(
                InvoiceFact.store_code == self.store_code,
                InvoiceFact.date >= start, InvoiceFact.date <= closed_end,
                InvoiceFact.voided.is_(False),
            )
            facts = [{'date': r.date, 'hour': r.hour, 'total': r.total or 0,
                      'seller_id': r.seller_id, 'seller_name': r.seller_name} for r in query]
        # Hoy va a medias: contarlo bajaría los promedios de su día de la
        # semana (mismo criterio que la rotación de Prendas). Solo si el
        # periodo es únicamente hoy.
        includes_today = start >= self.today and end >= self.today and self.client is not None
        if includes_today:
            for invoice in self.client.get_invoices_by_date(self.today.isoformat()):
                if invoice.get('id') is None:
                    continue
                fact = invoice_to_fact(invoice)
                if not fact['voided']:
                    facts.append({'date': self.today, 'hour': fact['hour'], 'total': fact['total'],
                                  'seller_id': fact['seller_id'], 'seller_name': fact['seller_name']})

        sellers: Dict[str, Dict[str, Any]] = {}
        for f in facts:
            if f['seller_id']:
                s = sellers.setdefault(f['seller_id'], {'id': f['seller_id'], 'name': f['seller_name'], 'sales': 0})
                s['sales'] += f['total']
        if seller_id:
            facts = [f for f in facts if f['seller_id'] == str(seller_id)]

        outdated_set = set(outdated)
        loaded = [d for d in _days(start, closed_end) if d not in outdated_set] if start <= closed_end else []
        if includes_today:
            loaded.append(self.today)
        # Días sin hora todavía: no se cuentan en el periodo (se completan en las tandas)
        facts = [f for f in facts if f['date'] not in outdated_set]

        days = (end - start).days + 1
        return {
            'date_range': {'start': start.isoformat(), 'end': end.isoformat()},
            'seller_id': str(seller_id) if seller_id else None,
            'sellers': sorted(sellers.values(), key=lambda s: s['sales'], reverse=True),
            'coverage': {
                'days': days,
                'loaded_days': len(loaded),
                'missing_days': len(outdated),
                'first_missing_day': outdated[0].isoformat() if outdated else None,
                'complete': not outdated,
            },
            **build_patterns(facts, loaded),
        }
