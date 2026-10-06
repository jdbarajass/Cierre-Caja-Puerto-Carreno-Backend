"""
Cuentas → Año (Fase 3 de docs/PLAN_CUENTAS_DIARIAS.md): resumen mensual y
anual, valores escritos a mano e inventario al cierre de cada mes. Solo
admin (la carga del inventario también la hace el cron de las 9 pm dentro
de invoice-facts/sync). Todo por tienda (header X-Store).
"""
import logging

from flask import Blueprint, request, jsonify

from app.exceptions import ConfigurationError
from app.middlewares.auth import token_required, get_current_user
from app.models.user import db
from app.models.monthly_summary import MonthlySummaryOverride
from app.routes.expenses import PERIOD_RE
from app.services import monthly_summary as svc
from app.stores import get_alegra_direct_client, get_current_store
from app.utils.timezone import get_colombia_now

logger = logging.getLogger(__name__)
bp = Blueprint('monthly_summary', __name__)

MAX_INVENTORY_CALLS = 14


def _require_admin():
    if get_current_user().get('role') != 'admin':
        return jsonify({'success': False, 'message': 'Solo el administrador puede acceder'}), 403
    return None


@bp.route('/api/monthly-summary', methods=['GET', 'OPTIONS'])
@token_required
def get_summary():
    if request.method == 'OPTIONS':
        return '', 204
    err = _require_admin()
    if err:
        return err
    year = request.args.get('year', type=int)
    if not year or not 2020 <= year <= 2100:
        return jsonify({'success': False, 'message': 'year es obligatorio'}), 400
    try:
        data = svc.build_year(get_current_store(), year, get_colombia_now().date())
        return jsonify({'success': True, **data}), 200
    except Exception as e:
        logger.error(f'Error armando el resumen anual: {e}', exc_info=True)
        return jsonify({'success': False, 'message': 'Error al armar el resumen'}), 500


@bp.route('/api/monthly-summary/override', methods=['PUT', 'OPTIONS'])
@token_required
def save_override():
    """Escribe a mano un dato de un mes (value=null lo borra y vuelve al calculado)."""
    if request.method == 'OPTIONS':
        return '', 204
    err = _require_admin()
    if err:
        return err
    data = request.get_json() or {}
    period, field = data.get('period') or '', data.get('field') or ''
    if not PERIOD_RE.match(period):
        return jsonify({'success': False, 'message': 'period debe ser AAAA-MM'}), 400
    if field not in svc.OVERRIDE_FIELDS:
        return jsonify({'success': False, 'message': f'Dato no editable: {field}'}), 400
    item = MonthlySummaryOverride.for_current_store().filter_by(period=period, field=field).first()
    if data.get('value') in (None, ''):
        if item:
            db.session.delete(item)
            db.session.commit()
        return jsonify({'success': True, 'deleted': True}), 200
    try:
        value = float(data['value'])
    except (TypeError, ValueError):
        return jsonify({'success': False, 'message': 'Valor inválido'}), 400
    if item is None:
        item = MonthlySummaryOverride(period=period, field=field, value=value)
        db.session.add(item)
    item.value = value
    item.note = (data.get('note') or '').strip() or None
    item.updated_by = get_current_user().get('userId')
    db.session.commit()
    return jsonify({'success': True}), 200


def refresh_inventory(store, months=None):
    """
    Trae de Alegra el inventario de los meses dados (o de los que falten /
    estén desactualizados). Devuelve lo cargado y los errores, sin cortar en
    el primero. Lo usa también la carga del cron.
    """
    today = get_colombia_now().date()
    client = get_alegra_direct_client(store)
    pending = months if months is not None else svc.months_needing_inventory(store, today)
    loaded, errors = [], []
    for y, m in pending[:MAX_INVENTORY_CALLS]:
        try:
            snap = svc.fetch_inventory(client, store, y, m, today)
            loaded.append({'period': snap.period, 'value': snap.value, 'as_of': snap.as_of.isoformat()})
        except Exception as e:
            db.session.rollback()
            logger.warning(f'[{store}] Inventario {y}-{m:02d}: {e}')
            errors.append({'period': f'{y}-{m:02d}', 'error': str(e)})
    return {'loaded': loaded, 'errors': errors}


@bp.route('/api/monthly-summary/inventory', methods=['POST', 'OPTIONS'])
@token_required
def load_inventory():
    """
    Body {"year": 2026, "month": 7} trae ese mes; sin mes, trae los que
    falten desde agosto-2026 (el mes anterior al arranque, para la variación).
    """
    if request.method == 'OPTIONS':
        return '', 204
    err = _require_admin()
    if err:
        return err
    data = request.get_json(silent=True) or {}
    months = None
    if data.get('year') and data.get('month'):
        try:
            months = [(int(data['year']), int(data['month']))]
        except (TypeError, ValueError):
            return jsonify({'success': False, 'message': 'Mes inválido'}), 400
    store = get_current_store()
    try:
        result = refresh_inventory(store, months)
    except ConfigurationError as e:
        return jsonify({'success': False, 'message': e.message, 'code': 'alegra_not_configured'}), 503
    ok = not result['errors']
    return jsonify({'success': ok, **result,
                    'message': None if ok else 'Alegra no entregó el inventario de algunos meses'}), 200 if ok else 502
