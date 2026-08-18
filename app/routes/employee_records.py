"""
Rutas de Control de Empleadas.
El campo nombre_empleada es texto libre — identifica a la persona sin depender de la sesión.
Reglas:
- Cualquier usuario autenticado puede CREAR y VER registros
- Solo admin puede EDITAR y ELIMINAR
"""
from flask import Blueprint, request, jsonify
from datetime import datetime
import logging

from app.middlewares.auth import token_required, get_current_user
from app.models.user import db
from app.models.employee_records import (
    EmployeeClothing, EmployeeLoan,
    EmployeePermission, EmployeeVacation, EmployeePayment
)
from app.utils.employee_names import CANONICAL_NAMES, group_key_for

logger = logging.getLogger(__name__)
bp = Blueprint('employee_records', __name__)


def parse_date(value):
    return datetime.strptime(value, '%Y-%m-%d').date()


def _is_admin():
    return get_current_user().get('role') == 'admin'


def _require_name(data):
    name = (data.get('nombre_empleada') or '').strip()
    if not name:
        return None, (jsonify({'success': False, 'message': 'El campo nombre_empleada es requerido'}), 400)
    return name, None


# ─────────────────────────────────────────────
#  ROPA
# ─────────────────────────────────────────────

@bp.route('/api/employee-records/clothing', methods=['GET', 'OPTIONS'])
@token_required
def list_clothing():
    if request.method == 'OPTIONS':
        return '', 204
    try:
        q = EmployeeClothing.query
        nombre = request.args.get('nombre_empleada')
        if nombre:
            q = q.filter(EmployeeClothing.nombre_empleada.ilike(f'%{nombre}%'))
        items = q.order_by(EmployeeClothing.date.desc()).all()
        total = sum(i.final_value for i in items)
        return jsonify({'success': True, 'items': [i.to_dict() for i in items], 'total_acumulado': total}), 200
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
        nombre, err = _require_name(data)
        if err: return err
        for f in ['date', 'product', 'value', 'discount_pct']:
            if f not in data:
                return jsonify({'success': False, 'message': f'Campo requerido: {f}'}), 400

        value = float(data['value'])
        discount_pct = float(data['discount_pct'])
        final_value = round(value * (1 - discount_pct / 100), 2)

        item = EmployeeClothing(
            nombre_empleada=nombre,
            date=parse_date(data['date']),
            product=data['product'].strip(),
            value=value,
            discount_pct=discount_pct,
            final_value=final_value,
            notes=data.get('notes', '').strip() or None
        )
        db.session.add(item)
        db.session.commit()
        return jsonify({'success': True, 'item': item.to_dict()}), 201
    except ValueError as e:
        return jsonify({'success': False, 'message': f'Dato inválido: {e}'}), 400
    except Exception as e:
        db.session.rollback()
        logger.error(f"Error creando ropa: {e}")
        return jsonify({'success': False, 'message': 'Error al crear registro'}), 500


@bp.route('/api/employee-records/clothing/<int:item_id>', methods=['PUT', 'DELETE', 'OPTIONS'])
@token_required
def manage_clothing(item_id):
    if request.method == 'OPTIONS':
        return '', 204
    if not _is_admin():
        return jsonify({'success': False, 'message': 'Solo admin puede editar o eliminar'}), 403
    item = EmployeeClothing.query.get_or_404(item_id)
    if request.method == 'DELETE':
        db.session.delete(item)
        db.session.commit()
        return jsonify({'success': True}), 200
    try:
        data = request.get_json() or {}
        if 'nombre_empleada' in data and data['nombre_empleada'].strip():
            item.nombre_empleada = data['nombre_empleada'].strip()
        if 'date' in data: item.date = parse_date(data['date'])
        if 'product' in data: item.product = data['product'].strip()
        if 'value' in data: item.value = float(data['value'])
        if 'discount_pct' in data: item.discount_pct = float(data['discount_pct'])
        item.final_value = round(item.value * (1 - item.discount_pct / 100), 2)
        if 'notes' in data: item.notes = data['notes'].strip() or None
        db.session.commit()
        return jsonify({'success': True, 'item': item.to_dict()}), 200
    except Exception as e:
        db.session.rollback()
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
        q = EmployeeLoan.query
        nombre = request.args.get('nombre_empleada')
        if nombre:
            q = q.filter(EmployeeLoan.nombre_empleada.ilike(f'%{nombre}%'))
        items = q.order_by(EmployeeLoan.date.desc()).all()
        return jsonify({'success': True, 'items': [i.to_dict() for i in items],
                        'total_acumulado': sum(i.amount for i in items)}), 200
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
        nombre, err = _require_name(data)
        if err: return err
        for f in ['date', 'amount']:
            if f not in data:
                return jsonify({'success': False, 'message': f'Campo requerido: {f}'}), 400
        item = EmployeeLoan(nombre_empleada=nombre, date=parse_date(data['date']),
                            amount=float(data['amount']), notes=data.get('notes', '').strip() or None)
        db.session.add(item)
        db.session.commit()
        return jsonify({'success': True, 'item': item.to_dict()}), 201
    except Exception as e:
        db.session.rollback()
        logger.error(f"Error creando préstamo: {e}")
        return jsonify({'success': False, 'message': 'Error al crear registro'}), 500


@bp.route('/api/employee-records/loans/<int:item_id>', methods=['PUT', 'DELETE', 'OPTIONS'])
@token_required
def manage_loan(item_id):
    if request.method == 'OPTIONS':
        return '', 204
    if not _is_admin():
        return jsonify({'success': False, 'message': 'Solo admin puede editar o eliminar'}), 403
    item = EmployeeLoan.query.get_or_404(item_id)
    if request.method == 'DELETE':
        db.session.delete(item); db.session.commit()
        return jsonify({'success': True}), 200
    try:
        data = request.get_json() or {}
        if 'nombre_empleada' in data and data['nombre_empleada'].strip():
            item.nombre_empleada = data['nombre_empleada'].strip()
        if 'date' in data: item.date = parse_date(data['date'])
        if 'amount' in data: item.amount = float(data['amount'])
        if 'notes' in data: item.notes = data['notes'].strip() or None
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
        q = EmployeePermission.query
        nombre = request.args.get('nombre_empleada')
        if nombre:
            q = q.filter(EmployeePermission.nombre_empleada.ilike(f'%{nombre}%'))
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
        nombre, err = _require_name(data)
        if err: return err
        for f in ['date', 'type']:
            if f not in data:
                return jsonify({'success': False, 'message': f'Campo requerido: {f}'}), 400
        if data['type'] not in EmployeePermission.TYPES:
            return jsonify({'success': False, 'message': f'Tipo inválido'}), 400
        item = EmployeePermission(
            nombre_empleada=nombre, date=parse_date(data['date']), type=data['type'],
            description=data.get('description', '').strip() or None,
            hours=float(data['hours']) if data.get('hours') else None
        )
        db.session.add(item); db.session.commit()
        return jsonify({'success': True, 'item': item.to_dict()}), 201
    except Exception as e:
        db.session.rollback()
        logger.error(f"Error creando permiso: {e}")
        return jsonify({'success': False, 'message': 'Error al crear registro'}), 500


@bp.route('/api/employee-records/permissions/<int:item_id>', methods=['PUT', 'DELETE', 'OPTIONS'])
@token_required
def manage_permission(item_id):
    if request.method == 'OPTIONS':
        return '', 204
    if not _is_admin():
        return jsonify({'success': False, 'message': 'Solo admin puede editar o eliminar'}), 403
    item = EmployeePermission.query.get_or_404(item_id)
    if request.method == 'DELETE':
        db.session.delete(item); db.session.commit()
        return jsonify({'success': True}), 200
    try:
        data = request.get_json() or {}
        if 'nombre_empleada' in data and data['nombre_empleada'].strip():
            item.nombre_empleada = data['nombre_empleada'].strip()
        if 'date' in data: item.date = parse_date(data['date'])
        if 'type' in data and data['type'] in EmployeePermission.TYPES: item.type = data['type']
        if 'description' in data: item.description = data['description'].strip() or None
        if 'hours' in data: item.hours = float(data['hours']) if data['hours'] else None
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
        q = EmployeeVacation.query
        nombre = request.args.get('nombre_empleada')
        if nombre:
            q = q.filter(EmployeeVacation.nombre_empleada.ilike(f'%{nombre}%'))
        items = q.order_by(EmployeeVacation.start_date.desc()).all()
        return jsonify({'success': True, 'items': [i.to_dict() for i in items],
                        'total_dias': sum(i.days for i in items)}), 200
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
        nombre, err = _require_name(data)
        if err: return err
        start = parse_date(data['start_date'])
        end = parse_date(data['end_date'])
        if end < start:
            return jsonify({'success': False, 'message': 'Fecha fin debe ser >= fecha inicio'}), 400
        item = EmployeeVacation(
            nombre_empleada=nombre, start_date=start, end_date=end,
            days=(end - start).days + 1, notes=data.get('notes', '').strip() or None
        )
        db.session.add(item); db.session.commit()
        return jsonify({'success': True, 'item': item.to_dict()}), 201
    except Exception as e:
        db.session.rollback()
        logger.error(f"Error creando vacaciones: {e}")
        return jsonify({'success': False, 'message': 'Error al crear registro'}), 500


@bp.route('/api/employee-records/vacations/<int:item_id>', methods=['PUT', 'DELETE', 'OPTIONS'])
@token_required
def manage_vacation(item_id):
    if request.method == 'OPTIONS':
        return '', 204
    if not _is_admin():
        return jsonify({'success': False, 'message': 'Solo admin puede editar o eliminar'}), 403
    item = EmployeeVacation.query.get_or_404(item_id)
    if request.method == 'DELETE':
        db.session.delete(item); db.session.commit()
        return jsonify({'success': True}), 200
    try:
        data = request.get_json() or {}
        if 'nombre_empleada' in data and data['nombre_empleada'].strip():
            item.nombre_empleada = data['nombre_empleada'].strip()
        if 'start_date' in data: item.start_date = parse_date(data['start_date'])
        if 'end_date' in data: item.end_date = parse_date(data['end_date'])
        item.days = (item.end_date - item.start_date).days + 1
        if 'notes' in data: item.notes = data['notes'].strip() or None
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
        q = EmployeePayment.query
        nombre = request.args.get('nombre_empleada')
        if nombre:
            q = q.filter(EmployeePayment.nombre_empleada.ilike(f'%{nombre}%'))
        items = q.order_by(EmployeePayment.date.desc()).all()
        return jsonify({'success': True, 'items': [i.to_dict() for i in items],
                        'total_pagado': sum(i.amount for i in items)}), 200
    except Exception as e:
        logger.error(f"Error listando pagos: {e}")
        return jsonify({'success': False, 'message': 'Error al obtener registros'}), 500


@bp.route('/api/employee-records/payments', methods=['POST', 'OPTIONS'])
@token_required
def create_payment():
    if request.method == 'OPTIONS':
        return '', 204
    if not _is_admin():
        return jsonify({'success': False, 'message': 'Solo admin puede registrar pagos'}), 403
    try:
        data = request.get_json() or {}
        nombre, err = _require_name(data)
        if err: return err
        for f in ['date', 'amount', 'type']:
            if f not in data:
                return jsonify({'success': False, 'message': f'Campo requerido: {f}'}), 400
        if data['type'] not in EmployeePayment.TYPES:
            return jsonify({'success': False, 'message': 'Tipo inválido'}), 400
        item = EmployeePayment(
            nombre_empleada=nombre, date=parse_date(data['date']),
            type=data['type'], amount=float(data['amount']),
            notes=data.get('notes', '').strip() or None
        )
        db.session.add(item); db.session.commit()
        return jsonify({'success': True, 'item': item.to_dict()}), 201
    except Exception as e:
        db.session.rollback()
        logger.error(f"Error creando pago: {e}")
        return jsonify({'success': False, 'message': 'Error al crear registro'}), 500


@bp.route('/api/employee-records/payments/<int:item_id>', methods=['PUT', 'DELETE', 'OPTIONS'])
@token_required
def manage_payment(item_id):
    if request.method == 'OPTIONS':
        return '', 204
    if not _is_admin():
        return jsonify({'success': False, 'message': 'Solo admin puede editar o eliminar'}), 403
    item = EmployeePayment.query.get_or_404(item_id)
    if request.method == 'DELETE':
        db.session.delete(item); db.session.commit()
        return jsonify({'success': True}), 200
    try:
        data = request.get_json() or {}
        if 'nombre_empleada' in data and data['nombre_empleada'].strip():
            item.nombre_empleada = data['nombre_empleada'].strip()
        if 'date' in data: item.date = parse_date(data['date'])
        if 'type' in data and data['type'] in EmployeePayment.TYPES: item.type = data['type']
        if 'amount' in data: item.amount = float(data['amount'])
        if 'notes' in data: item.notes = data['notes'].strip() or None
        db.session.commit()
        return jsonify({'success': True, 'item': item.to_dict()}), 200
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'message': 'Error al actualizar'}), 500


# ─────────────────────────────────────────────
#  RESUMEN POR EMPLEADA
# ─────────────────────────────────────────────

@bp.route('/api/employee-records/summary', methods=['GET', 'OPTIONS'])
@token_required
def summary():
    if request.method == 'OPTIONS':
        return '', 204
    if not _is_admin():
        return jsonify({'success': False, 'message': 'Solo admin puede ver el resumen'}), 403
    try:
        # Obtener todos los nombres únicos
        nombres = set()
        for model in [EmployeeClothing, EmployeeLoan, EmployeePermission,
                      EmployeeVacation, EmployeePayment]:
            for row in db.session.query(model.nombre_empleada).distinct():
                nombres.add(row[0])

        result = []
        for nombre in sorted(nombres):
            clothing = EmployeeClothing.query.filter_by(nombre_empleada=nombre).all()
            loans = EmployeeLoan.query.filter_by(nombre_empleada=nombre).all()
            perms = EmployeePermission.query.filter_by(nombre_empleada=nombre).all()
            vacs = EmployeeVacation.query.filter_by(nombre_empleada=nombre).all()
            payments = EmployeePayment.query.filter_by(nombre_empleada=nombre).all()
            result.append({
                'nombre_empleada': nombre,
                'clothing': {'count': len(clothing), 'total': sum(c.final_value for c in clothing)},
                'loans': {'count': len(loans), 'total': sum(l.amount for l in loans)},
                'permissions': {'count': len(perms),
                                'by_type': {t: sum(1 for p in perms if p.type == t)
                                            for t in EmployeePermission.TYPES}},
                'vacations': {'count': len(vacs), 'total_days': sum(v.days for v in vacs)},
                'payments': {'count': len(payments), 'total': sum(p.amount for p in payments)},
            })
        return jsonify({'success': True, 'employees': result}), 200
    except Exception as e:
        logger.error(f"Error en resumen: {e}")
        return jsonify({'success': False, 'message': 'Error al obtener resumen'}), 500


# ─────────────────────────────────────────────
#  NORMALIZACIÓN DE NOMBRES (una sola vez, mantenimiento)
# ─────────────────────────────────────────────

@bp.route('/api/employee-records/normalize-names', methods=['POST', 'OPTIONS'])
@token_required
def normalize_names():
    """
    Unifica variantes/typos historicos de nombre_empleada (ej: "monika vargas")
    hacia los nombres canonicos ("Mónica Vargas" / "Rita Infante").
    Por defecto corre en modo dry-run (no guarda). Usar ?apply=true para aplicar.
    """
    if request.method == 'OPTIONS':
        return '', 204
    if not _is_admin():
        return jsonify({'success': False, 'message': 'Solo admin puede ejecutar esta acción'}), 403
    try:
        apply_changes = request.args.get('apply', '').lower() == 'true'
        models = [EmployeeClothing, EmployeeLoan, EmployeePermission, EmployeeVacation, EmployeePayment]

        changes = []
        unmatched = set()

        for model in models:
            rows = model.query.all()
            for row in rows:
                key = group_key_for(row.nombre_empleada)
                if key is None:
                    unmatched.add(row.nombre_empleada)
                    continue
                canonical = CANONICAL_NAMES[key]
                if row.nombre_empleada != canonical:
                    changes.append({
                        'table': model.__tablename__, 'id': row.id,
                        'from': row.nombre_empleada, 'to': canonical,
                    })
                    if apply_changes:
                        row.nombre_empleada = canonical

        if apply_changes:
            db.session.commit()

        return jsonify({
            'success': True,
            'applied': apply_changes,
            'changes_count': len(changes),
            'changes': changes,
            'unmatched_names': sorted(unmatched),
        }), 200
    except Exception as e:
        db.session.rollback()
        logger.error(f"Error normalizando nombres: {e}")
        return jsonify({'success': False, 'message': 'Error al normalizar nombres'}), 500
