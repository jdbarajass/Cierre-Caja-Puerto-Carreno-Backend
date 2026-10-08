"""
Recordatorios del administrador (app/services/reminders.py): la ventana
emergente al entrar a la plataforma. Solo admin, por tienda (X-Store).
"""
import logging

from flask import Blueprint, request, jsonify

from app.middlewares.auth import token_required, get_current_user
from app.services import reminders as svc
from app.stores import get_current_store
from app.utils.timezone import get_colombia_now

logger = logging.getLogger(__name__)
bp = Blueprint('reminders', __name__)


def _require_admin():
    if get_current_user().get('role') != 'admin':
        return jsonify({'success': False, 'message': 'Solo el administrador puede acceder'}), 403
    return None


def _find(store, key):
    return next((r for r in svc.active(store, get_colombia_now().date()) if r['key'] == key), None)


@bp.route('/api/reminders', methods=['GET', 'OPTIONS'])
@token_required
def list_reminders():
    if request.method == 'OPTIONS':
        return '', 204
    err = _require_admin()
    if err:
        return err
    store = get_current_store()
    try:
        return jsonify({'success': True, 'reminders': svc.active(store, get_colombia_now().date())}), 200
    except Exception as e:
        logger.error(f'[{store}] Recordatorios: {e}', exc_info=True)
        return jsonify({'success': True, 'reminders': []}), 200   # un recordatorio nunca debe romper la página


@bp.route('/api/reminders/<key>/snooze', methods=['POST', 'OPTIONS'])
@token_required
def snooze(key):
    if request.method == 'OPTIONS':
        return '', 204
    err = _require_admin()
    if err:
        return err
    store = get_current_store()
    if _find(store, key) is None:
        return jsonify({'success': False, 'message': 'Ese recordatorio no está activo'}), 404
    data = request.get_json(silent=True) or {}
    try:
        days = max(1, min(30, int(data.get('days') or 1)))
    except (TypeError, ValueError):
        days = 1
    svc.snooze(store, key, days, get_colombia_now().date())
    return jsonify({'success': True}), 200


@bp.route('/api/reminders/<key>/done', methods=['POST', 'OPTIONS'])
@token_required
def done(key):
    if request.method == 'OPTIONS':
        return '', 204
    err = _require_admin()
    if err:
        return err
    store = get_current_store()
    r = _find(store, key)
    if r is None:
        return jsonify({'success': False, 'message': 'Ese recordatorio no está activo'}), 404
    if not r.get('done_label'):
        return jsonify({'success': False, 'message': 'Este recordatorio se quita solo cuando se hace la tarea'}), 400
    svc.mark_done(store, key, get_current_user().get('userId'))
    return jsonify({'success': True}), 200
