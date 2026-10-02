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
"""
import logging
import time
from datetime import date, datetime, timedelta
from typing import Any, Dict, Iterable, List, Optional

from sqlalchemy import func

from app.models.invoice_fact import InvoiceFact, InvoiceSyncDay
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


def sync_day(alegra_client, store_code: str, day: date) -> int:
    """Reemplaza las facturas guardadas de `day` por las que tiene Alegra. Devuelve cuántas."""
    invoices = alegra_client.get_invoices_by_date(day.isoformat())  # si falla, no se toca nada
    facts = [invoice_to_fact(i) for i in invoices if i.get('id') is not None]

    try:
        base = InvoiceFact.query.filter(InvoiceFact.store_code == store_code)
        base.filter(InvoiceFact.date == day).delete(synchronize_session=False)
        # Una factura a la que le cambiaron la fecha en Alegra estaría guardada
        # en otro día: se quita para no chocar con la unicidad (tienda, alegra_id).
        ids = [f['alegra_id'] for f in facts]
        if ids:
            base.filter(InvoiceFact.alegra_id.in_(ids)).delete(synchronize_session=False)
        db.session.add_all(InvoiceFact(store_code=store_code, date=day, **f) for f in facts)

        sync_row = InvoiceSyncDay.query.filter_by(store_code=store_code, date=day).first()
        if sync_row is None:
            sync_row = InvoiceSyncDay(store_code=store_code, date=day)
            db.session.add(sync_row)
        sync_row.invoice_count = len(facts)
        sync_row.synced_at = datetime.utcnow()
        db.session.commit()
    except Exception:
        db.session.rollback()
        raise
    return len(facts)


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
            logger.error(f'[{store_code}] Carga de facturas del {day}: {e}', exc_info=True)
            return {'synced_days': synced, 'invoices': invoices, 'failed_day': day.isoformat(),
                    'error': getattr(e, 'message', None) or str(e) or e.__class__.__name__,
                    'stopped_by_time': False}
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
        'next_missing_day': missing[0].isoformat() if missing else None,
        'last_synced_at': last_sync.isoformat() + 'Z' if last_sync else None,
        'invoices': facts.count(),
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
