"""
Estadísticas → Prendas (solo admin, por tienda vía X-Store). Ver
app/services/garment_insights.py.

- GET /api/analytics/garments/summary: prendas por factura y precio promedio
  por prenda (total y por vendedora) y prendas más vendidas. Rápido: lee las
  prendas guardadas + las de hoy.
- GET /api/analytics/garments/stock: más vendidos agotados, curva de tallas
  venta vs. stock y rotación. Consulta el stock actual de Alegra (la primera
  vez ~1 min; luego caché de 5 min por tienda).
"""
import logging
from datetime import date, datetime

from flask import Blueprint, jsonify, request

from app.exceptions import CierreCajaException, ConfigurationError
from app.middlewares.auth import role_required, token_required
from app.services.garment_insights import GarmentInsightsService
from app.stores import get_alegra_client, get_current_store
from app.utils.timezone import get_colombia_now, get_colombia_timestamp

logger = logging.getLogger(__name__)

bp = Blueprint('garment_insights', __name__)

# Las prendas guardadas empiezan el 1-ene-2026 (igual que el resumen de facturas)
MAX_RANGE_DAYS = 366


def _error(message, status, code=None):
    body = {'success': False, 'message': message, 'error': message}
    if code:
        body['code'] = code
    return jsonify(body), status


def _parse_range(today: date):
    """(start, end); por defecto, el mes en curso hasta hoy (Colombia)."""
    start_str = request.args.get('start_date')
    end_str = request.args.get('end_date')
    start = datetime.strptime(start_str, '%Y-%m-%d').date() if start_str else today.replace(day=1)
    end = datetime.strptime(end_str, '%Y-%m-%d').date() if end_str else today
    end = min(end, today)
    if start > end:
        raise ValueError('La fecha inicial no puede ser posterior a la final')
    if (end - start).days + 1 > MAX_RANGE_DAYS:
        raise ValueError('El rango máximo es de 1 año')
    return start, end


def _run(method_name, what):
    today = get_colombia_now().date()
    try:
        start, end = _parse_range(today)
    except ValueError as e:
        return _error(str(e), 400)
    try:
        service = GarmentInsightsService(get_current_store(), today, invoices_client=get_alegra_client())
    except ConfigurationError as e:
        return _error(e.message, 503, 'alegra_not_configured')
    try:
        data = getattr(service, method_name)(start, end)
    except CierreCajaException as e:
        logger.error(f'[{get_current_store()}] {what}: {e}')
        return _error(e.message, 502, 'alegra_error')
    except Exception:
        logger.exception(f'Error inesperado en {what}')
        return _error('Error interno del servidor', 500)
    return jsonify({'success': True, 'store': get_current_store(),
                    'server_timestamp': get_colombia_timestamp(), 'data': data}), 200


@bp.route('/api/analytics/garments/summary', methods=['GET', 'OPTIONS'])
@token_required
@role_required('admin')
def garments_summary():
    """
    Prendas por factura y precio promedio por prenda (total y por vendedora) y prendas más vendidas.
    ---
    tags:
      - Analytics
    parameters:
      - in: query
        name: start_date
        type: string
        required: false
        description: YYYY-MM-DD (por defecto, día 1 del mes en curso)
      - in: query
        name: end_date
        type: string
        required: false
        description: YYYY-MM-DD (por defecto, hoy)
    responses:
      200:
        description: Indicadores de prendas (data.coverage dice si faltan días por cargar)
      400:
        description: Rango de fechas inválido
      503:
        description: La tienda todavía no tiene cuenta de Alegra configurada
    """
    if request.method == 'OPTIONS':
        return '', 204
    return _run('summary', 'resumen de prendas')


@bp.route('/api/analytics/garments/stock', methods=['GET', 'OPTIONS'])
@token_required
@role_required('admin')
def garments_stock():
    """
    Más vendidos agotados, curva de tallas venta vs. stock y rotación por tipo de prenda.
    ---
    tags:
      - Analytics
    parameters:
      - in: query
        name: start_date
        type: string
        required: false
      - in: query
        name: end_date
        type: string
        required: false
    responses:
      200:
        description: Cruce de ventas del periodo con el stock actual de Alegra
      400:
        description: Rango de fechas inválido
      502:
        description: Alegra no respondió
      503:
        description: La tienda todavía no tiene cuenta de Alegra configurada
    """
    if request.method == 'OPTIONS':
        return '', 204
    return _run('stock_analysis', 'stock de prendas')
