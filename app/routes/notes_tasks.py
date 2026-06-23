"""
Rutas de Notas y Pendientes: Resurtido (Por Pedir) y Tareas Operativas.

Reglas de acceso:
- Cualquier usuario autenticado (admin o sales) puede: crear, ver, marcar completado/pendiente
- Solo admin puede: editar el contenido (texto/cantidad/prioridad) y eliminar
"""
from flask import Blueprint, request, jsonify
from datetime import datetime
import logging

from app.middlewares.auth import token_required, get_current_user
from app.models.user import db
from app.models.notes_tasks import RestockItem, OperationalTask

logger = logging.getLogger(__name__)
bp = Blueprint('notes_tasks', __name__)


def _is_admin():
    return get_current_user().get('role') == 'admin'


def _check_only_toggle_allowed(data, allowed_fields={'completed'}):
    """Si el usuario no es admin, solo puede tocar los campos permitidos (ej: completed)."""
    if _is_admin():
        return None
    if not set(data.keys()).issubset(allowed_fields):
        return jsonify({'success': False, 'message': 'Solo el administrador puede editar el contenido'}), 403
    return None


# ─────────────────────────────────────────────
#  RESURTIDO / POR PEDIR
# ─────────────────────────────────────────────

@bp.route('/api/notes-tasks/restock', methods=['GET', 'OPTIONS'])
@token_required
def list_restock():
    if request.method == 'OPTIONS':
        return '', 204
    try:
        items = RestockItem.query.order_by(RestockItem.completed.asc(), RestockItem.created_at.desc()).all()
        return jsonify({
            'success': True,
            'items': [i.to_dict() for i in items],
            'pendientes': sum(1 for i in items if not i.completed),
            'completados': sum(1 for i in items if i.completed)
        }), 200
    except Exception as e:
        logger.error(f"Error listando resurtido: {e}")
        return jsonify({'success': False, 'message': 'Error al obtener registros'}), 500


@bp.route('/api/notes-tasks/restock', methods=['POST', 'OPTIONS'])
@token_required
def create_restock():
    if request.method == 'OPTIONS':
        return '', 204
    try:
        data = request.get_json() or {}
        if not data.get('item'):
            return jsonify({'success': False, 'message': 'El campo item es requerido'}), 400

        item = RestockItem(
            item=data['item'].strip(),
            quantity=int(data['quantity']) if data.get('quantity') else None,
            created_by=get_current_user().get('userId')
        )
        db.session.add(item)
        db.session.commit()
        return jsonify({'success': True, 'item': item.to_dict()}), 201
    except ValueError as e:
        return jsonify({'success': False, 'message': f'Dato inválido: {e}'}), 400
    except Exception as e:
        db.session.rollback()
        logger.error(f"Error creando resurtido: {e}")
        return jsonify({'success': False, 'message': 'Error al crear registro'}), 500


@bp.route('/api/notes-tasks/restock/<int:item_id>', methods=['PUT', 'DELETE', 'OPTIONS'])
@token_required
def manage_restock(item_id):
    if request.method == 'OPTIONS':
        return '', 204

    item = RestockItem.query.get_or_404(item_id)

    if request.method == 'DELETE':
        if not _is_admin():
            return jsonify({'success': False, 'message': 'Solo el administrador puede eliminar'}), 403
        db.session.delete(item)
        db.session.commit()
        return jsonify({'success': True, 'message': 'Registro eliminado'}), 200

    try:
        data = request.get_json() or {}
        err = _check_only_toggle_allowed(data)
        if err:
            return err

        if 'item' in data:
            item.item = data['item'].strip()
        if 'quantity' in data:
            item.quantity = int(data['quantity']) if data['quantity'] else None
        if 'completed' in data:
            item.completed = bool(data['completed'])
            item.completed_at = datetime.utcnow() if item.completed else None

        db.session.commit()
        return jsonify({'success': True, 'item': item.to_dict()}), 200
    except Exception as e:
        db.session.rollback()
        logger.error(f"Error actualizando resurtido {item_id}: {e}")
        return jsonify({'success': False, 'message': 'Error al actualizar'}), 500


# ─────────────────────────────────────────────
#  TAREAS OPERATIVAS
# ─────────────────────────────────────────────

@bp.route('/api/notes-tasks/operational', methods=['GET', 'OPTIONS'])
@token_required
def list_operational():
    if request.method == 'OPTIONS':
        return '', 204
    try:
        tasks = OperationalTask.query.order_by(OperationalTask.completed.asc(), OperationalTask.created_at.desc()).all()
        return jsonify({
            'success': True,
            'items': [t.to_dict() for t in tasks],
            'pendientes': sum(1 for t in tasks if not t.completed),
            'completados': sum(1 for t in tasks if t.completed)
        }), 200
    except Exception as e:
        logger.error(f"Error listando tareas: {e}")
        return jsonify({'success': False, 'message': 'Error al obtener registros'}), 500


@bp.route('/api/notes-tasks/operational', methods=['POST', 'OPTIONS'])
@token_required
def create_operational():
    if request.method == 'OPTIONS':
        return '', 204
    try:
        data = request.get_json() or {}
        if not data.get('description'):
            return jsonify({'success': False, 'message': 'El campo description es requerido'}), 400

        priority = data.get('priority', 'media')
        if priority not in OperationalTask.PRIORITIES:
            priority = 'media'

        task = OperationalTask(
            description=data['description'].strip(),
            priority=priority,
            created_by=get_current_user().get('userId')
        )
        db.session.add(task)
        db.session.commit()
        return jsonify({'success': True, 'item': task.to_dict()}), 201
    except Exception as e:
        db.session.rollback()
        logger.error(f"Error creando tarea: {e}")
        return jsonify({'success': False, 'message': 'Error al crear registro'}), 500


@bp.route('/api/notes-tasks/operational/<int:task_id>', methods=['PUT', 'DELETE', 'OPTIONS'])
@token_required
def manage_operational(task_id):
    if request.method == 'OPTIONS':
        return '', 204

    task = OperationalTask.query.get_or_404(task_id)

    if request.method == 'DELETE':
        if not _is_admin():
            return jsonify({'success': False, 'message': 'Solo el administrador puede eliminar'}), 403
        db.session.delete(task)
        db.session.commit()
        return jsonify({'success': True, 'message': 'Registro eliminado'}), 200

    try:
        data = request.get_json() or {}
        err = _check_only_toggle_allowed(data)
        if err:
            return err

        if 'description' in data:
            task.description = data['description'].strip()
        if 'priority' in data and data['priority'] in OperationalTask.PRIORITIES:
            task.priority = data['priority']
        if 'completed' in data:
            task.completed = bool(data['completed'])
            task.completed_at = datetime.utcnow() if task.completed else None

        db.session.commit()
        return jsonify({'success': True, 'item': task.to_dict()}), 200
    except Exception as e:
        db.session.rollback()
        logger.error(f"Error actualizando tarea {task_id}: {e}")
        return jsonify({'success': False, 'message': 'Error al actualizar'}), 500
