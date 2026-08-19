"""
Tests para el calculador de caja
"""
import pytest
from app.services.cash_calculator import CashCalculator


class TestCashCalculator:
    def test_calcular_totales(self):
        """Test cálculo de totales básico"""
        calculator = CashCalculator()

        conteo_monedas = {50: 10, 100: 20, 200: 10, 500: 5, 1000: 3}
        conteo_billetes = {2000: 10, 5000: 5, 10000: 3}

        total_monedas, total_billetes, total_general = calculator.calcular_totales(
            conteo_monedas, conteo_billetes
        )

        # Monedas: 50*10 + 100*20 + 200*10 + 500*5 + 1000*3 = 500 + 2000 + 2000 + 2500 + 3000 = 10000
        assert total_monedas == 10000

        # Billetes: 2000*10 + 5000*5 + 10000*3 = 20000 + 25000 + 30000 = 75000
        assert total_billetes == 75000

        # Total
        assert total_general == 85000

    def test_calcular_totales_vacios(self):
        """Test con conteos vacíos"""
        calculator = CashCalculator()

        conteo_monedas = {50: 0, 100: 0, 200: 0, 500: 0, 1000: 0}
        conteo_billetes = {2000: 0, 5000: 0, 10000: 0, 20000: 0, 50000: 0, 100000: 0}

        total_monedas, total_billetes, total_general = calculator.calcular_totales(
            conteo_monedas, conteo_billetes
        )

        assert total_monedas == 0
        assert total_billetes == 0
        assert total_general == 0

    def test_aplicar_ajustes(self):
        """Test aplicación de ajustes (Escenario A: gastos y préstamos ya fueron
        sacados físicamente del efectivo ANTES de contar, por lo que no se resta
        nada aquí; ambos parámetros solo se usan para logging)."""
        calculator = CashCalculator()

        total_consignar = 100000
        excedente = 10000
        gastos = 5000
        prestamos = 3000

        resultado = calculator.aplicar_ajustes(
            total_consignar,
            excedente,
            gastos,
            prestamos
        )

        # No se resta nada: el efectivo contado ya refleja gastos y préstamos
        assert resultado == 100000

    def test_calcular_venta_efectivo_alegra(self):
        """Test cálculo de venta efectivo (Escenario A: se suman gastos y
        préstamos porque Alegra reporta el efectivo ANTES de sacarlos)."""
        calculator = CashCalculator()

        total_general = 500000
        excedente = 13500
        total_base = 450000
        gastos_operativos = 5000
        prestamos = 2000

        resultado = calculator.calcular_venta_efectivo_alegra(
            total_general,
            excedente,
            total_base,
            gastos_operativos,
            prestamos
        )

        # Fórmula: TOTAL_GENERAL - EXCEDENTE - BASE + GASTOS_OPERATIVOS + PRESTAMOS
        # 500000 - 13500 - 450000 + 5000 + 2000 = 43500
        assert resultado == 43500

    def test_procesar_cierre_completo(self):
        """Test procesamiento completo de cierre"""
        calculator = CashCalculator(
            base_objetivo=450000,
            umbral_menudo=10000
        )

        conteo_monedas = {50: 0, 100: 6, 200: 40, 500: 1, 1000: 0}
        conteo_billetes = {2000: 16, 5000: 7, 10000: 7, 20000: 12, 50000: 12, 100000: 9}

        resultado = calculator.procesar_cierre_completo(
            conteo_monedas=conteo_monedas,
            conteo_billetes=conteo_billetes,
            excedente=13500,
            gastos_operativos=0,
            prestamos=0
        )

        # Verificar estructura de respuesta
        assert 'input_coins' in resultado
        assert 'input_bills' in resultado
        assert 'totals' in resultado
        assert 'base' in resultado
        assert 'consignar' in resultado
        assert 'adjustments' in resultado

        # Verificar totales
        assert resultado['totals']['total_general'] > 0
        assert resultado['base']['total_base'] <= 450000

        # Verificar campos formateados
        assert resultado['totals']['total_general_formatted'].startswith('$')
        assert resultado['base']['total_base_formatted'].startswith('$')
