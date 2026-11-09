"""
Radiografía del año (Fase 2 de docs/PLAN_RADIOGRAFIA.md): por mes de una
tienda, ventas, costo estimado, utilidades, recompras, gastos, lo que quedó e
inventario de fin de mes; total y promedio.

Solo lee. Parte de Cuentas → Año (monthly_summary.build_year) para que cuadre
al peso con esa pantalla, incluidas las cifras escritas a mano:
- ventas, recompras e inventario escritos a mano mandan sobre lo calculado;
- gastos escritos a mano (como el Excel) son el total de todo: ya traen
  fletes, financieros y cuotas, así que no se separan (se marca el mes);
- "lo que quedó" = ganancia real de Año (desde SUMMARY_START, como Año).
El estado de resultados de cada mes sale de las mismas piezas que la Fase 1
(radiografia_month), sin las comparaciones.
"""
from datetime import date
from typing import Any, Dict, List

from app.services import radiografia as r
from app.services.radiografia_month import (
    MONTHS_ES, _commissions, _expenses_by_class, _items, _sales,
)

MONTH_FIELDS = (
    'ventas', 'precio_lista', 'descuentos', 'costo_estimado', 'fletes', 'costo_vendido', 'utilidad_bruta',
    'gastos_operativos', 'utilidad_operacional', 'gastos_financieros', 'utilidad_neta', 'cuotas',
    'recompras', 'lo_que_quedo',
)


def _month_row(store: str, row: Dict[str, Any], today: date, margin: float) -> Dict[str, Any]:
    from app.services.monthly_summary import SUMMARY_START
    year, month = row['year'], row['month']
    start, end = r.month_bounds(year, month)
    until = min(end, today)
    period = row['period']
    has_sales = row['has_sales_data'] or 'ventas' in row['edited']
    out: Dict[str, Any] = {
        'period': period, 'year': year, 'month': month, 'label': MONTHS_ES[month - 1].capitalize(),
        'future': False, 'in_progress': row['in_progress'], 'has_data': has_sales,
        'in_cuentas_anio': not row['before_start'],
        'edited': sorted(row['edited'].keys()),
    }
    items = _items(store, start, until)
    sales = _sales(store, start, until)
    exp = _expenses_by_class(store, period)
    gastos_a_mano = row['cuotas_en_gastos']
    if gastos_a_mano:
        # Total escrito a mano en Año: trae todo, no se puede separar
        fletes, operativos, financieros, cuotas = 0.0, row['gastos_operativos'], 0.0, 0.0
        comisiones, registered, calculadas = 0.0, True, False
    else:
        by_class = exp['by_class']
        com = _commissions(store, start, until, period)
        fletes, operativos = by_class[r.COSTO_MERCANCIA], by_class[r.OPERATIVO]
        financieros = by_class[r.FINANCIERO] + row['recompras_fee']
        cuotas = by_class[r.CUOTA_CREDITO]
        comisiones, registered = com['extra'], com['registered']
        calculadas = bool(com['extra'])
    lines = r.utility_lines(
        ventas=row['ventas'], precio_lista=items['precio_lista'] + items['tarjetas'], margin_pct=margin,
        otros_vendidos=items['bolsas'], fletes=fletes, operativos=operativos, financieros=financieros,
        comisiones=comisiones, cuotas=cuotas, recompras=row['recompras'], comisiones_registradas=registered)
    out.update({k: lines.get(k) for k in MONTH_FIELDS if k in lines})
    out['recompras'] = row['recompras']
    out['margen_bruto_pct'] = lines['margen_bruto_pct']
    out['margen_neto_pct'] = lines['margen_neto_pct']
    out['has_expenses'] = row['has_expenses']
    out['gastos_a_mano'] = gastos_a_mano
    out['comisiones_calculadas'] = calculadas
    # "Lo que quedó" es la ganancia real de Cuentas → Año (mismas cifras a mano);
    # antes del arranque de Año no hay gastos en el sistema: no se muestra.
    out['lo_que_quedo'] = row['ganancia_real'] if end >= SUMMARY_START else None
    if not row['has_expenses']:
        out['utilidad_operacional'] = out['utilidad_neta'] = out['margen_neto_pct'] = None
    out['transacciones'] = sales['transacciones']
    out['ticket'] = r.ratio(row['ventas'], sales['transacciones'])
    out['unidades'] = items['unidades']
    inv = row['inventario']
    out['inventario'] = inv
    out['inventario_costo'] = r.estimated_cost(inv, margin) if inv is not None else None
    out['inventario_cambio'] = row['inventario_cambio']
    out['inventory_as_of'] = row.get('inventory_as_of')
    # Mismo mes del año pasado (venta real de 2025); mes en curso: mismos días
    ly_start, ly_end = r.month_bounds(year - 1, month)
    if until < end:
        ly_end = ly_start.replace(day=min(until.day, ly_end.day))
    ly = _sales(store, ly_start, ly_end)['ventas']
    out['ventas_anio_anterior'] = ly or None
    out['ventas_vs_anio_anterior'] = r.pct_change(row['ventas'], ly) if ly else None
    return out


def _sum(rows: List[Dict[str, Any]], key: str):
    vals = [m[key] for m in rows if m.get(key) is not None]
    return sum(vals) if vals else None


def build_year(store: str, year: int, today: date) -> Dict[str, Any]:
    from app.services.finance_settings import get_settings
    from app.services.monthly_summary import build_year as summary_year
    margin = get_settings(store)['margin_pct']
    summary = summary_year(store, year, today)
    months: List[Dict[str, Any]] = []
    for row in summary['months']:
        if row['future']:
            months.append({'period': row['period'], 'year': year, 'month': row['month'],
                           'label': MONTHS_ES[row['month'] - 1].capitalize(), 'future': True, 'has_data': False})
            continue
        months.append(_month_row(store, row, today, margin))

    with_data = [m for m in months if m['has_data']]
    with_expenses = [m for m in with_data if m['has_expenses']]
    in_anio = [m for m in months if not m['future'] and m.get('in_cuentas_anio')]

    totals = {k: _sum(with_data, k) for k in (
        'ventas', 'precio_lista', 'descuentos', 'costo_estimado', 'utilidad_bruta', 'recompras',
        'transacciones', 'unidades')}
    # Gastos y utilidades: solo los meses con gastos registrados (sin gastos no se inventa)
    for k in ('fletes', 'gastos_operativos', 'gastos_financieros', 'utilidad_operacional', 'utilidad_neta', 'cuotas'):
        totals[k] = _sum(with_expenses, k)
    totals['ventas_con_gastos'] = _sum(with_expenses, 'ventas')
    # Lo que quedó: los mismos meses que suma Cuentas → Año
    totals['lo_que_quedo'] = _sum(in_anio, 'lo_que_quedo')
    totals['margen_bruto_pct'] = r.ratio(totals['utilidad_bruta'], totals['ventas'])
    totals['margen_neto_pct'] = r.ratio(totals['utilidad_neta'], totals['ventas_con_gastos'])
    totals['ticket'] = r.ratio(totals['ventas'], totals['transacciones'])

    def avg(rows, key):
        vals = [m[key] for m in rows if m.get(key) is not None]
        return sum(vals) / len(vals) if vals else None

    # Promedio por mes: los meses cerrados (el mes en curso bajaría el promedio)
    closed = [m for m in with_data if not m['in_progress']]
    closed_exp = [m for m in closed if m['has_expenses']]
    averages = {k: avg(closed, k) for k in ('ventas', 'utilidad_bruta', 'transacciones', 'ticket')}
    for k in ('gastos_operativos', 'utilidad_neta'):
        averages[k] = avg(closed_exp, k)
    averages['lo_que_quedo'] = avg([m for m in closed if m.get('in_cuentas_anio')], 'lo_que_quedo')
    averages['months'] = len(closed)
    averages['months_with_expenses'] = len(closed_exp)

    best = max(closed, key=lambda m: m['ventas'], default=None)
    worst = min(closed, key=lambda m: m['ventas'], default=None)

    warnings: List[str] = []
    no_exp = [m['label'] for m in with_data if not m['has_expenses']]
    if no_exp:
        warnings.append('Sin gastos registrados (solo ventas, costo estimado y utilidad bruta): ' + ', '.join(no_exp) + '.')
    a_mano = [m['label'] for m in with_data if m.get('gastos_a_mano')]
    if a_mano:
        warnings.append('Gastos escritos a mano en Cuentas → Año (el total trae todo, no se separa en operativos, '
                        'financieros y cuotas): ' + ', '.join(a_mano) + '.')
    if any(m.get('comisiones_calculadas') for m in with_data):
        warnings.append('En algunos meses las comisiones de datáfono/Addi no están registradas: se calculan '
                        '(ESTIMADO) y bajan la utilidad, no "lo que quedó".')
    if any(m['in_progress'] for m in with_data):
        warnings.append('El mes en curso no entra en los promedios.')

    return {
        'year': year,
        'margin_pct': margin,
        'summary_start': summary['summary_start'],
        'months': months,
        'totals': totals,
        'averages': averages,
        'best_month': {'label': best['label'], 'ventas': best['ventas']} if best else None,
        'worst_month': {'label': worst['label'], 'ventas': worst['ventas']} if worst and worst is not best else None,
        'months_with_data': len(with_data),
        'months_with_expenses': len(with_expenses),
        'warnings': warnings,
    }
