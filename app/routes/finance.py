"""
Fase 4 de docs/PLAN_CUENTAS_DIARIAS.md: configuración financiera por tienda e
incentivos por meta. Solo admin, por tienda (header X-Store).
"""
import logging
from datetime import date

from flask import Blueprint, request, jsonify

from app.middlewares.auth import token_required, get_current_user
from app.models.user import db
from app.models.expense import Expense, EXPENSE_METHODS, OUT_CATEGORIES, ACCOUNT_MODES
from app.models.incentive import IncentiveRule, THRESHOLDS
from app.routes.expenses import _sync_expense_account_movements, ExpenseError
from app.services import finance_settings
from app.stores import get_current_store
from app.utils.timezone import get_colombia_now

logger = logging.getLogger(__name__)
bp = Blueprint('finance', __name__)

MONTHS_ES = ['enero', 'febrero', 'marzo', 'abril', 'mayo', 'junio', 'julio',
             'agosto', 'septiembre', 'octubre', 'noviembre', 'diciembre']
PAID_MARKER = 'auto:incentivo:{rule}:{period}'

# Plantilla del Excel (INCENTIVO 1 = $200.000 + $100.000; INCENTIVO 2 = $100.000 + $50.000)
INCENTIVES_TEMPLATE = [
    {'name': 'Incentivo 1 empleadas (pasar la META 1)', 'amount': 300000, 'threshold': 'meta1', 'category': 'sueldo'},
    {'name': 'Incentivo 2 empleadas (pasar la META 2)', 'amount': 150000, 'threshold': 'meta2', 'category': 'sueldo'},
]


def _require_admin():
    if get_current_user().get('role') != 'admin':
        return jsonify({'success': False, 'message': 'Solo el administrador puede acceder'}), 403
    return None


# ─────────────────────────────────────────────
#  Configuración
# ─────────────────────────────────────────────

@bp.route('/api/finance-settings', methods=['GET', 'PUT', 'OPTIONS'])
@token_required
def settings():
    if request.method == 'OPTIONS':
        return '', 204
    err = _require_admin()
    if err:
        return err
    store = get_current_store()
    if request.method == 'GET':
        return jsonify({'success': True, 'settings': finance_settings.get_settings(store),
                        'defaults': finance_settings.DEFAULTS}), 200
    try:
        saved = finance_settings.save_settings(store, request.get_json() or {})
        from app.services.seller_goals import clear_cache
        clear_cache()  # la meta de la tienda depende del % de crecimiento
        return jsonify({'success': True, 'settings': saved}), 200
    except ValueError as e:
        return jsonify({'success': False, 'message': str(e)}), 400


# ─────────────────────────────────────────────
#  Incentivos
# ─────────────────────────────────────────────

def _apply_rule(rule, data, creating):
    if creating or 'name' in data:
        rule.name = (data.get('name') or '').strip()
    if not rule.name:
        raise ExpenseError('El nombre es obligatorio')
    if creating or 'amount' in data:
        try:
            rule.amount = float(data.get('amount') or 0)
        except (TypeError, ValueError):
            raise ExpenseError('Valor inválido')
    if rule.amount <= 0:
        raise ExpenseError('El valor debe ser mayor que cero')
    if creating or 'threshold' in data:
        rule.threshold = data.get('threshold') or 'meta1'
    if rule.threshold not in THRESHOLDS:
        raise ExpenseError('La meta debe ser meta1 o meta2')
    if creating or 'category' in data:
        rule.category = data.get('category') or 'sueldo'
    if rule.category not in OUT_CATEGORIES:
        raise ExpenseError(f'Categoría inválida: {rule.category}')
    if creating or 'active' in data:
        rule.active = bool(data.get('active', True))
    if 'sort_order' in data:
        rule.sort_order = int(data.get('sort_order') or 0)
    if creating or 'notes' in data:
        rule.notes = (data.get('notes') or '').strip() or None


def _period_args(source):
    try:
        year, month = int(source.get('year')), int(source.get('month'))
    except (TypeError, ValueError):
        raise ExpenseError('year y month son obligatorios')
    if not 1 <= month <= 12:
        raise ExpenseError('Mes inválido')
    return year, month


@bp.route('/api/incentives', methods=['GET', 'OPTIONS'])
@token_required
def list_incentives():
    """Reglas de la tienda y cuáles ya se pagaron en el mes pedido."""
    if request.method == 'OPTIONS':
        return '', 204
    err = _require_admin()
    if err:
        return err
    try:
        year, month = _period_args(request.args)
    except ExpenseError as e:
        return jsonify({'success': False, 'message': str(e)}), 400
    store = get_current_store()
    period = f'{year}-{month:02d}'
    rules = IncentiveRule.for_store(store).order_by(IncentiveRule.sort_order.asc(), IncentiveRule.id.asc()).all()
    paid = {}
    for e in Expense.for_store(store).filter(Expense.notes.like(f'auto:incentivo:%:{period}')).all():
        rule_id = e.notes.split(':')[2]
        paid[rule_id] = {'expense_id': e.id, 'date': e.date.isoformat(), 'amount': e.total}
    return jsonify({
        'success': True,
        'period': period,
        'settings': finance_settings.get_settings(store),
        'rules': [{**r.to_dict(), 'paid': paid.get(str(r.id))} for r in rules],
        'template_available': not rules,
    }), 200


@bp.route('/api/incentives/rules', methods=['POST', 'OPTIONS'])
@token_required
def create_rule():
    if request.method == 'OPTIONS':
        return '', 204
    err = _require_admin()
    if err:
        return err
    try:
        rule = IncentiveRule()
        _apply_rule(rule, request.get_json() or {}, creating=True)
        db.session.add(rule)
        db.session.commit()
        return jsonify({'success': True, 'rule': rule.to_dict()}), 201
    except ExpenseError as e:
        db.session.rollback()
        return jsonify({'success': False, 'message': str(e)}), 400


@bp.route('/api/incentives/rules/load-template', methods=['POST', 'OPTIONS'])
@token_required
def load_template():
    if request.method == 'OPTIONS':
        return '', 204
    err = _require_admin()
    if err:
        return err
    if IncentiveRule.for_current_store().count():
        return jsonify({'success': False, 'message': 'Esta tienda ya tiene incentivos'}), 409
    for i, data in enumerate(INCENTIVES_TEMPLATE):
        db.session.add(IncentiveRule(sort_order=i, active=True, **data))
    db.session.commit()
    return jsonify({'success': True, 'created': len(INCENTIVES_TEMPLATE)}), 201


@bp.route('/api/incentives/rules/<int:rule_id>', methods=['PUT', 'DELETE', 'OPTIONS'])
@token_required
def manage_rule(rule_id):
    if request.method == 'OPTIONS':
        return '', 204
    err = _require_admin()
    if err:
        return err
    rule = IncentiveRule.get_for_current_store_or_404(rule_id)
    if request.method == 'DELETE':
        db.session.delete(rule)  # los pagos ya registrados quedan en Gastos
        db.session.commit()
        return jsonify({'success': True}), 200
    try:
        _apply_rule(rule, request.get_json() or {}, creating=False)
        db.session.commit()
        return jsonify({'success': True, 'rule': rule.to_dict()}), 200
    except ExpenseError as e:
        db.session.rollback()
        return jsonify({'success': False, 'message': str(e)}), 400


def month_goal_status(store, year, month):
    """
    META 1 (meta de la tienda en Estadísticas → Metas), META 2 y la venta del
    mes. Separado para poder simularlo en tests (consulta Alegra).
    """
    from app.services.seller_goals import SellerGoalsService
    from app.stores import get_alegra_client, get_alegra_direct_client
    service = SellerGoalsService(store, get_colombia_now().date(), get_alegra_direct_client(), get_alegra_client())
    summary = service.summary(date(year, month, 1))
    meta1 = summary['store'].get('goal')
    extra = finance_settings.get_settings(store)['meta2_extra']
    return {'meta1': meta1, 'meta2': (meta1 + extra) if meta1 else None, 'sales': summary['store'].get('sales') or 0}


@bp.route('/api/incentives/pay', methods=['POST', 'OPTIONS'])
@token_required
def pay_incentive():
    """
    Registra el pago de un incentivo alcanzado como gasto (Cuentas → Gastos).
    Body: {rule_id, year, month, method: 'efectivo'|'qr'|..., account_mode}.
    Una sola vez por regla y mes. Verifica la meta con la venta del mes.
    """
    if request.method == 'OPTIONS':
        return '', 204
    err = _require_admin()
    if err:
        return err
    data = request.get_json() or {}
    store = get_current_store()
    try:
        year, month = _period_args(data)
        rule = IncentiveRule.for_store(store).filter_by(id=int(data.get('rule_id') or 0)).first()
        if rule is None:
            raise ExpenseError('El incentivo no existe en esta tienda')
        method = data.get('method') or 'efectivo'
        if method not in EXPENSE_METHODS:
            raise ExpenseError('Medio de pago inválido')
        mode = data.get('account_mode') or 'cuentas'
        if mode not in ACCOUNT_MODES or (mode == 'caja' and method != 'efectivo'):
            raise ExpenseError('¿De dónde sale la plata? inválido')
        period = f'{year}-{month:02d}'
        marker = PAID_MARKER.format(rule=rule.id, period=period)
        if Expense.for_store(store).filter_by(notes=marker).first():
            raise ExpenseError('Este incentivo ya se registró como pagado este mes')

        status = month_goal_status(store, year, month)
        target = status[rule.threshold]
        if not target or status['sales'] < target:
            raise ExpenseError('La venta del mes todavía no alcanza esa meta')

        # Fecha = hoy (cuando sale la plata); mes al que corresponde = el del incentivo
        expense = Expense(
            date=get_colombia_now().date(),
            period=period,
            concept=f'{rule.name} - {MONTHS_ES[month - 1]} {year}',
            category=rule.category,
            direction='out',
            account_mode=mode,
            apply_fee=True,
            notes=marker,
            created_by=get_current_user().get('userId'),
            **{m: (rule.amount if m == method else 0) for m in EXPENSE_METHODS},
        )
        db.session.add(expense)
        db.session.flush()
        _sync_expense_account_movements(expense)
        db.session.commit()
        return jsonify({'success': True, 'expense': expense.to_dict(), 'status': status}), 201
    except ExpenseError as e:
        db.session.rollback()
        return jsonify({'success': False, 'message': str(e)}), 400
    except Exception as e:
        db.session.rollback()
        logger.error(f'[{store}] Pago de incentivo: {e}', exc_info=True)
        return jsonify({'success': False, 'message': 'No se pudo registrar el pago (no se pudo leer la meta del mes)'}), 502
