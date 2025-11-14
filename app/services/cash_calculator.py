"""
Servicio de cálculos de cierre de caja
"""
from typing import Dict, Tuple
import logging

from app.config import Config
from app.services.knapsack_solver import construir_base_exacta
from app.utils.formatters import format_cop

logger = logging.getLogger(__name__)


class CashCalculator:
    """Calculador de cierres de caja"""

    def __init__(
        self,
        base_objetivo: int = None,
        umbral_menudo: int = None,
        denominaciones_monedas: list = None,
        denominaciones_billetes: list = None
    ):
        """
        Inicializa el calculador

        Args:
            base_objetivo: Monto objetivo para la base (default: Config.BASE_OBJETIVO)
            umbral_menudo: Umbral para considerar menudo (default: Config.UMBRAL_MENUDO)
            denominaciones_monedas: Lista de denominaciones de monedas válidas
            denominaciones_billetes: Lista de denominaciones de billetes válidas
        """
        self.base_objetivo = base_objetivo or Config.BASE_OBJETIVO
        self.umbral_menudo = umbral_menudo or Config.UMBRAL_MENUDO
        self.denominaciones_monedas = denominaciones_monedas or Config.DENOMINACIONES_MONEDAS
        self.denominaciones_billetes = denominaciones_billetes or Config.DENOMINACIONES_BILLETES

        logger.debug(
            f"CashCalculator inicializado: base={format_cop(self.base_objetivo)}, "
            f"umbral_menudo={format_cop(self.umbral_menudo)}"
        )

    def calcular_totales(
        self,
        conteo_monedas: Dict[int, int],
        conteo_billetes: Dict[int, int]
    ) -> Tuple[int, int, int]:
        """
        Calcula los totales de efectivo

        Args:
            conteo_monedas: Dict {denominación: cantidad}
            conteo_billetes: Dict {denominación: cantidad}

        Returns:
            Tuple (total_monedas, total_billetes, total_general)
        """
        total_monedas = sum(denom * cant for denom, cant in conteo_monedas.items())
        total_billetes = sum(denom * cant for denom, cant in conteo_billetes.items())
        total_general = total_monedas + total_billetes

        logger.info(
            f"Totales calculados: monedas={format_cop(total_monedas)}, "
            f"billetes={format_cop(total_billetes)}, "
            f"total={format_cop(total_general)}"
        )

        return total_monedas, total_billetes, total_general

    def calcular_base_y_consignacion(
        self,
        conteo_monedas: Dict[int, int],
        conteo_billetes: Dict[int, int]
    ) -> Dict:
        """
        Calcula la base y la consignación usando el algoritmo knapsack

        Args:
            conteo_monedas: Dict {denominación: cantidad}
            conteo_billetes: Dict {denominación: cantidad}

        Returns:
            Dict con toda la información de base y consignación
        """
        # Combinar todas las denominaciones
        todas_denoms = {**conteo_monedas, **conteo_billetes}

        # Resolver knapsack
        conteo_base, conteo_consignar, restante_base, exacto = construir_base_exacta(
            todas_denoms,
            self.base_objetivo,
            self.umbral_menudo
        )

        # Separar base en monedas y billetes
        base_monedas = {d: conteo_base.get(d, 0) for d in self.denominaciones_monedas}
        base_billetes = {d: conteo_base.get(d, 0) for d in self.denominaciones_billetes}

        # Separar consignación en monedas y billetes
        consignar_monedas = {d: conteo_consignar.get(d, 0) for d in self.denominaciones_monedas}
        consignar_billetes = {d: conteo_consignar.get(d, 0) for d in self.denominaciones_billetes}

        # Calcular totales de base
        total_base_monedas = sum(d * c for d, c in base_monedas.items())
        total_base_billetes = sum(d * c for d, c in base_billetes.items())
        total_base = total_base_monedas + total_base_billetes

        # Calcular totales de consignación
        total_consignar_sin_ajustes = sum(
            d * c for d, c in consignar_monedas.items()
        ) + sum(
            d * c for d, c in consignar_billetes.items()
        )

        resultado = {
            'base_monedas': base_monedas,
            'base_billetes': base_billetes,
            'total_base_monedas': int(total_base_monedas),
            'total_base_billetes': int(total_base_billetes),
            'total_base': int(total_base),
            'total_base_formatted': format_cop(total_base),
            'exact_base_obtained': bool(exacto),
            'restante_para_base': int(restante_base),
            'consignar_monedas': consignar_monedas,
            'consignar_billetes': consignar_billetes,
            'total_consignar_sin_ajustes': int(total_consignar_sin_ajustes),
            'total_consignar_sin_ajustes_formatted': format_cop(total_consignar_sin_ajustes)
        }

        logger.info(
            f"Base calculada: {format_cop(total_base)} "
            f"({'exacta' if exacto else f'inexacta, falta {format_cop(restante_base)}'})"
        )

        return resultado

    def aplicar_ajustes(
        self,
        total_consignar_sin_ajustes: int,
        excedente: float,
        gastos_operativos: float,
        prestamos: float
    ) -> int:
        """
        Aplica ajustes al monto de consignación

        Args:
            total_consignar_sin_ajustes: Total antes de ajustes
            excedente: Dinero excedente
            gastos_operativos: Gastos del día
            prestamos: Préstamos realizados

        Returns:
            Monto final para consignar
        """
        efectivo_para_consignar_final = (
            total_consignar_sin_ajustes
            - gastos_operativos
            - prestamos
        )

        logger.info(
            f"Ajustes aplicados: "
            f"sin_ajustes={format_cop(total_consignar_sin_ajustes)}, "
            f"gastos={format_cop(gastos_operativos)}, "
            f"prestamos={format_cop(prestamos)}, "
            f"final={format_cop(efectivo_para_consignar_final)}"
        )

        return int(efectivo_para_consignar_final)

    def calcular_venta_efectivo_alegra(
        self,
        total_general: int,
        excedente: float,
        total_base: int
    ) -> int:
        """
        Calcula la venta en efectivo según fórmula de Alegra

        Fórmula: TOTAL_GENERAL - EXCEDENTE - BASE

        Args:
            total_general: Total de efectivo contado
            excedente: Excedente del día
            total_base: Total de la base

        Returns:
            Venta en efectivo calculada
        """
        venta_efectivo = total_general - excedente - total_base

        logger.info(
            f"Venta efectivo calculada: {format_cop(venta_efectivo)} "
            f"(total={format_cop(total_general)} - excedente={format_cop(excedente)} - "
            f"base={format_cop(total_base)})"
        )

        return int(venta_efectivo)

    def procesar_cierre_completo(
        self,
        conteo_monedas: Dict[int, int],
        conteo_billetes: Dict[int, int],
        excedente: float,
        gastos_operativos: float,
        prestamos: float
    ) -> Dict:
        """
        Procesa un cierre de caja completo

        Args:
            conteo_monedas: Dict {denominación: cantidad}
            conteo_billetes: Dict {denominación: cantidad}
            excedente: Excedente del día
            gastos_operativos: Gastos operativos
            prestamos: Préstamos realizados

        Returns:
            Dict con toda la información del cierre
        """
        logger.info("=" * 60)
        logger.info("Iniciando procesamiento de cierre de caja")
        logger.info("=" * 60)

        # 1. Calcular totales
        total_monedas, total_billetes, total_general = self.calcular_totales(
            conteo_monedas,
            conteo_billetes
        )

        # 2. Calcular base y consignación
        base_info = self.calcular_base_y_consignacion(
            conteo_monedas,
            conteo_billetes
        )

        # 3. Aplicar ajustes
        efectivo_para_consignar_final = self.aplicar_ajustes(
            base_info['total_consignar_sin_ajustes'],
            excedente,
            gastos_operativos,
            prestamos
        )

        # 4. Calcular venta efectivo según Alegra
        venta_efectivo_diaria_alegra = self.calcular_venta_efectivo_alegra(
            total_general,
            excedente,
            base_info['total_base']
        )

        # 5. Construir respuesta completa
        resultado = {
            'input_coins': conteo_monedas,
            'input_bills': conteo_billetes,
            'totals': {
                'total_monedas': int(total_monedas),
                'total_billetes': int(total_billetes),
                'total_general': int(total_general),
                'total_general_formatted': format_cop(total_general)
            },
            'base': base_info,
            'consignar': {
                'consignar_monedas': base_info['consignar_monedas'],
                'consignar_billetes': base_info['consignar_billetes'],
                'total_consignar_sin_ajustes': base_info['total_consignar_sin_ajustes'],
                'total_consignar_sin_ajustes_formatted': base_info['total_consignar_sin_ajustes_formatted'],
                'efectivo_para_consignar_final': efectivo_para_consignar_final,
                'efectivo_para_consignar_final_formatted': format_cop(efectivo_para_consignar_final)
            },
            'adjustments': {
                'excedente': int(excedente),
                'excedente_formatted': format_cop(excedente),
                'gastos_operativos': int(gastos_operativos),
                'gastos_operativos_formatted': format_cop(gastos_operativos),
                'prestamos': int(prestamos),
                'prestamos_formatted': format_cop(prestamos),
                'venta_efectivo_diaria_alegra': venta_efectivo_diaria_alegra,
                'venta_efectivo_diaria_alegra_formatted': format_cop(venta_efectivo_diaria_alegra)
            }
        }

        logger.info("✓ Cierre de caja procesado exitosamente")
        logger.info("=" * 60)

        return resultado
