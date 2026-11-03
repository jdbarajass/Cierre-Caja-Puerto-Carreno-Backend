"""
Solicitudes de ajuste de inventario (docs/PLAN_AJUSTES_INVENTARIO.md). Por
tienda (X-Store).

- Vendedoras (sales) y admin: buscar un código, crear, ver y cancelar las
  suyas mientras estén pendientes.
- Solo admin: revisar contra Alegra, aceptar (crea el ajuste en Alegra),
  aceptar todas y rechazar. El admin de solo lectura solo puede ver.
"""
import logging
from datetime import datetime

from flask import Blueprint, request, jsonify

from app.exceptions import ConfigurationError
from app.middlewares.auth import token_required, role_required_any, get_current_user
from app.models.inventory_request import InventoryRequest, KINDS, OPEN_STATUSES
from app.models.user import db
from app.services import inventory_requests as svc
from app.stores import get_alegra_client, get_current_store
from app.utils.timezone import get_colombia_now

logger = logging.getLogger(__name__)
bp = Blueprint('inventory_requests', __name__)

ROLES = ['admin', 'sales']
EXCEDENTE_MEDIOS = ('efectivo', 'qr', 'nequi', 'daviplata', 'datafono', 'addi')
LIST_LIMIT = 150


def _error(message, status):
    return jsonify({'success': False, 'message': message, 'error': message}), status


def _require_admin():
    if get_current_user().get('role') != 'admin':
        return _error('Solo el administrador puede aceptar o rechazar ajustes', 403)
    return None


def _user_id():
    return get_current_user().get('userId')


def _alegra_items(client):
    return client.get_active_items()


def _alegra_error(e, store, what):
    if isinstance(e, ConfigurationError):
        return _error(e.message, 503)
    logger.error(f'[{store}] Ajustes de inventario ({what}): {e}', exc_info=True)
    return _error('No se pudo consultar Alegra. Intenta de nuevo en un momento.', 502)


@bp.route('/api/inventory-requests/lookup', methods=['GET', 'OPTIONS'])
@token_required
@role_required_any(ROLES)
def lookup():
    """La prenda de un código: nombre y existencia en Alegra (para que la vendedora verifique)."""
    if request.method == 'OPTIONS':
        return '', 204
    store = get_current_store()
    try:
        found = svc.find_item(_alegra_items(get_alegra_client()), request.args.get('code'))
    except svc.RequestError as e:
        return _error(str(e), 404)
    except Exception as e:
        return _alegra_error(e, store, 'buscar código')
    return jsonify({'success': True, 'item': {**found, 'is_gift_card': svc.is_gift_card(found['name'])}}), 200


@bp.route('/api/inventory-requests', methods=['GET', 'OPTIONS'])
@token_required
@role_required_any(ROLES)
def list_requests():
    """?status=open (pendientes y por revisar, por defecto) | all (las últimas 150)."""
    if request.method == 'OPTIONS':
        return '', 204
    q = InventoryRequest.for_current_store()
    if (request.args.get('status') or 'open') == 'open':
        q = q.filter(InventoryRequest.status.in_(list(OPEN_STATUSES) + ['aplicando']))
    items = q.order_by(InventoryRequest.created_at.desc(), InventoryRequest.id.desc()).limit(LIST_LIMIT).all()
    open_count = InventoryRequest.for_current_store().filter(InventoryRequest.status.in_(OPEN_STATUSES)).count()
    return jsonify({'success': True, 'items': [r.to_dict() for r in items], 'open_count': open_count}), 200


@bp.route('/api/inventory-requests', methods=['POST'])
@token_required
@role_required_any(ROLES)
def create_request():
    """
    Body: {kind: 'conteo'|'tarjeta_regalo', requested_by, notes?,
           conteo: lines [{code, physical_qty}];
           tarjeta_regalo: gift_card_code, lines [{code, quantity}], excedente_valor?, excedente_medio?}
    No toca Alegra (solo lee): queda pendiente hasta que el admin la acepte.
    """
    data = request.get_json(silent=True) or {}
    kind = data.get('kind')
    if kind not in KINDS:
        return _error('Tipo de ajuste no válido', 400)
    requested_by = (data.get('requested_by') or '').strip()
    if not requested_by:
        return _error('Elige quién pide el ajuste', 400)
    if len(requested_by) > 100:
        return _error('El nombre de quien lo pide es muy largo', 400)
    notes = (data.get('notes') or '').strip()[:500] or None

    excedente_valor, excedente_medio = None, None
    if kind == 'tarjeta_regalo':
        try:
            excedente_valor = float(data.get('excedente_valor') or 0)
        except (TypeError, ValueError):
            return _error('El excedente debe ser un número', 400)
        if excedente_valor < 0:
            return _error('El excedente no puede ser negativo', 400)
        if excedente_valor:
            excedente_medio = (data.get('excedente_medio') or '').strip().lower()
            if excedente_medio not in EXCEDENTE_MEDIOS:
                return _error('Elige por qué medio pagó el excedente', 400)
        else:
            excedente_valor = None

    store = get_current_store()
    try:
        lines = svc.build_lines(kind, data, _alegra_items(get_alegra_client()))
    except svc.RequestError as e:
        return _error(str(e), 400)
    except Exception as e:
        return _alegra_error(e, store, 'crear')

    req = InventoryRequest(kind=kind, request_date=get_colombia_now().date(), requested_by=requested_by,
                           notes=notes, excedente_valor=excedente_valor, excedente_medio=excedente_medio,
                           created_by_user_id=_user_id())
    req.lines = lines
    db.session.add(req)
    db.session.commit()
    logger.info(f'[{store}] Solicitud de ajuste {req.id} ({kind}) de {requested_by}: {len(lines)} renglones')
    return jsonify({'success': True, 'request': req.to_dict()}), 201


@bp.route('/api/inventory-requests/<int:req_id>/cancel', methods=['POST', 'OPTIONS'])
@token_required
@role_required_any(ROLES)
def cancel_request(req_id):
    if request.method == 'OPTIONS':
        return '', 204
    req = InventoryRequest.get_for_current_store_or_404(req_id)
    if req.status != 'pendiente':
        return _error('Solo se puede quitar una solicitud pendiente', 409)
    req.status = 'cancelada'
    req.reviewed_by_user_id = _user_id()
    req.reviewed_at = datetime.utcnow()
    db.session.commit()
    return jsonify({'success': True, 'request': req.to_dict()}), 200


@bp.route('/api/inventory-requests/<int:req_id>/check', methods=['GET', 'OPTIONS'])
@token_required
def check_request(req_id):
    """Para el admin antes de aceptar: existencia y costo de hoy en Alegra, y avisos."""
    if request.method == 'OPTIONS':
        return '', 204
    err = _require_admin()
    if err:
        return err
    req = InventoryRequest.get_for_current_store_or_404(req_id)
    store = get_current_store()
    try:
        fresh = svc.fresh_items(get_alegra_client(), req)
    except Exception as e:
        return _alegra_error(e, store, 'revisar')
    problem = None
    try:
        svc.build_payload(req, fresh)
    except svc.RequestError as e:
        problem = str(e)
    return jsonify({'success': True, 'current': fresh, 'warnings': svc.warnings_for(req, fresh),
                    'problem': problem}), 200


def _approve(req, client):
    check_existing = svc.claim(req, _user_id())
    if check_existing is None:
        raise svc.RequestError('Esta solicitud ya no está pendiente (otra persona la aceptó o la quitaron).')
    return svc.apply_request(client, req, _user_id(), check_existing=check_existing)


@bp.route('/api/inventory-requests/<int:req_id>/approve', methods=['POST', 'OPTIONS'])
@token_required
def approve_request(req_id):
    """Crea el ajuste en Alegra (una sola vez)."""
    if request.method == 'OPTIONS':
        return '', 204
    err = _require_admin()
    if err:
        return err
    req = InventoryRequest.get_for_current_store_or_404(req_id)
    store = get_current_store()
    try:
        client = get_alegra_client()
        return jsonify({'success': True, 'request': _approve(req, client)}), 200
    except svc.RequestError as e:
        db.session.refresh(req)
        return jsonify({'success': False, 'message': str(e), 'request': req.to_dict()}), 409
    except Exception as e:
        return _alegra_error(e, store, 'aceptar')


@bp.route('/api/inventory-requests/approve-all', methods=['POST', 'OPTIONS'])
@token_required
def approve_all():
    """Acepta, una por una, las abiertas de la tienda (de la más vieja a la más nueva)."""
    if request.method == 'OPTIONS':
        return '', 204
    err = _require_admin()
    if err:
        return err
    store = get_current_store()
    pending = (InventoryRequest.for_current_store().filter(InventoryRequest.status.in_(OPEN_STATUSES))
               .order_by(InventoryRequest.created_at, InventoryRequest.id).all())
    try:
        client = get_alegra_client()
    except Exception as e:
        return _alegra_error(e, store, 'aceptar todas')
    results = []
    for req in pending:
        try:
            done = _approve(req, client)
            results.append({'id': req.id, 'ok': True, 'alegra_number': done.get('alegra_number')})
        except svc.RequestError as e:
            results.append({'id': req.id, 'ok': False, 'message': str(e)})
        except Exception as e:
            logger.error(f'[{store}] Aceptar ajuste {req.id}: {e}', exc_info=True)
            results.append({'id': req.id, 'ok': False, 'message': 'Error inesperado'})
    applied = sum(1 for r in results if r['ok'])
    return jsonify({'success': True, 'applied': applied, 'failed': len(results) - applied, 'results': results}), 200


@bp.route('/api/inventory-requests/<int:req_id>/reject', methods=['POST', 'OPTIONS'])
@token_required
def reject_request(req_id):
    if request.method == 'OPTIONS':
        return '', 204
    err = _require_admin()
    if err:
        return err
    req = InventoryRequest.get_for_current_store_or_404(req_id)
    if req.status not in OPEN_STATUSES:
        return _error('Solo se puede rechazar una solicitud pendiente', 409)
    if req.status == 'revisar':
        return _error('Puede que ya esté en Alegra: tócale Aceptar para revisarlo antes de rechazarla', 409)
    reason = ((request.get_json(silent=True) or {}).get('reason') or '').strip()
    if not reason:
        return _error('Escribe el motivo del rechazo', 400)
    req.status = 'rechazada'
    req.reject_reason = reason[:500]
    req.reviewed_by_user_id = _user_id()
    req.reviewed_at = datetime.utcnow()
    db.session.commit()
    return jsonify({'success': True, 'request': req.to_dict()}), 200
