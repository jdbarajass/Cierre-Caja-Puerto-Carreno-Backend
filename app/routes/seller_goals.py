"""
Estadísticas → Metas por vendedora (solo admin, por tienda vía X-Store). Ver
app/services/seller_goals.py.

- GET /api/analytics/seller-goals?month=YYYY-MM: meta (automática o ajustada)
  y avance de cada vendedora y de la tienda. Por defecto, el mes en curso.
- PUT /api/analytics/seller-goals: {month, seller_id, seller_name, amount}
  ajusta la meta de una vendedora; amount null = volver a la automática.
"""
import logging
from datetime import date, datetime

from flask import Blueprint, jsonify, request

from app.exceptions import ConfigurationError
from app.middlewares.auth import get_current_user, role_required, token_required
from app.services import seller_goals as svc
from app.stores import get_alegra_client, get_alegra_direct_client, get_current_store
from app.utils.timezone import get_colombia_now, get_colombia_timestamp

logger = logging.getLogger(__name__)

bp = Blueprint('seller_goals', __name__)

FIRST_MONTH = date(2026, 1, 1)  # hay facturas guardadas desde aquí
MAX_GOAL = 10_000_000_000


def _error(message, status, code=None):
    body = {'success': False, 'message': message, 'error': message}
    if code:
        body['code'] = code
    return jsonify(body), status


def _parse_month(value, today):
    if not value:
        return today.replace(day=1)
    month = datetime.strptime(value, '%Y-%m').date()
    latest = svc.shift_months(today.replace(day=1), 1)  # se puede preparar el mes siguiente
    if month < FIRST_MONTH or month > latest:
        raise ValueError(f'El mes debe estar entre {FIRST_MONTH:%Y-%m} y {latest:%Y-%m}')
    return month


@bp.route('/api/analytics/seller-goals', methods=['GET', 'OPTIONS'])
@token_required
@role_required('admin')
def seller_goals():
    """
    Metas y avance por vendedora del mes (por defecto, el mes en curso).
    ---
    tags:
      - Analytics
    parameters:
      - in: query
        name: month
        type: string
        required: false
        description: YYYY-MM (desde 2026-01 hasta el mes siguiente)
    responses:
      200:
        description: Meta de la tienda, de cada vendedora (automática o ajustada) y su avance
      400:
        description: Mes inválido
      503:
        description: La tienda no tiene cuenta de Alegra configurada
    """
    if request.method == 'OPTIONS':
        return '', 204
    today = get_colombia_now().date()
    try:
        month = _parse_month(request.args.get('month'), today)
    except ValueError as e:
        return _error(str(e) if 'mes' in str(e) else 'Mes inválido (use YYYY-MM)', 400)
    try:
        service = svc.SellerGoalsService(get_current_store(), today, get_alegra_direct_client(), get_alegra_client())
    except ConfigurationError as e:
        return _error(e.message, 503, 'alegra_not_configured')
    try:
        data = service.summary(month)
    except Exception:
        logger.exception('Error inesperado en metas por vendedora')
        return _error('No se pudieron calcular las metas. Intenta de nuevo en unos minutos.', 502, 'alegra_error')
    return jsonify({'success': True, 'store': get_current_store(),
                    'server_timestamp': get_colombia_timestamp(), 'data': data}), 200


@bp.route('/api/analytics/seller-goals', methods=['PUT'])
@token_required
@role_required('admin')
def update_seller_goal():
    """
    Ajusta la meta mensual de una vendedora (amount null = volver a la automática).
    ---
    tags:
      - Analytics
    parameters:
      - in: body
        name: body
        schema:
          type: object
          required: [month, seller_id]
          properties:
            month:
              type: string
              description: YYYY-MM
            seller_id:
              type: string
            seller_name:
              type: string
            amount:
              type: integer
              description: Meta en pesos; null para volver a la automática
    responses:
      200:
        description: Meta guardada
      400:
        description: Datos inválidos
    """
    data = request.get_json(silent=True) or {}
    today = get_colombia_now().date()
    try:
        month = _parse_month(data.get('month'), today) if data.get('month') else None
    except ValueError as e:
        return _error(str(e) if 'mes' in str(e) else 'Mes inválido (use YYYY-MM)', 400)
    seller_id = str(data.get('seller_id') or '').strip()
    if not month or not seller_id:
        return _error('Faltan el mes o la vendedora', 400)
    amount = data.get('amount')
    if amount is not None:
        try:
            amount = int(amount)
        except (TypeError, ValueError):
            return _error('La meta debe ser un número', 400)
        if not 0 < amount <= MAX_GOAL:
            return _error('La meta debe ser mayor que $0', 400)
    user = (get_current_user() or {}).get('email')
    svc.set_goal(get_current_store(), month, seller_id, (data.get('seller_name') or '').strip()[:120] or None,
                 amount, user)
    return jsonify({'success': True}), 200
