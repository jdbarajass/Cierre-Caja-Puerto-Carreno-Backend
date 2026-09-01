"""
Rutas de Cuentas de Recompras.
Acceso: solo admin.
"""
from flask import Blueprint, request, jsonify
from datetime import datetime, date as dt_date
import calendar
import logging

from app.middlewares.auth import token_required, get_current_user
from app.models.user import db
from app.models.repurchase import RepurchaseEntry
from app.models.repurchase_purchase import RepurchasePurchase

logger = logging.getLogger(__name__)
bp = Blueprint('repurchase', __name__)

MONEY_FIELDS = ['efectivo', 'datafono', 'qr', 'daviplata', 'nequi', 'bbva',
                'valor_no_enviado', 'sobrante_mes_anterior']

PURCHASE_CATEGORIES = ('ropa', 'operacional')


def _require_admin():
    role = get_current_user().get('role')
    if role != 'admin':
        return jsonify({'success': False, 'message': 'Solo el administrador puede acceder'}), 403
    return None


def parse_date(value):
    return datetime.strptime(value, '%Y-%m-%d').date()


def _month_range(year, month):
    """Devuelve (inicio, fin) para un mes dado."""
    last_day = calendar.monthrange(year, month)[1]
    return dt_date(year, month, 1), dt_date(year, month, last_day)


# ─────────────────────────────────────────────
#  LISTAR
# ─────────────────────────────────────────────

@bp.route('/api/repurchase', methods=['GET', 'OPTIONS'])
@token_required
def list_entries():
    if request.method == 'OPTIONS':
        return '', 204

    err = _require_admin()
    if err:
        return err

    try:
        year  = request.args.get('year',  type=int)
        month = request.args.get('month', type=int)

        q = RepurchaseEntry.query

        # Filtro por rango de fechas en lugar de db.extract (no disponible en Flask-SQLAlchemy)
        if year and month:
            start, end = _month_range(year, month)
            q = q.filter(RepurchaseEntry.date >= start, RepurchaseEntry.date <= end)
        elif year:
            q = q.filter(RepurchaseEntry.date >= dt_date(year, 1, 1),
                         RepurchaseEntry.date <= dt_date(year, 12, 31))

        entries = q.order_by(RepurchaseEntry.date.asc(), RepurchaseEntry.id.asc()).all()

        totals = {
            'efectivo':          sum(e.efectivo   for e in entries),
            'datafono':          sum(e.datafono   for e in entries),
            'qr':                sum(e.qr         for e in entries),
            'daviplata':         sum(e.daviplata  for e in entries),
            'nequi':             sum(e.nequi      for e in entries),
            'bbva':              sum(e.bbva       for e in entries),
            'total_enviado':     sum(e.total_enviado for e in entries),
            'sobrante_acumulado':sum(e.sobrante_mes_anterior for e in entries),
        }
        # Comisión 4‰ sobre el total enviado
        totals['fee_4mil']      = round(totals['total_enviado'] * 4 / 1000)
        totals['valor_sobrante']= totals['total_enviado'] - totals['fee_4mil']

        return jsonify({
            'success': True,
            'entries': [e.to_dict() for e in entries],
            'totals':  totals,
            'count':   len(entries)
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

    err = _require_admin()
    if err:
        return err

    try:
        data = request.get_json() or {}

        if 'date' not in data:
            return jsonify({'success': False, 'message': 'El campo date es requerido'}), 400

        fecha_compra = None
        if data.get('fecha_compra'):
            fecha_compra = parse_date(data['fecha_compra'])

        entry = RepurchaseEntry(
            date=parse_date(data['date']),
            descripcion=data.get('descripcion', '').strip() or 'Recompra Jhonatan',
            valor_no_enviado=float(data.get('valor_no_enviado', 0)),
            efectivo=float(data.get('efectivo', 0)),
            datafono=float(data.get('datafono', 0)),
            qr=float(data.get('qr', 0)),
            daviplata=float(data.get('daviplata', 0)),
            nequi=float(data.get('nequi', 0)),
            bbva=float(data.get('bbva', 0)),
            sobrante_mes_anterior=float(data.get('sobrante_mes_anterior', 0)),
            fecha_compra=fecha_compra,
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

    err = _require_admin()
    if err:
        return err

    entry = RepurchaseEntry.query.get_or_404(entry_id)

    try:
        data = request.get_json() or {}

        if 'date' in data:
            entry.date = parse_date(data['date'])
        if 'descripcion' in data:
            entry.descripcion = data['descripcion'].strip() or 'Recompra Jhonatan'
        if 'fecha_compra' in data:
            entry.fecha_compra = parse_date(data['fecha_compra']) if data['fecha_compra'] else None

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

    err = _require_admin()
    if err:
        return err

    entry = RepurchaseEntry.query.get_or_404(entry_id)
    db.session.delete(entry)
    db.session.commit()
    return jsonify({'success': True, 'message': 'Registro eliminado'}), 200


# ─────────────────────────────────────────────
#  RESUMEN POR MES
# ─────────────────────────────────────────────

@bp.route('/api/repurchase/monthly-summary', methods=['GET', 'OPTIONS'])
@token_required
def monthly_summary():
    if request.method == 'OPTIONS':
        return '', 204

    err = _require_admin()
    if err:
        return err

    try:
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
            m['efectivo']            += e.efectivo
            m['datafono']            += e.datafono
            m['qr']                  += e.qr
            m['daviplata']           += e.daviplata
            m['nequi']               += e.nequi
            m['bbva']                += e.bbva
            m['total_enviado']       += e.total_enviado
            m['sobrante_mes_anterior'] += e.sobrante_mes_anterior
            m['valor_no_enviado']    = e.valor_no_enviado
            m['count']               += 1

        # Calcular fee 4‰ y sobrante por mes
        for m in months.values():
            m['fee_4mil']       = round(m['total_enviado'] * 4 / 1000)
            m['valor_sobrante'] = m['total_enviado'] - m['fee_4mil']

        return jsonify({'success': True, 'months': list(months.values())}), 200

    except Exception as e:
        logger.error(f"Error en resumen mensual recompras: {e}")
        return jsonify({'success': False, 'message': 'Error al obtener resumen'}), 500


# ─────────────────────────────────────────────
#  COMPRAS REALIZADAS POR EL SOCIO
# ─────────────────────────────────────────────

@bp.route('/api/repurchase/purchases', methods=['GET', 'OPTIONS'])
@token_required
def list_purchases():
    """Lista las compras hechas por el socio, con filtro opcional por mes/año."""
    if request.method == 'OPTIONS':
        return '', 204

    err = _require_admin()
    if err:
        return err

    try:
        year  = request.args.get('year',  type=int)
        month = request.args.get('month', type=int)

        q = RepurchasePurchase.query
        if year and month:
            start, end = _month_range(year, month)
            q = q.filter(RepurchasePurchase.date >= start, RepurchasePurchase.date <= end)
        elif year:
            q = q.filter(RepurchasePurchase.date >= dt_date(year, 1, 1),
                         RepurchasePurchase.date <= dt_date(year, 12, 31))

        purchases = q.order_by(RepurchasePurchase.date.asc(), RepurchasePurchase.id.asc()).all()
        total = sum(p.amount for p in purchases)
        total_ropa = sum(p.amount for p in purchases if p.category == 'ropa')
        total_operacional = sum(p.amount for p in purchases if p.category == 'operacional')

        return jsonify({
            'success': True,
            'purchases': [p.to_dict() for p in purchases],
            'total_compras': total,
            'total_ropa': total_ropa,
            'total_operacional': total_operacional,
            'count': len(purchases)
        }), 200

    except Exception as e:
        logger.error(f"Error listando compras: {e}")
        return jsonify({'success': False, 'message': 'Error al obtener compras'}), 500


@bp.route('/api/repurchase/purchases', methods=['POST', 'OPTIONS'])
@token_required
def create_purchase():
    """Registra una compra realizada por el socio."""
    if request.method == 'OPTIONS':
        return '', 204

    err = _require_admin()
    if err:
        return err

    try:
        data = request.get_json() or {}

        for f in ['date', 'store', 'amount']:
            if not data.get(f):
                return jsonify({'success': False, 'message': f'Campo requerido: {f}'}), 400

        category = data.get('category', 'ropa')
        if category not in PURCHASE_CATEGORIES:
            return jsonify({'success': False, 'message': f'category debe ser una de: {PURCHASE_CATEGORIES}'}), 400

        purchase = RepurchasePurchase(
            date=parse_date(data['date']),
            store=data['store'].strip(),
            amount=float(data['amount']),
            category=category,
            notes=data.get('notes', '').strip() or None,
            created_by=get_current_user().get('userId')
        )
        db.session.add(purchase)
        db.session.commit()
        logger.info(f"Compra registrada id={purchase.id}")
        return jsonify({'success': True, 'purchase': purchase.to_dict()}), 201

    except ValueError as e:
        return jsonify({'success': False, 'message': f'Dato inválido: {e}'}), 400
    except Exception as e:
        db.session.rollback()
        logger.error(f"Error creando compra: {e}")
        return jsonify({'success': False, 'message': 'Error al crear compra'}), 500


@bp.route('/api/repurchase/purchases/<int:purchase_id>', methods=['PUT', 'DELETE', 'OPTIONS'])
@token_required
def manage_purchase(purchase_id):
    """Edita o elimina una compra."""
    if request.method == 'OPTIONS':
        return '', 204

    err = _require_admin()
    if err:
        return err

    purchase = RepurchasePurchase.query.get_or_404(purchase_id)

    if request.method == 'DELETE':
        db.session.delete(purchase)
        db.session.commit()
        return jsonify({'success': True, 'message': 'Compra eliminada'}), 200

    try:
        data = request.get_json() or {}
        if 'date' in data and data['date']:
            purchase.date = parse_date(data['date'])
        if 'store' in data and data['store']:
            purchase.store = data['store'].strip()
        if 'amount' in data:
            purchase.amount = float(data['amount'])
        if 'category' in data:
            if data['category'] not in PURCHASE_CATEGORIES:
                return jsonify({'success': False, 'message': f'category debe ser una de: {PURCHASE_CATEGORIES}'}), 400
            purchase.category = data['category']
        if 'notes' in data:
            purchase.notes = data['notes'].strip() or None
        db.session.commit()
        return jsonify({'success': True, 'purchase': purchase.to_dict()}), 200

    except Exception as e:
        db.session.rollback()
        logger.error(f"Error actualizando compra {purchase_id}: {e}")
        return jsonify({'success': False, 'message': 'Error al actualizar'}), 500
