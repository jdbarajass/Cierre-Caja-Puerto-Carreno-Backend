"""
Carga el resumen de las facturas de Alegra en InvoiceFact (por tienda, día
por día). Ver app/models/invoice_fact.py.

Usa `AlegraClient.get_invoices_by_date`, el mismo método (y la misma caché de
días pasados) con el que la plataforma ya consulta las facturas para el
cierre de caja: no es una fuente nueva.

Reglas:
  - Un día se REEMPLAZA completo (borrar e insertar en la misma transacción),
    así volver a cargarlo es seguro y recoge facturas anuladas o editadas.
  - Las facturas se piden ANTES de tocar la base: si Alegra falla, los datos
    que ya había de ese día quedan intactos.
  - Al primer error se detiene la carga del rango y devuelve hasta dónde
    llegó; se puede volver a llamar y sigue con los días que falten.
  - Una sola carga a la vez por tienda (`store_sync_lock`): dos cargas al
    mismo tiempo sobre el mismo día chocaban con la unicidad (tienda,
    alegra_id) — visto en producción 2026-10-02 al dar clic otra vez
    mientras la primera seguía corriendo en el servidor.
"""
import logging
import time
import zlib
from contextlib import contextmanager
from datetime import date, datetime, timedelta
from typing import Any, Dict, Iterable, List, Optional

from sqlalchemy import func, text

from app.models.invoice_fact import InvoiceFact, InvoiceItemFact, InvoiceSyncDay
from app.exceptions import CierreCajaException
from app.models.user import db
from app.utils.formatters import is_invoice_void, safe_number

logger = logging.getLogger(__name__)


def _money(value) -> int:
    return int(round(safe_number(value)))


def _str(value, max_len) -> str:
    return str(value or '').strip()[:max_len] or None


def _items_gross(invoice: Dict[str, Any]) -> float:
    return sum(safe_number(i.get('price')) * safe_number(i.get('quantity') or 1)
               for i in invoice.get('items') or [])


def invoice_discount(invoice: Dict[str, Any]) -> int:
    """
    Descuento de la factura en pesos. Alegra lo trae a nivel de factura
    (`discount`); si no viniera, se calcula por ítem (`discount` del ítem es
    un PORCENTAJE sobre precio × cantidad).
    """
    if invoice.get('discount') is not None:
        return _money(invoice.get('discount'))
    total = 0.0
    for item in invoice.get('items') or []:
        pct = safe_number(item.get('discount'))
        if pct:
            total += safe_number(item.get('price')) * safe_number(item.get('quantity') or 1) * pct / 100
    return int(round(total))


def invoice_to_fact(invoice: Dict[str, Any]) -> Dict[str, Any]:
    """Campos de InvoiceFact a partir de una factura de /api/v1/invoices."""
    client = invoice.get('client') or {}
    seller = invoice.get('seller') or {}
    template = invoice.get('numberTemplate') or {}
    subtotal = invoice.get('subtotal')
    return {
        'alegra_id': str(invoice.get('id')),
        'number': _str(template.get('fullNumber') or template.get('number') or invoice.get('number'), 40),
        'client_id': _str(client.get('id'), 30),
        'client_name': _str(client.get('name'), 200),
        'client_identification': _str(client.get('identification'), 40),
        'seller_id': _str(seller.get('id'), 30),
        'seller_name': _str(seller.get('name'), 120),
        'subtotal': _money(subtotal) if subtotal is not None else int(round(_items_gross(invoice))),
        'discount': invoice_discount(invoice),
        'total': _money(invoice.get('total')),
        'voided': is_invoice_void(invoice),
    }


def invoice_to_items(invoice: Dict[str, Any]) -> List[Dict[str, Any]]:
    """
    Renglones de InvoiceItemFact de una factura de /api/v1/invoices. Las
    anuladas no tienen prendas vendidas (lista vacía). `items[].discount` es
    PORCENTAJE y `items[].total` ya trae el descuento.
    """
    if is_invoice_void(invoice):
        return []
    seller = invoice.get('seller') or {}
    rows = []
    for line, item in enumerate(invoice.get('items') or []):
        quantity = safe_number(item.get('quantity'))
        price = safe_number(item.get('price'))
        pct = safe_number(item.get('discount'))
        total = item.get('total')
        rows.append({
            'invoice_alegra_id': str(invoice.get('id')),
            'line': line,
            'seller_id': _str(seller.get('id'), 30),
            'seller_name': _str(seller.get('name'), 120),
            'item_id': _str(item.get('id'), 30),
            'name': _str(item.get('name'), 200) or 'Sin nombre',
            'quantity': int(round(quantity)),
            'unit_price': _money(price),
            'discount_pct': float(pct),
            'total': _money(total) if total is not None else int(round(price * quantity * (1 - pct / 100))),
        })
    return rows


def sync_day(alegra_client, store_code: str, day: date) -> int:
    """Reemplaza las facturas guardadas de `day` por las que tiene Alegra. Devuelve cuántas."""
    invoices = alegra_client.get_invoices_by_date(day.isoformat())  # si falla, no se toca nada
    # Si Alegra repitiera una factura entre páginas, se guarda una sola vez.
    unique_invoices = list({str(i['id']): i for i in invoices if i.get('id') is not None}.values())
    facts = [invoice_to_fact(i) for i in unique_invoices]
    items = [row for i in unique_invoices for row in invoice_to_items(i)]

    try:
        base = InvoiceFact.query.filter(InvoiceFact.store_code == store_code)
        base.filter(InvoiceFact.date == day).delete(synchronize_session=False)
        # Una factura a la que le cambiaron la fecha en Alegra estaría guardada
        # en otro día: se quita para no chocar con la unicidad (tienda, alegra_id).
        ids = [f['alegra_id'] for f in facts]
        if ids:
            base.filter(InvoiceFact.alegra_id.in_(ids)).delete(synchronize_session=False)
        db.session.add_all(InvoiceFact(store_code=store_code, date=day, **f) for f in facts)

        # Prendas: mismo reemplazo completo del día (y de las facturas movidas de fecha)
        items_base = InvoiceItemFact.query.filter(InvoiceItemFact.store_code == store_code)
        items_base.filter(InvoiceItemFact.date == day).delete(synchronize_session=False)
        if ids:
            items_base.filter(InvoiceItemFact.invoice_alegra_id.in_(ids)).delete(synchronize_session=False)
        db.session.add_all(InvoiceItemFact(store_code=store_code, date=day, **row) for row in items)

        sync_row = InvoiceSyncDay.query.filter_by(store_code=store_code, date=day).first()
        if sync_row is None:
            sync_row = InvoiceSyncDay(store_code=store_code, date=day)
            db.session.add(sync_row)
        sync_row.invoice_count = len(facts)
        sync_row.items_synced = True
        sync_row.synced_at = datetime.utcnow()
        db.session.commit()
    except Exception:
        db.session.rollback()
        raise
    return len(facts)


# Base de las llaves de pg_advisory_lock (una por tienda). Distinta de la
# de la migración multi-tienda (app/__init__.py).
SYNC_LOCK_KEY_BASE = 7420261002_000_000


@contextmanager
def store_sync_lock(store_code: str):
    """
    Candado de la carga de facturas de UNA tienda, compartido entre los
    workers de gunicorn y el cron. Entrega True si se obtuvo y False si ya
    hay otra carga corriendo (no espera). Usa una conexión propia para que
    el candado no dependa de las transacciones de la sesión (se hace commit
    por día). Si el proceso muere, Postgres lo suelta al cerrarse la conexión.
    Fuera de Postgres (tests con SQLite) no bloquea.
    """
    if db.engine.dialect.name != 'postgresql':
        yield True
        return
    key = SYNC_LOCK_KEY_BASE + zlib.crc32(store_code.encode()) % 1_000_000
    conn = db.engine.connect()
    try:
        acquired = bool(conn.execute(text('SELECT pg_try_advisory_lock(:k)'), {'k': key}).scalar())
        try:
            yield acquired
        finally:
            if acquired:
                conn.execute(text('SELECT pg_advisory_unlock(:k)'), {'k': key})
    finally:
        conn.close()


def _days(start: date, end: date) -> Iterable[date]:
    day = start
    while day <= end:
        yield day
        day += timedelta(days=1)


def missing_days(store_code: str, start: date, end: date) -> List[date]:
    """Días del rango que todavía no se han cargado para la tienda."""
    loaded = {row.date for row in InvoiceSyncDay.query.filter(
        InvoiceSyncDay.store_code == store_code,
        InvoiceSyncDay.date >= start,
        InvoiceSyncDay.date <= end,
    ).with_entities(InvoiceSyncDay.date)}
    return [d for d in _days(start, end) if d not in loaded]


def missing_item_days(store_code: str, start: date, end: date) -> List[date]:
    """Días del rango sin prendas guardadas (sin cargar, o cargados antes de existir las prendas)."""
    with_items = {row.date for row in InvoiceSyncDay.query.filter(
        InvoiceSyncDay.store_code == store_code,
        InvoiceSyncDay.date >= start,
        InvoiceSyncDay.date <= end,
        InvoiceSyncDay.items_synced.is_(True),
    ).with_entities(InvoiceSyncDay.date)}
    return [d for d in _days(start, end) if d not in with_items]


def pending_days(store_code: str, start: date, end: date) -> List[date]:
    """
    Días a cargar (les falta el resumen de facturas o las prendas), del MÁS
    RECIENTE al más antiguo: así "Este mes" y "Mes anterior" quedan completos
    primero (con el orden contrario, octubre esperaba ~9 noches).
    """
    return sorted(set(missing_days(store_code, start, end)) | set(missing_item_days(store_code, start, end)),
                  reverse=True)


def sync_range(alegra_client, store_code: str, days: List[date],
               deadline: Optional[float] = None) -> Dict[str, Any]:
    """
    Carga los días indicados en orden. Se detiene en el primer error, o al
    pasar `deadline` (time.monotonic()), y devuelve lo que alcanzó a cargar
    para continuar en otra llamada.
    """
    synced, invoices = [], 0
    for day in days:
        if deadline is not None and time.monotonic() >= deadline:
            return {'synced_days': synced, 'invoices': invoices, 'failed_day': None,
                    'error': None, 'stopped_by_time': True}
        try:
            invoices += sync_day(alegra_client, store_code, day)
            synced.append(day.isoformat())
        except Exception as e:
            # El detalle técnico va al log; al usuario, un mensaje que se entienda.
            logger.error(f'[{store_code}] Carga de facturas del {day}: {e}', exc_info=True)
            if isinstance(e, CierreCajaException):
                message = e.message  # errores de Alegra (conexión, timeout, credenciales)
            else:
                message = 'No se pudieron guardar las facturas de ese día'
            return {'synced_days': synced, 'invoices': invoices, 'failed_day': day.isoformat(),
                    'error': message, 'stopped_by_time': False}
    return {'synced_days': synced, 'invoices': invoices, 'failed_day': None, 'error': None,
            'stopped_by_time': False}


def coverage_status(store_code: str, start: date, end: date) -> Dict[str, Any]:
    """
    Cuánto del rango está cargado y qué tan completos vienen los datos de
    Alegra (sirve para verificar que las facturas traen vendedora, cédula y
    descuento).
    """
    total_days = (end - start).days + 1 if end >= start else 0
    missing = missing_days(store_code, start, end) if total_days else []
    missing_items = missing_item_days(store_code, start, end) if total_days else []
    facts = InvoiceFact.query.filter(
        InvoiceFact.store_code == store_code, InvoiceFact.date >= start, InvoiceFact.date <= end)
    active = facts.filter(InvoiceFact.voided.is_(False))
    last_sync = InvoiceSyncDay.query.filter(InvoiceSyncDay.store_code == store_code)         .with_entities(func.max(InvoiceSyncDay.synced_at)).scalar()
    return {
        'start': start.isoformat(),
        'end': end.isoformat(),
        'total_days': total_days,
        'loaded_days': total_days - len(missing),
        'missing_days': len(missing),
        'next_missing_day': missing[-1].isoformat() if missing else None,  # se carga del más reciente al más antiguo
        'last_synced_at': last_sync.isoformat() + 'Z' if last_sync else None,
        'invoices': facts.count(),
        # Prendas (Estadísticas → Prendas): días que ya tienen sus prendas guardadas
        'items': {
            'loaded_days': total_days - len(missing_items),
            'missing_days': len(missing_items),
            # La carga va del más reciente al más antiguo
            'next_missing_day': missing_items[-1].isoformat() if missing_items else None,
        },
        'quality': {
            'active_invoices': active.count(),
            'voided_invoices': facts.filter(InvoiceFact.voided.is_(True)).count(),
            'with_seller': active.filter(InvoiceFact.seller_id.isnot(None)).count(),
            'with_identification': active.filter(InvoiceFact.client_identification.isnot(None)).count(),
            'with_discount': active.filter(InvoiceFact.discount > 0).count(),
            'total': int(active.with_entities(func.coalesce(func.sum(InvoiceFact.total), 0)).scalar() or 0),
            'discount': int(active.with_entities(func.coalesce(func.sum(InvoiceFact.discount), 0)).scalar() or 0),
        },
    }
