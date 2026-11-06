"""
Radiografía financiera de los locales: reglas y fórmulas en UN SOLO LUGAR
(Fase 0 de docs/PLAN_RADIOGRAFIA.md).

Todo lo que diga "utilidad", "punto de equilibrio" o "costo estimado" en la
plataforma sale de aquí. Si una regla cambia, cambia aquí y se mueven juntos
Cuentas → Año, el comparativo de tiendas, la regla 70/30 y la Radiografía.

Reglas del usuario (2026-11-06):
- Solo 2026; sin costos reales en Alegra (su costo = precio de venta). El costo
  se ESTIMA con el margen KOAJ (finance_settings.margin_pct, 35 % para todo).
- Solo se resta lo que se registró a mano (gastos, cuotas, pagos). Nada
  pendiente o estimado se descuenta solo: lo pendiente va como aviso.
- La cuota de un crédito NO baja la utilidad neta (es devolver un préstamo),
  pero sí se resta en "lo que quedó" (ganancia real) y en "cuánto se puede
  retirar", en su propia línea. Cuando se conozca la tasa (Fase 0c), la parte
  de interés pasa a gasto financiero.
- "Otro" es gasto operativo. Préstamos (a empleadas o a la otra tienda),
  inversiones y retiros de socios no son gasto. Los excedentes del cierre no
  son venta.
- División por cero → None (la pantalla muestra "—").
"""
import calendar
from datetime import date
from typing import Dict, Optional, Tuple

# ─────────────────────────────────────────────
#  Clasificación de cada salida (§4 del plan)
# ─────────────────────────────────────────────

COSTO_MERCANCIA = 'costo_mercancia'   # resta utilidad (dentro del costo de lo vendido)
OPERATIVO = 'operativo'               # resta utilidad
FINANCIERO = 'financiero'             # resta utilidad
CUOTA_CREDITO = 'cuota_credito'       # no resta utilidad; sí resta lo que quedó
INVERSION = 'inversion'               # no resta utilidad
PRESTAMO = 'prestamo'                 # no resta utilidad (empleadas u otra tienda)
RETIRO_SOCIO = 'retiro_socio'         # no resta utilidad (reparto de la ganancia)

CLASS_BY_CATEGORY: Dict[str, str] = {
    'flete': COSTO_MERCANCIA,
    'operativo': OPERATIVO,
    'sueldo': OPERATIVO,
    'otro': OPERATIVO,
    'financiero': FINANCIERO,
    'cuota_credito': CUOTA_CREDITO,
    'inversion': INVERSION,
    'prestamo_empleada': PRESTAMO,
    'prestamo_tienda': PRESTAMO,
    'retiro_socio': RETIRO_SOCIO,
}

# Clases que restan utilidad
UTILITY_CLASSES = (COSTO_MERCANCIA, OPERATIVO, FINANCIERO)


def expense_class(category: Optional[str]) -> str:
    """Clase de una salida. Una categoría desconocida cuenta como gasto
    operativo: es mejor que reste a que se esconda."""
    return CLASS_BY_CATEGORY.get(category or '', OPERATIVO)


def categories_of(*classes: str) -> Tuple[str, ...]:
    return tuple(c for c, k in CLASS_BY_CATEGORY.items() if k in classes)


# Lo que Cuentas → Año y el comparativo llaman "gastos operativos": todo lo
# que resta utilidad (operativo, sueldo, otro, flete y financiero). Las cuotas
# de crédito van en su propia línea (DEBT_CATEGORIES).
EXPENSE_CATEGORIES = categories_of(*UTILITY_CLASSES)
DEBT_CATEGORIES = categories_of(CUOTA_CREDITO)


# ─────────────────────────────────────────────
#  Fórmulas (§5 del plan)
# ─────────────────────────────────────────────

def ratio(numerator: Optional[float], denominator: Optional[float]) -> Optional[float]:
    """numerador ÷ denominador; None si falta un dato o el denominador es 0."""
    if numerator is None or not denominator:
        return None
    return numerator / denominator


def pct_change(current: Optional[float], previous: Optional[float]) -> Optional[float]:
    """Variación (actual − anterior) ÷ anterior. None si no hay con qué comparar
    (un mes sin datos no se compara)."""
    if current is None or previous is None or previous == 0:
        return None
    return (current - previous) / abs(previous)


def estimated_cost(list_price_sold: float, margin_pct: float) -> float:
    """Costo estimado = precio de lista vendido × (1 − margen KOAJ). ESTIMADO."""
    return list_price_sold * (1 - margin_pct / 100)


def utility_lines(*, ventas: float, precio_lista: float, margin_pct: float, fletes: float,
                  operativos: float, financieros: float, comisiones: float,
                  cuotas: float, recompras: float) -> Dict[str, Optional[float]]:
    """Estado de resultados de un mes (todo en COP).

    operativos  = operativo + sueldo + otro
    financieros = financiero + 4x1000 (sin comisiones: van aparte)
    comisiones  = datáfono/Addi (registradas o calculadas, nunca las dos)
    """
    costo = estimated_cost(precio_lista, margin_pct)
    costo_vendido = costo + fletes
    bruta = ventas - costo_vendido
    operacional = bruta - operativos
    gastos_fin = financieros + comisiones
    neta = operacional - gastos_fin
    contribucion = ventas - costo - fletes - comisiones
    return {
        'ventas': ventas,
        'precio_lista': precio_lista,
        'descuentos': precio_lista - ventas,
        'costo_estimado': costo,
        'fletes': fletes,
        'costo_vendido': costo_vendido,
        'utilidad_bruta': bruta,
        'margen_bruto_pct': ratio(bruta, ventas),
        'gastos_operativos': operativos,
        'utilidad_operacional': operacional,
        'gastos_financieros': gastos_fin,
        'utilidad_neta': neta,
        'margen_neto_pct': ratio(neta, ventas),
        'margen_contribucion_pct': ratio(contribucion, ventas),
        'cuotas': cuotas,
        # Como el Excel / Cuentas → Año: ventas − recompras − todo lo que resta
        # utilidad − cuotas (no usa el costo estimado).
        'lo_que_quedo': ventas - recompras - fletes - operativos - gastos_fin - cuotas,
    }


def break_even(fixed_costs: float, contribution_pct: Optional[float]) -> Optional[float]:
    """Punto de equilibrio = gastos fijos ÷ margen de contribución %.
    None si el margen es 0, negativo o no se conoce."""
    if contribution_pct is None or contribution_pct <= 0:
        return None
    return fixed_costs / contribution_pct


def sales_for_target(fixed_costs: float, target: float, contribution_pct: Optional[float]) -> Optional[float]:
    """Ventas para sacar X = (gastos fijos + X) ÷ margen de contribución %."""
    return break_even(fixed_costs + target, contribution_pct)


# ─────────────────────────────────────────────
#  Periodos (hora de Colombia: `today` viene de get_colombia_now().date())
# ─────────────────────────────────────────────

def month_bounds(year: int, month: int) -> Tuple[date, date]:
    return date(year, month, 1), date(year, month, calendar.monthrange(year, month)[1])


def days_in_month(year: int, month: int) -> int:
    return calendar.monthrange(year, month)[1]


def previous_month(year: int, month: int) -> Tuple[int, int]:
    return (year - 1, 12) if month == 1 else (year, month - 1)


def comparable_range(year: int, month: int, today: date) -> Tuple[date, date]:
    """Rango del mes que se puede comparar: el mes completo si ya cerró, o del
    1 a hoy si va en curso. None-safe para meses futuros (devuelve el 1)."""
    start, end = month_bounds(year, month)
    if today < start:
        return start, start
    return start, min(end, today)


def same_days_previous_month(year: int, month: int, today: date) -> Tuple[date, date]:
    """Mismos días del mes anterior. Si el mes va en curso hasta el día d,
    devuelve del 1 al d del mes anterior (sin pasarse de su último día)."""
    start, end = comparable_range(year, month, today)
    py, pm = previous_month(year, month)
    p_start, p_end = month_bounds(py, pm)
    if end == month_bounds(year, month)[1]:
        return p_start, p_end
    return p_start, p_start.replace(day=min(end.day, p_end.day))


def daily(value: Optional[float], year: int, month: int) -> Optional[float]:
    """Valor del mes ÷ días calendario (las dos tiendas abren todos los días)."""
    return ratio(value, days_in_month(year, month))
