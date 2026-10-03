"""
Estadísticas → Día y hora (solo admin, por tienda vía X-Store). Ver
app/services/sales_patterns.py.

- GET /api/analytics/sales-patterns: venta promedio por día de la semana,
  por hora y mapa de calor día × hora (opcional `seller_id`). Lee las
  facturas guardadas (rápido).
"""
import logging
from datetime import date, datetime, timedelta

from flask import Blueprint, jsonify, request

from app.exceptions import CierreCajaException, ConfigurationError
from app.middlewares.auth import role_required, token_required
from app.services.sales_patterns import SalesPatternsService
from app.stores import get_alegra_client, get_current_store
from app.utils.timezone import get_colombia_now, get_colombia_timestamp

logger = logging.getLogger(__name__)

bp = Blueprint('sales_patterns', __name__)

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


@bp.route('/api/analytics/sales-patterns', methods=['GET', 'OPTIONS'])
@token_required
@role_required('admin')
def sales_patterns():
    """
    Ventas por día de la semana y hora (promedio por día) de la tienda activa.
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
        description: YYYY-MM-DD (por defecto, hoy; hoy solo cuenta si el periodo es únicamente hoy)
      - in: query
        name: seller_id
        type: string
        required: false
        description: Solo las ventas de esta vendedora
    responses:
      200:
        description: Promedios por día de la semana, por hora y mapa de calor (coverage dice si faltan días con hora)
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
        client = get_alegra_client()
    except ConfigurationError:
        client = None  # sin cuenta de Alegra: solo lo guardado
    try:
        data = SalesPatternsService(get_current_store(), today, client).summary(
            start, end, request.args.get('seller_id') or None)
    except CierreCajaException as e:
        logger.error(f'[{get_current_store()}] día y hora: {e}')
        return _error(e.message, 502, 'alegra_error')
    except Exception:
        logger.exception('Error inesperado en ventas por día y hora')
        return _error('Error interno del servidor', 500)
    return jsonify({'success': True, 'store': get_current_store(),
                    'server_timestamp': get_colombia_timestamp(), 'data': data}), 200
