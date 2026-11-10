"""
Corrección de cierres por el admin (Cuentas → Corrección de cierres, 2026-11-09).
Reglas en app/services/closing_corrections.py.

- GET  /api/closing-corrections            cierres no exitosos sin corregir + los corregidos (90 días)
- POST /api/closing-corrections/<AAAA-MM-DD> corrige ese cierre y lo pasa a Cuentas
Solo el admin (el administrador de solo lectura no la ve ni la usa).
"""
from datetime import datetime

from flask import Blueprint, jsonify, request

from app.middlewares.auth import get_current_user, token_required
from app.stores import get_current_store
from app.utils.timezone import get_colombia_now

bp = Blueprint('closing_corrections', __name__)


def _require_admin():
    user = get_current_user()
    # El de solo lectura entra como admin con read_only=True: esta sección no es para él
    if user.get('role') != 'admin' or user.get('read_only'):
        return jsonify({'success': False, 'message': 'Solo el administrador puede corregir cierres'}), 403
    return None


@bp.route('/api/closing-corrections', methods=['GET', 'OPTIONS'])
@token_required
def list_corrections():
    if request.method == 'OPTIONS':
        return '', 204
    err = _require_admin()
    if err:
        return err
    from app.services.closing_corrections import list_closings
    return jsonify({'success': True, **list_closings(get_current_store(), get_colombia_now().date())}), 200


@bp.route('/api/closing-corrections/<day>', methods=['POST', 'OPTIONS'])
@token_required
def correct_closing(day):
    if request.method == 'OPTIONS':
        return '', 204
    err = _require_admin()
    if err:
        return err
    try:
        closing_day = datetime.strptime(day, '%Y-%m-%d').date()
    except ValueError:
        return jsonify({'success': False, 'message': 'La fecha debe ser AAAA-MM-DD'}), 400
    from app.services.closing_corrections import CorrectionError, correct
    try:
        result = correct(get_current_store(), closing_day, request.get_json(silent=True) or {},
                         get_current_user(), get_colombia_now().date())
    except CorrectionError as e:
        return jsonify({'success': False, 'message': str(e)}), 400
    return jsonify({'success': True, **result}), 200
