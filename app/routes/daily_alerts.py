"""
Alertas diarias (Fase D4), por tienda vía X-Store. Ver app/services/daily_alerts.py.

- GET  /api/analytics/alerts: alertas sin descartar de los últimos 7 días (admin).
- POST /api/analytics/alerts/generate: calcula las alertas de un día (por
  defecto hoy si ya son las 8 pm en Colombia, si no ayer). Admin o el cron
  de las 9 pm (X-Sync-Token).
- POST /api/analytics/alerts/<id>/dismiss: descarta una alerta (admin).
"""
import logging
from datetime import datetime, timedelta

from flask import Blueprint, jsonify, request

from app.exceptions import ConfigurationError
from app.middlewares.auth import get_current_user, role_required, token_required
from app.models.daily_alert import DailyAlert
from app.models.user import db
from app.routes.accounts import sync_token_or_admin_required
from app.services import daily_alerts as svc
from app.stores import get_alegra_client, get_alegra_direct_client, get_current_store
from app.utils.timezone import get_colombia_now

logger = logging.getLogger(__name__)

bp = Blueprint('daily_alerts', __name__)

# La tienda vende hasta ~8 pm (última venta vista 7:38 pm): desde esa hora el día ya cerró
DAY_CLOSED_HOUR = 20


@bp.route('/api/analytics/alerts', methods=['GET', 'OPTIONS'])
@token_required
@role_required('admin')
def list_alerts():
    """
    Alertas sin descartar de los últimos 7 días de la tienda activa.
    ---
    tags:
      - Analytics
    responses:
      200:
        description: Lista de alertas (las de advertencia primero en cada día)
    """
    if request.method == 'OPTIONS':
        return '', 204
    today = get_colombia_now().date()
    return jsonify({'success': True, 'store': get_current_store(),
                    'data': svc.active_alerts(get_current_store(), today)}), 200


@bp.route('/api/analytics/alerts/generate', methods=['POST', 'OPTIONS'])
@sync_token_or_admin_required
def generate_alerts():
    """
    Calcula las alertas de un día ya cerrado (body opcional {"date": "YYYY-MM-DD"}).
    ---
    tags:
      - Analytics
    responses:
      200:
        description: Alertas creadas y las que no se pudieron calcular
      400:
        description: Fecha inválida
      503:
        description: La tienda no tiene cuenta de Alegra configurada
    """
    if request.method == 'OPTIONS':
        return '', 204
    now = get_colombia_now()
    body = request.get_json(silent=True) or {}
    try:
        day = (datetime.strptime(body['date'], '%Y-%m-%d').date() if body.get('date')
               else now.date() if now.hour >= DAY_CLOSED_HOUR else now.date() - timedelta(days=1))
    except ValueError:
        return jsonify({'success': False, 'message': 'Fecha inválida (use YYYY-MM-DD)'}), 400
    if day > now.date():
        return jsonify({'success': False, 'message': 'No se puede analizar un día futuro'}), 400

    store = get_current_store()
    try:
        client = get_alegra_client()
        direct = get_alegra_direct_client()
    except ConfigurationError as e:
        return jsonify({'success': False, 'message': e.message, 'code': 'alegra_not_configured'}), 503

    from app.services.seller_goals import SellerGoalsService
    result = svc.generate(
        store, day,
        items_loader=client.get_active_items,
        goals_loader=lambda: SellerGoalsService(store, day, direct, client).summary(day.replace(day=1)),
    )
    logger.info(f'[{store}] Alertas del {day}: {result}')
    return jsonify({'success': True, 'store': store, 'result': result}), 200


@bp.route('/api/analytics/alerts/<int:alert_id>/dismiss', methods=['POST', 'OPTIONS'])
@token_required
@role_required('admin')
def dismiss_alert(alert_id):
    """
    Descarta una alerta (deja de mostrarse).
    ---
    tags:
      - Analytics
    responses:
      200:
        description: Alerta descartada
      404:
        description: No existe en esta tienda
    """
    if request.method == 'OPTIONS':
        return '', 204
    row = DailyAlert.query.filter_by(id=alert_id, store_code=get_current_store()).first()
    if row is None:
        return jsonify({'success': False, 'message': 'Alerta no encontrada'}), 404
    row.dismissed_at = datetime.utcnow()
    row.dismissed_by = (get_current_user() or {}).get('email')
    db.session.commit()
    return jsonify({'success': True}), 200
