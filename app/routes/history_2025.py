"""
Reconstrucción de 2025 (docs/PLAN_RECONSTRUCCION_2025.md): cargar las
facturas de 2025 en la copia, revisar la clasificación de las anuladas,
marcar a mano e informe de inventario (pantalla y Excel). Solo admin.

No escribe nada en Alegra (el ajuste de inventario en Alegra es la fase R3,
pendiente de la revisión del usuario y su contador).
"""
import logging
import time

from flask import Blueprint, request, jsonify, Response

from app.exceptions import ConfigurationError
from app.middlewares.auth import token_required, get_current_user
from app.models.user import db
from app.models.invoice_fact import InvoiceFact, VoidOverride
from app.services import history_2025 as svc
from app.services import invoice_facts as facts_svc
from app.stores import STORES, get_alegra_client, get_current_store

logger = logging.getLogger(__name__)
bp = Blueprint('history_2025', __name__)

MAX_DAYS_PER_CALL = 31
TIME_BUDGET_SECONDS = 150


def _require_admin():
    if get_current_user().get('role') != 'admin':
        return jsonify({'success': False, 'message': 'Solo el administrador puede acceder'}), 403
    return None


@bp.route('/api/history-2025/status', methods=['GET', 'OPTIONS'])
@token_required
def status():
    if request.method == 'OPTIONS':
        return '', 204
    err = _require_admin()
    if err:
        return err
    store = get_current_store()
    try:
        return jsonify({'success': True, 'coverage': svc.coverage(store), 'summary': svc.summary(store)}), 200
    except Exception as e:
        logger.error(f'[{store}] Estado de la reconstrucción 2025: {e}', exc_info=True)
        return jsonify({'success': False, 'message': 'Error al leer la reconstrucción de 2025'}), 500


@bp.route('/api/history-2025/sync', methods=['POST', 'OPTIONS'])
@token_required
def sync():
    """Carga la siguiente tanda de días de 2025 que falten (body opcional {"max_days": 31})."""
    if request.method == 'OPTIONS':
        return '', 204
    err = _require_admin()
    if err:
        return err
    data = request.get_json(silent=True) or {}
    try:
        max_days = max(1, min(int(data.get('max_days') or MAX_DAYS_PER_CALL), MAX_DAYS_PER_CALL))
    except (TypeError, ValueError):
        return jsonify({'success': False, 'message': 'max_days inválido'}), 400
    store = get_current_store()
    try:
        client = get_alegra_client()
    except ConfigurationError as e:
        return jsonify({'success': False, 'message': e.message, 'code': 'alegra_not_configured'}), 503

    with facts_svc.store_sync_lock(store) as acquired:
        if not acquired:
            return jsonify({'success': False, 'code': 'sync_in_progress',
                            'message': 'Ya hay una carga de facturas en curso para esta tienda. Espera a que termine.'}), 409
        days = facts_svc.missing_days(store, svc.HISTORY_START, svc.HISTORY_END)[:max_days]
        result = facts_svc.sync_range(client, store, days, time.monotonic() + TIME_BUDGET_SECONDS)
    ok = result['error'] is None
    return jsonify({'success': ok, 'message': result['error'], **result,
                    'coverage': svc.coverage(store)}), 200 if ok else 502


@bp.route('/api/history-2025/override', methods=['PUT', 'OPTIONS'])
@token_required
def override():
    """
    Marca a mano una factura anulada de 2025 por su número (como sale en
    Alegra): counts_as_sale=true (anulación masiva, venta real), false
    (anulación real) o null (vuelve a la regla automática).
    """
    if request.method == 'OPTIONS':
        return '', 204
    err = _require_admin()
    if err:
        return err
    data = request.get_json() or {}
    number = str(data.get('number') or '').strip()
    q = InvoiceFact.for_current_store().filter(
        InvoiceFact.date >= svc.HISTORY_START, InvoiceFact.date <= svc.HISTORY_END, InvoiceFact.voided.is_(True))
    fact = q.filter(InvoiceFact.number == number).first() if number else None
    if fact is None and data.get('alegra_id'):
        fact = q.filter(InvoiceFact.alegra_id == str(data['alegra_id'])).first()
    if fact is None:
        return jsonify({'success': False, 'message': 'No hay una factura anulada de 2025 con ese número en la copia'}), 404
    item = VoidOverride.for_current_store().filter_by(alegra_id=fact.alegra_id).first()
    value = data.get('counts_as_sale')
    if value is None:
        if item:
            db.session.delete(item)
            db.session.commit()
        return jsonify({'success': True, 'deleted': True}), 200
    if item is None:
        item = VoidOverride(alegra_id=fact.alegra_id, counts_as_sale=bool(value))
        db.session.add(item)
    item.counts_as_sale = bool(value)
    item.note = (data.get('note') or '').strip() or None
    db.session.commit()
    return jsonify({'success': True, 'number': fact.number}), 200


def _report(store):
    items = get_alegra_client().get_active_items()
    return svc.inventory_report(store, items)


@bp.route('/api/history-2025/inventory', methods=['GET', 'OPTIONS'])
@token_required
def inventory():
    if request.method == 'OPTIONS':
        return '', 204
    err = _require_admin()
    if err:
        return err
    store = get_current_store()
    try:
        report = _report(store)
        return jsonify({'success': True, 'coverage': svc.coverage(store), **report}), 200
    except ConfigurationError as e:
        return jsonify({'success': False, 'message': e.message}), 503
    except Exception as e:
        logger.error(f'[{store}] Informe de inventario 2025: {e}', exc_info=True)
        return jsonify({'success': False, 'message': 'No se pudo leer el inventario de Alegra. Intenta de nuevo.'}), 502


@bp.route('/api/history-2025/inventory.xlsx', methods=['GET', 'OPTIONS'])
@token_required
def inventory_xlsx():
    if request.method == 'OPTIONS':
        return '', 204
    err = _require_admin()
    if err:
        return err
    store = get_current_store()
    try:
        content = svc.inventory_excel(_report(store), STORES[store]['name'])
    except Exception as e:
        logger.error(f'[{store}] Excel de inventario 2025: {e}', exc_info=True)
        return jsonify({'success': False, 'message': 'No se pudo generar el Excel'}), 502
    return Response(content, mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
                    headers={'Content-Disposition': f'attachment; filename=ajuste_inventario_2025_{store}.xlsx'})
