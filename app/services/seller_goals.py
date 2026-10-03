"""
Estadísticas → Metas por vendedora (Fase D3 de docs/PLAN_ESTADISTICAS.md), por tienda.

Decisión del usuario (2026-10-03): reparto automático con +15 % que el admin
puede ajustar.
  - Meta de la tienda del mes = venta del MISMO MES COMPLETO del año anterior
    × 1,15 (totales por día de Alegra, `get_all_sales_totals_by_day`).
  - Se reparte entre las vendedoras ACTIVAS según lo que vendió cada una en
    los 3 meses completos anteriores (reporte sales-by-seller). Si ninguna
    tiene historia, partes iguales. Redondeado a miles.
  - El admin puede escribir la meta de cualquier vendedora (SellerGoal); esa
    reemplaza la automática. La meta de la tienda mostrada = suma de las
    metas de las vendedoras.
Avance del mes: facturas guardadas (días cerrados) + hoy en vivo, con
prendas por factura y % de la venta con cliente identificado. Si al mes le
faltan días en la copia, la venta sale del reporte de Alegra (sin prendas ni
% con cliente).
"""
import calendar
import logging
from collections import defaultdict
from datetime import date, datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple

from app.models.invoice_fact import InvoiceFact, InvoiceItemFact
from app.models.seller_goal import SellerGoal
from app.models.user import db
from app.services.garment_insights import garment_rows
from app.services.invoice_facts import invoice_to_fact, invoice_to_items, missing_days, missing_item_days
from app.utils.ttl_cache import TTLCache

logger = logging.getLogger(__name__)

GROWTH_PCT = 15
HISTORY_MONTHS = 3
ROUND_TO = 1000
ANONYMOUS_IDENTIFICATION = '222222222222'
CACHE_TTL = 12 * 3600  # meses cerrados: no cambian

_cache = TTLCache()


def clear_cache():
    _cache.clear()


def _cached(key, loader):
    value = _cache.get(key)
    if value is None:
        value = loader()
        _cache.set(key, value, CACHE_TTL)
    return value


# ─── Fechas ─────────────────────────────────────────────────────────────────

def month_bounds(month: date) -> Tuple[date, date]:
    start = month.replace(day=1)
    return start, start.replace(day=calendar.monthrange(start.year, start.month)[1])


def shift_months(month: date, n: int) -> date:
    index = month.year * 12 + month.month - 1 + n
    return date(index // 12, index % 12 + 1, 1)


def history_range(month: date) -> Tuple[date, date]:
    """Los HISTORY_MONTHS meses completos anteriores a `month`."""
    start = shift_months(month, -HISTORY_MONTHS)
    return start, month.replace(day=1) - timedelta(days=1)


# ─── Cálculos puros ─────────────────────────────────────────────────────────

def _round(value: float) -> int:
    return int(round(value / ROUND_TO) * ROUND_TO)


def split_goal(store_goal: Optional[int], history: Dict[str, int], active_ids: List[str]) -> Dict[str, Optional[int]]:
    """Meta de cada vendedora activa según su parte de la venta de los meses anteriores."""
    if not active_ids:
        return {}
    if not store_goal:
        return {sid: None for sid in active_ids}
    base = {sid: max(history.get(sid, 0), 0) for sid in active_ids}
    total = sum(base.values())
    if not total:
        return {sid: _round(store_goal / len(active_ids)) for sid in active_ids}
    return {sid: _round(store_goal * base[sid] / total) for sid in active_ids}


def pace(month: date, today: date) -> Dict[str, Any]:
    """Días del mes, días transcurridos (hoy cuenta) y % del mes que ya pasó."""
    start, end = month_bounds(month)
    days = end.day
    if today < start:
        elapsed = 0
    elif today > end:
        elapsed = days
    else:
        elapsed = today.day
    return {'days_in_month': days, 'elapsed_days': elapsed, 'remaining_days': days - elapsed,
            'expected_pct': round(elapsed * 100 / days, 1), 'is_current': start <= today <= end}


def seller_progress(goal: Optional[int], sales: int, month_pace: Dict[str, Any]) -> Dict[str, Any]:
    elapsed, days = month_pace['elapsed_days'], month_pace['days_in_month']
    remaining_days = month_pace['remaining_days'] + (1 if month_pace['is_current'] else 0)  # hoy aún cuenta
    projection = round(sales / elapsed * days) if elapsed else 0
    out = {
        'progress_pct': round(sales * 100 / goal, 1) if goal else None,
        'projection': projection if month_pace['is_current'] else None,
        'remaining': max(goal - sales, 0) if goal else None,
        'needed_per_day': None,
        'on_track': None,
    }
    if goal and month_pace['is_current'] and remaining_days:
        out['needed_per_day'] = round(max(goal - sales, 0) / remaining_days)
        out['on_track'] = projection >= goal
    elif goal and not month_pace['is_current'] and elapsed:
        out['on_track'] = sales >= goal
    return out


def _is_anonymous(fact: Dict[str, Any]) -> bool:
    return (not fact.get('client_id') or fact.get('client_identification') == ANONYMOUS_IDENTIFICATION
            or str(fact.get('client_name') or '').strip().lower() == 'consumidor final')


# ─── Servicio ───────────────────────────────────────────────────────────────

class SellerGoalsService:
    def __init__(self, store_code: str, today: date, direct_client, invoices_client=None):
        self.store = store_code
        self.today = today
        self.direct = direct_client      # reportes de Alegra (totales, sales-by-seller, vendedoras)
        self.client = invoices_client    # facturas de hoy en vivo

    # Alegra (con caché de meses cerrados)
    def _month_total(self, start: date, end: date) -> Optional[int]:
        def load():
            result = self.direct.get_all_sales_totals_by_day(start.isoformat(), end.isoformat())
            if not result.get('success'):
                raise RuntimeError(result.get('error') or 'Alegra no respondió')
            return sum(float(r.get('total') or 0) for r in result.get('data') or [])
        return int(round(_cached(f'{self.store}:month-total:{start}:{end}', load)))

    def _history(self, month: date) -> Dict[str, int]:
        start, end = history_range(month)
        rows = _cached(f'{self.store}:seller-history:{start}:{end}',
                       lambda: self.direct.get_sales_by_seller(start.isoformat(), end.isoformat()))
        out: Dict[str, int] = defaultdict(int)
        for r in rows:
            out[str(r.get('idLocal') or r.get('id') or '')] += int(round(float(r.get('total') or r.get('afterTaxes') or 0)))
        return dict(out)

    def _sellers(self) -> List[Dict[str, Any]]:
        return _cached(f'{self.store}:sellers', self.direct.get_sellers)

    # Venta del mes
    def _month_sales(self, start: date, end: date) -> Dict[str, Any]:
        """Por vendedora: venta, facturas, venta con cliente y prendas (None si no se pudo)."""
        if self.today < start:
            return {'source': 'none', 'sellers': {}}
        closed_end = min(end, self.today - timedelta(days=1))
        includes_today = start <= self.today <= end and self.client is not None
        if closed_end >= start and missing_days(self.store, start, closed_end):
            return self._report_sales(start, min(end, self.today))

        acc: Dict[str, Dict[str, Any]] = defaultdict(lambda: {'name': None, 'sales': 0, 'invoices': 0,
                                                              'identified_sales': 0, 'units': 0})
        facts, items = [], []
        if closed_end >= start:
            facts = [{'seller_id': r.seller_id, 'seller_name': r.seller_name, 'total': r.total or 0,
                      'client_id': r.client_id, 'client_name': r.client_name,
                      'client_identification': r.client_identification}
                     for r in InvoiceFact.query.filter(
                         InvoiceFact.store_code == self.store, InvoiceFact.voided.is_(False),
                         InvoiceFact.date >= start, InvoiceFact.date <= closed_end)]
            items = [{'seller_id': r.seller_id, 'name': r.name, 'quantity': r.quantity}
                     for r in InvoiceItemFact.query.filter(
                         InvoiceItemFact.store_code == self.store,
                         InvoiceItemFact.date >= start, InvoiceItemFact.date <= closed_end)]
        units_complete = not (closed_end >= start and missing_item_days(self.store, start, closed_end))
        if includes_today:
            for invoice in self.client.get_invoices_by_date(self.today.isoformat()):
                if invoice.get('id') is None:
                    continue
                fact = invoice_to_fact(invoice)
                if not fact['voided']:
                    facts.append(fact)
                    items.extend(invoice_to_items(invoice))
        for f in facts:
            row = acc[f.get('seller_id') or '']
            row['name'] = f.get('seller_name') or row['name']
            row['sales'] += f['total']
            row['invoices'] += 1
            if not _is_anonymous(f):
                row['identified_sales'] += f['total']
        for it in garment_rows(items):
            acc[it.get('seller_id') or '']['units'] += int(it['quantity'])
        if not units_complete:
            for row in acc.values():
                row['units'] = None
        return {'source': 'facts', 'sellers': dict(acc)}

    def _report_sales(self, start: date, end: date) -> Dict[str, Any]:
        rows = self.direct.get_sales_by_seller(start.isoformat(), end.isoformat())
        acc = {}
        for r in rows:
            acc[str(r.get('idLocal') or '')] = {
                'name': r.get('name') or r.get('sellerName'),
                'sales': int(round(float(r.get('total') or r.get('afterTaxes') or 0))),
                'invoices': int(r.get('totalDocuments') or 0),
                'identified_sales': None, 'units': None,
            }
        return {'source': 'report', 'sellers': acc}

    def summary(self, month: date) -> Dict[str, Any]:
        start, end = month_bounds(month)
        month_pace = pace(start, self.today)
        last_year_start, last_year_end = month_bounds(date(start.year - 1, start.month, 1))

        warnings = []
        try:
            last_year_total = self._month_total(last_year_start, last_year_end)
        except Exception as e:
            logger.warning(f'[{self.store}] Venta del año anterior para metas: {e}')
            last_year_total = None
            warnings.append('No se pudo leer la venta del mismo mes del año anterior en Alegra.')
        store_auto_goal = _round(last_year_total * (1 + GROWTH_PCT / 100)) if last_year_total else None

        try:
            sellers = self._sellers()
        except Exception as e:
            logger.warning(f'[{self.store}] Vendedoras para metas: {e}')
            sellers = []
            warnings.append('No se pudo leer la lista de vendedoras de Alegra.')
        active = {str(s.get('id')): s for s in sellers if str(s.get('status') or 'active').lower() != 'inactive'}
        try:
            history = self._history(start)
        except Exception as e:
            logger.warning(f'[{self.store}] Historia de vendedoras para metas: {e}')
            history = {}
            warnings.append('No se pudo leer la venta de los meses anteriores: el reparto automático sale en partes iguales.')
        auto = split_goal(store_auto_goal, history, sorted(active))

        overrides = {g.seller_id: g for g in SellerGoal.query.filter(
            SellerGoal.store_code == self.store, SellerGoal.month == start)}
        current = self._month_sales(start, end)
        sales = current['sellers']

        ids = set(active) | set(overrides) | {sid for sid, s in sales.items() if sid and s['sales']}
        names = {sid: s.get('name') for sid, s in active.items()}
        all_sellers = {str(s.get('id')): s for s in sellers}
        rows = []
        for sid in ids:
            s = sales.get(sid, {})
            override = overrides.get(sid)
            # Activa en Alegra pero sin ventas en los 3 meses anteriores ni en
            # este mes (ej. Astrid, visto en producción 2026-10-03): su parte
            # automática es $0 y salía como "Meta sin definir". Se oculta hasta
            # que venda o el admin le ponga meta.
            if auto.get(sid) == 0 and not override and not s.get('sales'):
                continue
            goal = override.amount if override else auto.get(sid)
            seller_sales = s.get('sales', 0)
            invoices = s.get('invoices', 0)
            units = s.get('units')
            identified = s.get('identified_sales')
            rows.append({
                'id': sid,
                'name': names.get(sid) or (override.seller_name if override else None) or s.get('name')
                or (all_sellers.get(sid) or {}).get('name') or 'Sin nombre',
                'active': sid in active,
                'auto_goal': auto.get(sid),
                'goal': goal,
                'adjusted': override is not None,
                'history_sales': history.get(sid, 0),
                'sales': seller_sales,
                'invoices': invoices,
                'average_ticket': round(seller_sales / invoices) if invoices else 0,
                'units': units,
                'units_per_invoice': round(units / invoices, 2) if units is not None and invoices else None,
                'identified_pct': round(identified * 100 / seller_sales, 1) if identified is not None and seller_sales else None,
                **seller_progress(goal, seller_sales, month_pace),
            })
        rows.sort(key=lambda r: (r['active'], r['goal'] or 0, r['sales']), reverse=True)

        store_goal = sum(r['goal'] for r in rows if r['goal']) or None
        store_sales = sum(s['sales'] for s in sales.values())
        unassigned = sales.get('', {}).get('sales', 0)
        hist_start, hist_end = history_range(start)
        return {
            'month': start.isoformat()[:7],
            'date_range': {'start': start.isoformat(), 'end': end.isoformat()},
            'pace': month_pace,
            'growth_pct': GROWTH_PCT,
            'last_year': {'start': last_year_start.isoformat(), 'end': last_year_end.isoformat(), 'total': last_year_total},
            'store_auto_goal': store_auto_goal,
            'history_range': {'start': hist_start.isoformat(), 'end': hist_end.isoformat()},
            'source': current['source'],
            'store': {'goal': store_goal, 'sales': store_sales, 'unassigned_sales': unassigned,
                      **seller_progress(store_goal, store_sales, month_pace)},
            'sellers': rows,
            'warnings': warnings,
        }


def set_goal(store_code: str, month: date, seller_id: str, seller_name: Optional[str],
             amount: Optional[int], user: Optional[str]) -> None:
    """Guarda la meta ajustada (o la borra con amount=None: vuelve a la automática)."""
    start = month.replace(day=1)
    row = SellerGoal.query.filter_by(store_code=store_code, month=start, seller_id=str(seller_id)).first()
    if amount is None:
        if row:
            db.session.delete(row)
    else:
        if row is None:
            row = SellerGoal(store_code=store_code, month=start, seller_id=str(seller_id))
            db.session.add(row)
        row.amount = int(amount)
        row.seller_name = seller_name
        row.updated_by = user
        row.updated_at = datetime.utcnow()
    db.session.commit()
