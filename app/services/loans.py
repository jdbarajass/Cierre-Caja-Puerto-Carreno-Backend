"""
Préstamos de cada tienda (Radiografía Fase 0c, docs/PLAN_RADIOGRAFIA.md):
cálculos de cuota, tasa, tabla de pagos y saldo, y el enlace con Cuentas →
Gastos. Modelos en app/models/loan.py.

Reglas del usuario (2026-11-06):
- Cuota "francesa" (fija): cuota = P·r / (1 − (1 + r)^−n). La tasa que no se
  conoce sale de la cuota y el plazo (ESTIMADO) hasta que se escriba la real.
- Mientras un préstamo no tenga tasa, todo el pago baja la deuda. Con tasa,
  cada pago se parte: interés = saldo × tasa (una vez por mes) y el resto baja
  la deuda. El interés es gasto financiero (baja la ganancia); la parte de
  capital es "cuota de crédito" (no baja la utilidad neta, sí lo que quedó).
- Solo se resta lo que se registra a mano. Lo pendiente del mes es un aviso.
- Si se cambia el plazo o la tasa se recalcula la cuota; si se cambia la cuota
  se recalcula la tasa. Todo se recalcula de nuevo, incluso los pagos hechos.
"""
import json
import math
from collections import defaultdict
from datetime import date, datetime
from typing import Any, Dict, Iterable, List, Optional

from app.models.loan import PAYMENT_KINDS, Loan, LoanPayment
from app.models.user import db


class LoanError(ValueError):
    """Dato inválido: se responde 400."""


# ─────────────────────────────────────────────
#  Fórmulas
# ─────────────────────────────────────────────

def annuity_payment(principal: float, rate_pct: Optional[float], months: Optional[int]) -> Optional[float]:
    """Cuota fija. None si falta el plazo."""
    if not months or months <= 0 or principal <= 0:
        return None
    r = (rate_pct or 0) / 100
    if r == 0:
        return principal / months
    return principal * r / (1 - (1 + r) ** -months)


def rate_from_payment(principal: float, months: Optional[int], payment: Optional[float]) -> Optional[float]:
    """Tasa mensual % que da esa cuota con ese plazo (búsqueda por mitades).
    None si con esa cuota el préstamo no se paga en ese plazo ni sin intereses."""
    if not months or not payment or principal <= 0 or payment * months < principal:
        return None
    lo, hi = 0.0, 0.5
    for _ in range(200):
        mid = (lo + hi) / 2
        if annuity_payment(principal, mid * 100, months) > payment:
            hi = mid
        else:
            lo = mid
    return round(lo * 100, 4)


def installments_left(balance: float, rate_pct: Optional[float], payment: Optional[float]) -> Optional[int]:
    """Cuántas cuotas faltan con la cuota y la tasa de hoy (ESTIMADO)."""
    if balance <= 0:
        return 0
    if not payment or payment <= 0:
        return None
    r = (rate_pct or 0) / 100
    if r == 0:
        return math.ceil(balance / payment - 1e-9)
    if payment <= balance * r:
        return None  # con esa cuota no alcanza ni para el interés
    return math.ceil(-math.log(1 - balance * r / payment) / math.log(1 + r) - 1e-9)


def _ordered(payments: Iterable[LoanPayment]) -> List[LoanPayment]:
    return sorted(payments, key=lambda p: (p.date, p.id or 0))


def schedule(loan: Loan, payments: Iterable[LoanPayment]) -> Dict[str, Any]:
    """Tabla de pagos con interés y capital de cada uno y el saldo después."""
    balance = loan.principal
    r = (loan.monthly_rate_pct or 0) / 100
    charged_months = set()
    rows, interest_total, capital_total, paid_total = [], 0.0, 0.0, 0.0
    for p in _ordered(payments):
        interest = 0.0
        if p.kind == 'ajuste':
            capital = p.amount
        else:
            ym = (p.date.year, p.date.month)
            if r and ym not in charged_months and balance > 0:
                interest = min(round(balance * r), p.amount)
                charged_months.add(ym)
            capital = p.amount - interest
            interest_total += interest
            paid_total += p.amount
        capital_total += capital if p.kind != 'ajuste' else 0
        balance -= capital
        rows.append({
            'id': p.id, 'date': p.date.isoformat(), 'kind': p.kind, 'amount': p.amount,
            'interest': interest, 'capital': capital, 'balance_after': balance,
            'expense_id': p.expense_id, 'note': p.note,
        })
    return {'rows': rows, 'balance': balance, 'interest_total': interest_total,
            'capital_total': capital_total, 'paid_total': paid_total}


def _payments_of(loan_ids: Iterable[int]) -> Dict[int, List[LoanPayment]]:
    out = defaultdict(list)
    ids = list(loan_ids)
    if ids:
        for p in LoanPayment.query.filter(LoanPayment.loan_id.in_(ids)).all():
            out[p.loan_id].append(p)
    return out


def interest_by_expense(expenses: Iterable[Any]) -> Dict[int, float]:
    """Parte de interés de cada gasto de cuota ligado a un préstamo con tasa
    (lo usan Cuentas → Año y el comparativo para pasarla a gasto financiero)."""
    loan_ids = {e.loan_id for e in expenses if getattr(e, 'loan_id', None)}
    if not loan_ids:
        return {}
    loans = {l.id: l for l in Loan.query.filter(Loan.id.in_(loan_ids)).all()}
    payments = _payments_of(loan_ids)
    out = {}
    for lid, loan in loans.items():
        if not loan.monthly_rate_pct:
            continue
        for row in schedule(loan, payments.get(lid, []))['rows']:
            if row['expense_id'] and row['interest']:
                out[row['expense_id']] = row['interest']
    return out


# ─────────────────────────────────────────────
#  Vista de las tarjetas
# ─────────────────────────────────────────────

def loan_view(loan: Loan, payments: List[LoanPayment], today: date) -> Dict[str, Any]:
    sch = schedule(loan, payments)
    month_payments = [p for p in payments if p.kind != 'ajuste'
                      and (p.date.year, p.date.month) == (today.year, today.month)]
    return {
        'id': loan.id, 'group_name': loan.group_name, 'name': loan.name,
        'principal': loan.principal, 'start_date': loan.start_date.isoformat(),
        'term_months': loan.term_months, 'monthly_rate_pct': loan.monthly_rate_pct,
        'rate_estimated': bool(loan.rate_estimated), 'installment': loan.installment,
        'due_day': loan.due_day, 'fixed_expense_id': loan.fixed_expense_id, 'active': bool(loan.active),
        'notes': loan.notes, 'history': json.loads(loan.history) if loan.history else [],
        'payments': sch['rows'], 'paid_total': sch['paid_total'], 'interest_total': sch['interest_total'],
        'capital_total': sch['capital_total'], 'balance': sch['balance'],
        'installments_left': installments_left(sch['balance'], loan.monthly_rate_pct, loan.installment),
        'paid_this_month': sum(p.amount for p in month_payments),
        'pending_this_month': bool(loan.active and sch['balance'] > 0 and not month_payments),
    }


def groups(store: str, today: date) -> List[Dict[str, Any]]:
    loans = Loan.for_store(store).order_by(Loan.sort_order.asc(), Loan.id.asc()).all()
    payments = _payments_of(l.id for l in loans)
    cards = {}
    for loan in loans:
        v = loan_view(loan, payments.get(loan.id, []), today)
        g = cards.setdefault(loan.group_name, {'group_name': loan.group_name, 'loans': []})
        g['loans'].append(v)
    out = []
    for g in cards.values():
        active = [l for l in g['loans'] if l['active']]
        g.update({
            'principal': sum(l['principal'] for l in g['loans']),
            'balance': sum(l['balance'] for l in g['loans']),
            'paid_total': sum(l['paid_total'] for l in g['loans']),
            'interest_total': sum(l['interest_total'] for l in g['loans']),
            'installment': sum(l['installment'] or 0 for l in active) or None,
            'pending_this_month': [l['name'] for l in active if l['pending_this_month']],
            'due_day': min((l['due_day'] for l in active), default=25),
        })
        out.append(g)
    return out


# ─────────────────────────────────────────────
#  Crear y editar (con recálculo y rastro)
# ─────────────────────────────────────────────

EDITABLE = ('group_name', 'name', 'principal', 'start_date', 'term_months', 'monthly_rate_pct',
            'installment', 'due_day', 'fixed_expense_id', 'active', 'notes', 'sort_order')


def _num(value, field, integer=False, allow_none=True):
    if value in (None, ''):
        if allow_none:
            return None
        raise LoanError(f'Falta {field}')
    try:
        n = int(value) if integer else float(value)
    except (TypeError, ValueError):
        raise LoanError(f'Valor inválido en {field}')
    if n < 0:
        raise LoanError(f'{field} no puede ser negativo')
    return n


def apply_changes(loan: Loan, data: Dict[str, Any], user: Dict[str, Any], creating: bool = False) -> None:
    before = {k: getattr(loan, k) for k in EDITABLE}
    for key in ('group_name', 'name', 'notes'):
        if creating or key in data:
            setattr(loan, key, (data.get(key) or '').strip() or None)
    if not loan.group_name or not loan.name:
        raise LoanError('Escribe el nombre de la tarjeta y del préstamo')
    if creating or 'principal' in data:
        loan.principal = _num(data.get('principal'), 'valor prestado', allow_none=False)
    if creating or 'start_date' in data:
        try:
            loan.start_date = datetime.strptime(str(data.get('start_date')), '%Y-%m-%d').date()
        except ValueError:
            raise LoanError('Fecha inválida (AAAA-MM-DD)')
    if creating or 'due_day' in data:
        loan.due_day = _num(data.get('due_day'), 'día', integer=True) or 25
        if not 1 <= loan.due_day <= 31:
            raise LoanError('El día debe estar entre 1 y 31')
    if creating or 'fixed_expense_id' in data:
        loan.fixed_expense_id = _num(data.get('fixed_expense_id'), 'gasto fijo', integer=True)
    if creating or 'active' in data:
        loan.active = bool(data.get('active', True))
    if 'sort_order' in data:
        loan.sort_order = _num(data.get('sort_order'), 'orden', integer=True) or 0

    # Plazo, tasa y cuota: el último que se cambia manda y se recalcula el otro
    if creating or 'term_months' in data:
        loan.term_months = _num(data.get('term_months'), 'plazo', integer=True)
    rate_given = 'monthly_rate_pct' in data and data.get('monthly_rate_pct') not in (None, '')
    inst_given = 'installment' in data and data.get('installment') not in (None, '')
    if rate_given:
        loan.monthly_rate_pct = _num(data.get('monthly_rate_pct'), 'interés')
        loan.rate_estimated = bool(data.get('rate_estimated', False))
    elif 'monthly_rate_pct' in data:
        loan.monthly_rate_pct = None
    if inst_given:
        loan.installment = _num(data.get('installment'), 'cuota')
    elif 'installment' in data:
        loan.installment = None

    term_changed = creating or loan.term_months != before['term_months']
    if inst_given and not rate_given and loan.term_months:
        # Cambió la cuota (o se creó con cuota y plazo): la tasa sale de ahí (ESTIMADO)
        loan.monthly_rate_pct = rate_from_payment(loan.principal, loan.term_months, loan.installment)
        loan.rate_estimated = True
    elif (rate_given or term_changed or 'principal' in data) and loan.term_months and loan.monthly_rate_pct is not None \
            and not inst_given:
        loan.installment = round(annuity_payment(loan.principal, loan.monthly_rate_pct, loan.term_months))

    if not creating:
        changes = {k: [before[k].isoformat() if isinstance(before[k], date) else before[k],
                       getattr(loan, k).isoformat() if isinstance(getattr(loan, k), date) else getattr(loan, k)]
                   for k in EDITABLE if before[k] != getattr(loan, k)}
        if changes:
            hist = json.loads(loan.history) if loan.history else []
            hist.append({'at': datetime.utcnow().isoformat(timespec='seconds'), 'by': user.get('email'),
                         'changes': changes, 'note': (data.get('change_note') or '').strip()[:300] or None})
            loan.history = json.dumps(hist, ensure_ascii=False)


def add_manual_payment(loan: Loan, data: Dict[str, Any], user: Dict[str, Any], today: date) -> LoanPayment:
    """Cuota descontada del préstamo o ajuste de saldo (los pagos con plata se
    registran como gasto, ver sync_from_expense)."""
    kind = data.get('kind')
    if kind not in ('descontado', 'ajuste'):
        raise LoanError('Los pagos que salen de las cuentas se registran en Cuentas → Gastos')
    try:
        day = datetime.strptime(str(data.get('date') or today.isoformat()), '%Y-%m-%d').date()
    except ValueError:
        raise LoanError('Fecha inválida (AAAA-MM-DD)')
    note = (data.get('note') or '').strip()
    if kind == 'ajuste':
        if not note:
            raise LoanError('Escribe por qué se ajusta el saldo')
        new_balance = _num(data.get('new_balance'), 'saldo nuevo', allow_none=False)
        current = schedule(loan, LoanPayment.query.filter_by(loan_id=loan.id).all())['balance']
        amount = current - new_balance
        if amount == 0:
            raise LoanError('El saldo ya es ese')
    else:
        amount = _num(data.get('amount'), 'valor', allow_none=False)
        if amount <= 0:
            raise LoanError('El valor debe ser mayor que 0')
    p = LoanPayment(store_code=loan.store_code, loan_id=loan.id, date=day, kind=kind, amount=amount,
                    note=note or None, created_by=user.get('userId'))
    db.session.add(p)
    return p


def sync_from_expense(expense: Any, is_delete: bool = False) -> None:
    """Un gasto de cuota con préstamo = un pago del préstamo (kind 'pago').
    Se crea, actualiza o borra con el gasto. No hace commit."""
    existing = LoanPayment.query.filter_by(expense_id=expense.id).first() if expense.id else None
    wants = (not is_delete and expense.loan_id and expense.category == 'cuota_credito'
             and expense.direction == 'out')
    if not wants:
        if existing:
            db.session.delete(existing)
        if not is_delete and expense.category != 'cuota_credito':
            expense.loan_id = None
        return
    loan = Loan.for_store(expense.store_code).filter_by(id=expense.loan_id).first()
    if loan is None:
        raise LoanError('Ese préstamo no existe en esta tienda')
    if not expense.fixed_expense_id and loan.fixed_expense_id:
        expense.fixed_expense_id = loan.fixed_expense_id
    p = existing or LoanPayment(store_code=expense.store_code, expense_id=expense.id, created_by=expense.created_by)
    p.loan_id = loan.id
    p.date = expense.date
    p.kind = 'pago'
    p.amount = expense.total
    p.note = expense.concept
    if existing is None:
        db.session.add(p)


def payment_kinds() -> tuple:
    return PAYMENT_KINDS
