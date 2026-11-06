"""
Deuda entre tiendas (Radiografía Fase 0b, docs/PLAN_RADIOGRAFIA.md).

Lo que Primavera le debe a Carreño, en una tarjeta visible en las dos tiendas
(Cuentas → Resumen) que baja sola con cada abono.

Reglas del usuario (2026-11-06):
- Saldo de partida: $9.816.659 al 6-nov-2026 (valor neto: lo anterior ya está
  descontado). Lo registrado antes de esa fecha queda solo como historial.
- Saldo = partida
          + préstamos de la que presta a la que debe (prestamo_tienda, en la que presta)
          − abonos de la que debe (pago_prestamo_tienda, en la que debe)
          − devoluciones anotadas a mano en la que presta (devolucion_prestamo_tienda
            que NO son espejo de un abono, para no contar dos veces)
  todo con fecha desde la de partida.
- Ni el préstamo ni el abono son gasto: no bajan la ganancia de ninguna tienda.
- El abono baja las cuentas de la tienda que paga (si salió de ellas) y NO suma
  a las de la otra, salvo que la plata llegue a una de sus cuentas (espejo).
- Registros espejo (se crean, editan y borran solos con su movimiento):
  * purpose='recompra': recompra en la otra tienda, sin mover sus cuentas, con
    la nota "No se movió en cuentas: lo pagó <tienda>".
  * purpose='cuenta': entrada en la cuenta de la otra tienda donde llegó.
- El saldo de partida es compartido (app_settings, sin tienda) y cada cambio
  deja rastro (quién, cuándo, valor anterior y nuevo, nota).
"""
import json
from datetime import date, datetime
from typing import Any, Dict, List, Optional

from app.models.app_setting import AppSetting
from app.models.expense import (EXPENSE_METHODS, INTER_STORE_PURPOSES, Expense)
from app.models.repurchase import RepurchaseEntry
from app.models.user import db
from app.stores import STORES

SETTING_KEY = 'inter_store_debt'  # compartido: es de las dos tiendas
DEFAULTS = {
    'lender': 'carreno',
    'borrower': 'primavera',
    'opening_balance': 9816659,
    'opening_date': '2026-11-06',
    'history': [],
}
REPURCHASE_METHODS = ('efectivo', 'datafono', 'qr', 'daviplata', 'nequi', 'bbva')


class DebtError(ValueError):
    """Dato inválido: se responde 400."""


# ─────────────────────────────────────────────
#  Saldo de partida
# ─────────────────────────────────────────────

def get_config() -> Dict[str, Any]:
    row = AppSetting.query.get(SETTING_KEY)
    saved = {}
    if row and row.value:
        try:
            saved = json.loads(row.value)
        except ValueError:
            saved = {}
    return {k: saved.get(k, v) for k, v in DEFAULTS.items()}


def set_opening(balance: Any, opening_date: Any, note: str, user: Dict[str, Any]) -> Dict[str, Any]:
    """Cambia el saldo de partida y/o su fecha, dejando rastro."""
    try:
        balance = float(balance)
    except (TypeError, ValueError):
        raise DebtError('Saldo inválido')
    if balance < 0:
        raise DebtError('El saldo no puede ser negativo')
    try:
        day = datetime.strptime(str(opening_date), '%Y-%m-%d').date()
    except ValueError:
        raise DebtError('Fecha inválida (AAAA-MM-DD)')
    note = (note or '').strip()
    if not note:
        raise DebtError('Escribe por qué se cambia el saldo')
    config = get_config()
    config['history'] = list(config.get('history') or []) + [{
        'at': datetime.utcnow().isoformat(timespec='seconds'),
        'by': user.get('email'),
        'old_balance': config['opening_balance'], 'new_balance': balance,
        'old_date': config['opening_date'], 'new_date': day.isoformat(),
        'note': note[:300],
    }]
    config['opening_balance'] = int(balance) if balance == int(balance) else balance
    config['opening_date'] = day.isoformat()
    row = AppSetting.query.get(SETTING_KEY)
    if row is None:
        row = AppSetting(key=SETTING_KEY)
        db.session.add(row)
    row.value = json.dumps(config)
    row.updated_at = datetime.utcnow()
    db.session.commit()
    return config


# ─────────────────────────────────────────────
#  Saldo de hoy
# ─────────────────────────────────────────────

def _view(e: Expense, kind: str) -> Dict[str, Any]:
    methods = {m: getattr(e, m) for m in EXPENSE_METHODS if getattr(e, m)}
    return {
        'id': e.id, 'store_code': e.store_code, 'kind': kind, 'date': e.date.isoformat(),
        'amount': e.total, 'concept': e.concept, 'purpose': e.purpose,
        'purpose_label': INTER_STORE_PURPOSES.get(e.purpose or ''), 'methods': methods,
        'account_mode': e.account_mode, 'arrived_method': e.arrived_method, 'notes': e.notes,
    }


def compute(config: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    config = config or get_config()
    lender, borrower = config['lender'], config['borrower']
    since = date.fromisoformat(config['opening_date'])

    def rows(store, category, other, direction='out'):
        return Expense.for_store(store).filter(
            Expense.category == category, Expense.related_store_code == other,
            Expense.direction == direction,
        ).order_by(Expense.date.asc(), Expense.id.asc()).all()

    loans = rows(lender, 'prestamo_tienda', borrower)
    payments = rows(borrower, 'pago_prestamo_tienda', lender)
    manual_returns = [r for r in rows(lender, 'devolucion_prestamo_tienda', borrower, 'in') if not r.linked_from_id]

    new_loans = [e for e in loans if e.date >= since]
    new_payments = [e for e in payments if e.date >= since]
    new_returns = [e for e in manual_returns if e.date >= since]
    lent = sum(e.total for e in new_loans)
    paid = sum(e.total for e in new_payments) + sum(e.total for e in new_returns)

    movements = ([_view(e, 'prestamo') for e in new_loans] + [_view(e, 'abono') for e in new_payments]
                 + [_view(e, 'devolucion') for e in new_returns])
    movements.sort(key=lambda m: (m['date'], m['id']))
    running = config['opening_balance']
    for m in movements:
        running += m['amount'] if m['kind'] == 'prestamo' else -m['amount']
        m['balance_after'] = running

    old = [e for e in loans + payments + manual_returns if e.date < since]
    return {
        'lender': lender, 'lender_name': STORES[lender]['name'],
        'borrower': borrower, 'borrower_name': STORES[borrower]['name'],
        'opening_balance': config['opening_balance'], 'opening_date': config['opening_date'],
        'lent_since': lent, 'paid_since': paid,
        'balance': config['opening_balance'] + lent - paid,
        'movements': movements,
        'history_before': {'count': len(old), 'note': 'Registros anteriores a la fecha de partida: solo historial'},
        'opening_history': config.get('history') or [],
    }


# ─────────────────────────────────────────────
#  Registros espejo en la otra tienda
# ─────────────────────────────────────────────

def mirror_note(source: Expense) -> str:
    who = STORES.get(source.store_code, {}).get('name', source.store_code)
    kind = 'abono a la deuda' if source.category == 'pago_prestamo_tienda' else 'préstamo entre tiendas'
    return f'No se movió en cuentas: lo pagó {who} ({kind}, movimiento #{source.id} de {who}).'


def sync_mirrors(source: Expense, is_delete: bool = False) -> None:
    """Crea, actualiza o borra los registros espejo de un movimiento entre
    tiendas. No hace commit (lo confirma la ruta junto con lo demás)."""
    other = source.related_store_code
    mirrored_expenses = Expense.query.filter_by(linked_from_id=source.id).all()
    mirrored_repurchases = RepurchaseEntry.query.filter_by(linked_expense_id=source.id).all()
    is_inter = source.category in ('prestamo_tienda', 'pago_prestamo_tienda') and other

    want_repurchase = not is_delete and is_inter and source.purpose == 'recompra'
    want_entry = not is_delete and is_inter and source.purpose == 'cuenta'

    # Recompra en la otra tienda (sin mover sus cuentas, sin 4x1000)
    if want_repurchase:
        entry = mirrored_repurchases[0] if mirrored_repurchases else RepurchaseEntry(
            store_code=other, linked_expense_id=source.id, created_by=source.created_by)
        entry.store_code = other
        entry.date = source.date
        entry.descripcion = f'Recompra pagada por {STORES[source.store_code]["name"]}'[:200]
        for m in REPURCHASE_METHODS:
            setattr(entry, m, getattr(source, m) or 0)
        # Ahorro no existe en Recompras: se anota como efectivo (no mueve cuentas igual)
        entry.efectivo = (entry.efectivo or 0) + (source.ahorro or 0)
        entry.valor_no_enviado = 0
        entry.sobrante_mes_anterior = 0
        entry.fee_override = 0
        entry.synced_to_accounts = False
        entry.paid_by_store = source.store_code
        entry.notes = mirror_note(source) + (f' {source.notes}' if source.notes else '')
        if not mirrored_repurchases:
            db.session.add(entry)
        extra = mirrored_repurchases[1:]
    else:
        extra = mirrored_repurchases
    for r in extra:
        db.session.delete(r)

    # Entrada en la cuenta de la otra tienda donde llegó la plata
    from app.routes.expenses import _sync_expense_account_movements  # evita import circular
    if want_entry:
        mirror = mirrored_expenses[0] if mirrored_expenses else Expense(
            store_code=other, linked_from_id=source.id, created_by=source.created_by)
        mirror.store_code = other
        mirror.date = source.date
        mirror.period = source.date.strftime('%Y-%m')
        mirror.direction = 'in'
        mirror.category = ('devolucion_prestamo_tienda' if source.category == 'pago_prestamo_tienda'
                           else 'prestamo_recibido_tienda')
        mirror.subcategory = None
        mirror.related_store_code = source.store_code
        mirror.account_mode = 'cuentas'
        mirror.concept = (('Abono de ' if source.category == 'pago_prestamo_tienda' else 'Préstamo de ')
                          + STORES[source.store_code]['name'] + f': {source.concept}')[:255]
        for m in EXPENSE_METHODS:
            setattr(mirror, m, 0)
        setattr(mirror, source.arrived_method, source.total)
        mirror.apply_fee = False
        mirror.fee_override = None
        mirror.notes = (f'Espejo del movimiento #{source.id} de {STORES[source.store_code]["name"]}: '
                        'se edita desde allá.')
        if not mirrored_expenses:
            db.session.add(mirror)
        db.session.flush()
        _sync_expense_account_movements(mirror)
        extra = mirrored_expenses[1:]
    else:
        extra = mirrored_expenses
    for e in extra:
        _sync_expense_account_movements(e, is_delete=True)
        db.session.delete(e)


def validate_inter_store(expense: Expense, data: Dict[str, Any], creating: bool) -> None:
    """Valida para qué fue y la cuenta de llegada en préstamos y abonos."""
    if creating or 'purpose' in data:
        expense.purpose = (data.get('purpose') or '').strip() or None
    if creating or 'arrived_method' in data:
        expense.arrived_method = (data.get('arrived_method') or '').strip() or None
    if expense.category not in ('prestamo_tienda', 'pago_prestamo_tienda'):
        expense.purpose = None
        expense.arrived_method = None
        return
    if expense.direction != 'out':
        raise DebtError('El préstamo o abono a otra tienda es una salida')
    allowed = ('recompra', 'cuenta', 'otro') if expense.category == 'prestamo_tienda' else tuple(INTER_STORE_PURPOSES)
    if expense.purpose is None and not creating:
        return  # préstamos viejos sin "para qué fue": se dejan como estaban
    if expense.purpose not in allowed:
        raise DebtError('Elige para qué fue: ' + ', '.join(INTER_STORE_PURPOSES[p] for p in allowed))
    if expense.purpose == 'cuenta':
        if expense.arrived_method not in EXPENSE_METHODS:
            raise DebtError('Elige a qué cuenta de la otra tienda llegó la plata')
    else:
        expense.arrived_method = None


def mirror_lock_message(expense: Expense) -> Optional[str]:
    if expense.linked_from_id:
        return 'Este registro se creó solo desde la otra tienda: edítalo o bórralo desde allá.'
    return None


def list_purposes() -> List[Dict[str, str]]:
    return [{'value': k, 'label': v} for k, v in INTER_STORE_PURPOSES.items()]
