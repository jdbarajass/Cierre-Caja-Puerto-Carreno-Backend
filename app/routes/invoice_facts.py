"""
Carga del resumen de facturas por tienda (fase 4 del dashboard de clientes).
Ver app/services/invoice_facts.py.

- GET  /api/analytics/invoice-facts/status: cuánto está cargado desde el
  1-ene-2026 y qué tan completos vienen los datos (vendedora, cédula,
  descuento). Solo admin.
- POST /api/analytics/invoice-facts/sync: vuelve a cargar los últimos
  `recent_days` días (para recoger anulaciones/ediciones) y luego carga la
  siguiente tanda de días faltantes (`max_days`, máx. 31): sin resumen de
  facturas o sin prendas (Estadísticas → Prendas). Admin o el cron
  de las 9 pm (X-Sync-Token). Se detiene antes del límite de tiempo de
  Render; si quedan días, se vuelve a llamar.
"""
import logging
import time
from datetime import date, timedelta

from flask import Blueprint, jsonify, request

from app.exceptions import ConfigurationError
from app.middlewares.auth import role_required, token_required
from app.routes.accounts import sync_token_or_admin_required
from app.services import invoice_facts as svc
from app.stores import get_alegra_client, get_current_store
from app.utils.timezone import get_colombia_now

logger = logging.getLogger(__name__)

bp = Blueprint('invoice_facts', __name__)

# Decisión del usuario (2026-10-02): la historia guardada empieza aquí.
FACTS_START = date(2026, 1, 1)
MAX_DAYS_PER_CALL = 31
MAX_RECENT_DAYS = 7
# Gunicorn corta a los 240 s (Procfile) y el cron espera 200 s: se para a
# los 150 s y devuelve lo que alcanzó.
TIME_BUDGET_SECONDS = 150


def _int_param(data, name, default, low, high):
    try:
        value = int(data.get(name, default))
    except (TypeError, ValueError):
        raise ValueError(f'{name} debe ser un número')
    if not low <= value <= high:
        raise ValueError(f'{name} debe estar entre {low} y {high}')
    return value


@bp.route('/api/analytics/invoice-facts/status', methods=['GET', 'OPTIONS'])
@token_required
@role_required('admin')
def invoice_facts_status():
    """
    Estado de la carga de facturas de la tienda activa (desde el 1-ene-2026 hasta ayer).
    ---
    tags:
      - Analytics
    responses:
      200:
        description: Días cargados, faltantes y calidad de los datos
    """
    if request.method == 'OPTIONS':
        return '', 204
    yesterday = get_colombia_now().date() - timedelta(days=1)
    return jsonify({
        'success': True,
        'store': get_current_store(),
        'data': svc.coverage_status(get_current_store(), FACTS_START, yesterday),
    }), 200


@bp.route('/api/analytics/invoice-facts/sync', methods=['POST', 'OPTIONS'])
@sync_token_or_admin_required
def invoice_facts_sync():
    """
    Carga facturas de la tienda activa: primero vuelve a cargar los últimos
    `recent_days` días (hasta hoy), luego la siguiente tanda de días que
    falten desde el 1-ene-2026 hasta ayer (`max_days`).
    ---
    tags:
      - Analytics
    parameters:
      - in: body
        name: body
        schema:
          type: object
          properties:
            max_days:
              type: integer
              description: Días faltantes a cargar en esta llamada (0-31, por defecto 31)
            recent_days:
              type: integer
              description: Días recientes a volver a cargar, incluido hoy (0-7, por defecto 0)
    responses:
      200:
        description: Lo que se cargó y el estado actualizado
      400:
        description: Parámetro inválido
      409:
        description: Ya hay una carga en curso para esta tienda
      503:
        description: La tienda no tiene cuenta de Alegra configurada
    """
    if request.method == 'OPTIONS':
        return '', 204

    data = request.get_json(silent=True) or {}
    try:
        max_days = _int_param(data, 'max_days', MAX_DAYS_PER_CALL, 0, MAX_DAYS_PER_CALL)
        recent_days = _int_param(data, 'recent_days', 0, 0, MAX_RECENT_DAYS)
    except ValueError as e:
        return jsonify({'success': False, 'message': str(e)}), 400

    store = get_current_store()
    try:
        client = get_alegra_client()
    except ConfigurationError as e:
        return jsonify({'success': False, 'message': e.message, 'code': 'alegra_not_configured'}), 503

    with svc.store_sync_lock(store) as acquired:
        if not acquired:
            return jsonify({
                'success': False, 'code': 'sync_in_progress',
                'message': 'Ya hay una carga de facturas en curso para esta tienda. Espera a que termine.',
                'status': svc.coverage_status(store, FACTS_START, get_colombia_now().date() - timedelta(days=1)),
            }), 409
        return _run_sync(client, store, max_days, recent_days)


def _run_sync(client, store, max_days, recent_days):
    today = get_colombia_now().date()
    yesterday = today - timedelta(days=1)
    deadline = time.monotonic() + TIME_BUDGET_SECONDS

    recent = {'synced_days': [], 'invoices': 0, 'failed_day': None, 'error': None, 'stopped_by_time': False}
    if recent_days:
        days = [today - timedelta(days=i) for i in range(recent_days - 1, -1, -1)]
        recent = svc.sync_range(client, store, [d for d in days if d >= FACTS_START], deadline)

    backfill = {'synced_days': [], 'invoices': 0, 'failed_day': None, 'error': None, 'stopped_by_time': False}
    if max_days and not recent['error']:
        # Días sin resumen de facturas o sin prendas (las prendas llegaron
        # después: los días viejos se completan en estas mismas tandas)
        pending = svc.pending_days(store, FACTS_START, yesterday)[:max_days]
        backfill = svc.sync_range(client, store, pending, deadline)

    # Compras de mercancía (Estadísticas → Llegadas): pocas, se recargan
    # completas. Si fallan no se marca error: las facturas ya quedaron.
    purchases = _sync_purchases(store)

    status = svc.coverage_status(store, FACTS_START, yesterday)
    error = recent['error'] or backfill['error']
    logger.info(f'[{store}] invoice-facts/sync: recientes={len(recent["synced_days"])} '
                f'tanda={len(backfill["synced_days"])} faltan={status["missing_days"]} error={error}')

    return jsonify({
        'success': error is None,
        'store': store,
        'message': error,
        'recent': recent,
        'backfill': backfill,
        'purchases': purchases,
        'status': status,
    }), 200 if error is None else 502


def _sync_purchases(store):
    from app.services.purchase_facts import sync_purchases
    from app.stores import get_alegra_direct_client
    try:
        return {'success': True, **sync_purchases(get_alegra_direct_client(), store, FACTS_START)}
    except Exception as e:
        logger.error(f'[{store}] Carga de compras de mercancía: {e}', exc_info=True)
        return {'success': False, 'error': 'No se pudieron cargar las compras de Alegra'}
