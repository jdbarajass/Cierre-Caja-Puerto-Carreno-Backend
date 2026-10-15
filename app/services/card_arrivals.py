"""
ADDI + DATÁFONO = plata real del banco (pedido del usuario, 2026-10-14).

Antes, el cierre sumaba a la cuenta ADDI + DATÁFONO todo lo vendido por
datáfono y Addi el mismo día de la venta (bruto), y las comisiones se
descontaban una vez al mes. Así el saldo mezclaba plata que ya está en el
banco con plata que Addi todavía debe, y se podía pensar que estaba
disponible para recompras.

Desde que el admin lo activa (por tienda, con el saldo real del banco):
- El cierre ya NO suma a esta cuenta las ventas por datáfono/Addi
  (`_claim_and_credit_closing` en app/routes/accounts.py). Los excedentes
  del datáfono siguen entrando el día del cierre.
- Cada venta entra sola el día en que llega al banco y ya sin comisión
  (`payment_facts.arrival_date` / `net_amount`): datáfono el siguiente día
  hábil −3,8 %, Addi a los 30 días −7,735 %. Bold igual que el datáfono
  (desde 2026-10-15). Un movimiento `card_arrival` por día de
  llegada y medio (reference_id `card-arrival-<medio>-<AAAA-MM-DD>`), que se
  recalcula si cambian los recibos de Alegra o una corrección a mano.
- La comisión del mes se sigue registrando en Gastos, pero como gasto
  informativo (`account_mode='sin_mover'`): ya viene descontada en lo que llega.
- Lo que falta por llegar (`month_sheet.transit`) se muestra aparte, no está
  en el saldo.

La fecha de arranque (`card_arrivals_since`) es el día en que se igualó la
cuenta al banco: desde el día SIGUIENTE los pagos entran solos (lo que llegó
ese día ya está en el saldo que escribió el usuario).
"""
import logging
from collections import defaultdict
from datetime import date, datetime, timedelta
from typing import Any, Dict, Optional

from app.models.account import Account, AccountMovement
from app.models.app_setting import AppSetting
from app.models.user import db
from app.services.payment_facts import TRANSIT_MEDIOS, arrival_date, net_amount
from app.stores import store_setting_key

logger = logging.getLogger(__name__)

SETTING = 'card_arrivals_since'
ACCOUNT_KEY = 'addi_datafono'
MOVEMENT_TYPE = 'card_arrival'
REF_PREFIX = 'card-arrival-'
ARRIVAL_MEDIOS = TRANSIT_MEDIOS   # incluye Bold (como el datáfono)
MEDIO_LABEL = {'ahorro': 'Datáfono débito', 'credito': 'Datáfono crédito', 'addi': 'Addi', 'bold': 'Bold'}
# Solo se recalculan las llegadas de estos últimos días; las más viejas quedan
# como estaban (los recibos de hace más de un mes ya no cambian).
RECALC_DAYS = 40
# Addi paga a los 30 días (más fines de semana/festivos): se miran ventas de
# hasta 45 días antes de la primera llegada que se recalcula.
SALES_LOOKBACK_DAYS = 45


def since(store: str) -> Optional[date]:
    row = AppSetting.query.get(store_setting_key(SETTING, store))
    if not row or not row.value:
        return None
    try:
        return datetime.strptime(row.value, '%Y-%m-%d').date()
    except ValueError:
        return None


def is_active(store: str) -> bool:
    return since(store) is not None


def set_since(store: str, day: date) -> None:
    key = store_setting_key(SETTING, store)
    row = AppSetting.query.get(key)
    if row is None:
        row = AppSetting(key=key)
        db.session.add(row)
    row.value = day.isoformat()
    row.updated_at = datetime.utcnow()


def reference(medio: str, day: date) -> str:
    return f'{REF_PREFIX}{medio}-{day.isoformat()}'


def parse_reference(ref: str) -> Optional[date]:
    """Día de llegada de un movimiento card_arrival (para Cuentas → Mes)."""
    if not ref or not ref.startswith(REF_PREFIX):
        return None
    try:
        return datetime.strptime(ref[-10:], '%Y-%m-%d').date()
    except ValueError:
        return None


def expected_arrivals(store: str, first: date, today: date) -> Dict[tuple, Dict[str, float]]:
    """(día de llegada, medio) -> {gross, net} de lo que llega entre `first` y `today`."""
    from app.services.month_sheet import sale_entries  # evita import circular
    out: Dict[tuple, Dict[str, float]] = defaultdict(lambda: {'gross': 0.0, 'net': 0.0})
    for sale_day, medio, amount, _ in sale_entries(store, first - timedelta(days=SALES_LOOKBACK_DAYS), today, ARRIVAL_MEDIOS):
        arrives = arrival_date(medio, sale_day) or sale_day
        if first <= arrives <= today:
            g = out[(arrives, medio)]
            g['gross'] += amount
            g['net'] += net_amount(medio, amount)
    return out


def credit_arrivals(store: str, today: date) -> Dict[str, Any]:
    """
    Deja la cuenta con exactamente lo que ya llegó: crea, corrige o borra los
    movimientos card_arrival de los últimos RECALC_DAYS. Se puede llamar
    cuantas veces se quiera (no duplica). No hace commit.
    """
    start = since(store)
    if start is None:
        return {'active': False}
    account = (Account.for_store(store).filter_by(payment_key=ACCOUNT_KEY)
               .with_for_update().first())
    if account is None:
        return {'active': True, 'changed': 0}
    first = max(start + timedelta(days=1), today - timedelta(days=RECALC_DAYS))
    if first > today:
        return {'active': True, 'changed': 0}

    expected = expected_arrivals(store, first, today)
    existing = {}
    for mv in AccountMovement.query.filter_by(account_id=account.id, type=MOVEMENT_TYPE):
        day = parse_reference(mv.reference_id)
        if day and first <= day <= today:
            existing[mv.reference_id] = mv

    changed = 0
    for (day, medio), g in expected.items():
        ref = reference(medio, day)
        net = round(g['net'])
        mv = existing.pop(ref, None)
        if net == 0:
            if mv:
                existing[ref] = mv      # se borra abajo
            continue
        desc = f'Llegó {MEDIO_LABEL.get(medio, medio)} {day.isoformat()} (vendido {round(g["gross"]):,}, neto)'.replace(',', '.')
        if mv is None:
            db.session.add(AccountMovement(account_id=account.id, type=MOVEMENT_TYPE, amount=net,
                                           description=desc, reference_id=ref))
            account.balance += net
            changed += 1
        elif round(mv.amount) != net:
            account.balance += net - mv.amount
            mv.amount = net
            mv.description = desc
            changed += 1
    for mv in existing.values():          # ya no debe llegar nada ese día (corrección)
        account.balance -= mv.amount
        db.session.delete(mv)
        changed += 1
    if changed:
        logger.info(f'[{store}] Llegadas datáfono/Addi: {changed} movimiento(s) creados o corregidos')
    return {'active': True, 'changed': changed}


def credit_arrivals_safely(store: str, today: date) -> None:
    """Para llamarlo al consultar: si algo falla, no rompe la pantalla."""
    try:
        if not is_active(store):
            return
        credit_arrivals(store, today)
        db.session.commit()   # también suelta el bloqueo de la cuenta
    except Exception as e:  # noqa: BLE001 - nunca tumbar la consulta por esto
        db.session.rollback()
        logger.error(f'[{store}] No se pudieron acreditar las llegadas de datáfono/Addi: {e}', exc_info=True)
