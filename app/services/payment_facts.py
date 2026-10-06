"""
Ventas por medio de pago desde los recibos de pago de Alegra (Fase 2 de
docs/PLAN_CUENTAS_DIARIAS.md).

Cada recibo (`/payments`, tipo `in`) trae `paymentMethod` y `bankAccount`;
con los dos se separan los 10 medios del Excel (verificado el 5-oct-2026
contra el Excel: cuadra exacto). La venta cuenta el día de la FACTURA.

También: festivos de Colombia, fecha en que llega la plata del datáfono
(siguiente día hábil, −3,8 %) y de Addi (30 días, −6,5 % + IVA).
"""
import logging
from datetime import date, datetime, timedelta
from functools import lru_cache
from typing import Any, Dict, List, Optional, Tuple

from app.models.user import db
from app.models.month_sheet import PaymentFact

logger = logging.getLogger(__name__)

# Desde aquí se cargan los recibos: las cuentas diarias arrancan el 1-oct,
# pero el resumen mensual (Fase 3) arranca en septiembre y necesita sus
# ventas por medio de pago.
PAYMENTS_START = date(2026, 9, 1)
RECENT_DAYS = 7          # cada noche se recargan los últimos días
PAGE_SIZE = 30           # máximo que entrega Alegra por página
MAX_PAGES = 120

# Los 10 medios de venta del Excel, en el orden de sus columnas
SALE_MEDIOS = ('efectivo', 'qr', 'ahorro', 'credito', 'nequi', 'addi',
               'bbva', 'daviplata', 'sistecredito', 'bold')

# Medio de venta -> cuenta de Resumen donde termina la plata.
# Ahorro/crédito (datáfono) y Addi llegan a Bancolombia …6018 (ADDI + DATÁFONO).
# Bold: llega a la misma cuenta del datáfono y Addi (confirmado por el usuario
# 2026-10-06, "por el momento"); su comisión y días de llegada no se conocen,
# así que no entra a la plata en tránsito.
MEDIO_ACCOUNT = {
    'efectivo': 'cash', 'qr': 'qr', 'ahorro': 'addi_datafono', 'credito': 'addi_datafono',
    'addi': 'addi_datafono', 'nequi': 'nequi', 'daviplata': 'daviplata', 'bbva': 'bbva',
    'sistecredito': 'sistecredito', 'bold': 'addi_datafono',
}

DATAFONO_FEE = 0.038             # datáfono débito y crédito
ADDI_FEE = 0.065 * 1.19          # tarifa de intermediación 6,5 % + IVA 19 % = 7,735 %
ADDI_DAYS = 30
FEES = {'ahorro': DATAFONO_FEE, 'credito': DATAFONO_FEE, 'addi': ADDI_FEE}
TRANSIT_MEDIOS = ('ahorro', 'credito', 'addi')


# ─────────────────────────────────────────────
#  Festivos y días hábiles
# ─────────────────────────────────────────────

def _easter(year: int) -> date:
    """Domingo de Pascua (algoritmo anónimo gregoriano)."""
    a = year % 19
    b, c = divmod(year, 100)
    d, e = divmod(b, 4)
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i, k = divmod(c, 4)
    l = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * l) // 451
    month = (h + l - 7 * m + 114) // 31
    day = ((h + l - 7 * m + 114) % 31) + 1
    return date(year, month, day)


def _next_monday(d: date) -> date:
    return d + timedelta(days=(7 - d.weekday()) % 7)


@lru_cache(maxsize=16)
def colombia_holidays(year: int) -> frozenset:
    """Festivos de Colombia (Ley 51 de 1983 "Ley Emiliani")."""
    fixed = [date(year, 1, 1), date(year, 5, 1), date(year, 7, 20), date(year, 8, 7),
             date(year, 12, 8), date(year, 12, 25)]
    moved = [_next_monday(date(year, m, d)) for m, d in
             ((1, 6), (3, 19), (6, 29), (8, 15), (10, 12), (11, 1), (11, 11))]
    e = _easter(year)
    easter_based = [e - timedelta(days=3), e - timedelta(days=2),          # jueves y viernes santo
                    e + timedelta(days=43), e + timedelta(days=64),        # Ascensión, Corpus
                    e + timedelta(days=71)]                                # Sagrado Corazón
    return frozenset(fixed + moved + easter_based)


def is_business_day(d: date) -> bool:
    return d.weekday() < 5 and d not in colombia_holidays(d.year)


def next_business_day(d: date) -> date:
    """El primer día hábil DESPUÉS de d."""
    d += timedelta(days=1)
    while not is_business_day(d):
        d += timedelta(days=1)
    return d


def arrival_date(medio: str, sale_date: date) -> Optional[date]:
    """Cuándo llega a la cuenta la plata de una venta (None = llega el mismo día)."""
    if medio in ('ahorro', 'credito'):
        return next_business_day(sale_date)
    if medio == 'addi':
        d = sale_date + timedelta(days=ADDI_DAYS)
        return d if is_business_day(d) else next_business_day(d)
    return None


def net_amount(medio: str, amount: float) -> float:
    return amount * (1 - FEES.get(medio, 0))


# ─────────────────────────────────────────────
#  Clasificación de un recibo
# ─────────────────────────────────────────────

def classify_payment(method: str, bank_name: str) -> Tuple[str, bool]:
    """
    (medio, needs_review) a partir del método de pago y la cuenta de Alegra.
    needs_review=True cuando la regla adivina (ej. una transferencia
    registrada en una caja: el usuario la cuenta como QR).
    """
    method = (method or '').lower()
    name = (bank_name or '').lower()
    if 'addi' in name:
        return 'addi', False
    if 'bold' in name:
        return 'bold', False
    if 'sistecr' in name:
        return 'sistecredito', False
    if 'nequi' in name:
        return 'nequi', False
    if 'daviplata' in name:
        return 'daviplata', False
    if 'bbva' in name:
        return 'bbva', False
    if 'datafono' in name or 'datáfono' in name or method in ('debit-card', 'credit-card'):
        if method == 'credit-card':
            return 'credito', False
        return 'ahorro', method != 'debit-card'
    if 'qr' in name:
        return 'qr', False
    if method == 'cash':
        return 'efectivo', False
    if method == 'transfer':
        return 'qr', True
    return 'otro', True


def _parse_date(value) -> Optional[date]:
    try:
        return datetime.strptime(str(value)[:10], '%Y-%m-%d').date()
    except (TypeError, ValueError):
        return None


def payment_rows(payment: Dict[str, Any], since: date) -> List[Dict[str, Any]]:
    """Filas de PaymentFact de un recibo (una por factura con fecha >= since)."""
    if (payment.get('status') or '').lower() == 'void' or (payment.get('type') or 'in') != 'in':
        return []
    pdate = _parse_date(payment.get('date'))
    if pdate is None:
        return []
    bank = payment.get('bankAccount') or {}
    bank_name = bank.get('name') if isinstance(bank, dict) else str(bank)
    medio, review = classify_payment(payment.get('paymentMethod'), bank_name)
    rows = []
    for inv in payment.get('invoices') or []:
        inv_date = _parse_date(inv.get('date')) or pdate
        if inv_date < since:
            continue
        rows.append({
            'payment_id': str(payment.get('id')),
            'invoice_id': str(inv.get('id')),
            'invoice_number': str(inv.get('number') or '')[:40],
            'invoice_date': inv_date,
            'payment_date': pdate,
            'payment_method': (payment.get('paymentMethod') or '')[:30],
            'bank_account': (bank_name or '')[:120],
            'medio': medio,
            'needs_review': review,
            'amount': int(round(float(inv.get('amount') or 0))),
        })
    return rows


# ─────────────────────────────────────────────
#  Carga desde Alegra
# ─────────────────────────────────────────────

def default_since(store_code: str, today: date) -> date:
    """Primera vez: desde PAYMENTS_START; después, solo los últimos días."""
    has_any = PaymentFact.for_store(store_code).first() is not None
    if not has_any:
        return PAYMENTS_START
    return max(PAYMENTS_START, today - timedelta(days=RECENT_DAYS))


def sync_payments(alegra_client, store_code: str, since: date) -> Dict[str, Any]:
    """
    Trae los recibos de Alegra (del más nuevo al más viejo) hasta pasar
    `since` y reemplaza los de la tienda con factura desde `since`. Primero
    descarga todo y solo después borra/inserta: si Alegra falla no se pierde
    nada.
    """
    rows: List[Dict[str, Any]] = []
    start = 0
    pages = 0
    while pages < MAX_PAGES:
        page = alegra_client.get_payments_page(start, PAGE_SIZE)
        pages += 1
        for p in page:
            rows.extend(payment_rows(p, since))
        dates = [_parse_date(p.get('date')) for p in page]
        if len(page) < PAGE_SIZE or all(d is not None and d < since for d in dates):
            break
        start += PAGE_SIZE
    else:
        logger.warning(f'[{store_code}] sync_payments: se alcanzó el tope de {MAX_PAGES} páginas')

    # Un mismo recibo/factura no se repite
    unique = {(r['payment_id'], r['invoice_id']): r for r in rows}

    PaymentFact.for_store(store_code).filter(PaymentFact.invoice_date >= since).delete(synchronize_session=False)
    for r in unique.values():
        db.session.add(PaymentFact(store_code=store_code, **r))
    db.session.commit()
    logger.info(f'[{store_code}] sync_payments desde {since}: {len(unique)} pagos ({pages} páginas)')
    return {'since': since.isoformat(), 'payments': len(unique), 'pages': pages}
