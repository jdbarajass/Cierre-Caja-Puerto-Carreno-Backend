"""
Cuentas → Gastos (Fase 1 de docs/PLAN_CUENTAS_DIARIAS.md).

Gastos y otros movimientos de plata que no son ventas ni recompras, gastos
fijos del mes (pagado / pendiente / vencido) y préstamos entre tiendas.
Acceso: solo admin. Todo por tienda (header X-Store).
"""
import calendar
import logging
import re
from datetime import datetime, date as dt_date

from flask import Blueprint, request, jsonify

from app.middlewares.auth import token_required, get_current_user
from app.models.user import db
from app.models.account import Account, AccountMovement
from app.models.employee_records import EmployeeLoan, EmployeePayment
from app.models.expense import (
    Expense, FixedExpense, EXPENSE_ACCOUNT_MAP, EXPENSE_METHODS,
    OUT_CATEGORIES, IN_CATEGORIES, ACCOUNT_MODES, EXPENSE_SUBCATEGORIES,
)
from app.stores import STORES, get_current_store
from app.utils.timezone import get_colombia_now

logger = logging.getLogger(__name__)
bp = Blueprint('expenses', __name__)

PERIOD_RE = re.compile(r'^\d{4}-(0[1-9]|1[0-2])$')

# Plantilla de gastos fijos tomada del Excel KOAJ_CARRENO2026.xlsx (bloque
# "GASTOS FIJOS MES A MES" de septiembre/octubre). Valores de referencia,
# editables después. Los incentivos (dependen de la meta) no van aquí.
FIXED_EXPENSES_TEMPLATE = [
    {'name': 'Cuota Scotiabank', 'amount': 1110000, 'due_day': 5, 'category': 'cuota_credito', 'subcategory': 'cuota_banco'},
    {'name': 'Internet', 'amount': 266000, 'due_day': 5, 'category': 'operativo', 'subcategory': 'internet'},
    {'name': 'Sueldos empleadas 1ra quincena', 'amount': 1500000, 'due_day': 15, 'category': 'sueldo', 'subcategory': 'sueldos_empleadas_1'},
    {'name': 'Sueldo Jhonatan por recompras (1ra quincena)', 'amount': 200000, 'due_day': 15, 'category': 'sueldo', 'subcategory': 'sueldo_jhonatan_recompras'},
    {'name': 'YouTube', 'amount': 41900, 'due_day': 20, 'category': 'operativo', 'subcategory': 'youtube'},
    {'name': 'Alegra', 'amount': 139900, 'due_day': 22, 'category': 'operativo', 'subcategory': 'alegra'},
    {'name': 'Sueldos empleadas 2da quincena', 'amount': 1500000, 'due_day': 30, 'category': 'sueldo', 'subcategory': 'sueldos_empleadas_2'},
    {'name': 'Sueldo Jhonatan por recompras (2da quincena)', 'amount': 200000, 'due_day': 30, 'category': 'sueldo', 'subcategory': 'sueldo_jhonatan_recompras'},
    {'name': 'Luz', 'amount': 380000, 'due_day': 30, 'category': 'operativo', 'subcategory': 'luz'},
    {'name': 'Arriendo', 'amount': 1052000, 'due_day': 30, 'category': 'operativo', 'subcategory': 'arriendo'},
    {'name': 'Cuota de manejo Bancolombia', 'amount': 14900, 'due_day': 30, 'category': 'financiero', 'subcategory': 'cuota_manejo'},
    {'name': 'Ganancia Cristhian', 'amount': 1000000, 'due_day': 30, 'category': 'retiro_socio', 'subcategory': 'ganancia_cristian'},
    {'name': 'Ganancia Jhonatan', 'amount': 1000000, 'due_day': 30, 'category': 'retiro_socio', 'subcategory': 'ganancia_jhonatan'},
    {'name': 'Ganancia José', 'amount': 1000000, 'due_day': 30, 'category': 'retiro_socio', 'subcategory': 'ganancia_jose'},
]


class ExpenseError(ValueError):
    """Dato inválido o inconsistente: se responde 400 con el mensaje."""


def _require_admin():
    if get_current_user().get('role') != 'admin':
        return jsonify({'success': False, 'message': 'Solo el administrador puede acceder'}), 403
    return None


def _parse_date(value):
    try:
        return datetime.strptime(value, '%Y-%m-%d').date()
    except (TypeError, ValueError):
        raise ExpenseError(f'Fecha inválida: {value}')


def _month_range(year, month):
    return dt_date(year, month, 1), dt_date(year, month, calendar.monthrange(year, month)[1])


def _money(value, field):
    try:
        amount = float(value or 0)
    except (TypeError, ValueError):
        raise ExpenseError(f'Monto inválido en {field}')
    if amount < 0:
        raise ExpenseError(f'{field} no puede ser negativo')
    return amount


# ─────────────────────────────────────────────
#  Validación y aplicación de datos
# ─────────────────────────────────────────────

def _apply_payload(expense, data, creating):
    """Copia los campos de data al gasto y valida el resultado completo."""
    if creating or 'date' in data:
        expense.date = _parse_date(data.get('date'))
    if creating or 'period' in data:
        period = (data.get('period') or '').strip()
        expense.period = period or expense.date.strftime('%Y-%m')
    if not PERIOD_RE.match(expense.period or ''):
        raise ExpenseError('El mes al que corresponde debe ser AAAA-MM')

    if creating or 'concept' in data:
        expense.concept = (data.get('concept') or '').strip()
    if not expense.concept:
        raise ExpenseError('El concepto es obligatorio')

    if creating or 'direction' in data:
        expense.direction = data.get('direction') or 'out'
    if expense.direction not in ('out', 'in'):
        raise ExpenseError("direction debe ser 'out' o 'in'")

    if creating or 'subcategory' in data:
        expense.subcategory = (data.get('subcategory') or '').strip() or None
    if expense.direction != 'out':
        expense.subcategory = None
    if expense.subcategory:
        # La categoría detallada manda: el grupo sale de ella
        if expense.subcategory not in EXPENSE_SUBCATEGORIES:
            raise ExpenseError(f'Categoría inválida: {expense.subcategory}')
        expense.category = EXPENSE_SUBCATEGORIES[expense.subcategory]
    elif creating or 'category' in data:
        expense.category = data.get('category') or ('operativo' if expense.direction == 'out' else 'ingreso_extra')
    valid = OUT_CATEGORIES if expense.direction == 'out' else IN_CATEGORIES
    if expense.category not in valid:
        raise ExpenseError(f'Categoría inválida para este tipo de movimiento: {expense.category}')

    if creating or 'category_detail' in data:
        expense.category_detail = (data.get('category_detail') or '').strip()[:120] or None
    if expense.subcategory != 'otra':
        expense.category_detail = None
    elif not expense.category_detail:
        raise ExpenseError('Escribe qué otra categoría es')

    for m in EXPENSE_METHODS:
        if creating or m in data:
            setattr(expense, m, _money(data.get(m), m))
    if expense.total <= 0:
        raise ExpenseError('Escribe el valor en al menos un medio de pago')

    if creating or 'account_mode' in data:
        expense.account_mode = data.get('account_mode') or 'cuentas'
    if expense.account_mode not in ACCOUNT_MODES:
        raise ExpenseError(f'account_mode inválido: {expense.account_mode}')
    if expense.account_mode == 'caja' and expense.non_cash_total > 0:
        raise ExpenseError('Lo que sale de la caja del día solo puede ser en efectivo')

    if creating or 'apply_fee' in data:
        expense.apply_fee = bool(data.get('apply_fee', True))
    if creating or 'fee_override' in data:
        fee = data.get('fee_override')
        expense.fee_override = _money(fee, 'fee_override') if fee is not None else None

    if creating or 'related_store_code' in data:
        expense.related_store_code = (data.get('related_store_code') or '').strip() or None
    if expense.category in ('prestamo_tienda', 'devolucion_prestamo_tienda'):
        if expense.related_store_code not in STORES or expense.related_store_code == get_current_store():
            raise ExpenseError('Elige la otra tienda del préstamo')
    else:
        expense.related_store_code = None

    if creating or 'employee_name' in data:
        expense.employee_name = (data.get('employee_name') or '').strip() or None
    if expense.category == 'prestamo_empleada' and not expense.employee_name:
        raise ExpenseError('Escribe el nombre de la empleada del préstamo')

    if creating or 'fixed_expense_id' in data:
        fixed_id = data.get('fixed_expense_id')
        if fixed_id:
            if not FixedExpense.for_current_store().filter_by(id=int(fixed_id)).first():
                raise ExpenseError('El gasto fijo no existe en esta tienda')
            expense.fixed_expense_id = int(fixed_id)
        else:
            expense.fixed_expense_id = None

    if creating or 'notes' in data:
        expense.notes = (data.get('notes') or '').strip() or None


def _sync_expense_account_movements(expense, is_delete=False):
    """
    Mantiene los movimientos de Resumen ligados al gasto
    (reference_id='expense-{id}'): revierte los que existan y, si el gasto
    mueve cuentas (account_mode='cuentas'), crea los nuevos según los montos
    actuales. Salidas: cada medio descuenta su monto más su parte del 4x1000
    (repartido entre los medios que no son efectivo; el resto del redondeo va
    al último). Entradas: suman el monto. Mismo patrón que las recompras
    (_sync_entry_account_movements en app/routes/repurchase.py). No hace
    commit: el caller confirma todo junto.
    """
    reference_id = f'expense-{expense.id}'
    existing = AccountMovement.query.filter_by(reference_id=reference_id).all()

    medios = []
    if not is_delete and expense.account_mode == 'cuentas':
        medios = [(m, getattr(expense, m)) for m in EXPENSE_METHODS if getattr(expense, m)]

    accounts_by_key = {}
    if medios:
        keys = [EXPENSE_ACCOUNT_MAP[m] for m, _ in medios]
        accounts_by_key = {a.payment_key: a for a in Account.for_store(expense.store_code).filter(
            Account.payment_key.in_(keys)).all()}
        missing = [k for k in keys if k not in accounts_by_key]
        if missing:
            raise ExpenseError(f'Esta tienda no tiene la cuenta: {", ".join(missing)}')

    all_ids = {m.account_id for m in existing} | {a.id for a in accounts_by_key.values()}
    locked = {}
    if all_ids:
        locked = {a.id: a for a in Account.query.filter(Account.id.in_(all_ids))
                  .with_for_update().order_by(Account.id.asc()).all()}

    for mv in existing:
        account = locked.get(mv.account_id)
        if account:
            account.balance -= mv.amount
        db.session.delete(mv)

    if not medios:
        return

    user_id = get_current_user().get('userId')
    sign = -1 if expense.direction == 'out' else 1
    fee_total = expense.fee if expense.direction == 'out' else 0
    non_cash = [(m, a) for m, a in medios if m != 'efectivo']
    fee_base = sum(a for _, a in non_cash)
    fee_assigned = 0

    for m, amount in medios:
        fee_share = 0
        if fee_total and m != 'efectivo':
            if (m, amount) == non_cash[-1]:
                fee_share = fee_total - fee_assigned
            else:
                fee_share = round(fee_total * amount / fee_base) if fee_base else 0
            fee_assigned += fee_share
        elif fee_total and not non_cash and m == medios[-1][0]:
            # 4x1000 escrito a mano en un gasto solo en efectivo
            fee_share = fee_total
        account = locked[accounts_by_key[EXPENSE_ACCOUNT_MAP[m]].id]
        value = sign * (amount + fee_share)
        description = ('Gasto' if expense.direction == 'out' else 'Entrada') + f': {expense.concept}'
        if fee_share:
            description += f' (incluye {fee_share:,.0f} de 4x1000)'.replace(',', '.')
        db.session.add(AccountMovement(
            account_id=account.id,
            type='expense' if expense.direction == 'out' else 'expense_in',
            amount=value,
            description=description,
            reference_id=reference_id,
            created_by=user_id,
        ))
        account.balance += value


def _sync_employee_links(expense, is_delete=False, payment_type='quincena'):
    """
    Enlace con Empleadas:
    - prestamo_empleada -> EmployeeLoan por el total.
    - devolucion_prestamo con empleada -> EmployeeLoan NEGATIVO (abono: baja
      el total acumulado de la empleada).
    - sueldo con empleada -> EmployeePayment (tipo `payment_type` al crearlo:
      quincena por defecto; los incentivos usan 'comision').
    Crea, actualiza o borra el registro ligado según el estado actual.
    """
    want_loan = not is_delete and bool(expense.employee_name) and expense.category in (
        'prestamo_empleada', 'devolucion_prestamo')
    want_payment = not is_delete and bool(expense.employee_name) and expense.category == 'sueldo'
    note = f'Desde Gastos: {expense.concept}'

    loan = EmployeeLoan.for_store(expense.store_code).filter_by(
        id=expense.employee_loan_id).first() if expense.employee_loan_id else None
    if want_loan:
        amount = expense.total if expense.category == 'prestamo_empleada' else -expense.total
        if loan is None:
            loan = EmployeeLoan(store_code=expense.store_code)
            db.session.add(loan)
        loan.nombre_empleada = expense.employee_name
        loan.date = expense.date
        loan.amount = amount
        loan.notes = note
        db.session.flush()
        expense.employee_loan_id = loan.id
    else:
        if loan is not None:
            db.session.delete(loan)
        expense.employee_loan_id = None

    payment = EmployeePayment.for_store(expense.store_code).filter_by(
        id=expense.employee_payment_id).first() if expense.employee_payment_id else None
    if want_payment:
        if payment is None:
            payment = EmployeePayment(store_code=expense.store_code, type=payment_type)
            db.session.add(payment)
        payment.nombre_empleada = expense.employee_name
        payment.date = expense.date
        payment.amount = expense.total
        payment.notes = note
        db.session.flush()
        expense.employee_payment_id = payment.id
    else:
        if payment is not None:
            db.session.delete(payment)
        expense.employee_payment_id = None


# ─────────────────────────────────────────────
#  GASTOS: listar / crear / editar / borrar
# ─────────────────────────────────────────────

def _month_args():
    year = request.args.get('year', type=int)
    month = request.args.get('month', type=int)
    if not year or not month or not 1 <= month <= 12:
        raise ExpenseError('year y month son obligatorios')
    return year, month


@bp.route('/api/expenses', methods=['GET', 'OPTIONS'])
@token_required
def list_expenses():
    """
    Movimientos del mes: los que tienen la FECHA en el mes o el MES AL QUE
    CORRESPONDEN igual al mes. Totales:
    - by_method: lo que salió/entró de cada cuenta con fecha en el mes (con
      4x1000), solo de los movimientos con account_mode='cuentas'.
    - by_category: gastos que corresponden al mes (period), para la ganancia.
    """
    if request.method == 'OPTIONS':
        return '', 204
    err = _require_admin()
    if err:
        return err
    try:
        year, month = _month_args()
        start, end = _month_range(year, month)
        ym = f'{year}-{month:02d}'
        items = Expense.for_current_store().filter(db.or_(
            db.and_(Expense.date >= start, Expense.date <= end),
            Expense.period == ym,
        )).order_by(Expense.date.asc(), Expense.id.asc()).all()

        in_month = [e for e in items if start <= e.date <= end]
        by_method = {m: {'out': 0, 'in': 0} for m in EXPENSE_METHODS}
        fee_by_method = {m: 0 for m in EXPENSE_METHODS}
        # Solo lo que movió las cuentas de Resumen (no la caja del día ni sin_mover)
        for e in (e for e in in_month if e.account_mode == 'cuentas'):
            for m in EXPENSE_METHODS:
                by_method[m][e.direction] += getattr(e, m) or 0
            if e.fee:
                # el 4x1000 se reparte igual que en las cuentas: entre lo que no es efectivo
                base = e.non_cash_total
                for m in EXPENSE_METHODS:
                    if m != 'efectivo' and base:
                        fee_by_method[m] += e.fee * (getattr(e, m) or 0) / base
                if not base:
                    fee_by_method['efectivo'] += e.fee

        by_category = {}
        for e in items:
            if e.period != ym:
                continue
            c = by_category.setdefault(e.category, {'total': 0, 'fee': 0, 'count': 0, 'direction': e.direction})
            c['total'] += e.total
            c['fee'] += e.fee
            c['count'] += 1

        return jsonify({
            'success': True,
            'period': ym,
            'items': [e.to_dict() for e in items],
            'totals': {
                'out_total': sum(e.total_with_fee for e in in_month if e.direction == 'out'),
                'in_total': sum(e.total for e in in_month if e.direction == 'in'),
                'fee_total': sum(e.fee for e in in_month),
                'by_method': {m: {'out': round(v['out'] + fee_by_method[m]), 'in': v['in']}
                              for m, v in by_method.items()},
                'by_category': by_category,
            },
        }), 200
    except ExpenseError as e:
        return jsonify({'success': False, 'message': str(e)}), 400
    except Exception as e:
        logger.error(f'Error listando gastos: {e}')
        return jsonify({'success': False, 'message': 'Error al obtener los gastos'}), 500


@bp.route('/api/expenses', methods=['POST'])
@token_required
def create_expense():
    err = _require_admin()
    if err:
        return err
    try:
        expense = Expense(created_by=get_current_user().get('userId'))
        _apply_payload(expense, request.get_json() or {}, creating=True)
        db.session.add(expense)
        db.session.flush()
        _sync_expense_account_movements(expense)
        _sync_employee_links(expense)
        db.session.commit()
        return jsonify({'success': True, 'item': expense.to_dict()}), 201
    except ExpenseError as e:
        db.session.rollback()
        return jsonify({'success': False, 'message': str(e)}), 400
    except Exception as e:
        db.session.rollback()
        logger.error(f'Error creando gasto: {e}')
        return jsonify({'success': False, 'message': 'Error al guardar el gasto'}), 500


@bp.route('/api/expenses/<int:expense_id>', methods=['PUT', 'DELETE', 'OPTIONS'])
@token_required
def manage_expense(expense_id):
    if request.method == 'OPTIONS':
        return '', 204
    err = _require_admin()
    if err:
        return err
    expense = Expense.get_for_current_store_or_404(expense_id)
    try:
        if request.method == 'DELETE':
            _sync_expense_account_movements(expense, is_delete=True)
            _sync_employee_links(expense, is_delete=True)
            db.session.delete(expense)
            db.session.commit()
            return jsonify({'success': True}), 200

        _apply_payload(expense, request.get_json() or {}, creating=False)
        _sync_expense_account_movements(expense)
        _sync_employee_links(expense)
        db.session.commit()
        return jsonify({'success': True, 'item': expense.to_dict()}), 200
    except ExpenseError as e:
        db.session.rollback()
        return jsonify({'success': False, 'message': str(e)}), 400
    except Exception as e:
        db.session.rollback()
        logger.error(f'Error actualizando gasto {expense_id}: {e}')
        return jsonify({'success': False, 'message': 'Error al guardar el gasto'}), 500


# ─────────────────────────────────────────────
#  GASTOS FIJOS
# ─────────────────────────────────────────────

def _apply_fixed_payload(item, data, creating):
    if creating or 'name' in data:
        item.name = (data.get('name') or '').strip()
    if not item.name:
        raise ExpenseError('El nombre es obligatorio')
    if creating or 'amount' in data:
        item.amount = _money(data.get('amount'), 'amount')
    if creating or 'due_day' in data:
        try:
            item.due_day = int(data.get('due_day') or 30)
        except (TypeError, ValueError):
            raise ExpenseError('Día de pago inválido')
    if not 1 <= item.due_day <= 31:
        raise ExpenseError('El día de pago debe estar entre 1 y 31')
    if creating or 'subcategory' in data:
        item.subcategory = (data.get('subcategory') or '').strip() or None
    if item.subcategory:
        if item.subcategory not in EXPENSE_SUBCATEGORIES:
            raise ExpenseError(f'Categoría inválida: {item.subcategory}')
        item.category = EXPENSE_SUBCATEGORIES[item.subcategory]
    elif creating or 'category' in data:
        item.category = data.get('category') or 'operativo'
    if item.category not in OUT_CATEGORIES:
        raise ExpenseError(f'Categoría inválida: {item.category}')
    if creating or 'default_method' in data:
        item.default_method = data.get('default_method') or None
    if item.default_method and item.default_method not in EXPENSE_METHODS:
        raise ExpenseError(f'Medio de pago inválido: {item.default_method}')
    if creating or 'active' in data:
        item.active = bool(data.get('active', True))
    if 'sort_order' in data:
        item.sort_order = int(data.get('sort_order') or 0)
    if creating or 'notes' in data:
        item.notes = (data.get('notes') or '').strip() or None


@bp.route('/api/expenses/fixed', methods=['GET', 'OPTIONS'])
@token_required
def list_fixed():
    """Gastos fijos con su estado en el mes pedido (pagado / pendiente / vencido)."""
    if request.method == 'OPTIONS':
        return '', 204
    err = _require_admin()
    if err:
        return err
    try:
        year, month = _month_args()
        ym = f'{year}-{month:02d}'
        last_day = calendar.monthrange(year, month)[1]
        today = get_colombia_now().date()

        fixed = FixedExpense.for_current_store().order_by(
            FixedExpense.due_day.asc(), FixedExpense.sort_order.asc(), FixedExpense.id.asc()).all()
        paid = {}
        for e in Expense.for_current_store().filter(
                Expense.period == ym, Expense.fixed_expense_id.isnot(None)).all():
            p = paid.setdefault(e.fixed_expense_id, {'amount': 0, 'expense_ids': [], 'last_date': None})
            p['amount'] += e.total
            p['expense_ids'].append(e.id)
            p['last_date'] = max(p['last_date'] or e.date, e.date)

        result = []
        for f in fixed:
            d = f.to_dict()
            due = dt_date(year, month, min(f.due_day, last_day))
            d['due_date'] = due.isoformat()
            p = paid.get(f.id)
            if p:
                d['status'] = 'pagado'
                d['paid_amount'] = p['amount']
                d['expense_ids'] = p['expense_ids']
                d['paid_date'] = p['last_date'].isoformat()
            else:
                d['status'] = 'vencido' if f.active and today > due else 'pendiente'
                d['paid_amount'] = 0
                d['expense_ids'] = []
                d['paid_date'] = None
            if f.active or p:
                result.append(d)
        inactive = [f.to_dict() for f in fixed if not f.active]

        return jsonify({
            'success': True,
            'period': ym,
            'items': result,
            'inactive': inactive,
            'summary': {
                'pagado': sum(1 for r in result if r['status'] == 'pagado'),
                'pendiente': sum(1 for r in result if r['status'] == 'pendiente'),
                'vencido': sum(1 for r in result if r['status'] == 'vencido'),
                'reference_total': sum(r['amount'] for r in result if r['active']),
                'paid_total': sum(r['paid_amount'] for r in result),
            },
            'template_available': not fixed,
        }), 200
    except ExpenseError as e:
        return jsonify({'success': False, 'message': str(e)}), 400
    except Exception as e:
        logger.error(f'Error listando gastos fijos: {e}')
        return jsonify({'success': False, 'message': 'Error al obtener los gastos fijos'}), 500


@bp.route('/api/expenses/fixed', methods=['POST'])
@token_required
def create_fixed():
    err = _require_admin()
    if err:
        return err
    try:
        item = FixedExpense()
        _apply_fixed_payload(item, request.get_json() or {}, creating=True)
        db.session.add(item)
        db.session.commit()
        return jsonify({'success': True, 'item': item.to_dict()}), 201
    except ExpenseError as e:
        db.session.rollback()
        return jsonify({'success': False, 'message': str(e)}), 400


@bp.route('/api/expenses/fixed/load-template', methods=['POST', 'OPTIONS'])
@token_required
def load_fixed_template():
    """Crea los gastos fijos del Excel, solo si la tienda todavía no tiene ninguno."""
    if request.method == 'OPTIONS':
        return '', 204
    err = _require_admin()
    if err:
        return err
    if FixedExpense.for_current_store().count():
        return jsonify({'success': False, 'message': 'Esta tienda ya tiene gastos fijos'}), 409
    for i, data in enumerate(FIXED_EXPENSES_TEMPLATE):
        db.session.add(FixedExpense(sort_order=i, active=True, **data))
    db.session.commit()
    return jsonify({'success': True, 'created': len(FIXED_EXPENSES_TEMPLATE)}), 201


@bp.route('/api/expenses/fixed/<int:fixed_id>', methods=['PUT', 'DELETE', 'OPTIONS'])
@token_required
def manage_fixed(fixed_id):
    if request.method == 'OPTIONS':
        return '', 204
    err = _require_admin()
    if err:
        return err
    item = FixedExpense.get_for_current_store_or_404(fixed_id)
    try:
        if request.method == 'DELETE':
            # Los gastos ya pagados se conservan, solo pierden el enlace
            Expense.for_current_store().filter_by(fixed_expense_id=item.id).update(
                {'fixed_expense_id': None}, synchronize_session=False)
            db.session.delete(item)
            db.session.commit()
            return jsonify({'success': True}), 200
        _apply_fixed_payload(item, request.get_json() or {}, creating=False)
        db.session.commit()
        return jsonify({'success': True, 'item': item.to_dict()}), 200
    except ExpenseError as e:
        db.session.rollback()
        return jsonify({'success': False, 'message': str(e)}), 400


# ─────────────────────────────────────────────
#  PRÉSTAMOS ENTRE TIENDAS
# ─────────────────────────────────────────────

@bp.route('/api/expenses/inter-store', methods=['GET', 'OPTIONS'])
@token_required
def inter_store_loans():
    """
    Préstamos entre tiendas vistos desde la tienda actual:
    - lent: lo que esta tienda le prestó a cada otra (préstamos − devoluciones
      recibidas, ambos registrados en ESTA tienda).
    - owed: lo que esta tienda le debe a cada otra (lo mismo, registrado en la otra).
    """
    if request.method == 'OPTIONS':
        return '', 204
    err = _require_admin()
    if err:
        return err

    current = get_current_store()
    cats = ('prestamo_tienda', 'devolucion_prestamo_tienda')

    def balance_of(lender, borrower):
        rows = Expense.for_store(lender).filter(
            Expense.category.in_(cats), Expense.related_store_code == borrower
        ).order_by(Expense.date.asc(), Expense.id.asc()).all()
        lent = sum(r.total for r in rows if r.category == 'prestamo_tienda')
        returned = sum(r.total for r in rows if r.category == 'devolucion_prestamo_tienda')
        return {
            'lender': lender, 'lender_name': STORES[lender]['name'],
            'borrower': borrower, 'borrower_name': STORES[borrower]['name'],
            'lent': lent, 'returned': returned, 'balance': lent - returned,
            'items': [r.to_dict() for r in rows],
        }

    others = [code for code in STORES if code != current]
    return jsonify({
        'success': True,
        'lent': [balance_of(current, o) for o in others],
        'owed': [balance_of(o, current) for o in others],
    }), 200
