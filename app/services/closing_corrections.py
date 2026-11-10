"""
Corrección de cierres por el admin (Cuentas → Corrección de cierres, 2026-11-09).

Pedido del usuario: cuando una vendedora se equivoca en Alegra (ej. una venta
pagada en efectivo quedó como transferencia) el cierre nunca sale "exitoso" y
no pasa a Cuentas. No importa que Alegra quede con el medio de pago mal; lo
que sí debe cuadrar es el TOTAL de ventas del día entre Alegra y la plataforma,
y en la plataforma todo debe quedar como pasó de verdad.

Reglas:
- Solo el admin (el de solo lectura no). Solo cierres sin sincronizar (si ya
  pasó a Cuentas se corrige con un ajuste manual, como siempre).
- Venta por medio (efectivo, QR, Nequi, Daviplata, datáfono) + lo que Alegra
  tenga en medios que el cierre no maneja (BBVA, SisteCrédito) = total de
  Alegra del día. Si no, no se guarda.
- Efectivo a consignar = venta en efectivo + excedente en efectivo − gastos que
  salieron de la caja (los ya registrados del cierre de ese día).
- El reparto por medio de ese día se corrige también en Cuentas → Mes y Año
  (SaleMethodCorrection con la nota "Corrección del cierre AAAA-MM-DD"; una
  nueva corrección reemplaza las anteriores del mismo cierre).
- El cierre queda 'corrected' (se puede sincronizar), con rastro de quién,
  cuándo, la nota, lo que había antes y lo que quedó. Se sincroniza enseguida.
"""
import json
from collections import defaultdict
from datetime import date, datetime, timedelta
from typing import Any, Dict, List, Optional

from app.models.cash_closing import CashClosing
from app.models.expense import Expense
from app.models.month_sheet import MonthClose, SaleMethodCorrection
from app.models.user import db

# Campo del cierre -> medios de venta de Alegra (payment_facts.SALE_MEDIOS)
GROUPS = {
    'efectivo': ('efectivo',),
    'qr': ('qr',),
    'nequi': ('nequi',),
    'daviplata': ('daviplata',),
    'datafono': ('ahorro', 'credito', 'addi', 'bold'),
}
OTHER_MEDIOS = ('bbva', 'sistecredito')
EXCEDENTE_KEYS = ('efectivo', 'qr', 'nequi', 'daviplata', 'datafono')
MARK = 'Corrección del cierre {date}'
CLOSING_EXPENSE_NOTE = 'Gasto operativo del cierre de caja {date}'   # = cash_closing.CLOSING_EXPENSE_NOTE


class CorrectionError(ValueError):
    """Dato inválido o regla incumplida: se responde 400."""


def _marker(day: date) -> str:
    return MARK.format(date=day.isoformat())


def _own_corrections(store: str, day: date) -> List[SaleMethodCorrection]:
    return SaleMethodCorrection.for_store(store).filter(
        SaleMethodCorrection.date == day, SaleMethodCorrection.note.like(_marker(day) + '%')).all()


def alegra_day(store: str, day: date) -> Dict[str, float]:
    """Venta del día por medio según Alegra (con las correcciones a mano de
    Cuentas → Mes, pero SIN las de una corrección de cierre anterior)."""
    from app.services.month_sheet import day_by_medio
    out = defaultdict(float, day_by_medio(store, day))
    for c in _own_corrections(store, day):
        out[c.to_medio] -= c.amount
        out[c.from_medio] += c.amount
    return dict(out)


def _groups(by_medio: Dict[str, float]) -> Dict[str, float]:
    g = {k: sum(by_medio.get(m, 0) for m in medios) for k, medios in GROUPS.items()}
    g['otros'] = sum(by_medio.get(m, 0) for m in OTHER_MEDIOS)
    return g


def caja_gastos(store: str, day: date) -> float:
    """Gastos que salieron de la caja ese día (los del popup del cierre)."""
    rows = Expense.for_store(store).filter(Expense.notes == CLOSING_EXPENSE_NOTE.format(date=day.isoformat())).all()
    return float(sum(e.total for e in rows))


def _closing_values(c: CashClosing) -> Dict[str, Any]:
    ex = c.excedentes()
    return {
        'efectivo_consignar': c.efectivo, 'qr': c.qr, 'nequi': c.nequi, 'daviplata': c.daviplata,
        'datafono': c.addi_datafono,
        'excedentes': {'efectivo': ex['cash'], 'qr': ex['qr'], 'nequi': ex['nequi'],
                       'daviplata': ex['daviplata'], 'datafono': ex['addi_datafono']},
        'validation_status': c.validation_status, 'validation_message': c.validation_message,
    }


def _view(store: str, c: CashClosing) -> Dict[str, Any]:
    day = c.closing_date
    by_medio = alegra_day(store, day)
    groups = _groups(by_medio)
    return {
        'date': day.isoformat(),
        'status': c.validation_status,
        'message': c.validation_message,
        'synced': bool(c.synced_to_accounts),
        'current': _closing_values(c),
        'alegra': {**groups, 'total': sum(groups.values()), 'loaded': bool(by_medio)},
        'caja_gastos': caja_gastos(store, day),
        'history': json.loads(c.correction_log) if c.correction_log else [],
    }


def list_closings(store: str, today: date) -> Dict[str, Any]:
    pending = [c for c in CashClosing.for_store(store).filter(
        CashClosing.synced_to_accounts == False).order_by(CashClosing.closing_date.asc()).all()  # noqa: E712
        if not c.can_sync]
    corrected = CashClosing.for_store(store).filter(
        CashClosing.validation_status == 'corrected',
        CashClosing.closing_date >= today - timedelta(days=90)).order_by(CashClosing.closing_date.desc()).all()
    return {'pending': [_view(store, c) for c in pending], 'corrected': [_view(store, c) for c in corrected]}


def _amount(data: Dict[str, Any], key: str) -> int:
    try:
        v = int(round(float(data.get(key) or 0)))
    except (TypeError, ValueError):
        raise CorrectionError(f'{key} no es un número')
    if v < 0:
        raise CorrectionError(f'{key} no puede ser negativo')
    return v


def _plan_corrections(alegra: Dict[str, float], real: Dict[str, int]) -> List[tuple]:
    """Movimientos (de_medio, a_medio, valor) para que el día quede con el
    reparto real. Los grupos que tienen de más en Alegra le pasan a los que
    tienen de menos; del datáfono se toma de los medios que tengan valor."""
    groups = _groups(alegra)
    surplus = {k: groups[k] - real[k] for k in GROUPS if groups[k] - real[k] > 0.5}
    deficit = {k: real[k] - groups[k] for k in GROUPS if real[k] - groups[k] > 0.5}
    available = {m: alegra.get(m, 0) for medios in GROUPS.values() for m in medios}
    moves = []
    for to_group, need in deficit.items():
        to_medio = GROUPS[to_group][0]   # datáfono que falta → débito
        for from_group in list(surplus):
            if need <= 0.5:
                break
            for from_medio in GROUPS[from_group]:
                take = min(need, surplus[from_group], available[from_medio])
                if take > 0.5:
                    moves.append((from_medio, to_medio, int(round(take))))
                    available[from_medio] -= take
                    surplus[from_group] -= take
                    need -= take
                if surplus[from_group] <= 0.5 or need <= 0.5:
                    break
            if surplus[from_group] <= 0.5:
                surplus.pop(from_group)
    return moves


def correct(store: str, day: date, data: Dict[str, Any], user: Dict[str, Any], today: date) -> Dict[str, Any]:
    closing = CashClosing.for_store(store).filter_by(closing_date=day).first()
    if closing is None:
        raise CorrectionError(f'No hay cierre guardado del {day.isoformat()}: primero hay que enviarlo desde Cierre de Caja.')
    if closing.synced_to_accounts:
        raise CorrectionError('Ese cierre ya pasó a Cuentas: corrígelo con un ajuste manual en Cuentas → Resumen.')
    if day > today:
        raise CorrectionError('No se puede corregir un cierre de un día que no ha pasado.')
    if MonthClose.for_store(store).filter_by(period=day.strftime('%Y-%m')).first():
        raise CorrectionError('El mes de ese cierre está cerrado: reábrelo en Cuentas → Mes para corregir.')
    note = (data.get('note') or '').strip()
    if len(note) < 5:
        raise CorrectionError('Escribe en la nota qué pasó (por ejemplo, qué venta se registró mal y por qué).')

    real = {k: _amount(data, k) for k in ('efectivo', 'qr', 'nequi', 'daviplata', 'datafono')}
    exc = {k: _amount(data.get('excedentes') or {}, k) for k in EXCEDENTE_KEYS}
    alegra = alegra_day(store, day)
    if not alegra:
        raise CorrectionError('Todavía no están cargadas las ventas de Alegra de ese día (se cargan con el cron de las 9 pm '
                              'o con "Traer ventas de Alegra" en Cuentas → Mes).')
    groups = _groups(alegra)
    alegra_total = sum(groups.values())
    real_total = sum(real.values()) + groups['otros']
    if abs(real_total - alegra_total) > 1:
        raise CorrectionError(f'La venta del día debe sumar lo mismo que Alegra: Alegra {int(alegra_total):,} y la corrección '
                              f'{int(real_total):,} (diferencia {int(real_total - alegra_total):,}). Los excedentes van aparte '
                              f'porque no son venta.'.replace(',', '.'))
    gastos = caja_gastos(store, day)
    consignar = real['efectivo'] + exc['efectivo'] - gastos
    if consignar < 0:
        raise CorrectionError('Los gastos de la caja de ese día son mayores que el efectivo: revisa los valores.')

    before = _closing_values(closing)
    for c in _own_corrections(store, day):
        db.session.delete(c)
    db.session.flush()
    moves = _plan_corrections(alegra, real)
    marker = _marker(day)
    for from_medio, to_medio, amount in moves:
        db.session.add(SaleMethodCorrection(store_code=store, date=day, from_medio=from_medio, to_medio=to_medio,
                                            amount=amount, note=f'{marker}: {note}'[:1000],
                                            created_by=user.get('userId')))

    closing.efectivo = consignar
    closing.qr, closing.nequi, closing.daviplata = real['qr'], real['nequi'], real['daviplata']
    closing.addi_datafono = real['datafono']
    closing.excedente_efectivo, closing.excedente_qr = exc['efectivo'], exc['qr']
    closing.excedente_nequi, closing.excedente_daviplata = exc['nequi'], exc['daviplata']
    closing.excedente_datafono = exc['datafono']
    closing.validation_status = 'corrected'
    closing.validation_message = f'Corregido por el admin: {note}'[:500]
    closing.alegra_checked = True
    closing.alegra_discrepancy = 0   # el total cuadra con Alegra; el reparto quedó como pasó de verdad
    history = json.loads(closing.correction_log) if closing.correction_log else []
    history.append({'at': datetime.utcnow().isoformat() + 'Z', 'by': user.get('email') or user.get('userId'),
                    'note': note, 'before': before, 'after': _closing_values(closing),
                    'alegra': {k: groups[k] for k in groups}, 'moves': moves})
    closing.correction_log = json.dumps(history, ensure_ascii=False)
    db.session.commit()

    # Pasa a Cuentas enseguida (mismo camino que "Sincronizar ahora")
    from app.routes.accounts import _claim_and_credit_closing
    sync = _claim_and_credit_closing(closing, user.get('userId'))
    return {'closing': _view(store, closing), 'moves': [{'from': f, 'to': t, 'amount': a} for f, t, a in moves],
            'credited': sync.get('credited', []), 'efectivo_consignar': consignar}


def unsuccessful(store: str, start: date, today: date) -> List[Dict[str, str]]:
    """Cierres guardados que no salieron exitosos y no se han corregido (aviso de Cierre de Caja)."""
    rows = CashClosing.for_store(store).filter(
        CashClosing.synced_to_accounts == False,  # noqa: E712
        CashClosing.closing_date >= start, CashClosing.closing_date <= today,
    ).order_by(CashClosing.closing_date.asc()).all()
    return [{'date': c.closing_date.isoformat(), 'message': c.validation_message or ''} for c in rows if not c.can_sync]
