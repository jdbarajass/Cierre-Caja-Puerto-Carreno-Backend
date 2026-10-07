"""
Cuentas → Mes (Fase 2 de docs/PLAN_CUENTAS_DIARIAS.md): hoja del mes por
medio de pago, conciliación con el saldo real, comisiones del datáfono/Addi
y cerrar / reabrir el mes. Solo admin (la carga de pagos también la puede
llamar el cron con X-Sync-Token). Todo por tienda (header X-Store).
"""
import logging
from datetime import datetime

from flask import Blueprint, request, jsonify

from app.exceptions import ConfigurationError
from app.middlewares.auth import token_required, get_current_user
from app.models.user import db
from app.models.account import Account
from app.models.expense import Expense
from app.models.month_sheet import AccountReconciliation, MonthClose, SaleMethodCorrection
from app.routes.accounts import sync_token_or_admin_required
from app.routes.expenses import _sync_expense_account_movements, ExpenseError, PERIOD_RE
from app.services import month_sheet as svc
from app.services.payment_facts import PAYMENTS_START, SALE_MEDIOS, default_since, sync_payments
from app.stores import get_alegra_client, get_current_store
from app.utils.timezone import get_colombia_now

logger = logging.getLogger(__name__)
bp = Blueprint('month_sheet', __name__)


def _require_admin():
    if get_current_user().get('role') != 'admin':
        return jsonify({'success': False, 'message': 'Solo el administrador puede acceder'}), 403
    return None


def _year_month(source):
    try:
        year = int(source.get('year'))
        month = int(source.get('month'))
    except (TypeError, ValueError):
        raise ExpenseError('year y month son obligatorios')
    if not 1 <= month <= 12 or not 2020 <= year <= 2100:
        raise ExpenseError('Mes inválido')
    return year, month


@bp.route('/api/month-sheet', methods=['GET', 'OPTIONS'])
@token_required
def get_sheet():
    if request.method == 'OPTIONS':
        return '', 204
    err = _require_admin()
    if err:
        return err
    try:
        year, month = _year_month(request.args)
        sheet = svc.build_sheet(get_current_store(), year, month, get_colombia_now().date())
        return jsonify({'success': True, **sheet}), 200
    except ExpenseError as e:
        return jsonify({'success': False, 'message': str(e)}), 400
    except Exception as e:
        logger.error(f'Error armando la hoja del mes: {e}', exc_info=True)
        return jsonify({'success': False, 'message': 'Error al armar la hoja del mes'}), 500


def run_payments_sync(store, since=None):
    """Carga los recibos de Alegra de la tienda. Lo usa también la carga de facturas del cron."""
    client = get_alegra_client(store)
    today = get_colombia_now().date()
    return sync_payments(client, store, since or default_since(store, today))


@bp.route('/api/month-sheet/sync-payments', methods=['POST', 'OPTIONS'])
@sync_token_or_admin_required
def sync_payments_route():
    """Trae de Alegra las ventas por medio de pago (body opcional: {"since": "AAAA-MM-DD"})."""
    if request.method == 'OPTIONS':
        return '', 204
    data = request.get_json(silent=True) or {}
    since = None
    if data.get('since'):
        try:
            since = max(PAYMENTS_START, datetime.strptime(data['since'], '%Y-%m-%d').date())
        except ValueError:
            return jsonify({'success': False, 'message': 'since debe ser AAAA-MM-DD'}), 400
    store = get_current_store()
    try:
        result = run_payments_sync(store, since)
        return jsonify({'success': True, 'store': store, **result}), 200
    except ConfigurationError as e:
        return jsonify({'success': False, 'message': e.message, 'code': 'alegra_not_configured'}), 503
    except Exception as e:
        db.session.rollback()
        logger.error(f'[{store}] Error cargando pagos de Alegra: {e}', exc_info=True)
        return jsonify({'success': False, 'message': 'No se pudieron traer los pagos de Alegra. Intenta de nuevo.'}), 502


def _closed_period(store, day):
    return MonthClose.for_store(store).filter_by(period=day.strftime('%Y-%m')).first() is not None


@bp.route('/api/month-sheet/corrections', methods=['POST', 'OPTIONS'])
@token_required
def create_correction():
    """
    Corrige a mano el medio de pago de un día: mueve `amount` de `from_medio`
    a `to_medio` (ej. se pasó por datáfono pero pagó en efectivo). No cambia
    el total del día ni toca Alegra.
    """
    if request.method == 'OPTIONS':
        return '', 204
    err = _require_admin()
    if err:
        return err
    data = request.get_json(silent=True) or {}
    try:
        day = datetime.strptime(str(data.get('date') or ''), '%Y-%m-%d').date()
    except ValueError:
        return jsonify({'success': False, 'message': 'date debe ser AAAA-MM-DD'}), 400
    from_medio, to_medio = data.get('from_medio'), data.get('to_medio')
    if from_medio not in SALE_MEDIOS or to_medio not in SALE_MEDIOS:
        return jsonify({'success': False, 'message': 'Medio de pago inválido'}), 400
    if from_medio == to_medio:
        return jsonify({'success': False, 'message': 'El medio de origen y el de destino deben ser distintos'}), 400
    try:
        amount = int(round(float(data.get('amount') or 0)))
    except (TypeError, ValueError):
        amount = 0
    if amount <= 0:
        return jsonify({'success': False, 'message': 'El valor debe ser mayor que cero'}), 400
    if day < PAYMENTS_START or day > get_colombia_now().date():
        return jsonify({'success': False, 'message': 'Fecha fuera del rango de la hoja del mes'}), 400
    store = get_current_store()
    if _closed_period(store, day):
        return jsonify({'success': False, 'message': 'El mes está cerrado: reábrelo para corregir'}), 400
    available = svc.day_by_medio(store, day).get(from_medio, 0)
    if amount > available:
        return jsonify({'success': False,
                        'message': f'Ese día solo hay ${int(available):,} en {from_medio}'.replace(',', '.')}), 400
    c = SaleMethodCorrection(store_code=store, date=day, from_medio=from_medio, to_medio=to_medio,
                             amount=amount, note=(data.get('note') or '').strip() or None,
                             created_by=get_current_user().get('userId'))
    db.session.add(c)
    db.session.commit()
    return jsonify({'success': True, 'correction': c.to_dict()}), 201


@bp.route('/api/month-sheet/corrections/<int:correction_id>', methods=['DELETE', 'OPTIONS'])
@token_required
def delete_correction(correction_id):
    if request.method == 'OPTIONS':
        return '', 204
    err = _require_admin()
    if err:
        return err
    c = SaleMethodCorrection.get_for_current_store_or_404(correction_id)
    if _closed_period(c.store_code, c.date):
        return jsonify({'success': False, 'message': 'El mes está cerrado: reábrelo para corregir'}), 400
    # Si otra corrección del día usó el valor que esta movió, borrarla dejaría un medio en negativo
    after = svc.day_by_medio(c.store_code, c.date)
    after[c.to_medio] -= c.amount
    after[c.from_medio] += c.amount
    if after[c.to_medio] < 0:
        return jsonify({'success': False,
                        'message': 'Otra corrección de ese día usa este valor: bórrala primero'}), 400
    db.session.delete(c)
    db.session.commit()
    return jsonify({'success': True}), 200


@bp.route('/api/month-sheet/reconciliation', methods=['PUT', 'OPTIONS'])
@token_required
def save_reconciliation():
    """Guarda (o borra con real_balance=null) el saldo real de una cuenta en un mes."""
    if request.method == 'OPTIONS':
        return '', 204
    err = _require_admin()
    if err:
        return err
    data = request.get_json() or {}
    period = data.get('period') or ''
    if not PERIOD_RE.match(period):
        return jsonify({'success': False, 'message': 'period debe ser AAAA-MM'}), 400
    account = Account.get_for_current_store_or_404(int(data.get('account_id') or 0))
    rec = AccountReconciliation.for_current_store().filter_by(account_id=account.id, period=period).first()
    if data.get('real_balance') in (None, ''):
        if rec:
            db.session.delete(rec)
            db.session.commit()
        return jsonify({'success': True, 'deleted': True}), 200
    try:
        real = float(data['real_balance'])
    except (TypeError, ValueError):
        return jsonify({'success': False, 'message': 'Saldo real inválido'}), 400
    if rec is None:
        rec = AccountReconciliation(account_id=account.id, period=period)
        db.session.add(rec)
    rec.real_balance = real
    rec.note = (data.get('note') or '').strip() or None
    rec.updated_by = get_current_user().get('userId')
    db.session.commit()
    return jsonify({'success': True}), 200


@bp.route('/api/month-sheet/commissions', methods=['POST', 'OPTIONS'])
@token_required
def register_commissions():
    """
    Registra (o actualiza) como gasto financiero las comisiones estimadas del
    mes (datáfono 3,8 % y Addi 7,735 %), descontándolas de ADDI + DATÁFONO.
    Un solo gasto por mes (marcado en notes); si la comisión queda en 0 se borra.
    """
    if request.method == 'OPTIONS':
        return '', 204
    err = _require_admin()
    if err:
        return err
    try:
        year, month = _year_month(request.get_json() or {})
        store = get_current_store()
        start, end = svc.month_bounds(year, month)
        period = f'{year}-{month:02d}'
        comm = svc.commissions(store, start, end, period)
        marker = svc.COMMISSION_MARKER.format(period=period)
        expense = Expense.for_store(store).filter_by(notes=marker).first()
        if comm['total'] <= 0:
            if expense:
                _sync_expense_account_movements(expense, is_delete=True)
                db.session.delete(expense)
                db.session.commit()
            return jsonify({'success': True, 'total': 0}), 200
        if expense is None:
            expense = Expense(created_by=get_current_user().get('userId'), notes=marker)
            db.session.add(expense)
        expense.date = min(get_colombia_now().date(), end)
        expense.period = period
        expense.concept = svc.COMMISSION_CONCEPT.format(label=svc.period_label(year, month))
        expense.category = 'financiero'
        expense.direction = 'out'
        expense.account_mode = 'cuentas'
        expense.apply_fee = False
        expense.fee_override = None
        for m in ('efectivo', 'qr', 'daviplata', 'nequi', 'bbva', 'ahorro'):
            setattr(expense, m, 0)
        expense.datafono = comm['total']
        db.session.flush()
        _sync_expense_account_movements(expense)
        db.session.commit()
        return jsonify({'success': True, 'total': comm['total'], 'expense_id': expense.id}), 200
    except ExpenseError as e:
        db.session.rollback()
        return jsonify({'success': False, 'message': str(e)}), 400


@bp.route('/api/month-sheet/close', methods=['POST', 'DELETE', 'OPTIONS'])
@token_required
def close_month():
    """POST: cierra el mes (guarda la foto). DELETE ?year&month: lo reabre."""
    if request.method == 'OPTIONS':
        return '', 204
    err = _require_admin()
    if err:
        return err
    store = get_current_store()
    try:
        source = request.args if request.method == 'DELETE' else (request.get_json() or {})
        year, month = _year_month(source)
    except ExpenseError as e:
        return jsonify({'success': False, 'message': str(e)}), 400
    period = f'{year}-{month:02d}'
    existing = MonthClose.for_current_store().filter_by(period=period).first()

    if request.method == 'DELETE':
        if existing:
            db.session.delete(existing)
            db.session.commit()
        return jsonify({'success': True, 'reopened': True}), 200

    sheet = svc.build_sheet(store, year, month, get_colombia_now().date())
    if existing is None:
        existing = MonthClose(period=period)
        db.session.add(existing)
    existing.snapshot = svc.snapshot_of(sheet)
    existing.notes = ((source.get('notes') or '').strip() or None)
    existing.closed_by = get_current_user().get('userId')
    existing.closed_at = datetime.utcnow()
    db.session.commit()
    return jsonify({'success': True, 'period': period}), 200
