"""
Radiografía financiera (docs/PLAN_RADIOGRAFIA.md). Solo lee: admin y viewer.

- GET /api/radiografia/month?year=&month=&target=   Fase 1 (Mes)
- GET /api/radiografia/year?year=                    Fase 2 (Año)
- GET /api/radiografia/inventory?quiet=60|90|180       Fase 3 (Inventario)
- GET /api/radiografia/cash-flow?year=&month=          Fase 4 (Flujo de caja)
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


@bp.route('/api/radiografia/year', methods=['GET', 'OPTIONS'])
@token_required
def year():
    if request.method == 'OPTIONS':
        return '', 204
    err = _require_admin()
    if err:
        return err
    today = get_colombia_now().date()
    try:
        year_n = int(request.args.get('year') or today.year)
    except ValueError:
        return jsonify({'success': False, 'message': 'Parámetros inválidos'}), 400
    if year_n < 2026 or year_n > today.year:
        return jsonify({'success': False, 'message': 'La Radiografía es desde 2026 y hasta el año en curso'}), 400
    from app.services.radiografia_year import build_year
    return jsonify({'success': True, 'year': build_year(get_current_store(), year_n, today)}), 200


@bp.route('/api/radiografia/inventory', methods=['GET', 'OPTIONS'])
@token_required
def inventory():
    """Fase 3: necesita el stock de Alegra (la primera vez ~1 min; luego caché por tienda)."""
    if request.method == 'OPTIONS':
        return '', 204
    err = _require_admin()
    if err:
        return err
    from app.exceptions import CierreCajaException, ConfigurationError
    from app.services.radiografia_inventory import QUIET_OPTIONS, build_inventory
    from app.stores import get_alegra_client
    try:
        quiet = int(request.args.get('quiet') or 90)
    except ValueError:
        quiet = 0
    if quiet not in QUIET_OPTIONS:
        return jsonify({'success': False, 'message': 'quiet debe ser 60, 90 o 180'}), 400
    store = get_current_store()
    try:
        items = get_alegra_client().get_active_items()
    except ConfigurationError as e:
        return jsonify({'success': False, 'message': e.message, 'code': 'alegra_not_configured'}), 503
    except CierreCajaException as e:
        logger.error(f'[{store}] Radiografía inventario: {e}')
        return jsonify({'success': False, 'message': e.message, 'code': 'alegra_error'}), 502
    data = build_inventory(store, get_colombia_now().date(), items, quiet)
    return jsonify({'success': True, 'inventory': data}), 200


@bp.route('/api/radiografia/cash-flow', methods=['GET', 'OPTIONS'])
@token_required
def cash_flow():
    """Fase 4: la plata del mes por cuenta y, hoy, lo que le deben, lo que debe y cuánto se puede retirar."""
    if request.method == 'OPTIONS':
        return '', 204
    err = _require_admin()
    if err:
        return err
    today = get_colombia_now().date()
    try:
        year_n = int(request.args.get('year') or today.year)
        month_n = int(request.args.get('month') or today.month)
    except ValueError:
        return jsonify({'success': False, 'message': 'Parámetros inválidos'}), 400
    if not 1 <= month_n <= 12 or year_n < 2026:
        return jsonify({'success': False, 'message': 'La Radiografía es desde enero de 2026'}), 400
    from app.services.radiografia_cashflow import build_cash_flow
    data = build_cash_flow(get_current_store(), year_n, month_n, today)
    return jsonify({'success': True, 'cash_flow': data}), 200
