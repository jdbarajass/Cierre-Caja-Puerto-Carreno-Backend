"""
Préstamos de cada tienda (Radiografía Fase 0c): tarjetas de Cuentas → Resumen.
Ver app/models/loan.py y app/services/loans.py.

- GET  /api/loans                      tarjetas de la tienda (admin y viewer)
- POST /api/loans                      crear un préstamo (admin)
- PUT  /api/loans/<id>                 editar con recálculo y rastro (admin)
- POST /api/loans/<id>/payments        cuota descontada del préstamo o ajuste de saldo (admin)
- DELETE /api/loans/payments/<id>      borrar una de esas dos (admin); los pagos con plata
                                       se borran desde Cuentas → Gastos
"""
import logging

from flask import Blueprint, jsonify, request

from app.middlewares.auth import get_current_user, token_required
from app.models.loan import Loan, LoanPayment
from app.models.user import db
from app.services import loans as svc
from app.stores import get_current_store
from app.utils.timezone import get_colombia_now

logger = logging.getLogger(__name__)
bp = Blueprint('loans', __name__)


def _require_admin():
    if get_current_user().get('role') != 'admin':
        return jsonify({'success': False, 'message': 'Solo el administrador puede acceder'}), 403
    return None


def _today():
    return get_colombia_now().date()


def _groups():
    return svc.groups(get_current_store(), _today())


@bp.route('/api/loans', methods=['GET', 'OPTIONS'])
@token_required
def list_loans():
    if request.method == 'OPTIONS':
        return '', 204
    err = _require_admin()
    if err:
        return err
    return jsonify({'success': True, 'groups': _groups()}), 200


@bp.route('/api/loans', methods=['POST'])
@token_required
def create_loan():
    err = _require_admin()
    if err:
        return err
    try:
        loan = Loan()
        svc.apply_changes(loan, request.get_json() or {}, get_current_user(), creating=True)
        db.session.add(loan)
        db.session.commit()
        return jsonify({'success': True, 'id': loan.id, 'groups': _groups()}), 201
    except svc.LoanError as e:
        db.session.rollback()
        return jsonify({'success': False, 'message': str(e)}), 400


@bp.route('/api/loans/<int:loan_id>', methods=['PUT', 'OPTIONS'])
@token_required
def update_loan(loan_id):
    if request.method == 'OPTIONS':
        return '', 204
    err = _require_admin()
    if err:
        return err
    loan = Loan.get_for_current_store_or_404(loan_id)
    try:
        svc.apply_changes(loan, request.get_json() or {}, get_current_user())
        db.session.commit()
        return jsonify({'success': True, 'groups': _groups()}), 200
    except svc.LoanError as e:
        db.session.rollback()
        return jsonify({'success': False, 'message': str(e)}), 400


@bp.route('/api/loans/<int:loan_id>/payments', methods=['POST', 'OPTIONS'])
@token_required
def add_payment(loan_id):
    if request.method == 'OPTIONS':
        return '', 204
    err = _require_admin()
    if err:
        return err
    loan = Loan.get_for_current_store_or_404(loan_id)
    try:
        svc.add_manual_payment(loan, request.get_json() or {}, get_current_user(), _today())
        db.session.commit()
        return jsonify({'success': True, 'groups': _groups()}), 201
    except svc.LoanError as e:
        db.session.rollback()
        return jsonify({'success': False, 'message': str(e)}), 400


@bp.route('/api/loans/payments/<int:payment_id>', methods=['DELETE', 'OPTIONS'])
@token_required
def delete_payment(payment_id):
    if request.method == 'OPTIONS':
        return '', 204
    err = _require_admin()
    if err:
        return err
    p = LoanPayment.get_for_current_store_or_404(payment_id)
    if p.expense_id:
        return jsonify({'success': False, 'message': 'Este pago salió de las cuentas: bórralo desde Cuentas → Gastos'}), 400
    db.session.delete(p)
    db.session.commit()
    return jsonify({'success': True, 'groups': _groups()}), 200
