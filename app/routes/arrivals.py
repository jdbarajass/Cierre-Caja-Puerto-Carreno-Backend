"""
Estadísticas → Llegadas (solo admin, por tienda vía X-Store). Ver
app/services/purchase_facts.py.

- GET  /api/analytics/arrivals: llegadas de mercancía del periodo con lo que
  se vendió de cada una (por defecto, últimos 90 días).
- POST /api/analytics/arrivals/sync: vuelve a cargar las compras desde el
  1-ene-2026 (también se cargan solas con la carga de facturas de las 9 pm).
"""
import logging
from datetime import date, datetime, timedelta

from flask import Blueprint, jsonify, request

from app.exceptions import ConfigurationError
from app.middlewares.auth import role_required, token_required
from app.services.purchase_facts import ArrivalsService, purchases_status, sync_purchases
from app.stores import get_alegra_direct_client, get_current_store
from app.utils.timezone import get_colombia_now, get_colombia_timestamp

logger = logging.getLogger(__name__)

bp = Blueprint('arrivals', __name__)

PURCHASES_START = date(2026, 1, 1)  # igual que las facturas guardadas
DEFAULT_DAYS = 90
MAX_RANGE_DAYS = 366


def _error(message, status, code=None):
    body = {'success': False, 'message': message, 'error': message}
    if code:
        body['code'] = code
    return jsonify(body), status


def _parse_range(today: date):
    start_str = request.args.get('start_date')
    end_str = request.args.get('end_date')
    start = datetime.strptime(start_str, '%Y-%m-%d').date() if start_str else today - timedelta(days=DEFAULT_DAYS - 1)
    end = datetime.strptime(end_str, '%Y-%m-%d').date() if end_str else today
    end = min(end, today)
    if start > end:
        raise ValueError('La fecha inicial no puede ser posterior a la final')
    if (end - start).days + 1 > MAX_RANGE_DAYS:
        raise ValueError('El rango máximo es de 1 año')
    return start, end


@bp.route('/api/analytics/arrivals', methods=['GET', 'OPTIONS'])
@token_required
@role_required('admin')
def arrivals_summary():
    """
    Llegadas de mercancía del periodo y cuánto se vendió de cada una.
    ---
    tags:
      - Analytics
    parameters:
      - in: query
        name: start_date
        type: string
        required: false
        description: YYYY-MM-DD (por defecto, hace 90 días)
      - in: query
        name: end_date
        type: string
        required: false
        description: YYYY-MM-DD (por defecto, hoy)
    responses:
      200:
        description: Llegadas con prendas, vendidas y % vendido (coverage dice si faltan días de prendas)
      400:
        description: Rango de fechas inválido
    """
    if request.method == 'OPTIONS':
        return '', 204
    today = get_colombia_now().date()
    try:
        start, end = _parse_range(today)
    except ValueError as e:
        return _error(str(e), 400)
    try:
        data = ArrivalsService(get_current_store(), today).summary(start, end)
    except Exception:
        logger.exception('Error inesperado en llegadas de mercancía')
        return _error('Error interno del servidor', 500)
    return jsonify({'success': True, 'store': get_current_store(),
                    'server_timestamp': get_colombia_timestamp(), 'data': data}), 200


@bp.route('/api/analytics/arrivals/sync', methods=['POST', 'OPTIONS'])
@token_required
@role_required('admin')
def arrivals_sync():
    """
    Vuelve a cargar las compras de mercancía de la tienda desde el 1-ene-2026.
    ---
    tags:
      - Analytics
    responses:
      200:
        description: Compras cargadas
      502:
        description: Alegra no respondió (no se borró nada)
      503:
        description: La tienda no tiene cuenta de Alegra configurada
    """
    if request.method == 'OPTIONS':
        return '', 204
    store = get_current_store()
    try:
        client = get_alegra_direct_client()
    except ConfigurationError as e:
        return _error(e.message, 503, 'alegra_not_configured')
    try:
        result = sync_purchases(client, store, PURCHASES_START)
    except Exception as e:
        logger.error(f'[{store}] Carga de compras: {e}', exc_info=True)
        return _error('No se pudieron cargar las compras de Alegra. Intenta de nuevo en unos minutos.', 502, 'alegra_error')
    return jsonify({'success': True, 'store': store, 'result': result, 'status': purchases_status(store)}), 200
