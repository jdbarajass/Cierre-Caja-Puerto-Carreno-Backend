"""
Tests de las reglas comunes de la Radiografía (Fase 0 de docs/PLAN_RADIOGRAFIA.md):
clasificación de salidas, fórmulas, división por cero y periodos. Sin base de datos.
"""
from datetime import date

import pytest

from app.services import radiografia as r


def test_clasificacion_de_cada_salida():
    from app.models.expense import OUT_CATEGORIES
    # Toda categoría de salida tiene clase (si se agrega una, hay que decidir)
    assert set(OUT_CATEGORIES) == set(r.CLASS_BY_CATEGORY)
    assert r.expense_class('flete') == r.COSTO_MERCANCIA
    assert r.expense_class('otro') == r.OPERATIVO              # decisión del usuario
    assert r.expense_class('cuota_credito') == r.CUOTA_CREDITO
    assert r.expense_class('retiro_socio') == r.RETIRO_SOCIO
    assert r.expense_class('prestamo_tienda') == r.PRESTAMO
    assert r.expense_class('nueva_rara') == r.OPERATIVO         # desconocida: resta, no se esconde
    assert set(r.EXPENSE_CATEGORIES) == {'operativo', 'sueldo', 'flete', 'financiero', 'otro'}
    assert r.DEBT_CATEGORIES == ('cuota_credito',)
    assert not set(r.EXPENSE_CATEGORIES) & set(r.DEBT_CATEGORIES)


def test_division_por_cero_y_variaciones():
    assert r.ratio(10, 0) is None and r.ratio(None, 5) is None and r.ratio(10, None) is None
    assert r.ratio(1, 4) == 0.25
    assert r.pct_change(120, 100) == pytest.approx(0.2)
    assert r.pct_change(100, 0) is None and r.pct_change(None, 100) is None
    assert r.pct_change(-50, -100) == pytest.approx(0.5)        # mejora de una pérdida


def test_costo_estimado_y_estado_de_resultados():
    assert r.estimated_cost(1000000, 35) == pytest.approx(650000)
    u = r.utility_lines(ventas=900000, precio_lista=1000000, margin_pct=35, fletes=20000,
                        operativos=100000, financieros=4000, comisiones=10000, cuotas=50000, recompras=600000)
    assert u['descuentos'] == 100000
    assert u['costo_vendido'] == pytest.approx(670000)
    assert u['utilidad_bruta'] == pytest.approx(230000)
    assert u['utilidad_operacional'] == pytest.approx(130000)
    assert u['gastos_financieros'] == 14000
    assert u['utilidad_neta'] == pytest.approx(116000)          # la cuota NO baja la utilidad neta
    assert u['margen_contribucion_pct'] == pytest.approx((900000 - 650000 - 20000 - 10000) / 900000)
    # Lo que quedó (como Año): ventas − recompras − lo que resta utilidad − cuotas
    assert u['lo_que_quedo'] == 900000 - 600000 - 20000 - 100000 - 14000 - 50000
    vacio = r.utility_lines(ventas=0, precio_lista=0, margin_pct=35, fletes=0, operativos=0,
                            financieros=0, comisiones=0, cuotas=0, recompras=0)
    assert vacio['margen_bruto_pct'] is None and vacio['margen_contribucion_pct'] is None


def test_punto_de_equilibrio():
    assert r.break_even(6000000, 0.3) == pytest.approx(20000000)
    assert r.break_even(6000000, 0) is None and r.break_even(6000000, -0.1) is None
    assert r.break_even(6000000, None) is None
    assert r.sales_for_target(6000000, 3000000, 0.3) == pytest.approx(30000000)
    assert r.daily(31000000, 2026, 10) == pytest.approx(1000000)   # todos los días del mes


def test_mismos_dias_del_mes_anterior():
    # Mes en curso: del 1 al 6 de noviembre contra del 1 al 6 de octubre
    assert r.same_days_previous_month(2026, 11, date(2026, 11, 6)) == (date(2026, 10, 1), date(2026, 10, 6))
    # Mes cerrado: completo contra completo
    assert r.same_days_previous_month(2026, 10, date(2026, 11, 6)) == (date(2026, 9, 1), date(2026, 9, 30))
    # 30 de marzo en curso contra febrero (no se pasa de su último día)
    assert r.same_days_previous_month(2026, 3, date(2026, 3, 30)) == (date(2026, 2, 1), date(2026, 2, 28))
    # Enero contra diciembre del año anterior
    assert r.same_days_previous_month(2026, 1, date(2026, 1, 10)) == (date(2025, 12, 1), date(2025, 12, 10))
    assert r.comparable_range(2026, 11, date(2026, 11, 6)) == (date(2026, 11, 1), date(2026, 11, 6))
