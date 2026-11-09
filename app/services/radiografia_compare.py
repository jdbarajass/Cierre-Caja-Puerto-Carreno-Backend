"""
Radiografía, Fase 5: comparativo de las tiendas y consolidado (docs/PLAN_RADIOGRAFIA.md).

Solo lee y no recalcula nada: toma lo mismo que ven Mes (Fase 1) y Flujo de
caja (Fase 4) de cada tienda y lo pone lado a lado, más una columna "Las dos"
con la suma. El inventario sale de la foto de Alegra del mes elegido
(InventorySnapshot, la de Cuentas → Año) para no pedir el stock de las dos
tiendas a Alegra (~1 min cada una); el detalle por prenda está en Inventario.

Consolidado (regla del plan): el préstamo entre las tiendas no aparece. Lo
que una "le debe" a la otra se cancela, no es gasto ni ingreso, y las
devoluciones o préstamos que llegaron a una cuenta de la otra se cancelan con
su salida. Lo que salió de una tienda y no llegó a la otra (por ejemplo
ganancias de los dueños pagadas como abono) sí es plata que salió de las dos
y queda en la línea "Entre las dos tiendas".
Los porcentajes del consolidado se calculan con las sumas, no se suman.
"""
from datetime import date
from typing import Any, Dict, List, Optional

from app.services import radiografia as r
from app.stores import STORES

SUM_STATEMENT = ('ventas', 'precio_lista', 'descuentos', 'costo_estimado', 'fletes', 'costo_vendido',
                 'utilidad_bruta', 'gastos_operativos', 'utilidad_operacional', 'gastos_financieros',
                 'utilidad_neta', 'cuotas', 'recompras', 'lo_que_quedo')
INTER_STORE_OUT = ('prestamo_tienda', 'pago_prestamo_tienda')
INTER_STORE_IN = ('devolucion_prestamo_tienda', 'prestamo_recibido_tienda')


def _inventory(store: str, margin: float, period: str) -> Optional[Dict[str, Any]]:
    """Foto de Alegra del mes elegido (fin de mes, o la de hoy si el mes va en
    curso); si ese mes no tiene, la más reciente anterior."""
    from app.models.monthly_summary import InventorySnapshot
    snap = InventorySnapshot.for_store(store).filter(InventorySnapshot.period <= period).order_by(
        InventorySnapshot.period.desc(), InventorySnapshot.as_of.desc()).first()
    if not snap:
        return None
    return {'as_of': snap.as_of.isoformat(), 'period': snap.period, 'valor_venta': snap.value,
            'valor_costo': snap.value * (1 - margin / 100)}


def _store_column(store: str, year: int, month: int, today: date) -> Dict[str, Any]:
    from app.services.finance_settings import get_settings
    from app.services.radiografia_cashflow import build_cash_flow
    from app.services.radiografia_month import build_month
    margin = get_settings(store)['margin_pct']
    m = build_month(store, year, month, today)
    cf = build_cash_flow(store, year, month, today, month_data=m)
    col = {'store': store, 'name': STORES[store]['name'], 'margin_pct': margin, 'future': m.get('future', False),
           'inventory': _inventory(store, margin, f'{year}-{month:02d}'), 'today': cf['today']}
    if m.get('future'):
        return col
    flow = cf['flow']
    inter_out = sum(i['amount'] for s in flow['salidas'] if s['key'] == r.PRESTAMO
                    for i in s['items'] if i['category'] in INTER_STORE_OUT)
    inter_in = sum(e['total'] for e in flow['entradas'] if e['key'] in INTER_STORE_IN)
    col.update({
        'has_expenses': m['has_expenses'], 'in_progress': m['in_progress'], 'data_until': m['data_until'],
        'statement': {k: m['statement'][k] for k in SUM_STATEMENT},
        'pct': {k: m['pct_of_sales'].get(k) for k in ('utilidad_bruta', 'utilidad_neta', 'lo_que_quedo')},
        'indicators': {k: m['indicators'][k] for k in ('transacciones', 'ticket', 'unidades', 'descuentos_pct',
                                                         'gastos_ventas_pct', 'nomina_ventas_pct')},
        'break_even': {k: m['break_even'][k] for k in ('fixed_costs', 'month', 'day', 'progress_pct')},
        'flow': {'initial': flow['initial'], 'final': flow['final'], 'change': flow['change'],
                 'entradas_total': flow['entradas_total'], 'salidas_total': flow['salidas_total'],
                 'inter_store_out': inter_out, 'inter_store_in': inter_in},
        'warnings': m['warnings'] + cf['warnings'],
    })
    return col


def _sum(cols: List[Dict[str, Any]], path: tuple) -> Optional[float]:
    vals = []
    for c in cols:
        v = c
        for p in path:
            v = (v or {}).get(p)
        if v is not None:
            vals.append(v)
    return sum(vals) if vals else None


def _consolidated(cols: List[Dict[str, Any]]) -> Dict[str, Any]:
    out: Dict[str, Any] = {'name': 'Las dos tiendas'}
    live = [c for c in cols if not c['future']]
    inv = [c['inventory'] for c in cols if c['inventory']]
    out['inventory'] = {'valor_venta': sum(i['valor_venta'] for i in inv), 'valor_costo': sum(i['valor_costo'] for i in inv),
                        'as_of': min(i['as_of'] for i in inv)} if inv else None
    today = [c['today'] for c in cols]
    plata = sum(t['plata'] for t in today)
    receivable = sum(x['value'] for t in today for x in t['receivable'] if x['key'] != 'otra_tienda')
    payable = sum(x['value'] for t in today for x in t['payable'] if x['key'] != 'otra_tienda')
    avisos = sum(a['value'] for t in today for a in t['withdraw']['avisos'] if a['key'] != 'otra_tienda')
    out['today'] = {'plata': plata, 'receivable_total': receivable, 'payable_total': payable,
                    'avisos_total': avisos, 'quedarian': plata - avisos,
                    'inter_store_debt': next((x['value'] for t in today for x in t['payable'] if x['key'] == 'otra_tienda'), 0)}
    if not live:
        out['future'] = True
        return out
    st = {k: _sum(live, ('statement', k)) for k in SUM_STATEMENT}
    ventas = st['ventas'] or 0
    all_expenses = all(c['has_expenses'] for c in live)
    if not all_expenses:
        # Sin gastos en alguna tienda, la utilidad de las dos no se puede sumar
        for k in ('utilidad_operacional', 'utilidad_neta'):
            st[k] = None
    out.update({
        'future': False, 'has_expenses': all_expenses,
        'statement': st,
        'pct': {'utilidad_bruta': r.ratio(st['utilidad_bruta'], ventas), 'utilidad_neta': r.ratio(st['utilidad_neta'], ventas),
                'lo_que_quedo': r.ratio(st['lo_que_quedo'], ventas)},
        'indicators': {
            'transacciones': _sum(live, ('indicators', 'transacciones')),
            'ticket': r.ratio(ventas, _sum(live, ('indicators', 'transacciones'))),
            'unidades': _sum(live, ('indicators', 'unidades')),
            # Descuentos ÷ precio de lista vendido (con bolsas) = descuentos ÷ (descuentos + ventas)
            'descuentos_pct': r.ratio(st['descuentos'], (st['descuentos'] or 0) + ventas),
            'gastos_ventas_pct': r.ratio((st['gastos_operativos'] or 0) + (st['gastos_financieros'] or 0), ventas) if all_expenses else None,
            'nomina_ventas_pct': r.ratio(sum((c['indicators']['nomina_ventas_pct'] or 0) * c['statement']['ventas'] for c in live),
                                         ventas) if all_expenses else None,
        },
        'break_even': {'fixed_costs': _sum(live, ('break_even', 'fixed_costs')), 'month': _sum(live, ('break_even', 'month')),
                       'day': _sum(live, ('break_even', 'day')), 'progress_pct': None},
    })
    be = out['break_even']
    out['break_even']['progress_pct'] = r.ratio(ventas, be['month'])
    flow = {k: _sum(live, ('flow', k)) for k in ('initial', 'final', 'change', 'entradas_total', 'salidas_total',
                                                 'inter_store_out', 'inter_store_in')}
    # Lo que llegó a la otra tienda se cancela: se quita de las entradas y de las salidas
    cancel = min(flow['inter_store_out'], flow['inter_store_in'])
    flow['entradas_total'] -= cancel
    flow['salidas_total'] -= cancel
    flow['inter_store_net'] = flow['inter_store_out'] - flow['inter_store_in']
    out['flow'] = flow
    return out


def build_compare(year: int, month: int, today: date, stores: Optional[List[str]] = None) -> Dict[str, Any]:
    from app.services.radiografia_month import MONTHS_ES
    stores = stores or list(STORES)
    cols = [_store_column(s, year, month, today) for s in stores]
    return {
        'period': f'{year}-{month:02d}', 'year': year, 'month': month, 'label': f'{MONTHS_ES[month - 1]} {year}',
        'stores': cols,
        'consolidated': _consolidated(cols),
        'notes': [
            'El préstamo entre las tiendas no aparece en "Las dos": lo que una le debe a la otra se cancela.',
            'Inventario: foto de Alegra del mes (la de Cuentas → Año; si el mes va en curso, la de hoy) a precio de venta y a costo ESTIMADO.',
            'Los porcentajes de "Las dos" salen de las sumas, no se suman.',
        ],
    }
