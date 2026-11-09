"""
Radiografía del mes (Fase 1 de docs/PLAN_RADIOGRAFIA.md): estado de
resultados, punto de equilibrio, indicadores y comparaciones de una tienda.

Solo lee. Las fórmulas viven en app/services/radiografia.py; aquí se juntan
los datos que ya existen:
- Ventas y transacciones: copia de facturas (InvoiceFact, no anuladas), igual
  que Cuentas → Año. En el mes en curso, hasta el último día cargado.
- Precio de lista vendido y unidades: InvoiceItemFact sin bolsa ni tarjetas
  regalo (si faltan días con prendas, el costo estimado se avisa incompleto).
- Gastos: Expense por mes al que corresponde (period), con su 4x1000, por
  clase; la parte de interés de las cuotas va a financiero (Fase 0c).
- Comisiones de datáfono/Addi: las registradas (ya están en financiero) o, si
  no se registraron, las calculadas (marcadas "calculadas"). Nunca las dos.
- Recompras: lo enviado a Jhonatan en el mes (como Año); su 4x1000 es financiero.
- Mismo mes de 2025: venta real de la reconstrucción (sale_condition).
"""
from collections import defaultdict
from datetime import date, timedelta
from typing import Any, Dict, List, Optional

from sqlalchemy import func

from app.models.expense import Expense, FixedExpense
from app.models.invoice_fact import InvoiceFact, InvoiceItemFact
from app.models.repurchase import RepurchaseEntry
from app.models.user import db
from app.services import radiografia as r

CLASS_LABELS = {
    r.COSTO_MERCANCIA: 'Fletes (costo de la mercancía)',
    r.OPERATIVO: 'Gastos operativos',
    r.FINANCIERO: 'Gastos financieros',
    r.CUOTA_CREDITO: 'Cuotas de crédito (capital)',
    r.INVERSION: 'Inversiones',
    r.PRESTAMO: 'Préstamos y abonos (empleadas / otra tienda)',
    r.RETIRO_SOCIO: 'Retiros de socios',
}
MONTHS_ES = ['enero', 'febrero', 'marzo', 'abril', 'mayo', 'junio', 'julio', 'agosto',
             'septiembre', 'octubre', 'noviembre', 'diciembre']


def _sales(store: str, start: date, end: date) -> Dict[str, Any]:
    """Ventas netas y transacciones de un rango (2025 con la venta real)."""
    from app.services.history_2025 import sale_condition
    cond = sale_condition(store, start, end)
    total, count = db.session.query(func.sum(InvoiceFact.total), func.count(InvoiceFact.id)).filter(
        InvoiceFact.store_code == store, InvoiceFact.date >= start, InvoiceFact.date <= end, cond).one()
    return {'ventas': float(total or 0), 'transacciones': int(count or 0)}


GIFT_CARD_KEYWORDS = ('TARJETA REGALO', 'BONO REGALO')


def _items(store: str, start: date, end: date) -> Dict[str, float]:
    """Precio de lista vendido: ropa (sin bolsa), tarjetas regalo vendidas
    (cuentan como venta en Alegra y se canjean después por ropa sin factura,
    así que su costo se estima aquí) y bolsas (solo para los descuentos)."""
    ropa = tarjetas = bolsas = unidades = 0.0
    for name, qty, price in db.session.query(InvoiceItemFact.name, InvoiceItemFact.quantity,
                                             InvoiceItemFact.unit_price).filter(
            InvoiceItemFact.store_code == store, InvoiceItemFact.date >= start, InvoiceItemFact.date <= end):
        value = (qty or 0) * (price or 0)
        upper = (name or '').upper()
        if any(k in upper for k in GIFT_CARD_KEYWORDS):
            tarjetas += value
        elif 'BOLSA PAPEL' in upper:
            bolsas += value
        else:
            ropa += value
            unidades += qty or 0
    return {'precio_lista': ropa, 'tarjetas': tarjetas, 'bolsas': bolsas, 'unidades': unidades}


def _data_until(store: str, start: date, end: date) -> Dict[str, Any]:
    """Último día cargado del rango y los días sin cargar antes de él (una
    tienda que abrió a mitad de mes, como Primavera el 25-oct, puede no tener
    los primeros días: solo se avisa)."""
    from app.models.invoice_fact import InvoiceSyncDay
    from app.services.invoice_facts import missing_days
    last = db.session.query(func.max(InvoiceSyncDay.date)).filter(
        InvoiceSyncDay.store_code == store, InvoiceSyncDay.date >= start, InvoiceSyncDay.date <= end).scalar()
    gaps = [d for d in missing_days(store, start, last)] if last else []
    return {'until': last, 'gaps': gaps}


def _expenses_by_class(store: str, period: str) -> Dict[str, Any]:
    from app.services.loans import interest_by_expense
    rows = Expense.for_store(store).filter(Expense.period == period, Expense.direction == 'out').all()
    interest = interest_by_expense(rows)
    by_class = defaultdict(float)
    by_cat = defaultdict(float)
    detail = defaultdict(list)
    for e in rows:
        amount = e.total_with_fee
        part = interest.get(e.id, 0)
        cls = r.expense_class(e.category)
        if part:
            by_class[r.FINANCIERO] += part
            amount -= part
        by_class[cls] += amount
        by_cat[e.category] += e.total_with_fee
        detail[cls].append({'id': e.id, 'date': e.date.isoformat(), 'concept': e.concept,
                            'category': e.category, 'subcategory': e.subcategory,
                            'amount': e.total_with_fee, 'interest': part})
    return {'by_class': by_class, 'by_cat': by_cat, 'detail': detail, 'count': len(rows),
            'sueldos': by_cat['sueldo']}


def _fixed_costs(store: str, period: str) -> Dict[str, Any]:
    """Gastos fijos que restan utilidad (sin retiros, préstamos ni cuotas):
    por cada uno, el mayor entre el valor de referencia y lo pagado en el mes."""
    paid = defaultdict(float)
    for e in Expense.for_store(store).filter(Expense.period == period, Expense.fixed_expense_id.isnot(None)).all():
        paid[e.fixed_expense_id] += e.total_with_fee
    items, cuotas = [], 0.0
    for f in FixedExpense.for_store(store).filter_by(active=True).all():
        value = max(f.amount or 0, paid.get(f.id, 0))
        cls = r.expense_class(f.category)
        if cls == r.CUOTA_CREDITO:
            cuotas += value
        if cls not in r.UTILITY_CLASSES:
            continue
        items.append({'id': f.id, 'name': f.name, 'reference': f.amount or 0, 'paid': paid.get(f.id, 0), 'value': value})
    return {'total': sum(i['value'] for i in items), 'items': items, 'cuotas': cuotas}


def _commissions(store: str, start: date, end: date, period: str) -> Dict[str, Any]:
    from app.services.month_sheet import commissions
    c = commissions(store, start, end, period)
    registered = bool(c['registered_expense_id'])
    return {'calculated': c['total'], 'registered': registered,
            # Si están registradas ya van dentro de los gastos financieros
            'extra': 0 if registered else c['total']}


def build_month(store: str, year: int, month: int, today: date, target: Optional[float] = None) -> Dict[str, Any]:
    from app.services.finance_settings import get_settings
    margin = get_settings(store)['margin_pct']
    start, end = r.month_bounds(year, month)
    period = f'{year}-{month:02d}'
    in_progress = start <= today <= end
    if start > today:
        return {'period': period, 'future': True}
    range_end = min(end, today)
    cov = _data_until(store, start, range_end)
    until = cov['until']
    warnings: List[str] = []
    if until is None:
        warnings.append('Todavía no hay facturas cargadas de este mes.')
        until = start - timedelta(days=1)
    else:
        if until < range_end and not (in_progress and until >= range_end - timedelta(days=1)):
            warnings.append(f'Las ventas van hasta el {until.isoformat()} (último día cargado).')
        if cov['gaps']:
            warnings.append(f'Hay {len(cov["gaps"])} día(s) sin cargar en la copia de facturas antes del '
                            f'{until.isoformat()} (desde el {cov["gaps"][0].isoformat()}).')

    sales = _sales(store, start, until) if until >= start else {'ventas': 0.0, 'transacciones': 0}
    items = _items(store, start, until) if until >= start else {'precio_lista': 0.0, 'tarjetas': 0.0, 'bolsas': 0.0, 'unidades': 0.0}
    from app.services.invoice_facts import missing_item_days
    # Días cargados pero sin prendas (los días sin cargar ya se avisaron arriba)
    if until >= start and set(missing_item_days(store, start, until)) - set(cov['gaps']):
        warnings.append('Faltan días con prendas cargadas: el costo estimado y las unidades pueden quedar cortos.')

    exp = _expenses_by_class(store, period)
    entries = RepurchaseEntry.for_store(store).filter(RepurchaseEntry.date >= start, RepurchaseEntry.date <= end).all()
    recompras = sum(e.total_enviado for e in entries)
    recompras_fee = sum(e.fee_4mil for e in entries)
    com = _commissions(store, start, until if until >= start else start, period)
    by_class = exp['by_class']
    financieros = by_class[r.FINANCIERO] + recompras_fee

    lines = r.utility_lines(
        ventas=sales['ventas'], precio_lista=items['precio_lista'] + items['tarjetas'], margin_pct=margin,
        otros_vendidos=items['bolsas'], fletes=by_class[r.COSTO_MERCANCIA], operativos=by_class[r.OPERATIVO],
        financieros=financieros, comisiones=com['extra'], cuotas=by_class[r.CUOTA_CREDITO], recompras=recompras,
        comisiones_registradas=com['registered'])
    has_expenses = exp['count'] > 0
    if not has_expenses:
        warnings.append('No hay gastos registrados en este mes: la utilidad operacional y la neta no se pueden calcular.')
    if in_progress:
        warnings.append('Mes en curso: los gastos van por mes, faltan los que se registren de aquí al cierre.')

    fixed = _fixed_costs(store, period)
    contrib = lines['margen_contribucion_pct']
    days = r.days_in_month(year, month)
    days_elapsed = (until - start).days + 1 if until >= start else 0
    be = r.break_even(fixed['total'], contrib)
    be_cuotas = r.break_even(fixed['total'] + fixed['cuotas'], contrib)
    pace = (sales['ventas'] / days_elapsed * days) if (in_progress and days_elapsed) else None

    ventas = sales['ventas']
    indicators = {
        'transacciones': sales['transacciones'],
        'ticket': r.ratio(ventas, sales['transacciones']),
        'unidades': items['unidades'],
        'prendas_por_factura': r.ratio(items['unidades'], sales['transacciones']),
        'descuentos_pct': r.ratio(lines['descuentos'], lines['precio_lista'] + items['bolsas']),
        'gastos_ventas_pct': r.ratio(lines['gastos_operativos'] + lines['gastos_financieros'], ventas) if has_expenses else None,
        'nomina_ventas_pct': r.ratio(exp['sueldos'], ventas) if has_expenses else None,
    }

    # Comparaciones: ventas por los mismos días; gastos y utilidad solo entre meses cerrados
    # Mes completo contra mes completo; mes en curso (o con días sin cargar) del 1 al mismo día
    p_start, p_end = r.same_days_previous_month(year, month, until if until >= start else start)
    prev_sales = _sales(store, p_start, p_end) if days_elapsed else {'ventas': 0.0, 'transacciones': 0}
    prev_items = _items(store, p_start, p_end) if days_elapsed else {'unidades': 0.0}
    ly_start, ly_month_end = r.month_bounds(year - 1, month)
    # Sin días cargados todavía (until = día antes del mes) o 29 de febrero: el día se acota al mes del año pasado
    ly_day = min(until.day if until >= start else 1, ly_month_end.day)
    ly_end = ly_month_end if until >= end else ly_start.replace(day=ly_day)
    ly = _sales(store, ly_start, ly_end) if days_elapsed else {'ventas': 0.0, 'transacciones': 0}

    def comp(cur, prev):
        has = prev is not None and prev != 0
        return {'value': prev if has else None, 'change_pct': r.pct_change(cur, prev) if has else None}

    comparisons = {
        'previous_month': {
            'range': [p_start.isoformat(), p_end.isoformat()],
            'ventas': comp(ventas, prev_sales['ventas']),
            'transacciones': comp(sales['transacciones'], prev_sales['transacciones']),
            'ticket': comp(indicators['ticket'], r.ratio(prev_sales['ventas'], prev_sales['transacciones'])),
            'unidades': comp(items['unidades'], prev_items['unidades']),
        },
        'last_year': {
            'range': [ly_start.isoformat(), ly_end.isoformat()],
            'ventas': comp(ventas, ly['ventas']),
            'transacciones': comp(sales['transacciones'], ly['transacciones']),
            'ticket': comp(indicators['ticket'], r.ratio(ly['ventas'], ly['transacciones'])),
        },
    }
    # Mes anterior completo (gastos y utilidad) solo si este mes ya cerró
    prev_closed = None
    if not in_progress:
        py, pm = r.previous_month(year, month)
        pstart, pend = r.month_bounds(py, pm)
        pexp = _expenses_by_class(store, f'{py}-{pm:02d}')
        if pexp['count']:
            ps, pi = _sales(store, pstart, pend), _items(store, pstart, pend)
            pentries = RepurchaseEntry.for_store(store).filter(RepurchaseEntry.date >= pstart, RepurchaseEntry.date <= pend).all()
            pcom = _commissions(store, pstart, pend, f'{py}-{pm:02d}')
            pl = r.utility_lines(
                ventas=ps['ventas'], precio_lista=pi['precio_lista'] + pi['tarjetas'], margin_pct=margin,
                otros_vendidos=pi['bolsas'],
                fletes=pexp['by_class'][r.COSTO_MERCANCIA], operativos=pexp['by_class'][r.OPERATIVO],
                financieros=pexp['by_class'][r.FINANCIERO] + sum(e.fee_4mil for e in pentries),
                comisiones=pcom['extra'], cuotas=pexp['by_class'][r.CUOTA_CREDITO],
                recompras=sum(e.total_enviado for e in pentries), comisiones_registradas=pcom['registered'])
            prev_closed = {k: comp(lines[k], pl[k]) for k in (
                'utilidad_bruta', 'gastos_operativos', 'utilidad_operacional', 'gastos_financieros',
                'utilidad_neta', 'lo_que_quedo')}
    comparisons['previous_month_closed'] = prev_closed

    outflows = [{
        'class': cls, 'label': CLASS_LABELS[cls], 'total': by_class[cls] + (recompras_fee if cls == r.FINANCIERO else 0),
        'reduces_utility': cls in r.UTILITY_CLASSES,
        'reduces_what_is_left': cls in r.UTILITY_CLASSES or cls == r.CUOTA_CREDITO,
        'items': exp['detail'].get(cls, []),
    } for cls in CLASS_LABELS if by_class[cls] or exp['detail'].get(cls) or (cls == r.FINANCIERO and recompras_fee)]

    return {
        'period': period, 'year': year, 'month': month, 'label': f'{MONTHS_ES[month - 1]} {year}',
        'future': False, 'in_progress': in_progress,
        'data_until': until.isoformat() if until >= start else None,
        'days_in_month': days, 'days_elapsed': days_elapsed,
        'margin_pct': margin, 'has_expenses': has_expenses,
        'statement': {**lines, 'recompras': recompras, 'recompras_fee': recompras_fee,
                      'ropa_lista': items['precio_lista'], 'tarjetas_regalo': items['tarjetas'], 'bolsas': items['bolsas'],
                      'comisiones_calculadas': com['calculated'], 'comisiones_registradas': com['registered']},
        'pct_of_sales': {k: r.ratio(lines[k], ventas) for k in (
            'costo_vendido', 'utilidad_bruta', 'gastos_operativos', 'utilidad_operacional',
            'gastos_financieros', 'utilidad_neta', 'cuotas', 'lo_que_quedo')},
        'indicators': indicators,
        'break_even': {
            'fixed_costs': fixed['total'], 'fixed_items': fixed['items'], 'fixed_cuotas': fixed['cuotas'],
            'contribution_pct': contrib,
            'month': be, 'day': r.daily(be, year, month),
            'month_with_cuotas': be_cuotas, 'day_with_cuotas': r.daily(be_cuotas, year, month),
            'progress_pct': r.ratio(ventas, be),
            'pace_month': pace,
            'target': target,
            'sales_for_target': r.sales_for_target(fixed['total'], target, contrib) if target else None,
        },
        'comparisons': comparisons,
        'outflows': outflows,
        'warnings': warnings,
    }
