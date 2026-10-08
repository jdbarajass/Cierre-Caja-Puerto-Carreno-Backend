"""
Blindaje de la copia de facturas (docs/PLAN_BLINDAJE_COPIA.md): estado,
repaso completo, congelar hasta una fecha y respaldo en Excel. Solo admin,
por tienda (header X-Store). No escribe nada en Alegra.
"""
import logging
from datetime import date, datetime

from flask import Blueprint, request, jsonify, Response

from app.middlewares.auth import token_required, get_current_user
from app.services import facts_freeze as svc
from app.stores import STORES, get_current_store
from app.utils.timezone import get_colombia_now

logger = logging.getLogger(__name__)
bp = Blueprint('facts_freeze', __name__)

CONFIRM_WORD = 'CONGELAR'


def _require_admin():
    if get_current_user().get('role') != 'admin':
        return jsonify({'success': False, 'message': 'Solo el administrador puede acceder'}), 403
    return None


def _date(value, default=None):
    if value in (None, ''):
        return default
    try:
        return datetime.strptime(str(value), '%Y-%m-%d').date()
    except ValueError:
        raise svc.FreezeError('La fecha debe ser AAAA-MM-DD')


def _default_until(today: date) -> date:
    """Por defecto: el último día del año anterior (si ya terminó) o ayer."""
    last_year_end = date(today.year - 1, 12, 31)
    return last_year_end if last_year_end >= svc.FACTS_START else today.fromordinal(today.toordinal() - 1)


@bp.route('/api/facts-freeze/status', methods=['GET', 'OPTIONS'])
@token_required
def status():
    if request.method == 'OPTIONS':
        return '', 204
    err = _require_admin()
    if err:
        return err
    store = get_current_store()
    today = get_colombia_now().date()
    try:
        until = _date(request.args.get('until'), _default_until(today))
        until = min(until, today.fromordinal(today.toordinal() - 1))
        return jsonify({'success': True, 'store': store, **svc.status(store, until)}), 200
    except svc.FreezeError as e:
        return jsonify({'success': False, 'message': str(e)}), 400
    except Exception as e:
        logger.error(f'[{store}] Estado del blindaje: {e}', exc_info=True)
        return jsonify({'success': False, 'message': 'Error al leer el estado de la copia'}), 500


@bp.route('/api/facts-freeze/review', methods=['POST', 'OPTIONS'])
@token_required
def review():
    """Marca los días hasta `until` para volver a descargarlos una vez (repaso completo)."""
    if request.method == 'OPTIONS':
        return '', 204
    err = _require_admin()
    if err:
        return err
    store = get_current_store()
    data = request.get_json(silent=True) or {}
    today = get_colombia_now().date()
    try:
        until = _date(data.get('until'))
        if until is None or until >= today:
            raise svc.FreezeError('Indica hasta qué día repasar (hasta ayer)')
        days = svc.start_review(store, until, get_current_user().get('userId'))
        return jsonify({'success': True, 'days': days, **svc.status(store, until)}), 200
    except svc.FreezeError as e:
        return jsonify({'success': False, 'message': str(e)}), 400


@bp.route('/api/facts-freeze/freeze', methods=['POST', 'OPTIONS'])
@token_required
def freeze():
    """Congela la copia hasta `until` (body: {"until": "AAAA-MM-DD", "confirm": "CONGELAR"})."""
    if request.method == 'OPTIONS':
        return '', 204
    err = _require_admin()
    if err:
        return err
    store = get_current_store()
    data = request.get_json(silent=True) or {}
    if str(data.get('confirm') or '').strip().upper() != CONFIRM_WORD:
        return jsonify({'success': False, 'message': f'Escribe {CONFIRM_WORD} para confirmar'}), 400
    try:
        until = _date(data.get('until'))
        if until is None:
            raise svc.FreezeError('Indica hasta qué día congelar')
        frozen = svc.freeze(store, until, get_colombia_now().date(), get_current_user().get('userId'))
        logger.info(f'[{store}] Copia de facturas congelada hasta {until}')
        return jsonify({'success': True, 'frozen': frozen, **svc.status(store, until)}), 200
    except svc.FreezeError as e:
        return jsonify({'success': False, 'message': str(e)}), 400


@bp.route('/api/facts-freeze/backup.xlsx', methods=['GET', 'OPTIONS'])
@token_required
def backup():
    """Excel con las facturas y prendas guardadas de un año (?year=2026)."""
    if request.method == 'OPTIONS':
        return '', 204
    err = _require_admin()
    if err:
        return err
    store = get_current_store()
    try:
        year = int(request.args.get('year') or get_colombia_now().year)
        if not 2025 <= year <= 2100:
            raise ValueError
    except ValueError:
        return jsonify({'success': False, 'message': 'Año inválido'}), 400
    try:
        content = svc.backup_excel(store, STORES[store]['name'], date(year, 1, 1), date(year, 12, 31))
    except Exception as e:
        logger.error(f'[{store}] Respaldo de facturas {year}: {e}', exc_info=True)
        return jsonify({'success': False, 'message': 'No se pudo generar el respaldo'}), 500
    return Response(content, mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
                    headers={'Content-Disposition': f'attachment; filename=respaldo_facturas_{year}_{store}.xlsx'})
