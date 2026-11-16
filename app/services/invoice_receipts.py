"""
Pagos reales de cada factura desde los recibos de Alegra (`/payments`).

Desde el 2026-11-09 /invoices ya no trae `payments` y `ensure_invoice_payments`
armaba el pago con `paymentForm`: una factura pagada con dos medios quedaba
COMPLETA en uno. Caso real (Carreño, 15-nov-2026): KPC4934 por $170.100 pagada
con $60.100 en efectivo + $110.000 por QR quedó toda en transferencia; la
preconsulta decía efectivo $282.800 / transferencia $320.100 y el Reporte
diario de Alegra (y el Excel del cierre) efectivo $342.900 / transferencia
$260.000.

Cada recibo (`/payments`, tipo in) sí trae la división: su paymentMethod y
`invoices[]` con el monto aplicado a cada factura. Aquí se arma, para un día,
{id de factura: [{amount, paymentMethod}]} con los recibos de esa factura.

- Los recibos se recorren del más nuevo al más viejo hasta pasar el día pedido
  (hoy = 1 página). Un recibo nunca tiene fecha anterior a su factura, así que
  al llegar a recibos más viejos que el día, ese día y todos los posteriores
  quedan completos (se guardan en caché los días pasados).
- Más atrás de RECEIPTS_LOOKBACK_DAYS o si Alegra falla: devuelve None y se
  sigue usando `paymentForm` (lo de antes). Nunca rompe el cierre.
"""
import logging
import threading
from datetime import date as date_cls, timedelta
from typing import Callable, Dict, List, Optional

from app.utils.ttl_cache import TTLCache

logger = logging.getLogger(__name__)

RECEIPTS_PAGE_SIZE = 30         # máximo de /payments
RECEIPTS_MAX_PAGES = 60         # tope de seguridad por recorrido (1.800 recibos)
RECEIPTS_LOOKBACK_DAYS = 62     # más atrás no se recorre: se usa paymentForm
RECEIPTS_CACHE_TTL_SECONDS = 600

_receipts_cache = TTLCache()
_locks: Dict[str, threading.Lock] = {}
_locks_guard = threading.Lock()


def _lock_for(key: str) -> threading.Lock:
    with _locks_guard:
        return _locks.setdefault(key, threading.Lock())


def _day(value) -> Optional[date_cls]:
    try:
        return date_cls.fromisoformat(str(value or '')[:10])
    except ValueError:
        return None


def needs_receipts(invoices) -> bool:
    """¿Alguna factura activa y pagada llegó sin `payments`?"""
    for inv in invoices or []:
        if not isinstance(inv, dict) or inv.get('payments'):
            continue
        if str(inv.get('status') or '').lower() == 'void':
            continue
        try:
            if float(inv.get('totalPaid') or inv.get('total') or 0) > 0:
                return True
        except (TypeError, ValueError):
            continue
    return False


def clear_cache() -> None:
    _receipts_cache.clear()


def receipts_by_invoice_for_date(
    fetch_page: Callable[[int, int], List[Dict]],
    cache_user: str,
    day: str,
    today: str,
) -> Optional[Dict[str, List[Dict]]]:
    """
    {id de factura (str): [{'amount', 'paymentMethod'}]} de las facturas con
    fecha `day`, según los recibos de Alegra. None = no se pudo saber.
    `fetch_page(start, limit)` devuelve una página de /payments (tipo in) del
    más nuevo al más viejo y lanza excepción si falla.
    """
    target, today_d = _day(day), _day(today)
    if target is None or today_d is None or target > today_d:
        return None
    if (today_d - target).days > RECEIPTS_LOOKBACK_DAYS:
        return None

    key = f"{cache_user}|{day}"
    cached = _receipts_cache.get(key)
    if cached is not None:
        return cached

    with _lock_for(cache_user):
        cached = _receipts_cache.get(key)   # otro hilo pudo llenarlo mientras se esperaba
        if cached is not None:
            return cached

        by_date: Dict[date_cls, Dict[str, List[Dict]]] = {}
        reached = False
        try:
            for page_no in range(RECEIPTS_MAX_PAGES):
                page = fetch_page(page_no * RECEIPTS_PAGE_SIZE, RECEIPTS_PAGE_SIZE) or []
                for receipt in page:
                    if not isinstance(receipt, dict):
                        continue
                    if str(receipt.get('status') or '').lower() == 'void':
                        continue
                    if (receipt.get('type') or 'in') != 'in':
                        continue
                    method = receipt.get('paymentMethod') or ''
                    pdate = _day(receipt.get('date'))
                    for inv in receipt.get('invoices') or []:
                        if not isinstance(inv, dict) or inv.get('id') in (None, ''):
                            continue
                        inv_date = _day(inv.get('date')) or pdate
                        if inv_date is None or inv_date < target:
                            continue
                        try:
                            amount = float(inv.get('amount') or 0)
                        except (TypeError, ValueError):
                            amount = 0
                        if amount <= 0:
                            continue
                        by_date.setdefault(inv_date, {}).setdefault(str(inv['id']), []).append(
                            {'amount': amount, 'paymentMethod': method})
                dates = [d for d in (_day(r.get('date')) for r in page if isinstance(r, dict)) if d]
                if len(page) < RECEIPTS_PAGE_SIZE or (dates and max(dates) < target):
                    reached = True   # no hay más recibos o ya todos son de antes del día
                    break
        except Exception as e:  # noqa: BLE001 - si Alegra falla se sigue con paymentForm
            logger.warning(f"No se pudieron leer los recibos de Alegra para {day}: {e}")
            return None

        if not reached:
            logger.warning(f"Recibos de Alegra: no se llegó al {day} en {RECEIPTS_MAX_PAGES} páginas")
            return None

        # Del día pedido hasta ayer quedan completos: caché (hoy siguen llegando)
        d = target
        while d < today_d:
            _receipts_cache.set(f"{cache_user}|{d.isoformat()}", by_date.get(d, {}),
                                RECEIPTS_CACHE_TTL_SECONDS)
            d += timedelta(days=1)
        return by_date.get(target, {})
