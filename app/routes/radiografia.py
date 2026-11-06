"""
Radiografía financiera (docs/PLAN_RADIOGRAFIA.md). Solo lee: admin y viewer.

- GET /api/radiografia/month?year=&month=&target=   Fase 1 (Mes)
"""
import logging

from flask import Blueprint, jsonify, request

from app.middlewares.auth import get_current_user, token_required
from app.stores import get_current_store
from app.utils.timezone import get_colombia_now

logger = logging.getLogger(__name__)
bp = Blueprint('radiografia', __name__)


def _require_admin():
    if get_current_user().get('role') != 'admin':
        return jsonify({'success': False, 'message': 'Solo el administrador puede acceder'}), 403
    return None


@bp.route('/api/radiografia/month', methods=['GET', 'OPTIONS'])
@token_required
def month():
    if request.method == 'OPTIONS':
        return '', 204
    err = _require_admin()
    if err:
        return err
    today = get_colombia_now().date()
    try:
        year = int(request.args.get('year') or today.year)
        month_n = int(request.args.get('month') or today.month)
        target = request.args.get('target')
        target = float(target) if target not in (None, '') else None
    except ValueError:
        return jsonify({'success': False, 'message': 'Parámetros inválidos'}), 400
    if not 1 <= month_n <= 12 or year < 2026:
        return jsonify({'success': False, 'message': 'La Radiografía es desde enero de 2026'}), 400
    if target is not None and target < 0:
        return jsonify({'success': False, 'message': 'La utilidad deseada no puede ser negativa'}), 400
    from app.services.radiografia_month import build_month
    data = build_month(get_current_store(), year, month_n, today, target)
    return jsonify({'success': True, 'month': data}), 200
