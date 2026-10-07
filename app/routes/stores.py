"""
Multi-tienda: tiendas disponibles para el usuario actual (alimenta el
selector de tienda del frontend) y comparativo entre tiendas (solo admin).
Ver app/stores.py.
"""
import logging
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta

from flask import Blueprint, jsonify, request

from app.middlewares.auth import token_required, role_required, get_current_user
from app.stores import STORES, get_alegra_client, get_current_store, get_store_info, stores_for_user
from app.utils.formatters import filter_voided_invoices, safe_number
from app.utils.timezone import get_colombia_now

logger = logging.getLogger(__name__)

bp = Blueprint('stores', __name__)

# Cada día del rango es una consulta a Alegra por tienda: se limita el rango
# para no dejar al backend (Render free) minutos consultando.
MAX_COMPARISON_DAYS = 92


@bp.route('/api/stores', methods=['GET', 'OPTIONS'])
@token_required
def list_user_stores():
    if request.method == 'OPTIONS':
        return '', 204

    codes = stores_for_user(get_current_user())
    return jsonify({
        'success': True,
        'stores': [get_store_info(code) for code in codes],
        'current_store': get_current_store(),
        'default_store': codes[0],
    }), 200


# ─────────────────────────────────────────────
#  COMPARATIVO ENTRE TIENDAS
# ─────────────────────────────────────────────

def _parse_range():
    """(start, end) del query string; por defecto el mes en curso hasta hoy (Colombia)."""
    today = get_colombia_now().date()
    start_str = request.args.get('start_date')
    end_str = request.args.get('end_date')
    start = datetime.strptime(start_str, '%Y-%m-%d').date() if start_str else today.replace(day=1)
    end = datetime.strptime(end_str, '%Y-%m-%d').date() if end_str else today
    end = min(end, today)  # las fechas futuras no tienen ventas
    if start > end:
        raise ValueError('La fecha inicial no puede ser posterior a la final')
    if (end - start).days + 1 > MAX_COMPARISON_DAYS:
        raise ValueError(f'El rango máximo es de {MAX_COMPARISON_DAYS} días')
    return start, end


def _sales_metrics(client, start, end, mass_ids=None):
    """
    Ventas de UNA tienda en el rango (corre en un hilo aparte: solo usa el
    cliente de Alegra, nada de base de datos ni del contexto de Flask).
    Usa build_sales_summary: exactamente el mismo cálculo que Ventas Mensuales.
    `mass_ids`: facturas de la anulación masiva de 2025 que sí fueron venta
    (calculadas antes, en el hilo del request; vacío en 2026).
    """
    from app.services.history_2025 import revive_with_ids
    start_str, end_str = start.isoformat(), end.isoformat()
    invoices = revive_with_ids(client.get_all_invoices_in_range(start_str, end_str), mass_ids or set())
    summary = client.build_sales_summary(invoices, start_str, end_str)

    by_day = defaultdict(float)
    for inv in filter_voided_invoices(invoices)['active_invoices']:
        by_day[str(inv.get('date', ''))[:10]] += safe_number(inv.get('total', 0))

    total = summary['total_vendido']['total']
    invoices_count = summary['cantidad_facturas']
    days = [start + timedelta(days=i) for i in range((end - start).days + 1)]
    return {
        'total': total,
        'invoices': invoices_count,
        'average_ticket': round(total / invoices_count) if invoices_count else 0,
        'voided_invoices': summary['invoices_summary']['voided_invoices'],
        'payment_methods': {
            key: {'label': data['label'], 'total': data['total']}
            for key, data in summary['payment_methods'].items()
        },
        'daily': [{'date': d.isoformat(), 'total': int(by_day.get(d.isoformat(), 0))} for d in days],
        # Días que Alegra no entregó: el total de esta tienda está incompleto
        'failed_days': list(getattr(client, 'last_failed_days', []) or []),
    }


def _operational_metrics(store_code, start, end):
    """Datos propios del sistema (no dependen de Alegra) de UNA tienda en el rango."""
    from app.models.account import Account
    from app.models.cash_closing import CashClosing
    from app.models.repurchase import RepurchaseEntry
    from app.models.repurchase_purchase import RepurchasePurchase
    from app.routes.accounts import ACCOUNTS_EXCLUDED_FROM_RECOMPRA_TOTAL

    closings = CashClosing.for_store(store_code).filter(
        CashClosing.closing_date >= start, CashClosing.closing_date <= end
    ).all()
    discrepancies = [c.alegra_discrepancy for c in closings if c.alegra_discrepancy is not None]

    accounts = Account.for_store(store_code).filter_by(active=True).all()
    entries = RepurchaseEntry.for_store(store_code).filter(
        RepurchaseEntry.date >= start, RepurchaseEntry.date <= end
    ).all()
    purchases = RepurchasePurchase.for_store(store_code).filter(
        RepurchasePurchase.date >= start, RepurchasePurchase.date <= end
    ).all()

    # Cuentas → Gastos (Fase 4 de PLAN_CUENTAS_DIARIAS): salidas con fecha en
    # el rango, separadas como en el resumen anual (operativos vs. lo que no
    # es gasto del mes). Incluye el 4x1000.
    from app.models.expense import Expense
    from app.services.monthly_summary import OPERATING_CATEGORIES
    expenses = Expense.for_store(store_code).filter(
        Expense.date >= start, Expense.date <= end, Expense.direction == 'out').all()
    operating = sum(e.total_with_fee for e in expenses if e.category in OPERATING_CATEGORIES)
    operating += sum(e.fee_4mil for e in entries)  # 4x1000 de las recompras
    other = sum(e.total_with_fee for e in expenses if e.category not in OPERATING_CATEGORIES)

    return {
        'closings_registered': len(closings),
        'period_days': (end - start).days + 1,
        # Cierres cuya diferencia con Alegra no fue $0 (redondeado al peso)
        'closings_with_difference': sum(1 for d in discrepancies if round(d) != 0),
        'alegra_difference_total': round(sum(discrepancies)),
        # Saldo HOY (no del periodo): mismo total que muestra Cuentas > Resumen
        'accounts_balance': round(sum(
            a.balance for a in accounts if a.payment_key not in ACCOUNTS_EXCLUDED_FROM_RECOMPRA_TOTAL
        )),
        'repurchase_sent': round(sum(e.total_enviado for e in entries)),
        'repurchase_purchases': round(sum(p.amount for p in purchases)),
        'expenses_operating': round(operating),
        'expenses_other': round(other),
    }


@bp.route('/api/stores/comparison', methods=['GET', 'OPTIONS'])
@token_required
@role_required('admin')
def store_comparison():
    """
    Comparativo de todas las tiendas en un rango de fechas (por defecto, el
    mes en curso). Si una tienda no puede consultar Alegra (ej. todavía no
    tiene la cuenta configurada), sus ventas vienen con available=False y el
    motivo; el resto del comparativo sale igual.
    ---
    tags:
      - Multi-tienda
    parameters:
      - in: query
        name: start_date
        type: string
        required: false
      - in: query
        name: end_date
        type: string
        required: false
    responses:
      200:
        description: Métricas de ventas y operación por tienda
      400:
        description: Rango de fechas inválido
    """
    if request.method == 'OPTIONS':
        return '', 204

    try:
        start, end = _parse_range()
    except ValueError as e:
        return jsonify({'success': False, 'message': str(e)}), 400

    # Clientes de Alegra (en el hilo principal); las tiendas sin cuenta
    # configurada quedan registradas con su motivo.
    clients, sales = {}, {}
    for code in STORES:
        try:
            clients[code] = get_alegra_client(code)
        except Exception as e:
            sales[code] = {'available': False, 'error': getattr(e, 'message', None) or str(e)}

    # 2025: anulación masiva de POS (base de datos: aquí, no en los hilos)
    from app.services.history_2025 import mass_ids_for_range
    mass = {}
    for code in clients:
        try:
            mass[code] = mass_ids_for_range(code, start, end)
        except Exception as e:
            logger.warning(f'Comparativo: anulación masiva 2025 de {code}: {e}')

    # Las consultas a Alegra de cada tienda corren en paralelo.
    if clients:
        with ThreadPoolExecutor(max_workers=len(clients)) as pool:
            futures = {code: pool.submit(_sales_metrics, client, start, end, mass.get(code))
                       for code, client in clients.items()}
            for code, future in futures.items():
                try:
                    sales[code] = {'available': True, **future.result()}
                except Exception as e:
                    logger.error(f"Comparativo: no se pudieron obtener ventas de {code}: {e}", exc_info=True)
                    sales[code] = {'available': False,
                                   'error': getattr(e, 'message', None) or 'No se pudo consultar Alegra'}

    stores = []
    for code in STORES:
        stores.append({
            **get_store_info(code),
            'sales': sales[code],
            'operations': _operational_metrics(code, start, end),
        })

    return jsonify({
        'success': True,
        'date_range': {'start': start.isoformat(), 'end': end.isoformat()},
        'stores': stores,
    }), 200
