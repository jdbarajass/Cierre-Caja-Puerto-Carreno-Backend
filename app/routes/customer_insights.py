"""
Dashboard de clientes (solo admin, por tienda vía X-Store). Ver
app/services/customer_insights.py.
"""
import logging
from datetime import date, datetime

import requests
from flask import Blueprint, jsonify, request

from app.exceptions import ConfigurationError
from app.middlewares.auth import token_required, role_required
from app.services.customer_insights import CustomerInsightsService, INACTIVE_LOOKBACK_DAYS
from app.stores import get_alegra_direct_client, get_current_store
from app.utils.timezone import get_colombia_now, get_colombia_timestamp

logger = logging.getLogger(__name__)

bp = Blueprint('customer_insights', __name__)

# Alegra suma el rango en el servidor: se permiten rangos largos.
MAX_RANGE_DAYS = 3 * 366
INACTIVE_DAYS_OPTIONS = (30, 60, 90, 120, 180)


def _error(message, status, code=None):
    body = {'success': False, 'message': message, 'error': message}
    if code:
        body['code'] = code
    return jsonify(body), status


def _parse_range(today: date):
    """(start, end) del query string; por defecto, el año en curso hasta hoy (Colombia)."""
    start_str = request.args.get('start_date')
    end_str = request.args.get('end_date')
    start = datetime.strptime(start_str, '%Y-%m-%d').date() if start_str else today.replace(month=1, day=1)
    end = datetime.strptime(end_str, '%Y-%m-%d').date() if end_str else today
    end = min(end, today)  # las fechas futuras no tienen ventas
    if start > end:
        raise ValueError('La fecha inicial no puede ser posterior a la final')
    if (end - start).days + 1 > MAX_RANGE_DAYS:
        raise ValueError('El rango máximo es de 3 años')
    return start, end


def _service(today):
    """(servicio, None) o (None, respuesta de error) si la tienda no tiene Alegra configurado."""
    try:
        return CustomerInsightsService(get_alegra_direct_client(), get_current_store(), today), None
    except ConfigurationError as e:
        return None, _error(e.message, 503, 'alegra_not_configured')


def _alegra_failure(e, what):
    if isinstance(e, requests.exceptions.HTTPError) and e.response is not None and e.response.status_code in (401, 403):
        return _error('Alegra rechazó las credenciales de esta tienda', 502, 'alegra_auth')
    if isinstance(e, requests.exceptions.Timeout):
        return _error('Alegra tardó demasiado en responder. Intenta de nuevo en un momento.', 504, 'alegra_timeout')
    if isinstance(e, requests.exceptions.RequestException):
        return _error('No se pudo consultar Alegra', 502, 'alegra_error')
    logger.exception(f'Error inesperado en {what}')
    return _error('Error interno del servidor', 500)


@bp.route('/api/analytics/customers/summary', methods=['GET', 'OPTIONS'])
@token_required
@role_required('admin')
def customers_summary():
    """
    Dashboard de clientes de la tienda activa: % de venta con cliente
    identificado (total y por vendedora), mejores clientes por monto,
    frecuencia y descuento, compras del equipo y clientes nuevos vs
    recurrentes.
    ---
    tags:
      - Analytics
    parameters:
      - in: query
        name: start_date
        type: string
        required: false
        description: YYYY-MM-DD (por defecto, 1 de enero del año en curso)
      - in: query
        name: end_date
        type: string
        required: false
        description: YYYY-MM-DD (por defecto, hoy)
      - in: query
        name: limit
        type: integer
        required: false
        description: Clientes por ranking (5-100, por defecto 25)
    responses:
      200:
        description: Indicadores de clientes
      400:
        description: Rango de fechas inválido
      503:
        description: La tienda todavía no tiene cuenta de Alegra configurada
    """
    if request.method == 'OPTIONS':
        return '', 204

    today = get_colombia_now().date()
    try:
        start, end = _parse_range(today)
        limit = min(100, max(5, int(request.args.get('limit', 25))))
    except ValueError as e:
        return _error(str(e), 400)

    service, error = _service(today)
    if error:
        return error
    try:
        data = service.summary(start, end, limit)
    except Exception as e:
        return _alegra_failure(e, 'dashboard de clientes')

    return jsonify({
        'success': True,
        'store': get_current_store(),
        'date_range': {'start': start.isoformat(), 'end': end.isoformat()},
        'server_timestamp': get_colombia_timestamp(),
        'data': data,
    }), 200


@bp.route('/api/analytics/customers/inactive', methods=['GET', 'OPTIONS'])
@token_required
@role_required('admin')
def customers_inactive():
    """
    Clientas que compraron en el último año pero no en los últimos `days`
    días, de mayor a menor compra. Las primeras 50 traen teléfono, número
    de WhatsApp y fecha de la última compra.
    ---
    tags:
      - Analytics
    parameters:
      - in: query
        name: days
        type: integer
        required: false
        description: Días sin comprar (30, 60, 90, 120 o 180; por defecto 90)
    responses:
      200:
        description: Clientas inactivas
      400:
        description: Parámetro inválido
      503:
        description: La tienda todavía no tiene cuenta de Alegra configurada
    """
    if request.method == 'OPTIONS':
        return '', 204

    try:
        days = int(request.args.get('days', 90))
    except ValueError:
        days = 0
    if days not in INACTIVE_DAYS_OPTIONS:
        return _error(f'days debe ser uno de {", ".join(map(str, INACTIVE_DAYS_OPTIONS))}', 400)

    today = get_colombia_now().date()
    service, error = _service(today)
    if error:
        return error
    try:
        data = service.inactive(days, INACTIVE_LOOKBACK_DAYS)
    except Exception as e:
        return _alegra_failure(e, 'clientas inactivas')

    return jsonify({
        'success': True,
        'store': get_current_store(),
        'server_timestamp': get_colombia_timestamp(),
        'data': data,
    }), 200
