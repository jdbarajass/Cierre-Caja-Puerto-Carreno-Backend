"""
Solicitudes de ajuste de inventario (docs/PLAN_AJUSTES_INVENTARIO.md).

- find_item: busca una prenda por el código que escriben las vendedoras. En
  Alegra el código va al final del nombre de la variante
  ("CAMISETA NIÑA 39900 / 1054399004"); la referencia suele estar vacía.
- build_lines: arma los renglones de una solicitud con lo que dice Alegra.
- apply_request: la crea en Alegra (solo admin), una sola vez.
"""
import logging
import re
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

GIFT_CARD_KEYWORDS = ('TARJETA REGALO', 'BONO REGALO')
MAX_LINES = 60
MAX_QUANTITY = 999
MARK = '[KOAJ-AJ-{id}]'
STALE_AFTER = timedelta(minutes=5)
NO_ANSWER = 'Alegra no respondió: puede que el ajuste sí se haya creado. Al aceptar de nuevo se revisa primero.'


class RequestError(ValueError):
    """La solicitud no es válida o no se puede aplicar (mensaje para la pantalla)."""


# ─── Buscar la prenda por código ─────────────────────────────────────────────

def normalize_code(code) -> str:
    return re.sub(r'\s+', '', str(code or '')).strip()


def item_code(item: Dict[str, Any]) -> Optional[str]:
    """Código de la prenda: lo que va después del último " / " del nombre (o la referencia)."""
    name = item.get('name') or ''
    if ' / ' in name:
        tail = normalize_code(name.rsplit(' / ', 1)[1])
        if tail:
            return tail
    ref = item.get('reference')
    if isinstance(ref, dict):
        ref = ref.get('reference')
    return normalize_code(ref) or None


def _warehouse(item: Dict[str, Any]) -> Dict[str, Any]:
    inv = item.get('inventory') or {}
    warehouses = inv.get('warehouses') or []
    default = next((w for w in warehouses if w.get('isDefault')), None) or (warehouses[0] if warehouses else None)
    return default or {}


def item_summary(item: Dict[str, Any]) -> Dict[str, Any]:
    inv = item.get('inventory') or {}
    wh = _warehouse(item)
    qty = wh.get('availableQuantity', inv.get('availableQuantity'))
    price = None
    for p in item.get('price') or []:
        if isinstance(p, dict) and (p.get('main') or price is None):
            price = p.get('price')
    return {
        'item_id': str(item.get('id')), 'code': item_code(item), 'name': item.get('name') or '',
        'available': int(round(float(qty or 0))), 'unit_cost': float(inv.get('unitCost') or 0),
        'price': float(price or 0), 'warehouse_id': str(wh['id']) if wh.get('id') is not None else None,
        'inventoriable': bool(inv),
    }


def find_item(items: List[Dict[str, Any]], code) -> Dict[str, Any]:
    wanted = normalize_code(code)
    if not wanted or not wanted.isdigit():
        raise RequestError('Escribe el código de la prenda (solo números).')
    matches = [it for it in items if item_code(it) == wanted]
    if not matches:
        raise RequestError(f'No hay ninguna prenda activa con el código {wanted} en Alegra. Revisa el código.')
    if len(matches) > 1:
        raise RequestError(f'Hay {len(matches)} prendas con el código {wanted} en Alegra: avísale al administrador.')
    summary = item_summary(matches[0])
    if not summary['inventoriable']:
        raise RequestError(f'{summary["name"]} no lleva inventario en Alegra.')
    return summary


def is_gift_card(name: str) -> bool:
    upper = (name or '').upper()
    return any(k in upper for k in GIFT_CARD_KEYWORDS)


# ─── Armar la solicitud ──────────────────────────────────────────────────────

def _int(value, field: str, minimum: int = 0) -> int:
    try:
        number = int(str(value).strip())
    except (TypeError, ValueError):
        raise RequestError(f'{field}: escribe un número entero.')
    if number < minimum or number > MAX_QUANTITY:
        raise RequestError(f'{field}: debe estar entre {minimum} y {MAX_QUANTITY}.')
    return number


def build_lines(kind: str, data: Dict[str, Any], items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Renglones validados contra Alegra. El código, nombre y existencia se toman
    de Alegra (nunca de lo que mande la pantalla).
    - conteo: [{code, physical_qty}] -> sube o baja la diferencia con el sistema.
    - tarjeta_regalo: gift_card_code (entra 1) + [{code, quantity}] que salen.
    """
    lines: List[Dict[str, Any]] = []
    seen = set()

    def take(code, what):
        found = find_item(items, code)
        if found['item_id'] in seen:
            raise RequestError(f'El código {found["code"]} está repetido en la solicitud.')
        seen.add(found['item_id'])
        return found

    def line(found, type_, quantity, **extra):
        return {'code': found['code'], 'item_id': found['item_id'], 'name': found['name'], 'type': type_,
                'quantity': quantity, 'system_qty': found['available'], **extra}

    if kind == 'conteo':
        rows = data.get('lines') or []
        if not rows:
            raise RequestError('Agrega al menos una prenda.')
        if len(rows) > MAX_LINES:
            raise RequestError(f'Máximo {MAX_LINES} prendas por solicitud.')
        for row in rows:
            found = take(row.get('code'), 'prenda')
            physical = _int(row.get('physical_qty'), f'Físico de {found["code"]}')
            diff = physical - found['available']
            if diff == 0:
                raise RequestError(f'{found["code"]}: el físico ({physical}) es igual al sistema, no hay nada que ajustar.')
            lines.append(line(found, 'in' if diff > 0 else 'out', abs(diff), physical_qty=physical))
        return lines

    if kind == 'tarjeta_regalo':
        card = take(data.get('gift_card_code'), 'tarjeta')
        if not is_gift_card(card['name']):
            raise RequestError(f'El código {card["code"]} es {card["name"]}, no una tarjeta regalo.')
        lines.append(line(card, 'in', 1))
        rows = data.get('lines') or []
        if not rows:
            raise RequestError('Agrega la prenda que sale.')
        if len(rows) > MAX_LINES:
            raise RequestError(f'Máximo {MAX_LINES} prendas por solicitud.')
        for row in rows:
            found = take(row.get('code'), 'prenda')
            quantity = _int(row.get('quantity') or 1, f'Cantidad de {found["code"]}', minimum=1)
            if quantity > found['available']:
                raise RequestError(f'{found["code"]}: en Alegra hay {found["available"]} y salen {quantity}. '
                                   'Revisa el código o pide primero un conteo.')
            lines.append(line(found, 'out', quantity))
        return lines

    raise RequestError('Tipo de ajuste no válido.')


# ─── Aplicar en Alegra ───────────────────────────────────────────────────────

def observations(req) -> str:
    from app.models.inventory_request import KIND_LABELS
    text = f'{KIND_LABELS.get(req.kind, req.kind)} - pedido por {req.requested_by} desde la plataforma KOAJ'
    if req.kind == 'tarjeta_regalo' and req.excedente_valor:
        text += f'. Excedente ${req.excedente_valor:,.0f}'.replace(',', '.')
        if req.excedente_medio:
            text += f' ({req.excedente_medio})'
    if req.notes:
        text += f'. {req.notes}'
    return f'{text[:400]} {MARK.format(id=req.id)}'


def _find_existing(client, req) -> Optional[Dict[str, Any]]:
    mark = MARK.format(id=req.id)
    for adj in client.get_inventory_adjustments(req.request_date.isoformat()):
        if mark in (adj.get('observations') or ''):
            return adj
    return None


def build_payload(req, fresh: Dict[str, Dict[str, Any]]) -> Dict[str, Any]:
    """Payload de Alegra con existencia y costo del momento (`fresh`: item_id -> item_summary)."""
    warehouses = {fresh[l['item_id']]['warehouse_id'] for l in req.lines}
    if len(warehouses) != 1 or None in warehouses:
        raise RequestError('Las prendas no están en la misma bodega de Alegra: hazlo a mano en Alegra.')
    items = []
    for l in req.lines:
        f = fresh[l['item_id']]
        if l['type'] == 'out' and l['quantity'] > f['available']:
            raise RequestError(f'{l["code"]}: en Alegra hay {f["available"]} y el ajuste quita {l["quantity"]}; '
                               'quedaría en negativo. Pide que revisen o recházala.')
        cost = f['unit_cost'] or f['price']
        items.append({'id': l['item_id'], 'type': l['type'], 'quantity': int(l['quantity']), 'unitCost': round(cost, 2)})
    return {'date': req.request_date.isoformat(), 'observations': observations(req),
            'warehouse': {'id': warehouses.pop()}, 'items': items}


def warnings_for(req, fresh: Dict[str, Dict[str, Any]]) -> List[str]:
    """Avisos para el admin: la existencia cambió desde que la pidieron."""
    out = []
    for l in req.lines:
        f = fresh.get(l['item_id'])
        if f and f['available'] != l.get('system_qty'):
            out.append(f'{l["code"]}: cuando lo pidieron había {l.get("system_qty")} y ahora hay {f["available"]}.')
    return out


def fresh_items(client, req) -> Dict[str, Dict[str, Any]]:
    return {l['item_id']: item_summary(client.get_item(l['item_id'])) for l in req.lines}


def apply_request(client, req, user_id=None, check_existing=False) -> Dict[str, Any]:
    """
    Crea el ajuste en Alegra. Llamar con la solicitud YA marcada 'aplicando'
    (lo hace claim(), que dice si hay que buscar primero uno ya creado).
    Deja la solicitud en 'aplicada', 'pendiente' (Alegra la rechazó o no se
    puede: last_error) o 'revisar' (no se sabe si se creó).
    """
    from app.models.user import db
    from app.exceptions import AlegraConnectionError

    def finish(status, error=None, created=None):
        req.status = status
        req.last_error = error
        req.reviewed_by_user_id = user_id
        req.reviewed_at = datetime.utcnow()
        if created is not None:
            req.alegra_id = str(created.get('id')) if created.get('id') is not None else None
            req.alegra_number = str(created.get('fullNumeration') or created.get('number') or '') or None
        db.session.commit()

    try:
        existing = _find_existing(client, req) if check_existing else None
        if existing:
            finish('aplicada', created=existing)
            return req.to_dict()
        payload = build_payload(req, fresh_items(client, req))
    except RequestError as e:
        finish('revisar' if check_existing else 'pendiente', str(e))
        raise
    except Exception as e:
        # Si había que revisar si ya existía y no se pudo, sigue "por revisar"
        finish('revisar' if check_existing else 'pendiente', f'No se pudo leer Alegra: {getattr(e, "message", str(e))[:300]}')
        raise RequestError('No se pudo leer Alegra. Intenta de nuevo en un momento.') from e

    try:
        created = client.create_inventory_adjustment(payload)
    except AlegraConnectionError as e:
        details = (getattr(e, 'payload', None) or {}).get('details') or {}
        if details.get('status_code'):   # Alegra respondió que no: no se creó
            finish('pendiente', f'Alegra no aceptó el ajuste: {str(details.get("response"))[:300]}')
            raise RequestError('Alegra no aceptó el ajuste. Revisa el motivo en la solicitud.') from e
        finish('revisar', NO_ANSWER)
        raise RequestError('Alegra no respondió. Vuelve a tocar Aceptar: primero se revisa si ya quedó creado.') from e
    except Exception as e:
        finish('revisar', NO_ANSWER)
        raise RequestError('Alegra no respondió. Vuelve a tocar Aceptar: primero se revisa si ya quedó creado.') from e

    finish('aplicada', created=created)
    try:
        client.invalidate_items_cache()
    except Exception:
        pass
    logger.warning(f'[{req.store_code}] Ajuste de inventario {req.alegra_number} creado (solicitud {req.id})')
    return req.to_dict()


def is_stale(req, now: Optional[datetime] = None) -> bool:
    """'aplicando' hace rato: el proceso se cortó a mitad (ej. reinicio del servidor)."""
    now = now or datetime.utcnow()
    return req.status == 'aplicando' and (req.reviewed_at is None or now - req.reviewed_at > STALE_AFTER)


def claim(req, user_id=None) -> Optional[bool]:
    """
    Pasa la solicitud a 'aplicando' solo si sigue abierta (evita aplicarla dos
    veces a la vez). Devuelve None si no se pudo, o si hay que buscar primero
    en Alegra un ajuste ya creado (venía de 'revisar' o de un 'aplicando' viejo).
    """
    from app.models.inventory_request import InventoryRequest, OPEN_STATUSES
    from app.models.user import db
    now = datetime.utcnow()
    check_existing = req.status == 'revisar' or is_stale(req, now)
    allowed = list(OPEN_STATUSES) + (['aplicando'] if is_stale(req, now) else [])
    updated = (InventoryRequest.query
               .filter(InventoryRequest.id == req.id, InventoryRequest.store_code == req.store_code,
                       InventoryRequest.status.in_(allowed), InventoryRequest.status == req.status)
               .update({'status': 'aplicando', 'reviewed_at': now, 'reviewed_by_user_id': user_id},
                       synchronize_session=False))
    db.session.commit()
    if updated != 1:
        return None
    db.session.refresh(req)
    return check_existing
