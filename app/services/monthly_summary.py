"""
Resumen mensual y anual (Cuentas → Año, Fase 3 de docs/PLAN_CUENTAS_DIARIAS.md).

Por mes (lo de la hoja CierreGeneral2026 del Excel, con el criterio contable
del plan):
- ventas: facturas de Alegra no anuladas (copia InvoiceFact, desde ene-2026).
- recompras: lo enviado a Jhonatan (RepurchaseEntry.total_enviado).
- gastos operativos: gastos que CORRESPONDEN al mes (Expense.period) de las
  categorías operativo, sueldo, flete, financiero, cuota_credito y otro, con
  su 4x1000, más el 4x1000 de las recompras.
- ganancia bruta = ventas − recompras; ganancia neta = ventas − gastos
  operativos (como el Excel); ganancia real = ventas − recompras − gastos.
- inventario al cierre del mes (Alegra) y cuánto subió/bajó; ganancia real
  + aumento del inventario (si el inventario sube, esa plata está en la tienda).
- aparte (no son gasto): inversiones, retiros de socios, préstamos, fletes,
  lo que tiene Jhonatan al cierre del mes.
- excedentes (otros ingresos, no son venta): lo abonado como 'excedente' por
  los cierres de caja del mes ya sincronizados con Cuentas. No cambian ventas,
  ganancias ni la regla 70/30; se muestran aparte con ventas + excedentes.
Cada dato se puede escribir a mano (MonthlySummaryOverride) y manda sobre el
calculado.

Por medio de pago (lo de DATOS_ANUALES_2026): ventas por los 10 medios desde
los recibos de Alegra (PaymentFact, desde PAYMENTS_START).
"""
import calendar
from collections import defaultdict
from datetime import date, timedelta
from typing import Any, Dict, Optional

from sqlalchemy import func

from app.models.user import db
from app.models.account import AccountMovement
from app.models.cash_closing import CashClosing
from app.models.expense import Expense
from app.models.invoice_fact import InvoiceFact
from app.models.month_sheet import PaymentFact
from app.models.monthly_summary import InventorySnapshot, MonthlySummaryOverride
from app.models.repurchase import RepurchaseEntry
from app.models.repurchase_purchase import RepurchasePurchase
from app.services.payment_facts import SALE_MEDIOS, PAYMENTS_START

# Arranque del resumen (decisión del usuario): desde septiembre 2026
SUMMARY_START = date(2026, 9, 1)

OPERATING_CATEGORIES = ('operativo', 'sueldo', 'flete', 'financiero', 'cuota_credito', 'otro')

# Datos que el usuario puede escribir a mano
OVERRIDE_FIELDS = (
    'ventas', 'recompras', 'gastos_operativos', 'inventario',
    'inversiones', 'retiros', 'prestamos', 'fletes',
)

MONTHS_ES = ['Enero', 'Febrero', 'Marzo', 'Abril', 'Mayo', 'Junio', 'Julio',
             'Agosto', 'Septiembre', 'Octubre', 'Noviembre', 'Diciembre']


def _bounds(year: int, month: int):
    return date(year, month, 1), date(year, month, calendar.monthrange(year, month)[1])


def _period(year: int, month: int) -> str:
    return f'{year}-{month:02d}'


def _prev(year: int, month: int):
    return (year - 1, 12) if month == 1 else (year, month - 1)


def _sum(query) -> float:
    return float(query.scalar() or 0)


def computed_month(store: str, year: int, month: int) -> Dict[str, Any]:
    """Lo que el sistema calcula solo para un mes (sin lo escrito a mano)."""
    start, end = _bounds(year, month)
    ym = _period(year, month)

    ventas = _sum(db.session.query(func.sum(InvoiceFact.total)).filter(
        InvoiceFact.store_code == store, InvoiceFact.voided.is_(False),
        InvoiceFact.date >= start, InvoiceFact.date <= end))
    invoice_days = db.session.query(func.count(func.distinct(InvoiceFact.date))).filter(
        InvoiceFact.store_code == store, InvoiceFact.date >= start, InvoiceFact.date <= end).scalar() or 0

    entries = RepurchaseEntry.for_store(store).filter(
        RepurchaseEntry.date >= start, RepurchaseEntry.date <= end).all()
    recompras = sum(e.total_enviado for e in entries)
    recompras_fee = sum(e.fee_4mil for e in entries)
    compras_jhonatan = _sum(db.session.query(func.sum(RepurchasePurchase.amount)).filter(
        RepurchasePurchase.store_code == store, RepurchasePurchase.date >= start, RepurchasePurchase.date <= end))

    by_cat = defaultdict(float)
    expense_count = 0
    for e in Expense.for_store(store).filter(Expense.period == ym, Expense.direction == 'out').all():
        by_cat[e.category] += e.total_with_fee
        expense_count += 1
    gastos_operativos = sum(by_cat[c] for c in OPERATING_CATEGORIES) + recompras_fee

    medios = {m: 0 for m in SALE_MEDIOS + ('otro',)}
    for medio, total in db.session.query(PaymentFact.medio, func.sum(PaymentFact.amount)).filter(
            PaymentFact.store_code == store, PaymentFact.invoice_date >= start,
            PaymentFact.invoice_date <= end).group_by(PaymentFact.medio):
        medios[medio] = float(total or 0)
    # Correcciones a mano del medio (Cuentas → Mes)
    from app.services.month_sheet import corrections
    for c in corrections(store, start, end):
        medios[c.from_medio] = medios.get(c.from_medio, 0) - c.amount
        medios[c.to_medio] = medios.get(c.to_medio, 0) + c.amount

    # Excedentes de los cierres del mes (solo los sincronizados con Cuentas,
    # es decir, cierres exitosos: lo mismo que entró a las cuentas)
    excedentes = _sum(db.session.query(func.sum(AccountMovement.amount)).join(
        CashClosing, AccountMovement.cash_closing_id == CashClosing.id).filter(
        AccountMovement.type == 'excedente', CashClosing.store_code == store,
        CashClosing.closing_date >= start, CashClosing.closing_date <= end))

    return {
        'ventas': ventas,
        'excedentes': excedentes,
        'recompras': recompras,
        'gastos_operativos': gastos_operativos,
        'inversiones': by_cat['inversion'],
        'retiros': by_cat['retiro_socio'],
        'prestamos': by_cat['prestamo_empleada'] + by_cat['prestamo_tienda'],
        'fletes': by_cat['flete'],
        'gastos_por_categoria': dict(by_cat),
        'recompras_fee': recompras_fee,
        'compras_jhonatan': compras_jhonatan,
        'ventas_por_medio': medios,
        'has_sales_data': invoice_days > 0,
        'has_payments_data': any(medios.values()),
        'has_expenses': expense_count > 0,
    }


def _inventory(store: str, year: int, month: int) -> Optional[InventorySnapshot]:
    return InventorySnapshot.for_store(store).filter_by(period=_period(year, month)).first()


def build_year(store: str, year: int, today: date) -> Dict[str, Any]:
    overrides = defaultdict(dict)
    for o in MonthlySummaryOverride.for_store(store).filter(MonthlySummaryOverride.period.like(f'{year}-%')).all():
        overrides[o.period][o.field] = o

    # Inventario de diciembre del año anterior (para la variación de enero)
    py, pm = _prev(year, 1)
    prev_snap = _inventory(store, py, pm)
    prev_override = MonthlySummaryOverride.for_store(store).filter_by(period=_period(py, pm), field='inventario').first()
    prev_inventory = prev_override.value if prev_override else (prev_snap.value if prev_snap else None)

    from app.routes.repurchase import _carryover_before, CARRYOVER_START
    from app.services.finance_settings import get_settings
    settings = get_settings(store)

    months = []
    for month in range(1, 13):
        start, end = _bounds(year, month)
        ym = _period(year, month)
        future = start > today
        row: Dict[str, Any] = {
            'period': ym, 'year': year, 'month': month, 'label': MONTHS_ES[month - 1],
            'future': future, 'in_progress': start <= today <= end,
            'before_start': end < SUMMARY_START,
        }
        if future:
            months.append(row)
            continue

        comp = computed_month(store, year, month)
        snap = _inventory(store, year, month)
        comp['inventario'] = snap.value if snap else None
        row['inventory_as_of'] = snap.as_of.isoformat() if snap else None

        values, edited = {}, {}
        for f in OVERRIDE_FIELDS:
            o = overrides[ym].get(f)
            values[f] = o.value if o else comp[f]
            if o:
                edited[f] = {'computed': comp[f], 'note': o.note}
        row.update(values)
        row['edited'] = edited
        row['computed'] = {f: comp[f] for f in OVERRIDE_FIELDS}
        for k in ('excedentes', 'gastos_por_categoria', 'recompras_fee', 'compras_jhonatan', 'ventas_por_medio',
                  'has_sales_data', 'has_payments_data', 'has_expenses'):
            row[k] = comp[k]
        # Si se escribieron los gastos a mano, el mes sí tiene gastos
        row['has_expenses'] = comp['has_expenses'] or 'gastos_operativos' in edited

        ventas, recompras, gastos = row['ventas'], row['recompras'], row['gastos_operativos']
        row['ganancia_bruta'] = ventas - recompras
        row['ganancia_neta'] = ventas - gastos
        row['ganancia_real'] = ventas - recompras - gastos
        row['porcentaje'] = (row['ganancia_real'] / ventas) if ventas else None
        row['ventas_mas_excedentes'] = ventas + row['excedentes']

        inv = row['inventario']
        row['inventario_cambio'] = (inv - prev_inventory) if (inv is not None and prev_inventory is not None) else None
        row['ganancia_con_inventario'] = (row['ganancia_real'] + row['inventario_cambio']) if row['inventario_cambio'] is not None else None
        prev_inventory = inv if inv is not None else prev_inventory

        # Regla 70/30 (Fase 4): lo que debía ir a resurtido vs. lo recomprado,
        # y la utilidad esperada vs. la ganancia real.
        share = settings['resurtido_pct'] / 100
        row['resurtido_esperado'] = ventas * share
        row['resurtido_diferencia'] = recompras - row['resurtido_esperado']
        row['utilidad_esperada'] = ventas * (1 - share)
        row['utilidad_diferencia'] = row['ganancia_real'] - row['utilidad_esperada']
        margin = settings['margin_pct'] / 100
        row['resurtido_en_ropa'] = row['resurtido_esperado'] / (1 - margin) if margin < 1 else None

        next_start = end + timedelta(days=1)
        row['jhonatan'] = _carryover_before(next_start) if end >= CARRYOVER_START else None
        months.append(row)

    done = [m for m in months if not m['future'] and not m['before_start']]
    numeric = ('ventas', 'excedentes', 'ventas_mas_excedentes', 'recompras', 'gastos_operativos', 'ganancia_bruta', 'ganancia_neta', 'ganancia_real',
               'inversiones', 'retiros', 'prestamos', 'fletes', 'resurtido_esperado', 'resurtido_diferencia',
               'utilidad_esperada', 'utilidad_diferencia')
    totals = {k: sum(m[k] for m in done) for k in numeric}
    totals['porcentaje'] = (totals['ganancia_real'] / totals['ventas']) if totals['ventas'] else None
    with_sales = [m for m in done if m['ventas']]
    averages = {k: (sum(m[k] for m in with_sales) / len(with_sales)) if with_sales else 0
                for k in ('ventas', 'ganancia_real', 'gastos_operativos')}
    medios_year = {m: sum(r['ventas_por_medio'][m] for r in months if not r['future']) for m in SALE_MEDIOS + ('otro',)}

    return {
        'year': year,
        'summary_start': SUMMARY_START.isoformat(),
        'payments_start': PAYMENTS_START.isoformat(),
        'months': months,
        'totals': totals,
        'averages': averages,
        'months_counted': len(done),
        'ventas_por_medio_year': medios_year,
        'override_fields': list(OVERRIDE_FIELDS),
        'settings': settings,
    }


# ─────────────────────────────────────────────
#  Inventario desde Alegra
# ─────────────────────────────────────────────

def fetch_inventory(direct_client, store: str, year: int, month: int, today: date) -> InventorySnapshot:
    """Trae de Alegra el valor del inventario al cierre del mes (o a hoy si va en curso) y lo guarda."""
    start, end = _bounds(year, month)
    if start > today:
        raise ValueError('Ese mes todavía no ha empezado')
    as_of = min(end, today)
    result = direct_client.get_inventory_value_totals(to_date=as_of.isoformat(), query='', force_inventory_parallel=False)
    if not result.get('success'):
        raise RuntimeError(result.get('error') or 'Alegra no entregó el valor del inventario')
    value = float((result.get('data') or {}).get('total') or 0)
    snap = _inventory(store, year, month)
    if snap is None:
        snap = InventorySnapshot(store_code=store, period=_period(year, month), value=value, as_of=as_of)
        db.session.add(snap)
    snap.value = value
    snap.as_of = as_of
    from datetime import datetime
    snap.fetched_at = datetime.utcnow()
    db.session.commit()
    return snap


def months_needing_inventory(store: str, today: date, since: date = SUMMARY_START):
    """
    Meses desde un mes antes de `since` (para la variación) hasta hoy cuyo
    inventario falta o quedó tomado antes del cierre del mes (o, si va en
    curso, antes de hoy).
    """
    y, m = _prev(since.year, since.month)
    result = []
    while date(y, m, 1) <= today:
        start, end = _bounds(y, m)
        snap = _inventory(store, y, m)
        if snap is None or snap.as_of < min(end, today):
            result.append((y, m))
        y, m = (y + 1, 1) if m == 12 else (y, m + 1)
    return result
