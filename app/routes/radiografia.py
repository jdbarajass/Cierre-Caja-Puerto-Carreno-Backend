"""
Radiografía financiera (docs/PLAN_RADIOGRAFIA.md). Solo lee: admin y viewer.

- GET /api/radiografia/month?year=&month=&target=   Fase 1 (Mes)
- GET /api/radiografia/year?year=                    Fase 2 (Año)
- GET /api/radiografia/inventory?quiet=60|90|180       Fase 3 (Inventario)
- GET /api/radiografia/cash-flow?year=&month=          Fase 4 (Flujo de caja)
- GET /api/radiografia/compare?year=&month=            Fase 5 (Comparativo y consolidado)

Fase 6: cualquiera de ellas con &format=xlsx o &format=pdf devuelve el archivo con
las mismas cifras (app/services/radiografia_export.py).
"""
import logging

from flask import Blueprint, Response, jsonify, request

from app.middlewares.auth import get_current_user, token_required
from app.stores import get_current_store
from app.utils.timezone import get_colombia_now

logger = logging.getLogger(__name__)
bp = Blueprint('radiografia', __name__)


def _export_format():
    """None (JSON), 'xlsx' o 'pdf'; ValueError si piden otro."""
    fmt = (request.args.get('format') or '').lower() or None
    if fmt not in (None, 'xlsx', 'pdf'):
        raise ValueError
    return fmt


def _file(report, fmt, view, store, period):
    from app.services import radiografia_export as ex
    try:
        content = ex.render(report, fmt)
    except Exception as e:
        logger.error(f'Radiografía, exportar {view} {store} {period} ({fmt}): {e}', exc_info=True)
        return jsonify({'success': False, 'message': 'No se pudo generar el archivo'}), 500
    name = ex.filename(view, store, period, fmt)
    return Response(content, mimetype=ex.MIMES[fmt], headers={'Content-Disposition': f'attachment; filename={name}'})


def _bad_format():
    return jsonify({'success': False, 'message': 'format debe ser xlsx o pdf'}), 400


def _store_name(code):
    from app.stores import STORES
    return STORES[code]['name']


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
    try:
        fmt = _export_format()
    except ValueError:
        return _bad_format()
    from app.services.radiografia_month import build_month
    store = get_current_store()
    data = build_month(store, year, month_n, today, target)
    if fmt:
        from app.services.radiografia_export import month_report
        return _file(month_report(data, _store_name(store)), fmt, 'mes', store, f'{year}-{month_n:02d}')
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
    try:
        fmt = _export_format()
    except ValueError:
        return _bad_format()
    from app.services.radiografia_year import build_year
    store = get_current_store()
    data = build_year(store, year_n, today)
    if fmt:
        from app.services.radiografia_export import year_report
        return _file(year_report(data, _store_name(store)), fmt, 'anio', store, str(year_n))
    return jsonify({'success': True, 'year': data}), 200


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
    try:
        fmt = _export_format()
    except ValueError:
        return _bad_format()
    store = get_current_store()
    try:
        items = get_alegra_client().get_active_items()
    except ConfigurationError as e:
        return jsonify({'success': False, 'message': e.message, 'code': 'alegra_not_configured'}), 503
    except CierreCajaException as e:
        logger.error(f'[{store}] Radiografía inventario: {e}')
        return jsonify({'success': False, 'message': e.message, 'code': 'alegra_error'}), 502
    today = get_colombia_now().date()
    data = build_inventory(store, today, items, quiet)
    if fmt:
        from app.services.radiografia_export import inventory_report
        return _file(inventory_report(data, _store_name(store)), fmt, 'inventario', store, today.isoformat())
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
    try:
        fmt = _export_format()
    except ValueError:
        return _bad_format()
    from app.services.radiografia_cashflow import build_cash_flow
    store = get_current_store()
    data = build_cash_flow(store, year_n, month_n, today)
    if fmt:
        from app.services.radiografia_export import cash_flow_report
        return _file(cash_flow_report(data, _store_name(store)), fmt, 'flujo', store, f'{year_n}-{month_n:02d}')
    return jsonify({'success': True, 'cash_flow': data}), 200


@bp.route('/api/radiografia/compare', methods=['GET', 'OPTIONS'])
@token_required
def compare():
    """Fase 5: las tiendas lado a lado y "Las dos" sumadas (solo quien ve las dos tiendas)."""
    if request.method == 'OPTIONS':
        return '', 204
    err = _require_admin()
    if err:
        return err
    from app.stores import STORES, stores_for_user
    stores = [s for s in STORES if s in stores_for_user(get_current_user())]
    if len(stores) < 2:
        return jsonify({'success': False, 'message': 'El comparativo necesita acceso a las dos tiendas'}), 403
    today = get_colombia_now().date()
    try:
        year_n = int(request.args.get('year') or today.year)
        month_n = int(request.args.get('month') or today.month)
    except ValueError:
        return jsonify({'success': False, 'message': 'Parámetros inválidos'}), 400
    if not 1 <= month_n <= 12 or year_n < 2026:
        return jsonify({'success': False, 'message': 'La Radiografía es desde enero de 2026'}), 400
    try:
        fmt = _export_format()
    except ValueError:
        return _bad_format()
    from app.services.radiografia_compare import build_compare
    data = build_compare(year_n, month_n, today, stores)
    if fmt:
        from app.services.radiografia_export import compare_report
        return _file(compare_report(data), fmt, 'comparativo', None, f'{year_n}-{month_n:02d}')
    return jsonify({'success': True, 'compare': data}), 200
