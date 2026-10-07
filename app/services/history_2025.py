"""
Reconstrucción de 2025 tras la anulación masiva de facturas POS
(docs/PLAN_RECONSTRUCCION_2025.md).

- Clasifica las facturas anuladas de 2025 de la copia (InvoiceFact):
  * 'masiva'  = POS anulada en la anulación masiva de oct-2026 → fue una
    VENTA REAL (cuenta como venta y sus prendas volvieron al inventario).
  * 'real'    = anulación real que se queda así: electrónica anulada, o
    marcada a mano (VoidOverride).
  Las POS que se volvieron a facturar con las mismas prendas y el mismo
  total hasta 60 minutos después quedan como 'masiva' pero marcadas
  `possible_real` para que el usuario las revise: la prueba contra Alegra
  (oct-2025 antes de la anulación = $47.838.020 = vigentes + TODAS las POS
  anuladas de octubre) mostró que esa regla daba falsos positivos (dos
  clientas comprando lo mismo).
- Venta real de 2025 = vigentes + 'masiva'.
- Informe de inventario: por prenda, unidades que devolvió la anulación
  masiva y existencia antes de ella (= existencia de hoy − devueltas).
"""
import io
import logging
from collections import defaultdict
from datetime import date, datetime, timedelta
from typing import Any, Dict, List, Optional, Set

from sqlalchemy import func

from app.models.invoice_fact import InvoiceFact, InvoiceItemFact, InvoiceVoidItem, VoidOverride
from app.services.invoice_facts import missing_days

logger = logging.getLogger(__name__)

HISTORY_START = date(2025, 1, 1)
HISTORY_END = date(2025, 12, 31)
REPLACEMENT_WINDOW = timedelta(minutes=60)
BAG_KEYWORD = 'bolsa papel'


def _parse_dt(value: Optional[str]) -> Optional[datetime]:
    try:
        return datetime.strptime(value[:19], '%Y-%m-%d %H:%M:%S') if value else None
    except ValueError:
        return None


def coverage(store: str) -> Dict[str, Any]:
    missing = missing_days(store, HISTORY_START, HISTORY_END)
    total = (HISTORY_END - HISTORY_START).days + 1
    return {
        'start': HISTORY_START.isoformat(), 'end': HISTORY_END.isoformat(),
        'total_days': total, 'loaded_days': total - len(missing), 'missing_days': len(missing),
        'complete': not missing,
        'next_missing_day': missing[0].isoformat() if missing else None,
    }


def _signatures(store: str, start: date, end: date) -> Dict[str, tuple]:
    """Prendas (item, cantidad) de cada factura del rango, vigentes y anuladas."""
    lines = defaultdict(list)
    for model in (InvoiceItemFact, InvoiceVoidItem):
        for inv_id, item_id, qty in model.query.filter(
                model.store_code == store, model.date >= start, model.date <= end).with_entities(
                model.invoice_alegra_id, model.item_id, model.quantity):
            lines[inv_id].append((item_id or '', qty))
    return {k: tuple(sorted(v)) for k, v in lines.items()}


def classify(store: str, start: date = HISTORY_START, end: date = HISTORY_END) -> Dict[str, Any]:
    """Clasificación de cada factura anulada del rango (por defecto, 2025)."""
    facts = InvoiceFact.query.filter(
        InvoiceFact.store_code == store, InvoiceFact.date >= start, InvoiceFact.date <= end).all()
    overrides = {o.alegra_id: o for o in VoidOverride.for_store(store).all()}
    sigs = _signatures(store, start, end)
    by_day = defaultdict(list)
    for f in facts:
        by_day[f.date].append(f)

    rows = []
    for f in facts:
        if not f.voided:
            continue
        status, reason = 'masiva', 'POS anulada en la anulación masiva'
        possible_real = False
        if f.is_electronic:
            status, reason = 'real', 'Factura electrónica anulada'
        else:
            t = _parse_dt(f.issued_at)
            sig = sigs.get(f.alegra_id)
            if t and sig:
                for other in by_day[f.date]:
                    if other.alegra_id == f.alegra_id or other.total != f.total or sigs.get(other.alegra_id) != sig:
                        continue
                    ot = _parse_dt(other.issued_at)
                    if ot and t < ot <= t + REPLACEMENT_WINDOW:
                        minutes = int((ot - t).total_seconds() // 60)
                        possible_real = True
                        reason = (f'Hay otra factura con lo mismo {minutes} min después (factura {other.number}): '
                                  'puede ser otra clienta o una re-facturación')
                        break
        o = overrides.get(f.alegra_id)
        if o is not None:
            status = 'masiva' if o.counts_as_sale else 'real'
            reason = 'Marcada a mano' + (f': {o.note}' if o.note else '')
        rows.append({
            'alegra_id': f.alegra_id, 'number': f.number, 'date': f.date.isoformat(), 'issued_at': f.issued_at,
            'total': f.total, 'total_paid': f.total_paid, 'is_electronic': f.is_electronic,
            'seller_name': f.seller_name, 'status': status, 'reason': reason,
            'manual': o is not None, 'possible_real': possible_real and o is None,
        })
    return {'rows': rows}


def mass_voided_ids(store: str, start: date = HISTORY_START, end: date = HISTORY_END) -> Set[str]:
    return {r['alegra_id'] for r in classify(store, start, end)['rows'] if r['status'] == 'masiva'}


def summary(store: str) -> Dict[str, Any]:
    rows = classify(store)['rows']
    by_month = defaultdict(lambda: {'masiva_count': 0, 'masiva_total': 0, 'real_count': 0, 'real_total': 0})
    for r in rows:
        m = by_month[r['date'][:7]]
        m[f"{r['status']}_count"] += 1
        m[f"{r['status']}_total"] += r['total']
    active = InvoiceFact.query.filter(
        InvoiceFact.store_code == store, InvoiceFact.date >= HISTORY_START, InvoiceFact.date <= HISTORY_END,
        InvoiceFact.voided.is_(False))
    active_total = int(active.with_entities(func.coalesce(func.sum(InvoiceFact.total), 0)).scalar() or 0)
    masiva = [r for r in rows if r['status'] == 'masiva']
    real = [r for r in rows if r['status'] == 'real']
    return {
        'voided_count': len(rows),
        'masiva_count': len(masiva),
        'masiva_total': sum(r['total'] for r in masiva),
        'real_count': len(real),
        'real_total': sum(r['total'] for r in real),
        'active_count': active.count(),
        'active_total': active_total,
        'real_sales_total': active_total + sum(r['total'] for r in masiva),
        'by_month': [{'month': k, **v} for k, v in sorted(by_month.items())],
        'real_voids': sorted(real, key=lambda r: (r['date'], r['issued_at'] or '')),
        # Cuentan como venta, pero conviene revisarlas (ver classify)
        'review': sorted((r for r in masiva if r['possible_real']), key=lambda r: (r['date'], r['issued_at'] or '')),
    }


def real_sales_total(store: str, start: date, end: date) -> Optional[int]:
    """
    Venta real de un rango de 2025 desde la copia (vigentes + anulación
    masiva). None si el rango no está completo en la copia o no es de 2025.
    """
    if start < HISTORY_START or end > HISTORY_END or missing_days(store, start, end):
        return None
    facts = InvoiceFact.query.filter(
        InvoiceFact.store_code == store, InvoiceFact.date >= start, InvoiceFact.date <= end).all()
    mass = mass_voided_ids(store, start, end)
    return int(sum(f.total for f in facts if not f.voided or f.alegra_id in mass))


# ─────────────────────────────────────────────
#  Inventario
# ─────────────────────────────────────────────

def returned_units(store: str) -> Dict[str, Dict[str, Any]]:
    """Unidades por prenda que devolvió al inventario la anulación masiva."""
    mass = mass_voided_ids(store)
    out: Dict[str, Dict[str, Any]] = {}
    if not mass:
        return out
    for row in InvoiceVoidItem.query.filter(
            InvoiceVoidItem.store_code == store, InvoiceVoidItem.date >= HISTORY_START,
            InvoiceVoidItem.date <= HISTORY_END).all():
        if row.invoice_alegra_id not in mass:
            continue
        key = row.item_id or f'sin-id:{row.name}'
        r = out.setdefault(key, {'item_id': row.item_id, 'name': row.name, 'units': 0, 'invoices': set()})
        r['units'] += row.quantity
        r['invoices'].add(row.invoice_alegra_id)
    for r in out.values():
        r['invoices'] = len(r['invoices'])
    return out


def inventory_report(store: str, alegra_items: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Cruza las unidades devueltas con la existencia y el costo de hoy en
    Alegra (`alegra_items` = AlegraClient.get_active_items()).
    """
    current = {}
    for item in alegra_items:
        inv = item.get('inventory') or {}
        if not inv:
            continue
        current[str(item.get('id'))] = {
            'name': item.get('name') or '',
            'stock': float(inv.get('availableQuantity') or 0),
            'unit_cost': float(inv.get('unitCost') or 0),
            'reference': (item.get('reference') or {}).get('reference') if isinstance(item.get('reference'), dict) else item.get('reference'),
        }
    value_now = sum(c['stock'] * c['unit_cost'] for c in current.values())

    rows = []
    for key, r in returned_units(store).items():
        c = current.get(str(r['item_id'])) if r['item_id'] else None
        stock = c['stock'] if c else None
        cost = c['unit_cost'] if c else 0
        before = (stock - r['units']) if stock is not None else None
        flag = None
        if c is None:
            flag = 'No está activa en Alegra (o no maneja inventario)'
        elif before < 0:
            flag = 'Da negativo: la existencia de hoy es menor que lo devuelto; revisar en físico'
        units_to_remove = min(r['units'], stock) if stock is not None and stock > 0 else 0
        rows.append({
            'item_id': r['item_id'], 'name': c['name'] if c else r['name'], 'reference': c['reference'] if c else None,
            'units_returned': r['units'], 'invoices': r['invoices'],
            'stock_now': stock, 'stock_before': max(before, 0) if before is not None else None,
            'units_to_remove': units_to_remove,
            'unit_cost': cost, 'value_to_remove': units_to_remove * cost,
            'is_bag': BAG_KEYWORD in (r['name'] or '').lower(),
            'flag': flag,
        })
    rows.sort(key=lambda x: -x['value_to_remove'])
    value_to_remove = sum(r['value_to_remove'] for r in rows)
    return {
        'rows': rows,
        'items_count': len(rows),
        'units_returned': sum(r['units_returned'] for r in rows),
        'units_to_remove': sum(r['units_to_remove'] for r in rows),
        'value_now': value_now,
        'value_to_remove': value_to_remove,
        'value_before': value_now - value_to_remove,
        'flagged': sum(1 for r in rows if r['flag']),
    }


def inventory_excel(report: Dict[str, Any], store_name: str) -> bytes:
    """Excel del informe para revisarlo con el contador."""
    from openpyxl import Workbook
    from openpyxl.styles import Font, PatternFill, Alignment

    wb = Workbook()
    ws = wb.active
    ws.title = 'Ajuste propuesto'
    ws.append([f'{store_name} - Inventario antes de la anulación masiva de facturas POS 2025'])
    ws['A1'].font = Font(bold=True, size=13)
    ws.append([f'Generado: {datetime.now().strftime("%Y-%m-%d %H:%M")}. Existencia antes = existencia hoy en Alegra − unidades que devolvió la anulación masiva.'])
    ws.append(['Valor del inventario hoy (Alegra, a costo)', round(report['value_now'])])
    ws.append(['Valor a retirar (ajuste de salida)', round(report['value_to_remove'])])
    ws.append(['Valor del inventario antes de la anulación (estimado)', round(report['value_before'])])
    ws.append([])
    headers = ['ID Alegra', 'Referencia', 'Prenda', 'Unidades devueltas por la anulación', 'Facturas',
               'Existencia hoy en Alegra', 'Existencia antes de la anulación', 'Unidades a retirar (ajuste)',
               'Costo unitario', 'Valor a retirar', 'Revisar']
    ws.append(headers)
    header_row = ws.max_row
    for cell in ws[header_row]:
        cell.font = Font(bold=True, color='FFFFFF')
        cell.fill = PatternFill('solid', fgColor='1F2937')
        cell.alignment = Alignment(wrap_text=True, vertical='center')
    for r in report['rows']:
        ws.append([r['item_id'], r['reference'], r['name'], r['units_returned'], r['invoices'],
                   r['stock_now'], r['stock_before'], r['units_to_remove'], round(r['unit_cost']),
                   round(r['value_to_remove']), r['flag'] or ''])
    widths = [10, 16, 44, 16, 10, 14, 16, 16, 14, 16, 48]
    for i, w in enumerate(widths):
        ws.column_dimensions[chr(65 + i)].width = w
    ws.freeze_panes = ws.cell(row=header_row + 1, column=1)
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


# ─────────────────────────────────────────────
#  R3: ajuste de inventario en Alegra
# ─────────────────────────────────────────────

ADJUSTMENT_SETTING = 'history2025_inventory_adjustment'
ADJUSTMENT_CHUNK = 200            # prendas por ajuste (Alegra no documenta un máximo)
WAREHOUSE_ID = '1'                # bodega "Principal" (la de los ajustes de la tienda)
ADJUSTMENT_NOTE = ('Reverso de la anulación masiva de facturas POS 2025 (oct-2026): '
                   'esas ventas fueron reales y sus prendas volvieron al inventario. '
                   'Creado desde la plataforma KOAJ. Parte {part} de {parts}.')


class AdjustmentError(ValueError):
    """El ajuste no se puede crear (ya existe, faltan datos, cambió el cálculo...)."""


def _setting(store: str):
    from app.models.app_setting import AppSetting
    from app.stores import store_setting_key
    return AppSetting.query.get(store_setting_key(ADJUSTMENT_SETTING, store))


def adjustment_state(store: str) -> Optional[Dict[str, Any]]:
    import json
    row = _setting(store)
    return json.loads(row.value) if row and row.value else None


def _save_state(store: str, state: Dict[str, Any]) -> None:
    import json
    from app.models.app_setting import AppSetting
    from app.models.user import db
    from app.stores import store_setting_key
    row = _setting(store)
    if row is None:
        row = AppSetting(key=store_setting_key(ADJUSTMENT_SETTING, store))
        db.session.add(row)
    row.value = json.dumps(state, ensure_ascii=False)
    row.updated_at = datetime.utcnow()
    db.session.commit()


def adjustment_items(report: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Renglones del ajuste de salida (formato de Alegra) a partir del informe."""
    return [{'id': str(r['item_id']), 'type': 'out', 'quantity': int(r['units_to_remove']),
             'unitCost': round(float(r['unit_cost'] or 0), 2), 'name': r['name']}
            for r in report['rows'] if r['item_id'] and r['units_to_remove'] > 0]


def create_adjustment(client, store: str, report: Optional[Dict[str, Any]], today: date,
                      expected_units: Optional[int] = None, user_id=None) -> Dict[str, Any]:
    """
    Crea en Alegra el ajuste de salida, por partes de ADJUSTMENT_CHUNK prendas.
    - Primera vez: exige 2025 completo y que las unidades a retirar coincidan
      con las que el usuario aprobó (expected_units); guarda el plan completo.
    - Si una parte falla, se guarda lo hecho y otra llamada sigue con las
      partes que faltan usando el MISMO plan (no se recalcula: las partes ya
      creadas cambiaron la existencia en Alegra).
    - Si ya se completó, no se vuelve a crear.
    """
    state = adjustment_state(store)
    if state and state.get('completed'):
        raise AdjustmentError('El ajuste ya se creó en Alegra; no se puede volver a crear desde aquí.')

    if not state:
        if not coverage(store)['complete']:
            raise AdjustmentError('Primero hay que traer todo 2025: el ajuste solo se crea con el año completo.')
        items = adjustment_items(report)
        if not items:
            raise AdjustmentError('No hay unidades para retirar.')
        units = sum(i['quantity'] for i in items)
        if expected_units is None or int(expected_units) != units:
            raise AdjustmentError(
                f'El cálculo cambió desde que lo revisaste ({units} unidades ahora). Vuelve a calcular y revisa antes de crear el ajuste.')
        chunks = [items[i:i + ADJUSTMENT_CHUNK] for i in range(0, len(items), ADJUSTMENT_CHUNK)]
        state = {
            'started_at': datetime.utcnow().isoformat() + 'Z', 'date': today.isoformat(), 'user_id': user_id,
            'units': units, 'value': round(sum(i['quantity'] * i['unitCost'] for i in items)),
            'items_count': len(items), 'chunks': chunks, 'done': [], 'errors': [], 'completed': False,
        }
        _save_state(store, state)

    parts = len(state['chunks'])
    done_parts = {d['part'] for d in state['done']}
    for index, chunk in enumerate(state['chunks'], start=1):
        if index in done_parts:
            continue
        payload = {
            'date': state['date'],
            'observations': ADJUSTMENT_NOTE.format(part=index, parts=parts),
            'warehouse': {'id': WAREHOUSE_ID},
            'items': [{k: v for k, v in i.items() if k != 'name'} for i in chunk],
        }
        try:
            created = client.create_inventory_adjustment(payload)
        except Exception as e:
            state['errors'].append({'part': index, 'at': datetime.utcnow().isoformat() + 'Z',
                                    'error': getattr(e, 'message', str(e))[:500]})
            _save_state(store, state)
            raise AdjustmentError(
                f'Alegra no aceptó la parte {index} de {parts}. Lo ya creado quedó guardado; '
                f'vuelve a tocar el botón para seguir con lo que falta.') from e
        state['done'].append({
            'part': index, 'alegra_id': str(created.get('id')),
            'number': created.get('fullNumeration') or created.get('number'),
            'items': len(chunk), 'units': sum(i['quantity'] for i in chunk),
        })
        _save_state(store, state)

    state['completed'] = True
    state['completed_at'] = datetime.utcnow().isoformat() + 'Z'
    _save_state(store, state)
    return public_state(state)


def public_state(state: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    """Estado del ajuste sin la lista completa de prendas (para la pantalla)."""
    if not state:
        return None
    return {k: v for k, v in state.items() if k != 'chunks'} | {'parts': len(state.get('chunks') or [])}


# ─────────────────────────────────────────────
#  R4 (resto): que las demás estadísticas cuenten la venta real de 2025
# ─────────────────────────────────────────────

def _overlap_2025(start: date, end: date):
    s, e = max(start, HISTORY_START), min(end, HISTORY_END)
    return (s, e) if s <= e else None


def mass_ids_for_range(store: str, start: date, end: date) -> Set[str]:
    """Facturas de la anulación masiva dentro del rango (vacío si no toca 2025)."""
    overlap = _overlap_2025(start, end)
    return mass_voided_ids(store, *overlap) if overlap else set()


def sale_condition(store: str, start: date, end: date):
    """
    Condición SQL de "factura que cuenta como venta" para InvoiceFact: no
    anulada, o de la anulación masiva de 2025. En 2026 es igual a voided=False.
    """
    from sqlalchemy import or_
    mass = mass_ids_for_range(store, start, end)
    if not mass:
        return InvoiceFact.voided.is_(False)
    return or_(InvoiceFact.voided.is_(False), InvoiceFact.alegra_id.in_(mass))


def mass_voided_item_rows(store: str, start: date, end: date) -> List[Dict[str, Any]]:
    """
    Prendas de las facturas de la anulación masiva del rango, con el mismo
    formato que las filas de InvoiceItemFact que usa Prendas (vendedora tomada
    de la factura).
    """
    mass = mass_ids_for_range(store, start, end)
    if not mass:
        return []
    sellers = {f.alegra_id: (f.seller_id, f.seller_name) for f in InvoiceFact.query.filter(
        InvoiceFact.store_code == store, InvoiceFact.alegra_id.in_(mass))}
    rows = []
    for v in InvoiceVoidItem.query.filter(
            InvoiceVoidItem.store_code == store, InvoiceVoidItem.date >= start, InvoiceVoidItem.date <= end,
            InvoiceVoidItem.invoice_alegra_id.in_(mass)):
        seller_id, seller_name = sellers.get(v.invoice_alegra_id, (None, None))
        rows.append({'invoice_alegra_id': v.invoice_alegra_id, 'seller_id': seller_id, 'seller_name': seller_name,
                     'item_id': v.item_id, 'name': v.name, 'quantity': v.quantity, 'total': v.total})
    return rows


def mass_voided_client_rows(store: str, start: date, end: date) -> List[Dict[str, Any]]:
    """
    Compras por cliente de la anulación masiva del rango, con el formato del
    reporte sales-by-client de Alegra (idLocal, clientName, identification,
    totalDocuments, subtotal, discount, total), para sumarlas a la historia
    de clientes (nuevos/recurrentes, inactivas).
    """
    mass = mass_ids_for_range(store, start, end)
    if not mass:
        return []
    out: Dict[str, Dict[str, Any]] = {}
    for f in InvoiceFact.query.filter(InvoiceFact.store_code == store, InvoiceFact.alegra_id.in_(mass)):
        if not f.client_id:
            continue
        r = out.setdefault(f.client_id, {'idLocal': f.client_id, 'clientName': f.client_name,
                                         'identification': f.client_identification,
                                         'totalDocuments': 0, 'subtotal': 0, 'discount': 0, 'total': 0})
        r['totalDocuments'] += 1
        r['subtotal'] += f.subtotal or 0
        r['discount'] += f.discount or 0
        r['total'] += f.total or 0
    return list(out.values())


def merge_client_rows(rows: List[Dict[str, Any]], extra: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Suma `extra` (mismo formato que sales-by-client) a las filas de Alegra por idLocal."""
    if not extra:
        return rows
    merged = {str(r.get('idLocal') or ''): dict(r) for r in rows}
    for e in extra:
        key = str(e['idLocal'])
        if key in merged:
            m = merged[key]
            for k in ('totalDocuments', 'subtotal', 'discount', 'total'):
                m[k] = float(m.get(k) or 0) + e[k]
        else:
            merged[key] = dict(e)
    return list(merged.values())


_INVOICE_METHOD = {'CASH': 'cash', 'DEBIT_CARD': 'debit-card', 'CREDIT_CARD': 'credit-card',
                   'DEBIT_TRANSFER': 'transfer', 'TRANSFER': 'transfer'}


def revive_mass_voided(invoices: List[Dict[str, Any]], store: str) -> List[Dict[str, Any]]:
    """
    En listas de facturas que vienen de Alegra (Totales, Documentos, Analytics,
    Productos, Comparativo): las de la anulación masiva de 2025 vuelven a
    contar como venta (status 'closed', marcadas `mass_voided`). Como sus
    recibos se anularon, se les pone un pago con el medio de la factura para
    que también cuenten por medio de pago. Las de 2026 no se tocan.
    """
    from app.utils.formatters import is_invoice_void
    candidates = [i for i in invoices if str(i.get('date') or '')[:4] == '2025' and is_invoice_void(i)]
    if not candidates:
        return invoices
    dates = sorted(str(i['date'])[:10] for i in candidates)
    mass = mass_ids_for_range(store, date.fromisoformat(dates[0]), date.fromisoformat(dates[-1]))
    return revive_with_ids(invoices, mass)


def revive_with_ids(invoices: List[Dict[str, Any]], mass: Set[str]) -> List[Dict[str, Any]]:
    """
    Lo mismo que revive_mass_voided con los ids ya calculados (sin base de
    datos: sirve dentro de hilos, ej. el comparativo de tiendas).
    """
    if not mass:
        return invoices
    out = []
    for inv in invoices:
        if str(inv.get('id')) in mass:
            inv = dict(inv)
            for k in ('voided_at', 'cancelled_at', 'deleted_at', 'voided_by'):
                inv.pop(k, None)
            inv['status'] = 'closed'
            inv['mass_voided'] = True
            total = inv.get('total') or 0
            inv['totalPaid'] = total
            for k in ('observations', 'anotation', 'notes'):
                if any(w in str(inv.get(k) or '').lower() for w in ('anul', 'void', 'cancel', 'revers')):
                    inv.pop(k, None)
            pays = [dict(p, status='open') for p in (inv.get('payments') or []) if p.get('amount')]
            if not pays:
                method = _INVOICE_METHOD.get(str(inv.get('paymentMethod') or '').upper(), 'cash')
                pays = [{'amount': total, 'paymentMethod': method, 'status': 'open'}]
            inv['payments'] = pays
        out.append(inv)
    return out


def revive_for_current_store(invoices: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """revive_mass_voided para la tienda del request; si algo falla, deja la lista igual."""
    try:
        from app.stores import get_current_store
        return revive_mass_voided(invoices, get_current_store())
    except Exception as e:
        logger.warning(f'Anulación masiva 2025 (revivir facturas): {e}')
        return invoices
