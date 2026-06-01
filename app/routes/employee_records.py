"""
Rutas de Control de Empleadas: Ropa, Préstamos, Permisos, Vacaciones, Pagos.

Reglas de acceso:
- sales: solo puede CREAR y VER sus propios registros (sin editar ni borrar)
- admin: CRUD completo sobre todos los registros
"""
from flask import Blueprint, request, jsonify
from datetime import datetime, date
import logging

from app.middlewares.auth import token_required, role_required, get_current_user
from app.models.user import db, User
from app.models.employee_records import (
    EmployeeClothing, EmployeeLoan,
    EmployeePermission, EmployeeVacation, EmployeePayment
)

logger = logging.getLogger(__name__)
bp = Blueprint('employee_records', __name__)


def parse_date(value):
    """Convierte string YYYY-MM-DD a date, o lanza ValueError."""
    return datetime.strptime(value, '%Y-%m-%d').date()


def _is_admin():
    return get_current_user().get('role') == 'admin'


def _current_user_id():
    return get_current_user().get('userId')


# ─────────────────────────────────────────────
#  ROPA
# ─────────────────────────────────────────────

@bp.route('/api/employee-records/clothing', methods=['GET', 'OPTIONS'])
@token_required
def list_clothing():
    if request.method == 'OPTIONS':
        return '', 204
    try:
        if _is_admin():
            employee_id = request.args.get('employee_id')
            q = EmployeeClothing.query
            if employee_id:
                q = q.filter_by(employee_id=int(employee_id))
        else:
            q = EmployeeClothing.query.filter_by(employee_id=_current_user_id())

        items = q.order_by(EmployeeClothing.date.desc()).all()
        total = sum(i.final_value for i in items)
        return jsonify({
            'success': True,
            'items': [i.to_dict() for i in items],
            'total_acumulado': total
        }), 200
    except Exception as e:
        logger.error(f"Error listando ropa: {e}")
        return jsonify({'success': False, 'message': 'Error al obtener registros'}), 500


@bp.route('/api/employee-records/clothing', methods=['POST', 'OPTIONS'])
@token_required
def create_clothing():
    if request.method == 'OPTIONS':
        return '', 204
    try:
        data = request.get_json() or {}
        required = ['date', 'product', 'value', 'discount_pct']
        for f in required:
            if f not in data:
                return jsonify({'success': False, 'message': f'Campo requerido: {f}'}), 400

        value = float(data['value'])
        discount_pct = float(data['discount_pct'])
        final_value = round(value * (1 - discount_pct / 100), 2)

        # sales registra para sí mismo; admin puede especificar employee_id
        if _is_admin() and data.get('employee_id'):
            employee_id = int(data['employee_id'])
        else:
            employee_id = _current_user_id()

        item = EmployeeClothing(
            employee_id=employee_id,
            date=parse_date(data['date']),
            product=data['product'].strip(),
            value=value,
            discount_pct=discount_pct,
            final_value=final_value,
            notes=data.get('notes', '').strip() or None
        )
        db.session.add(item)
        db.session.commit()
        logger.info(f"Ropa creada id={item.id} por user={_current_user_id()}")
        return jsonify({'success': True, 'item': item.to_dict()}), 201
    except ValueError as e:
        return jsonify({'success': False, 'message': f'Dato inválido: {e}'}), 400
    except Exception as e:
        db.session.rollback()
        logger.error(f"Error creando ropa: {e}")
        return jsonify({'success': False, 'message': 'Error al crear registro'}), 500


@bp.route('/api/employee-records/clothing/<int:item_id>', methods=['PUT', 'DELETE', 'OPTIONS'])
@token_required
@role_required('admin')
def manage_clothing(item_id):
    if request.method == 'OPTIONS':
        return '', 204
    item = EmployeeClothing.query.get_or_404(item_id)
    if request.method == 'DELETE':
        db.session.delete(item)
        db.session.commit()
        return jsonify({'success': True, 'message': 'Registro eliminado'}), 200
    # PUT
    try:
        data = request.get_json() or {}
        if 'date' in data:
            item.date = parse_date(data['date'])
        if 'product' in data:
            item.product = data['product'].strip()
        if 'value' in data:
            item.value = float(data['value'])
        if 'discount_pct' in data:
            item.discount_pct = float(data['discount_pct'])
        item.final_value = round(item.value * (1 - item.discount_pct / 100), 2)
        if 'notes' in data:
            item.notes = data['notes'].strip() or None
        db.session.commit()
        return jsonify({'success': True, 'item': item.to_dict()}), 200
    except Exception as e:
        db.session.rollback()
        logger.error(f"Error actualizando ropa {item_id}: {e}")
        return jsonify({'success': False, 'message': 'Error al actualizar'}), 500


# ─────────────────────────────────────────────
#  PRÉSTAMOS
# ─────────────────────────────────────────────

@bp.route('/api/employee-records/loans', methods=['GET', 'OPTIONS'])
@token_required
def list_loans():
    if request.method == 'OPTIONS':
        return '', 204
    try:
        if _is_admin():
            employee_id = request.args.get('employee_id')
            q = EmployeeLoan.query
            if employee_id:
                q = q.filter_by(employee_id=int(employee_id))
        else:
            q = EmployeeLoan.query.filter_by(employee_id=_current_user_id())

        items = q.order_by(EmployeeLoan.date.desc()).all()
        total = sum(i.amount for i in items)
        return jsonify({
            'success': True,
            'items': [i.to_dict() for i in items],
            'total_acumulado': total
        }), 200
    except Exception as e:
        logger.error(f"Error listando préstamos: {e}")
        return jsonify({'success': False, 'message': 'Error al obtener registros'}), 500


@bp.route('/api/employee-records/loans', methods=['POST', 'OPTIONS'])
@token_required
def create_loan():
    if request.method == 'OPTIONS':
        return '', 204
    try:
        data = request.get_json() or {}
        for f in ['date', 'amount']:
            if f not in data:
                return jsonify({'success': False, 'message': f'Campo requerido: {f}'}), 400

        if _is_admin() and data.get('employee_id'):
            employee_id = int(data['employee_id'])
        else:
            employee_id = _current_user_id()

        item = EmployeeLoan(
            employee_id=employee_id,
            date=parse_date(data['date']),
            amount=float(data['amount']),
            notes=data.get('notes', '').strip() or None
        )
        db.session.add(item)
        db.session.commit()
        return jsonify({'success': True, 'item': item.to_dict()}), 201
    except ValueError as e:
        return jsonify({'success': False, 'message': f'Dato inválido: {e}'}), 400
    except Exception as e:
        db.session.rollback()
        logger.error(f"Error creando préstamo: {e}")
        return jsonify({'success': False, 'message': 'Error al crear registro'}), 500


@bp.route('/api/employee-records/loans/<int:item_id>', methods=['PUT', 'DELETE', 'OPTIONS'])
@token_required
@role_required('admin')
def manage_loan(item_id):
    if request.method == 'OPTIONS':
        return '', 204
    item = EmployeeLoan.query.get_or_404(item_id)
    if request.method == 'DELETE':
        db.session.delete(item)
        db.session.commit()
        return jsonify({'success': True, 'message': 'Registro eliminado'}), 200
    try:
        data = request.get_json() or {}
        if 'date' in data:
            item.date = parse_date(data['date'])
        if 'amount' in data:
            item.amount = float(data['amount'])
        if 'notes' in data:
            item.notes = data['notes'].strip() or None
        db.session.commit()
        return jsonify({'success': True, 'item': item.to_dict()}), 200
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'message': 'Error al actualizar'}), 500


# ─────────────────────────────────────────────
#  PERMISOS / INCAPACIDADES
# ─────────────────────────────────────────────

@bp.route('/api/employee-records/permissions', methods=['GET', 'OPTIONS'])
@token_required
def list_permissions():
    if request.method == 'OPTIONS':
        return '', 204
    try:
        if _is_admin():
            employee_id = request.args.get('employee_id')
            q = EmployeePermission.query
            if employee_id:
                q = q.filter_by(employee_id=int(employee_id))
        else:
            q = EmployeePermission.query.filter_by(employee_id=_current_user_id())

        items = q.order_by(EmployeePermission.date.desc()).all()
        return jsonify({'success': True, 'items': [i.to_dict() for i in items]}), 200
    except Exception as e:
        logger.error(f"Error listando permisos: {e}")
        return jsonify({'success': False, 'message': 'Error al obtener registros'}), 500


@bp.route('/api/employee-records/permissions', methods=['POST', 'OPTIONS'])
@token_required
def create_permission():
    if request.method == 'OPTIONS':
        return '', 204
    try:
        data = request.get_json() or {}
        for f in ['date', 'type']:
            if f not in data:
                return jsonify({'success': False, 'message': f'Campo requerido: {f}'}), 400

        if data['type'] not in EmployeePermission.TYPES:
            return jsonify({'success': False, 'message': f'Tipo inválido. Use: {EmployeePermission.TYPES}'}), 400

        if _is_admin() and data.get('employee_id'):
            employee_id = int(data['employee_id'])
        else:
            employee_id = _current_user_id()

        item = EmployeePermission(
            employee_id=employee_id,
            date=parse_date(data['date']),
            type=data['type'],
            description=data.get('description', '').strip() or None,
            hours=float(data['hours']) if data.get('hours') else None
        )
        db.session.add(item)
        db.session.commit()
        return jsonify({'success': True, 'item': item.to_dict()}), 201
    except ValueError as e:
        return jsonify({'success': False, 'message': f'Dato inválido: {e}'}), 400
    except Exception as e:
        db.session.rollback()
        logger.error(f"Error creando permiso: {e}")
        return jsonify({'success': False, 'message': 'Error al crear registro'}), 500


@bp.route('/api/employee-records/permissions/<int:item_id>', methods=['PUT', 'DELETE', 'OPTIONS'])
@token_required
@role_required('admin')
def manage_permission(item_id):
    if request.method == 'OPTIONS':
        return '', 204
    item = EmployeePermission.query.get_or_404(item_id)
    if request.method == 'DELETE':
        db.session.delete(item)
        db.session.commit()
        return jsonify({'success': True, 'message': 'Registro eliminado'}), 200
    try:
        data = request.get_json() or {}
        if 'date' in data:
            item.date = parse_date(data['date'])
        if 'type' in data and data['type'] in EmployeePermission.TYPES:
            item.type = data['type']
        if 'description' in data:
            item.description = data['description'].strip() or None
        if 'hours' in data:
            item.hours = float(data['hours']) if data['hours'] else None
        db.session.commit()
        return jsonify({'success': True, 'item': item.to_dict()}), 200
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'message': 'Error al actualizar'}), 500


# ─────────────────────────────────────────────
#  VACACIONES
# ─────────────────────────────────────────────

@bp.route('/api/employee-records/vacations', methods=['GET', 'OPTIONS'])
@token_required
def list_vacations():
    if request.method == 'OPTIONS':
        return '', 204
    try:
        if _is_admin():
            employee_id = request.args.get('employee_id')
            q = EmployeeVacation.query
            if employee_id:
                q = q.filter_by(employee_id=int(employee_id))
        else:
            q = EmployeeVacation.query.filter_by(employee_id=_current_user_id())

        items = q.order_by(EmployeeVacation.start_date.desc()).all()
        total_days = sum(i.days for i in items)
        return jsonify({
            'success': True,
            'items': [i.to_dict() for i in items],
            'total_dias': total_days
        }), 200
    except Exception as e:
        logger.error(f"Error listando vacaciones: {e}")
        return jsonify({'success': False, 'message': 'Error al obtener registros'}), 500


@bp.route('/api/employee-records/vacations', methods=['POST', 'OPTIONS'])
@token_required
def create_vacation():
    if request.method == 'OPTIONS':
        return '', 204
    try:
        data = request.get_json() or {}
        for f in ['start_date', 'end_date']:
            if f not in data:
                return jsonify({'success': False, 'message': f'Campo requerido: {f}'}), 400

        start = parse_date(data['start_date'])
        end = parse_date(data['end_date'])
        if end < start:
            return jsonify({'success': False, 'message': 'La fecha de fin debe ser mayor o igual a la de inicio'}), 400

        days = (end - start).days + 1

        if _is_admin() and data.get('employee_id'):
            employee_id = int(data['employee_id'])
        else:
            employee_id = _current_user_id()

        item = EmployeeVacation(
            employee_id=employee_id,
            start_date=start,
            end_date=end,
            days=days,
            notes=data.get('notes', '').strip() or None
        )
        db.session.add(item)
        db.session.commit()
        return jsonify({'success': True, 'item': item.to_dict()}), 201
    except ValueError as e:
        return jsonify({'success': False, 'message': f'Dato inválido: {e}'}), 400
    except Exception as e:
        db.session.rollback()
        logger.error(f"Error creando vacaciones: {e}")
        return jsonify({'success': False, 'message': 'Error al crear registro'}), 500


@bp.route('/api/employee-records/vacations/<int:item_id>', methods=['PUT', 'DELETE', 'OPTIONS'])
@token_required
@role_required('admin')
def manage_vacation(item_id):
    if request.method == 'OPTIONS':
        return '', 204
    item = EmployeeVacation.query.get_or_404(item_id)
    if request.method == 'DELETE':
        db.session.delete(item)
        db.session.commit()
        return jsonify({'success': True, 'message': 'Registro eliminado'}), 200
    try:
        data = request.get_json() or {}
        if 'start_date' in data:
            item.start_date = parse_date(data['start_date'])
        if 'end_date' in data:
            item.end_date = parse_date(data['end_date'])
        item.days = (item.end_date - item.start_date).days + 1
        if 'notes' in data:
            item.notes = data['notes'].strip() or None
        db.session.commit()
        return jsonify({'success': True, 'item': item.to_dict()}), 200
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'message': 'Error al actualizar'}), 500


# ─────────────────────────────────────────────
#  PAGOS
# ─────────────────────────────────────────────

@bp.route('/api/employee-records/payments', methods=['GET', 'OPTIONS'])
@token_required
def list_payments():
    if request.method == 'OPTIONS':
        return '', 204
    try:
        if _is_admin():
            employee_id = request.args.get('employee_id')
            q = EmployeePayment.query
            if employee_id:
                q = q.filter_by(employee_id=int(employee_id))
        else:
            q = EmployeePayment.query.filter_by(employee_id=_current_user_id())

        items = q.order_by(EmployeePayment.date.desc()).all()
        total = sum(i.amount for i in items)
        return jsonify({
            'success': True,
            'items': [i.to_dict() for i in items],
            'total_pagado': total
        }), 200
    except Exception as e:
        logger.error(f"Error listando pagos: {e}")
        return jsonify({'success': False, 'message': 'Error al obtener registros'}), 500


@bp.route('/api/employee-records/payments', methods=['POST', 'OPTIONS'])
@token_required
@role_required('admin')
def create_payment():
    """Solo admin puede registrar pagos"""
    if request.method == 'OPTIONS':
        return '', 204
    try:
        data = request.get_json() or {}
        for f in ['date', 'amount', 'type', 'employee_id']:
            if f not in data:
                return jsonify({'success': False, 'message': f'Campo requerido: {f}'}), 400

        if data['type'] not in EmployeePayment.TYPES:
            return jsonify({'success': False, 'message': f'Tipo inválido. Use: {EmployeePayment.TYPES}'}), 400

        item = EmployeePayment(
            employee_id=int(data['employee_id']),
            date=parse_date(data['date']),
            type=data['type'],
            amount=float(data['amount']),
            notes=data.get('notes', '').strip() or None
        )
        db.session.add(item)
        db.session.commit()
        return jsonify({'success': True, 'item': item.to_dict()}), 201
    except ValueError as e:
        return jsonify({'success': False, 'message': f'Dato inválido: {e}'}), 400
    except Exception as e:
        db.session.rollback()
        logger.error(f"Error creando pago: {e}")
        return jsonify({'success': False, 'message': 'Error al crear registro'}), 500


@bp.route('/api/employee-records/payments/<int:item_id>', methods=['PUT', 'DELETE', 'OPTIONS'])
@token_required
@role_required('admin')
def manage_payment(item_id):
    if request.method == 'OPTIONS':
        return '', 204
    item = EmployeePayment.query.get_or_404(item_id)
    if request.method == 'DELETE':
        db.session.delete(item)
        db.session.commit()
        return jsonify({'success': True, 'message': 'Registro eliminado'}), 200
    try:
        data = request.get_json() or {}
        if 'date' in data:
            item.date = parse_date(data['date'])
        if 'type' in data and data['type'] in EmployeePayment.TYPES:
            item.type = data['type']
        if 'amount' in data:
            item.amount = float(data['amount'])
        if 'notes' in data:
            item.notes = data['notes'].strip() or None
        db.session.commit()
        return jsonify({'success': True, 'item': item.to_dict()}), 200
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'message': 'Error al actualizar'}), 500


# ─────────────────────────────────────────────
#  RESUMEN GENERAL (solo admin)
# ─────────────────────────────────────────────

@bp.route('/api/employee-records/summary', methods=['GET', 'OPTIONS'])
@token_required
@role_required('admin')
def summary():
    """Resumen de todos los registros agrupados por empleada"""
    if request.method == 'OPTIONS':
        return '', 204
    try:
        employees = User.query.filter_by(role='sales', is_active=True).all()
        result = []
        for emp in employees:
            clothing = EmployeeClothing.query.filter_by(employee_id=emp.id).all()
            loans = EmployeeLoan.query.filter_by(employee_id=emp.id).all()
            perms = EmployeePermission.query.filter_by(employee_id=emp.id).all()
            vacs = EmployeeVacation.query.filter_by(employee_id=emp.id).all()
            payments = EmployeePayment.query.filter_by(employee_id=emp.id).all()

            result.append({
                'employee_id': emp.id,
                'employee_name': emp.name,
                'employee_email': emp.email,
                'clothing': {
                    'count': len(clothing),
                    'total': sum(c.final_value for c in clothing)
                },
                'loans': {
                    'count': len(loans),
                    'total': sum(l.amount for l in loans)
                },
                'permissions': {
                    'count': len(perms),
                    'by_type': {t: sum(1 for p in perms if p.type == t) for t in EmployeePermission.TYPES}
                },
                'vacations': {
                    'count': len(vacs),
                    'total_days': sum(v.days for v in vacs)
                },
                'payments': {
                    'count': len(payments),
                    'total': sum(p.amount for p in payments)
                }
            })

        return jsonify({'success': True, 'employees': result}), 200
    except Exception as e:
        logger.error(f"Error en resumen: {e}")
        return jsonify({'success': False, 'message': 'Error al obtener resumen'}), 500
