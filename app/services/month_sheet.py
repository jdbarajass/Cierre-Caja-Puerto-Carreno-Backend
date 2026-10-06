"""
Hoja del mes (Cuentas → Mes, Fase 2 de docs/PLAN_CUENTAS_DIARIAS.md).

Junta en una sola respuesta lo que el usuario veía "todo de una" en el Excel:
- Ventas diarias por los 10 medios (recibos de Alegra, PaymentFact) con la
  calificación del día (mala / bajita / buena / alta).
- Estado de cada cuenta de Resumen en el mes: saldo inicial + ventas −
  recompras − gastos + entradas ± ajustes/transferencias = saldo final, día
  por día, y el saldo real que escribe el usuario (conciliación).
- Plata en tránsito del datáfono y Addi (bruto, neto y cuándo llega) y las
  comisiones del mes.
"""
import calendar
import json
from collections import defaultdict
from datetime import date, timedelta
from typing import Any, Dict, List

from app.models.account import Account, AccountMovement
from app.models.cash_closing import CashClosing
from app.models.expense import Expense
from app.models.month_sheet import PaymentFact, AccountReconciliation, MonthClose
from app.models.repurchase import RepurchaseEntry
from app.services.payment_facts import (
    SALE_MEDIOS, FEES, TRANSIT_MEDIOS, PAYMENTS_START, arrival_date, net_amount,
)

# Calificación del día (umbrales del Excel)
RATING_LIMITS = (
    (680000, 'mala'),
    (1000000, 'bajita'),
    (2000000, 'buena'),
)
RATING_ORDER = ('mala', 'bajita', 'buena', 'alta')

# Tipo de movimiento de Resumen -> columna del estado de cuenta
MOVEMENT_COLUMNS = {
    'cash_closing': 'ventas',
    'repurchase_send': 'recompras',
    'expense': 'gastos',
    'expense_in': 'entradas',
    'manual_adjustment': 'ajustes',
    'transfer_in': 'transferencias',
    'transfer_out': 'transferencias',
}
STATEMENT_COLUMNS = ('ventas', 'recompras', 'gastos', 'entradas', 'ajustes', 'transferencias')

COMMISSION_MARKER = 'auto:comisiones:{period}'
COMMISSION_CONCEPT = 'Comisiones datáfono y Addi {label}'
MONTHS_ES = ['enero', 'febrero', 'marzo', 'abril', 'mayo', 'junio', 'julio',
             'agosto', 'septiembre', 'octubre', 'noviembre', 'diciembre']


def rating(total: float) -> str:
    for limit, name in RATING_LIMITS:
        if total <= limit:
            return name
    return 'alta'


def month_bounds(year: int, month: int):
    return date(year, month, 1), date(year, month, calendar.monthrange(year, month)[1])


def period_label(year: int, month: int) -> str:
    return f'{MONTHS_ES[month - 1]} {year}'


# ─────────────────────────────────────────────
#  Ventas por medio
# ─────────────────────────────────────────────

def sales_by_day(store: str, start: date, end: date, today: date) -> Dict[str, Any]:
    facts = PaymentFact.for_store(store).filter(
        PaymentFact.invoice_date >= start, PaymentFact.invoice_date <= end).all()
    by_day: Dict[date, Dict[str, float]] = defaultdict(lambda: defaultdict(float))
    review: Dict[date, int] = defaultdict(int)
    for f in facts:
        by_day[f.invoice_date][f.medio] += f.amount
        if f.needs_review:
            review[f.invoice_date] += 1

    days = []
    totals = {m: 0 for m in SALE_MEDIOS + ('otro',)}
    ratings = {r: {'count': 0, 'total': 0} for r in RATING_ORDER}
    d = start
    last = min(end, today)
    while d <= last:
        medios = {m: by_day[d].get(m, 0) for m in SALE_MEDIOS + ('otro',)}
        total = sum(medios.values())
        r = rating(total) if total > 0 else None
        if r:
            ratings[r]['count'] += 1
            ratings[r]['total'] += total
        for m, v in medios.items():
            totals[m] += v
        days.append({'date': d.isoformat(), 'medios': medios, 'total': total,
                     'rating': r, 'needs_review': review.get(d, 0)})
        d += timedelta(days=1)

    return {
        'days': days,
        'totals': totals,
        'total': sum(totals.values()),
        'ratings': ratings,
        'has_data': bool(facts),
        'before_start': end < PAYMENTS_START,
    }


# ─────────────────────────────────────────────
#  Estado de cuenta por cuenta de Resumen
# ─────────────────────────────────────────────

def _effective_dates(movements: List[AccountMovement]) -> Dict[int, date]:
    """
    Fecha "de negocio" de cada movimiento: la del cierre, el envío o el gasto
    al que pertenece; si no tiene (ajustes, transferencias), el día en
    Colombia en que se registró.
    """
    closing_ids = {m.cash_closing_id for m in movements if m.cash_closing_id}
    entry_ids, expense_ids = set(), set()
    for m in movements:
        ref = m.reference_id or ''
        if ref.startswith('repurchase-entry-'):
            entry_ids.add(int(ref.rsplit('-', 1)[1]))
        elif ref.startswith('expense-'):
            expense_ids.add(int(ref.rsplit('-', 1)[1]))
    closings = {c.id: c.closing_date for c in CashClosing.query.filter(CashClosing.id.in_(closing_ids))} if closing_ids else {}
    entries = {e.id: e.date for e in RepurchaseEntry.query.filter(RepurchaseEntry.id.in_(entry_ids))} if entry_ids else {}
    expenses = {e.id: e.date for e in Expense.query.filter(Expense.id.in_(expense_ids))} if expense_ids else {}

    result = {}
    for m in movements:
        ref = m.reference_id or ''
        d = None
        if m.cash_closing_id:
            d = closings.get(m.cash_closing_id)
        elif ref.startswith('repurchase-entry-'):
            d = entries.get(int(ref.rsplit('-', 1)[1]))
        elif ref.startswith('expense-'):
            d = expenses.get(int(ref.rsplit('-', 1)[1]))
        if d is None:
            created = m.created_at
            d = (created - timedelta(hours=5)).date() if created else date.today()  # UTC -> Colombia
        result[m.id] = d
    return result


def account_statement(store: str, start: date, end: date, period: str) -> List[Dict[str, Any]]:
    accounts = Account.for_store(store).filter(Account.active.is_(True)).order_by(
        Account.sort_order.asc(), Account.id.asc()).all()
    if not accounts:
        return []
    movements = AccountMovement.query.filter(
        AccountMovement.account_id.in_([a.id for a in accounts])).all()
    eff = _effective_dates(movements)
    recs = {r.account_id: r for r in AccountReconciliation.for_store(store).filter_by(period=period)}

    by_account = defaultdict(list)
    for m in movements:
        by_account[m.account_id].append(m)

    rows = []
    for a in accounts:
        after = sum(m.amount for m in by_account[a.id] if eff[m.id] > end)
        final = a.balance - after
        cols = {c: 0.0 for c in STATEMENT_COLUMNS}
        daily: Dict[date, Dict[str, float]] = defaultdict(lambda: {c: 0.0 for c in STATEMENT_COLUMNS})
        for m in by_account[a.id]:
            d = eff[m.id]
            if start <= d <= end:
                col = MOVEMENT_COLUMNS.get(m.type, 'ajustes')
                cols[col] += m.amount
                daily[d][col] += m.amount
        initial = final - sum(cols.values())

        running = initial
        days = []
        for d in sorted(daily):
            running += sum(daily[d].values())
            days.append({'date': d.isoformat(), **daily[d], 'balance': running})

        rec = recs.get(a.id)
        rows.append({
            'account_id': a.id,
            'name': a.name,
            'payment_key': a.payment_key,
            'color': a.color,
            'initial': initial,
            **cols,
            'final': final,
            'real_balance': rec.real_balance if rec else None,
            'real_note': rec.note if rec else None,
            'difference': (rec.real_balance - final) if rec else None,
            'days': days,
        })
    return rows


# ─────────────────────────────────────────────
#  Plata en tránsito y comisiones
# ─────────────────────────────────────────────

def transit(store: str, cutoff: date) -> Dict[str, Any]:
    """Ventas de datáfono/Addi hechas hasta `cutoff` que todavía no llegan a esa fecha."""
    facts = PaymentFact.for_store(store).filter(
        PaymentFact.medio.in_(TRANSIT_MEDIOS),
        PaymentFact.invoice_date <= cutoff,
        PaymentFact.invoice_date >= cutoff - timedelta(days=45),
    ).all()
    groups: Dict[tuple, Dict[str, Any]] = {}
    for f in facts:
        arrives = arrival_date(f.medio, f.invoice_date)
        if arrives is None or arrives <= cutoff:
            continue
        g = groups.setdefault((arrives, f.medio), {
            'arrival_date': arrives.isoformat(), 'medio': f.medio, 'gross': 0, 'net': 0,
            'sales_dates': set(),
        })
        g['gross'] += f.amount
        g['net'] += net_amount(f.medio, f.amount)
        g['sales_dates'].add(f.invoice_date.isoformat())
    items = sorted(groups.values(), key=lambda g: (g['arrival_date'], g['medio']))
    for g in items:
        g['sales_dates'] = sorted(g['sales_dates'])
        g['net'] = round(g['net'])
    return {
        'cutoff': cutoff.isoformat(),
        'items': items,
        'gross': sum(g['gross'] for g in items),
        'net': sum(g['net'] for g in items),
    }


def commissions(store: str, start: date, end: date, period: str) -> Dict[str, Any]:
    facts = PaymentFact.for_store(store).filter(
        PaymentFact.medio.in_(tuple(FEES)),
        PaymentFact.invoice_date >= start, PaymentFact.invoice_date <= end).all()
    by_medio = defaultdict(lambda: {'sales': 0, 'fee': 0.0})
    for f in facts:
        by_medio[f.medio]['sales'] += f.amount
        by_medio[f.medio]['fee'] += f.amount * FEES[f.medio]
    total = round(sum(v['fee'] for v in by_medio.values()))
    registered = Expense.for_store(store).filter_by(notes=COMMISSION_MARKER.format(period=period)).first()
    return {
        'by_medio': {m: {'sales': v['sales'], 'fee': round(v['fee'])} for m, v in by_medio.items()},
        'total': total,
        'registered_expense_id': registered.id if registered else None,
        'registered_amount': registered.total if registered else 0,
    }


# ─────────────────────────────────────────────
#  Hoja completa
# ─────────────────────────────────────────────

def build_sheet(store: str, year: int, month: int, today: date) -> Dict[str, Any]:
    start, end = month_bounds(year, month)
    period = f'{year}-{month:02d}'
    cutoff = min(today, end)

    sales = sales_by_day(store, start, end, today)
    statement = account_statement(store, start, end, period)
    tr = transit(store, cutoff)
    comm = commissions(store, start, end, period)

    # Cuenta ADDI + DATÁFONO: cuánto de su saldo todavía no llega y la
    # comisión del mes que aún no se ha registrado como gasto.
    for row in statement:
        if row['payment_key'] == 'addi_datafono':
            pending_fee = max(0, comm['total'] - comm['registered_amount'])
            row['in_transit_gross'] = tr['gross']
            row['pending_commission'] = pending_fee
            row['estimated_available'] = row['final'] - tr['gross'] - pending_fee

    close = MonthClose.for_store(store).filter_by(period=period).first()
    close_info = None
    if close:
        snap = json.loads(close.snapshot)
        snap_finals = {str(a['account_id']): a['final'] for a in snap.get('accounts', [])}
        changed = [r['name'] for r in statement
                   if str(r['account_id']) in snap_finals and abs(snap_finals[str(r['account_id'])] - r['final']) >= 1]
        close_info = {
            'closed_at': close.closed_at.isoformat() + 'Z' if close.closed_at else None,
            'notes': close.notes,
            'snapshot': snap,
            'changed_accounts': changed,
        }

    return {
        'period': period,
        'label': period_label(year, month),
        'start': start.isoformat(),
        'end': end.isoformat(),
        'sales': sales,
        'statement': statement,
        'transit': tr,
        'commissions': comm,
        'closed': close_info,
        'payments_start': PAYMENTS_START.isoformat(),
    }


def snapshot_of(sheet: Dict[str, Any]) -> str:
    """Lo que se guarda al cerrar el mes (sin el detalle día por día)."""
    return json.dumps({
        'accounts': [{k: r[k] for k in ('account_id', 'name', 'payment_key', 'initial', *STATEMENT_COLUMNS,
                                         'final', 'real_balance', 'difference')}
                     for r in sheet['statement']],
        'sales_totals': sheet['sales']['totals'],
        'sales_total': sheet['sales']['total'],
        'ratings': sheet['sales']['ratings'],
        'commissions': sheet['commissions']['total'],
        'in_transit': sheet['transit']['gross'],
    }, ensure_ascii=False)
