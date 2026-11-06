"""
Recordatorios del administrador (ventana emergente al entrar a la
plataforma). Pedido del usuario (2026-10-08): que la plataforma le avise lo
que tiene que hacer y en qué fecha, con los pasos y a dónde ir.

Cada recordatorio se calcula solo según la fecha y el estado real de la
plataforma, por tienda:
- freeze-AAAA: del 1-dic al 30-jun siguiente, mientras la copia de facturas
  no esté congelada hasta el 31-dic de ese año (docs/PLAN_BLINDAJE_COPIA.md).
- month-close-AAAA-MM: del 1 al 10 de cada mes, si el mes anterior no se ha
  cerrado en Cuentas → Mes (desde octubre de 2026).
- backup-AAAA-MM: del 1 al 10 de cada mes, bajar el respaldo de facturas
  en Excel (se marca a mano "Ya lo hice").
- loans-AAAA-MM: desde el 25 (día de aviso de cada préstamo) hasta que se
  registre la cuota del mes (Radiografía Fase 0c).
- fixed-AAAA-MM: desde 2 días antes de fin de mes, gastos fijos sin registrar.
- inventory-requests: hay solicitudes de ajuste de inventario por aceptar
  (docs/PLAN_AJUSTES_INVENTARIO.md); se quita sola al no quedar ninguna.

"Recordarme después" lo pospone N días; "Ya lo hice" / "No aplica" lo quita
para ese periodo. Se guarda en app_settings (por tienda).
"""
import json
from datetime import date, datetime, timedelta
from typing import Any, Dict, List, Optional

SETTING = 'reminders_state'
FIRST_MONTH_CLOSE = date(2026, 10, 1)   # primer mes completo de Cuentas → Mes
MONTHS_ES = ['enero', 'febrero', 'marzo', 'abril', 'mayo', 'junio', 'julio',
             'agosto', 'septiembre', 'octubre', 'noviembre', 'diciembre']


def _row(store: str):
    from app.models.app_setting import AppSetting
    from app.stores import store_setting_key
    return AppSetting.query.get(store_setting_key(SETTING, store))


def _state(store: str) -> Dict[str, Any]:
    row = _row(store)
    return json.loads(row.value) if row and row.value else {}


def _save(store: str, state: Dict[str, Any]) -> None:
    from app.models.app_setting import AppSetting
    from app.models.user import db
    from app.stores import store_setting_key
    row = _row(store)
    if row is None:
        row = AppSetting(key=store_setting_key(SETTING, store))
        db.session.add(row)
    row.value = json.dumps(state, ensure_ascii=False)
    row.updated_at = datetime.utcnow()
    db.session.commit()


# ─── Qué hay que recordar hoy ────────────────────────────────────────────────

def _freeze(store: str, today: date) -> Optional[Dict[str, Any]]:
    from app.services.facts_freeze import frozen_until
    if today.month == 12:
        year = today.year
    elif today.month <= 6:
        year = today.year - 1
    else:
        return None
    if year < 2026:
        return None
    until = frozen_until(store)
    if until is not None and until >= date(year, 12, 31):
        return None
    december = today.month == 12
    steps = [
        'Pregúntale al contador qué día van a anular las facturas de este año en Alegra (la anulación masiva).',
        f'Unos días ANTES de esa anulación entra a Estadísticas → Respaldo de facturas.',
        f'En "Hasta el día" pon 31/12/{year} (si la anulación es antes de que acabe el año, pon el día de ayer y después extiéndelo).',
        'Toca "Repasar todo hasta esa fecha" y espera a que diga que no falta ningún día (deja la página abierta).',
        'Escribe CONGELAR y toca "Congelar".',
    ]
    if december:
        steps.insert(2, f'El 31 de diciembre solo se puede congelar desde el 1 de enero de {year + 1}: si te alcanza el tiempo, hazlo los primeros días de enero.')
    return {
        'key': f'freeze-{year}',
        'kind': 'freeze',
        'priority': 1,
        'title': f'Proteger las ventas de {year} antes de la anulación masiva',
        'body': (f'Si este año se van a anular en Alegra de forma masiva las facturas de {year} (como pasó con 2025), '
                 'congela antes la copia de la plataforma. Así las estadísticas, metas y cuentas siguen mostrando las ventas reales.'),
        'steps': steps,
        'path': '/estadisticas-estandar/respaldo-facturas',
        'action_label': 'Ir a Respaldo de facturas',
        'done_label': f'No habrá anulación de {year} / ya lo hice',
    }


def _month_close(store: str, today: date) -> Optional[Dict[str, Any]]:
    from app.models.month_sheet import MonthClose
    if today.day > 10:
        return None
    prev = (today.replace(day=1) - timedelta(days=1)).replace(day=1)
    if prev < FIRST_MONTH_CLOSE:
        return None
    period = prev.strftime('%Y-%m')
    if MonthClose.for_store(store).filter_by(period=period).first() is not None:
        return None
    label = f'{MONTHS_ES[prev.month - 1]} {prev.year}'
    return {
        'key': f'month-close-{period}',
        'kind': 'month_close',
        'priority': 2,
        'title': f'Cerrar el mes de {label}',
        'body': f'Revisa que las cuentas de {label} cuadren con el banco y guarda la foto del mes.',
        'steps': [
            f'Entra a Gestión → Cuentas → Mes y elige {label}.',
            'Toca "Registrar en Gastos" en el cuadro de comisiones (datáfono y Addi).',
            'Revisa en Gastos que ningún gasto fijo quede "Vencido".',
            'En cada cuenta escribe el "Saldo real" del banco o de la caja y toca Guardar.',
            'Toca "Cerrar el mes".',
        ],
        'path': '/cuentas?tab=mes',
        'action_label': 'Ir a Cuentas → Mes',
        'done_label': None,   # se quita solo al cerrar el mes
    }


def _backup(store: str, today: date) -> Optional[Dict[str, Any]]:
    if today.day > 10 or today < date(2026, 11, 1):
        return None
    period = today.strftime('%Y-%m')
    year = today.year if today.month > 1 else today.year - 1
    return {
        'key': f'backup-{period}',
        'kind': 'backup',
        'priority': 3,
        'title': 'Descargar el respaldo de facturas',
        'body': 'Una copia de las facturas guardadas, fuera de la plataforma, por si acaso.',
        'steps': [
            'Entra a Estadísticas → Respaldo de facturas.',
            f'Elige el año {year} y toca "Descargar respaldo en Excel".',
            'Guarda el archivo en tu OneDrive (por ejemplo, en una carpeta "Respaldos KOAJ").',
        ],
        'path': '/estadisticas-estandar/respaldo-facturas',
        'action_label': 'Ir a Respaldo de facturas',
        'done_label': 'Ya lo descargué',
    }


def _inventory_requests(store: str, today: date) -> Optional[Dict[str, Any]]:
    """Solicitudes de ajuste de inventario esperando al admin (docs/PLAN_AJUSTES_INVENTARIO.md)."""
    from app.models.inventory_request import InventoryRequest, OPEN_STATUSES
    q = InventoryRequest.for_store(store).filter(InventoryRequest.status.in_(OPEN_STATUSES))
    count = q.count()
    if not count:
        return None
    # La llave cambia con cada solicitud nueva: "Recordarme después" no esconde las que lleguen luego
    latest = q.order_by(InventoryRequest.id.desc()).first().id
    plural = count != 1
    return {
        'key': f'inventory-requests-{latest}',
        'kind': 'inventory_requests',
        'priority': 0,
        'title': f'{count} ajuste{"s" if plural else ""} de inventario por aceptar',
        'body': 'Las vendedoras pidieron ajustes de inventario. No se aplican en Alegra hasta que los aceptes.',
        'steps': [
            'Entra a Inventario → Ajustes de inventario.',
            'Revisa cada solicitud (prenda, cantidades y lo que dice Alegra hoy).',
            'Toca "Aceptar" (o "Aceptar todas"), o "Rechazar" con el motivo.',
        ],
        'path': '/ajustes-inventario',
        'action_label': 'Ir a Ajustes de inventario',
        'done_label': None,   # se quita solo cuando no queda ninguna pendiente
    }


def _fmt_cop(v: float) -> str:
    return '$ ' + f'{round(v):,}'.replace(',', '.')


def _loan_installments(store: str, today: date) -> Optional[Dict[str, Any]]:
    """Cuotas de los préstamos (Radiografía Fase 0c): desde el día de aviso
    (25) hasta que se registre un pago del mes. Pedido del usuario 2026-11-06."""
    from app.services.loans import groups
    pending = []
    for g in groups(store, today):
        for l in g['loans']:
            if l['pending_this_month'] and today.day >= l['due_day']:
                pending.append(f"{g['group_name']} · {l['name']}"
                               + (f" (cuota {_fmt_cop(l['installment'])})" if l['installment'] else ''))
    if not pending:
        return None
    period = today.strftime('%Y-%m')
    return {
        'key': f'loans-{period}',
        'kind': 'loans',
        'priority': 1,
        'title': 'Pagar las cuotas de los préstamos',
        'body': 'Este mes falta registrar: ' + '; '.join(pending) + '.',
        'steps': [
            'Entra a Gestión → Cuentas → Resumen y abre la tarjeta del préstamo.',
            'Toca "Registrar pago", elige el préstamo, el valor y de dónde salió la plata.',
            'Si la cuota se descontó del mismo préstamo, elige "Descontada del préstamo".',
        ],
        'path': '/cuentas',
        'action_label': 'Ir a Cuentas → Resumen',
        'done_label': None,   # se quita solo al registrar el pago
    }


def _fixed_expenses(store: str, today: date) -> Optional[Dict[str, Any]]:
    """Gastos fijos sin pagar: desde 2 días antes de fin de mes (30 → 28,
    31 → 29, febrero de 28 → 26) hasta que se registren. Las cuotas de crédito
    van en su propio aviso (_loan_installments)."""
    import calendar
    from app.models.expense import Expense, FixedExpense
    last = calendar.monthrange(today.year, today.month)[1]
    if today.day < last - 2:
        return None
    period = today.strftime('%Y-%m')
    paid = {e.fixed_expense_id for e in Expense.for_store(store).filter(
        Expense.period == period, Expense.fixed_expense_id.isnot(None)).all()}
    missing = [f for f in FixedExpense.for_store(store).filter_by(active=True).order_by(
        FixedExpense.due_day.asc(), FixedExpense.id.asc()).all()
        if f.id not in paid and f.category != 'cuota_credito']
    if not missing:
        return None
    return {
        'key': f'fixed-{period}',
        'kind': 'fixed_expenses',
        'priority': 1,
        'title': f'{len(missing)} gasto{"s" if len(missing) != 1 else ""} fijo{"s" if len(missing) != 1 else ""} sin registrar este mes',
        'body': 'Falta: ' + ', '.join(f'{f.name} ({_fmt_cop(f.amount)})' for f in missing) + '.',
        'steps': [
            'Entra a Gestión → Cuentas → Gastos.',
            'En "Gastos fijos del mes" toca "Registrar pago" en cada uno y revisa el valor y de dónde salió.',
            'Solo se descuenta lo que registres: este aviso no resta nada solo.',
        ],
        'path': '/cuentas?tab=gastos',
        'action_label': 'Ir a Cuentas → Gastos',
        'done_label': None,
    }


BUILDERS = (_inventory_requests, _loan_installments, _fixed_expenses, _freeze, _month_close, _backup)


def active(store: str, today: date) -> List[Dict[str, Any]]:
    state = _state(store)
    out = []
    for build in BUILDERS:
        r = build(store, today)
        if r is None:
            continue
        s = state.get(r['key']) or {}
        if s.get('done'):
            continue
        if s.get('snooze_until') and date.fromisoformat(s['snooze_until']) > today:
            continue
        out.append(r)
    return sorted(out, key=lambda r: r['priority'])


def snooze(store: str, key: str, days: int, today: date) -> None:
    state = _state(store)
    state[key] = {**(state.get(key) or {}), 'snooze_until': (today + timedelta(days=days)).isoformat()}
    _save(store, state)


def mark_done(store: str, key: str, user_id: Optional[int]) -> None:
    state = _state(store)
    state[key] = {'done': datetime.utcnow().isoformat() + 'Z', 'user_id': user_id}
    _save(store, state)
