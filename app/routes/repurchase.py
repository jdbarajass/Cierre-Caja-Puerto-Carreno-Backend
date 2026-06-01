"""
Rutas de Cuentas de Recompras.

Acceso:
- admin:   CRUD completo
- partner: solo lectura (GET)
"""
from flask import Blueprint, request, jsonify
from datetime import datetime
import logging

from app.middlewares.auth import token_required, get_current_user
from app.models.user import db
from app.models.repurchase import RepurchaseEntry

logger = logging.getLogger(__name__)
bp = Blueprint('repurchase', __name__)

ALLOWED_ROLES = ('admin', 'partner')
MONEY_FIELDS = ['efectivo', 'datafono', 'qr', 'daviplata', 'nequi', 'bbva',
                'valor_no_enviado', 'sobrante_mes_anterior']


def _check_role():
    """Devuelve el rol del usuario actual o lanza 403."""
    role = get_current_user().get('role')
    if role not in ALLOWED_ROLES:
        return None, (jsonify({'success': False, 'message': 'Sin permisos para esta sección'}), 403)
    return role, None


def parse_date(value):
    return datetime.strptime(value, '%Y-%m-%d').date()


# ─────────────────────────────────────────────
#  LISTAR
# ─────────────────────────────────────────────

@bp.route('/api/repurchase', methods=['GET', 'OPTIONS'])
@token_required
def list_entries():
    if request.method == 'OPTIONS':
        return '', 204

    role, err = _check_role()
    if err:
        return err

    try:
        # Filtros opcionales por mes/año
        year  = request.args.get('year',  type=int)
        month = request.args.get('month', type=int)

        q = RepurchaseEntry.query
        if year:
            q = q.filter(db.extract('year', RepurchaseEntry.date) == year)
        if month:
            q = q.filter(db.extract('month', RepurchaseEntry.date) == month)

        entries = q.order_by(RepurchaseEntry.date.asc()).all()

        # Totales globales del período
        totals = {
            'efectivo':   sum(e.efectivo   for e in entries),
            'datafono':   sum(e.datafono   for e in entries),
            'qr':         sum(e.qr         for e in entries),
            'daviplata':  sum(e.daviplata  for e in entries),
            'nequi':      sum(e.nequi      for e in entries),
            'bbva':       sum(e.bbva       for e in entries),
            'total_enviado': sum(e.total_enviado for e in entries),
            'sobrante_acumulado': sum(e.sobrante_mes_anterior for e in entries),
        }

        return jsonify({
            'success': True,
            'entries': [e.to_dict() for e in entries],
            'totals': totals,
            'count': len(entries)
        }), 200

    except Exception as e:
        logger.error(f"Error listando recompras: {e}")
        return jsonify({'success': False, 'message': 'Error al obtener registros'}), 500


# ─────────────────────────────────────────────
#  CREAR
# ─────────────────────────────────────────────

@bp.route('/api/repurchase', methods=['POST', 'OPTIONS'])
@token_required
def create_entry():
    if request.method == 'OPTIONS':
        return '', 204

    role, err = _check_role()
    if err:
        return err
    if role != 'admin':
        return jsonify({'success': False, 'message': 'Solo el administrador puede crear registros'}), 403

    try:
        data = request.get_json() or {}

        if 'date' not in data:
            return jsonify({'success': False, 'message': 'El campo date es requerido'}), 400

        entry = RepurchaseEntry(
            date=parse_date(data['date']),
            valor_no_enviado=float(data.get('valor_no_enviado', 0)),
            efectivo=float(data.get('efectivo', 0)),
            datafono=float(data.get('datafono', 0)),
            qr=float(data.get('qr', 0)),
            daviplata=float(data.get('daviplata', 0)),
            nequi=float(data.get('nequi', 0)),
            bbva=float(data.get('bbva', 0)),
            sobrante_mes_anterior=float(data.get('sobrante_mes_anterior', 0)),
            notes=data.get('notes', '').strip() or None,
            created_by=get_current_user().get('userId')
        )

        db.session.add(entry)
        db.session.commit()
        logger.info(f"Recompra creada id={entry.id}")
        return jsonify({'success': True, 'entry': entry.to_dict()}), 201

    except ValueError as e:
        return jsonify({'success': False, 'message': f'Dato inválido: {e}'}), 400
    except Exception as e:
        db.session.rollback()
        logger.error(f"Error creando recompra: {e}")
        return jsonify({'success': False, 'message': 'Error al crear registro'}), 500


# ─────────────────────────────────────────────
#  ACTUALIZAR
# ─────────────────────────────────────────────

@bp.route('/api/repurchase/<int:entry_id>', methods=['PUT', 'OPTIONS'])
@token_required
def update_entry(entry_id):
    if request.method == 'OPTIONS':
        return '', 204

    role, err = _check_role()
    if err:
        return err
    if role != 'admin':
        return jsonify({'success': False, 'message': 'Solo el administrador puede editar'}), 403

    entry = RepurchaseEntry.query.get_or_404(entry_id)

    try:
        data = request.get_json() or {}

        if 'date' in data:
            entry.date = parse_date(data['date'])

        for field in MONEY_FIELDS:
            if field in data:
                setattr(entry, field, float(data[field]))

        if 'notes' in data:
            entry.notes = data['notes'].strip() or None

        db.session.commit()
        return jsonify({'success': True, 'entry': entry.to_dict()}), 200

    except Exception as e:
        db.session.rollback()
        logger.error(f"Error actualizando recompra {entry_id}: {e}")
        return jsonify({'success': False, 'message': 'Error al actualizar'}), 500


# ─────────────────────────────────────────────
#  ELIMINAR
# ─────────────────────────────────────────────

@bp.route('/api/repurchase/<int:entry_id>', methods=['DELETE', 'OPTIONS'])
@token_required
def delete_entry(entry_id):
    if request.method == 'OPTIONS':
        return '', 204

    role, err = _check_role()
    if err:
        return err
    if role != 'admin':
        return jsonify({'success': False, 'message': 'Solo el administrador puede eliminar'}), 403

    entry = RepurchaseEntry.query.get_or_404(entry_id)
    db.session.delete(entry)
    db.session.commit()
    return jsonify({'success': True, 'message': 'Registro eliminado'}), 200


# ─────────────────────────────────────────────
#  RESUMEN POR MES (para el panel de totales)
# ─────────────────────────────────────────────

@bp.route('/api/repurchase/monthly-summary', methods=['GET', 'OPTIONS'])
@token_required
def monthly_summary():
    if request.method == 'OPTIONS':
        return '', 204

    role, err = _check_role()
    if err:
        return err

    try:
        # Obtener todos los años/meses disponibles
        entries = RepurchaseEntry.query.order_by(RepurchaseEntry.date.asc()).all()

        months = {}
        for e in entries:
            key = f"{e.date.year}-{e.date.month:02d}"
            if key not in months:
                months[key] = {
                    'year': e.date.year,
                    'month': e.date.month,
                    'label': e.date.strftime('%B %Y'),
                    'efectivo': 0, 'datafono': 0, 'qr': 0,
                    'daviplata': 0, 'nequi': 0, 'bbva': 0,
                    'total_enviado': 0, 'sobrante_mes_anterior': 0,
                    'valor_no_enviado': 0, 'count': 0
                }
            m = months[key]
            m['efectivo']   += e.efectivo
            m['datafono']   += e.datafono
            m['qr']         += e.qr
            m['daviplata']  += e.daviplata
            m['nequi']      += e.nequi
            m['bbva']       += e.bbv if hasattr(e, 'bbv') else e.bbva
            m['total_enviado'] += e.total_enviado
            m['sobrante_mes_anterior'] += e.sobrante_mes_anterior
            m['valor_no_enviado'] = e.valor_no_enviado  # último valor del mes
            m['count'] += 1

        return jsonify({
            'success': True,
            'months': list(months.values())
        }), 200

    except Exception as e:
        logger.error(f"Error en resumen mensual recompras: {e}")
        return jsonify({'success': False, 'message': 'Error al obtener resumen'}), 500
