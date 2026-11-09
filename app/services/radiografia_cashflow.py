"""
Radiografía, Fase 4: flujo de caja (docs/PLAN_RADIOGRAFIA.md).

Solo lee. Dos partes:

1. La plata del mes (por fecha, como Cuentas → Mes): saldo inicial y final de
   cada cuenta (`month_sheet.account_statement`), lo que entró (ventas de los
   cierres, llegadas de datáfono/Addi/Bold, excedentes, devoluciones, ingresos
   extra), lo que salió por clase (§4 del plan: recompras, gastos, cuotas,
   inversiones, préstamos, retiros) y los traslados entre cuentas propias
   aparte (no cuentan). Los gastos pagados "de la caja del día" ya vienen
   descontados del efectivo del cierre: se suman a las ventas y se restan en
   su clase para que se vean (el resultado no cambia).
   Al lado, la utilidad del mes (Fase 1) y las partidas que separan una de la
   otra.

2. Hoy: lo que le deben a la tienda, lo que debe y "cuánto se puede retirar"
   (ESTIMADO). Regla del usuario (2026-11-06): solo se resta lo registrado a
   mano; lo que falta por pagar (fijos, cuotas, recomprar lo vendido, deuda
   con la otra tienda) va en líneas de aviso, aparte, y "quedarían si se
   pagara todo" es un VALOR APROXIMADO de referencia. AHORRO cuenta como
   plata disponible.
"""
from collections import defaultdict
from datetime import date
from typing import Any, Dict, List, Optional

from app.models.account import Account, AccountMovement
from app.models.expense import Expense, FixedExpense
from app.services import radiografia as r
from app.services.radiografia_month import CLASS_LABELS, MONTHS_ES

RECOMPRAS = 'recompras'
OUT_ORDER = (RECOMPRAS, r.COSTO_MERCANCIA, r.OPERATIVO, r.FINANCIERO, r.CUOTA_CREDITO,
             r.INVERSION, r.PRESTAMO, r.RETIRO_SOCIO)
OUT_LABELS = {RECOMPRAS: 'Recompras enviadas a Jhonatan', **CLASS_LABELS,
              r.CUOTA_CREDITO: 'Cuotas de crédito (capital)'}
IN_LABELS = {
    'ventas': 'Ventas que entraron por los cierres',
    'llegadas': 'Datáfono, Addi y Bold que llegaron al banco',
    'excedentes': 'Excedentes de los cierres (no son venta)',
    'devolucion_prestamo': 'Devoluciones de préstamos (empleadas u otras personas)',
    'devolucion_prestamo_tienda': 'Devoluciones de la otra tienda',
    'prestamo_recibido_tienda': 'Préstamos recibidos de la otra tienda',
    'ingreso_extra': 'Ingresos extra (no son venta)',
}
SALE_INS = ('ventas', 'llegadas')


def _expense_id(ref: Optional[str]) -> Optional[int]:
    if ref and ref.startswith('expense-'):
        try:
            return int(ref.rsplit('-', 1)[1])
        except ValueError:
            return None
    return None


# ─────────────────────────────────────────────
#  1. La plata del mes
# ─────────────────────────────────────────────

def _month_flow(store: str, start: date, end: date, period: str) -> Dict[str, Any]:
    from app.services.loans import interest_by_expense
    from app.services.month_sheet import _effective_dates, account_statement

    statement = account_statement(store, start, end, period)
    accounts = Account.for_store(store).filter(Account.active.is_(True)).all()
    ids = [a.id for a in accounts]
    movements = AccountMovement.query.filter(AccountMovement.account_id.in_(ids)).all() if ids else []
    eff = _effective_dates(movements)
    first_day = min(eff.values()) if eff else None
    month_movs = [m for m in movements if start <= eff[m.id] <= end]

    ins = defaultdict(float)
    outs = defaultdict(float)
    out_items = defaultdict(list)
    ajustes = traslados_net = traslados_bruto = 0.0
    by_expense = defaultdict(float)
    for m in month_movs:
        if m.type == 'cash_closing':
            ins['ventas'] += m.amount
        elif m.type == 'card_arrival':
            ins['llegadas'] += m.amount
        elif m.type == 'excedente':
            ins['excedentes'] += m.amount
        elif m.type == 'repurchase_send':
            outs[RECOMPRAS] -= m.amount
        elif m.type in ('expense', 'expense_in') and _expense_id(m.reference_id):
            by_expense[_expense_id(m.reference_id)] += m.amount
        elif m.type in ('transfer_in', 'transfer_out'):
            traslados_net += m.amount
            traslados_bruto += max(m.amount, 0)
        else:
            ajustes += m.amount

    expenses = {e.id: e for e in Expense.for_store(store).filter(Expense.id.in_(list(by_expense))).all()} if by_expense else {}
    # Gastos pagados de la caja del día: el cierre ya los descontó del efectivo
    caja = Expense.for_store(store).filter(Expense.date >= start, Expense.date <= end,
                                           Expense.account_mode == 'caja', Expense.direction == 'out').all()
    interest = interest_by_expense(list(expenses.values()) + caja)

    def add_out(e: Expense, amount: float, from_caja: bool = False):
        part = min(interest.get(e.id, 0), amount)
        cls = r.expense_class(e.category)
        base = {'id': e.id, 'date': e.date.isoformat(), 'category': e.category, 'caja': from_caja}
        if part:
            # El interés de una cuota es gasto financiero: se ve en su clase con su detalle
            outs[r.FINANCIERO] += part
            out_items[r.FINANCIERO].append({**base, 'concept': f'Interés de: {e.concept}', 'amount': part, 'interest': 0})
        outs[cls] += amount - part
        out_items[cls].append({**base, 'concept': e.concept, 'amount': amount - part, 'interest': part})

    for eid, amount in by_expense.items():
        e = expenses.get(eid)
        if e is None:
            ajustes += amount
        elif amount >= 0:
            ins[e.category if e.category in IN_LABELS else 'ingreso_extra'] += amount
        else:
            add_out(e, -amount)
    caja_total = 0.0
    for e in caja:
        caja_total += e.total_with_fee
        add_out(e, e.total_with_fee, from_caja=True)
    ins['ventas'] += caja_total

    initial = sum(s['initial'] for s in statement)
    final = sum(s['final'] for s in statement)
    entradas = sum(ins.values())
    salidas = sum(outs.values())
    return {
        'accounts': [{'account_id': s['account_id'], 'name': s['name'], 'payment_key': s['payment_key'],
                      'initial': s['initial'], 'final': s['final'], 'change': s['final'] - s['initial']}
                     for s in statement],
        'initial': initial, 'final': final, 'change': final - initial,
        'entradas': [{'key': k, 'label': IN_LABELS.get(k, k), 'total': ins[k]}
                     for k in IN_LABELS if ins.get(k)],
        'entradas_total': entradas,
        'salidas': [{'key': k, 'label': OUT_LABELS[k], 'total': outs[k],
                     'reduces_utility': k in r.UTILITY_CLASSES,
                     'items': sorted(out_items.get(k, []), key=lambda i: (i['date'], i['id']))}
                    for k in OUT_ORDER if outs.get(k)],
        'salidas_total': salidas,
        'caja_del_dia': caja_total,
        'ajustes': ajustes,
        'traslados': {'bruto': traslados_bruto, 'neto': traslados_net},
        'ins': dict(ins), 'outs': dict(outs),
        'first_day': first_day,
    }


def _bridge(flow: Dict[str, Any], month: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Utilidad neta del mes → cambio en la plata, con las partidas que las separan."""
    if not month.get('has_expenses'):
        return None
    s = month['statement']
    outs, ins = flow['outs'], flow['ins']
    lines = [
        ('costo_estimado', 'Costo estimado de lo vendido (se resta en la utilidad, no es plata que sale)', s['costo_estimado']),
        ('comisiones', 'Comisiones calculadas sin registrar (bajan la utilidad, no han salido)',
         0 if s['comisiones_registradas'] else s['comisiones_calculadas']),
        ('recompras', 'Recompras enviadas a Jhonatan (sí es plata que sale)', -outs.get(RECOMPRAS, 0)),
        ('cuotas', 'Cuotas de crédito (capital)', -outs.get(r.CUOTA_CREDITO, 0)),
        ('inversiones', 'Inversiones', -outs.get(r.INVERSION, 0)),
        ('prestamos', 'Préstamos dados, abonos y devoluciones recibidas',
         -outs.get(r.PRESTAMO, 0) + ins.get('devolucion_prestamo', 0) + ins.get('devolucion_prestamo_tienda', 0)
         + ins.get('prestamo_recibido_tienda', 0)),
        ('retiros', 'Retiros de socios', -outs.get(r.RETIRO_SOCIO, 0)),
        ('otras_entradas', 'Excedentes e ingresos extra (no son venta)', ins.get('excedentes', 0) + ins.get('ingreso_extra', 0)),
        ('ajustes', 'Ajustes a mano (igualar al banco) y traslados', flow['ajustes'] + flow['traslados']['neto']),
    ]
    explained = s['utilidad_neta'] + sum(v for _, _, v in lines)
    rest = flow['change'] - explained
    lines.append(('fechas', 'Diferencias de fechas: ventas por llegar o que llegaron de antes, gastos de otro mes, 4x1000', rest))
    return {
        'utilidad_neta': s['utilidad_neta'], 'lo_que_quedo': s['lo_que_quedo'],
        'lines': [{'key': k, 'label': label, 'value': v} for k, label, v in lines if abs(v) >= 1 or k == 'fechas'],
        'cambio_plata': flow['change'],
    }


# ─────────────────────────────────────────────
#  2. Hoy: lo que le deben, lo que debe y cuánto se puede retirar
# ─────────────────────────────────────────────

def _jhonatan(store: str, today: date) -> float:
    """Plata de las recompras que tiene Jhonatan hoy (misma regla que Cuentas
    Recompras: enviado + sobrante manual − compras, desde CARRYOVER_START)."""
    from app.models.repurchase import RepurchaseEntry
    from app.models.repurchase_purchase import RepurchasePurchase
    from app.routes.repurchase import CARRYOVER_START
    entries = RepurchaseEntry.for_store(store).filter(
        RepurchaseEntry.date >= CARRYOVER_START, RepurchaseEntry.date <= today).all()
    purchases = RepurchasePurchase.for_store(store).filter(
        RepurchasePurchase.date >= CARRYOVER_START, RepurchasePurchase.date <= today).all()
    return sum(e.total_enviado + e.sobrante_mes_anterior for e in entries) - sum(p.amount for p in purchases)


def _employee_loans(store: str) -> List[Dict[str, Any]]:
    from app.models.employee_records import EmployeeLoan
    totals = defaultdict(float)
    for l in EmployeeLoan.for_store(store).all():
        totals[l.nombre_empleada] += l.amount or 0
    return [{'name': n, 'balance': v} for n, v in sorted(totals.items()) if v >= 1]


def _pending_fixed(store: str, period: str) -> List[Dict[str, Any]]:
    """Gastos fijos sin registrar este mes que restan utilidad (sin cuotas: van
    con su préstamo; sin ganancias de socios: son lo que se retira)."""
    paid = {e.fixed_expense_id for e in Expense.for_store(store).filter(
        Expense.period == period, Expense.fixed_expense_id.isnot(None)).all()}
    out = []
    for f in FixedExpense.for_store(store).filter_by(active=True).order_by(
            FixedExpense.due_day.asc(), FixedExpense.id.asc()).all():
        if f.id in paid or r.expense_class(f.category) not in r.UTILITY_CLASSES:
            continue
        out.append({'id': f.id, 'name': f.name, 'due_day': f.due_day, 'value': f.amount or 0})
    return out


def _pending_installments(store: str, today: date) -> List[Dict[str, Any]]:
    from app.services.loans import groups
    fixed = {f.id: f.amount for f in FixedExpense.for_store(store).all()}
    out = []
    for g in groups(store, today):
        for l in g['loans']:
            if not l['pending_this_month']:
                continue
            value = l['installment'] or fixed.get(l['fixed_expense_id']) or None
            out.append({'group': g['group_name'], 'name': l['name'], 'due_day': l['due_day'],
                        'value': value, 'free': not l['installment']})
    return out


def _today(store: str, today: date, current_month: Dict[str, Any]) -> Dict[str, Any]:
    from app.services import card_arrivals, inter_store_debt, loans
    from app.services.month_sheet import transit
    from app.stores import STORES

    accounts = Account.for_store(store).filter(Account.active.is_(True)).order_by(
        Account.sort_order.asc(), Account.id.asc()).all()
    tr = transit(store, today)
    card_active = card_arrivals.is_active(store)
    rows = []
    for a in accounts:
        row = {'account_id': a.id, 'name': a.name, 'payment_key': a.payment_key, 'balance': a.balance,
               'available': a.balance}
        if a.payment_key == card_arrivals.ACCOUNT_KEY and not card_active:
            # Sin "plata real del banco" el saldo incluye lo vendido que no ha llegado
            row['available'] = a.balance - tr['gross']
            row['note'] = 'Sin lo vendido que todavía no llega'
        rows.append(row)
    plata = sum(r_['available'] for r_ in rows)

    # Lo que le deben / lo que debe
    debt = inter_store_debt.compute()
    other_owes = debt['balance'] if store == debt['lender'] and debt['balance'] else 0
    owes_other = debt['balance'] if store == debt['borrower'] and debt['balance'] else 0
    other_name = STORES[debt['borrower'] if store == debt['lender'] else debt['lender']]['name']
    jhon = _jhonatan(store, today)
    employees = _employee_loans(store)
    loan_groups = loans.groups(store, today)

    receivable = [
        {'key': 'por_llegar', 'label': 'Datáfono, Addi y Bold por llegar', 'value': tr['net'],
         'items': [{'date': i['arrival_date'], 'medio': i['medio'], 'value': i['net']} for i in tr['items']],
         'note': None if card_active else 'Ya está dentro del saldo de ADDI + DATÁFONO'},
        {'key': 'empleadas', 'label': 'Préstamos a empleadas', 'value': sum(e['balance'] for e in employees),
         'items': employees},
        {'key': 'otra_tienda', 'label': f'{other_name} nos debe', 'value': other_owes},
        {'key': 'jhonatan', 'label': 'Plata en manos de Jhonatan (para recompras)', 'value': max(jhon, 0)},
    ]
    payable = [{'key': f'prestamo:{g["group_name"]}', 'label': g['group_name'], 'value': g['balance'],
                'items': [{'name': l['name'], 'value': l['balance']} for l in g['loans'] if l['balance'] >= 1]}
               for g in loan_groups if g['balance'] >= 1]
    if owes_other:
        payable.append({'key': 'otra_tienda', 'label': f'Le debemos a {other_name}', 'value': owes_other})
    if jhon < 0:
        payable.append({'key': 'jhonatan', 'label': 'A Jhonatan (compró más de lo que se le envió)', 'value': -jhon})

    # Cuánto se puede retirar: la plata de hoy; los avisos van aparte y no se restan solos
    period = f'{today.year}-{today.month:02d}'
    fixed = _pending_fixed(store, period)
    cuotas = _pending_installments(store, today)
    s = current_month.get('statement') or {}
    falta_recomprar = max(0.0, (s.get('costo_estimado') or 0) - (s.get('recompras') or 0))
    avisos = [
        {'key': 'fijos', 'label': 'Gastos fijos que faltan este mes', 'value': sum(f['value'] for f in fixed), 'items': fixed},
        {'key': 'cuotas', 'label': 'Cuotas de préstamos que faltan este mes',
         'value': sum(c['value'] or 0 for c in cuotas), 'items': cuotas},
        {'key': 'recomprar', 'label': 'Falta por recomprar de lo vendido este mes', 'value': falta_recomprar,
         'estimated': True,
         'formula': 'Costo estimado de lo vendido en el mes − recompras enviadas en el mes (si da positivo)'},
        {'key': 'otra_tienda', 'label': f'Deuda con {other_name}', 'value': owes_other},
    ]
    avisos = [a for a in avisos if a['value'] >= 1 or a.get('items')]
    retiros_mes = sum(e.total_with_fee for e in Expense.for_store(store).filter(
        Expense.period == period, Expense.category == 'retiro_socio').all())
    return {
        'date': today.isoformat(),
        'accounts': rows, 'plata': plata, 'card_arrivals_active': card_active,
        'receivable': receivable, 'receivable_total': sum(x['value'] for x in receivable),
        'payable': payable, 'payable_total': sum(x['value'] for x in payable),
        'withdraw': {
            'plata_hoy': plata,
            'avisos': avisos,
            'avisos_total': sum(a['value'] for a in avisos),
            'quedarian': plata - sum(a['value'] for a in avisos),
            'retiros_mes': retiros_mes,
            'formula': 'Plata en las cuentas hoy (con AHORRO, sin lo que está por llegar). Las líneas de aviso no se '
                       'restan solas: solo se descuenta lo que se registra. "Quedarían" = plata de hoy − avisos.',
        },
    }


# ─────────────────────────────────────────────
#  Respuesta completa
# ─────────────────────────────────────────────

def build_cash_flow(store: str, year: int, month: int, today: date,
                    month_data: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """month_data: la Radiografía del mes ya calculada (el comparativo la reutiliza)."""
    from app.services.radiografia_month import build_month
    start, end = r.month_bounds(year, month)
    period = f'{year}-{month:02d}'
    current = (month_data if month_data and (year, month) == (today.year, today.month)
               else build_month(store, today.year, today.month, today))
    out: Dict[str, Any] = {'period': period, 'year': year, 'month': month,
                           'label': f'{MONTHS_ES[month - 1]} {year}', 'future': start > today,
                           'today': _today(store, today, current)}
    if start > today:
        return out
    m = month_data or (current if (year, month) == (today.year, today.month) else build_month(store, year, month, today))
    flow = _month_flow(store, start, min(end, today), period)
    warnings: List[str] = []
    if flow['first_day'] is None or flow['first_day'] > start:
        first = flow['first_day'].strftime('%d/%m/%Y') if flow['first_day'] else None
        warnings.append('Las cuentas se llevan en la plataforma desde el '
                        f'{first}: antes de eso los saldos no son confiables.' if first else
                        'Esta tienda todavía no tiene movimientos en las cuentas.')
    if start <= today <= end:
        warnings.append('Mes en curso: la plata va hasta hoy.')
    if flow['caja_del_dia']:
        warnings.append('Los gastos pagados de la caja del día ya venían descontados del efectivo del cierre: '
                        'aquí se suman a las ventas y se restan en su clase para que se vean (el saldo no cambia).')
    flow.pop('first_day')
    flow.pop('ins')
    outs = flow.pop('outs')
    out.update({
        'in_progress': start <= today <= end,
        'flow': flow,
        'bridge': _bridge({**flow, 'outs': outs, 'ins': {e['key']: e['total'] for e in flow['entradas']}}, m),
        'utility': {'utilidad_neta': m['statement']['utilidad_neta'] if m.get('has_expenses') else None,
                    'lo_que_quedo': m['statement']['lo_que_quedo'], 'has_expenses': m.get('has_expenses')},
        'warnings': warnings,
    })
    return out
