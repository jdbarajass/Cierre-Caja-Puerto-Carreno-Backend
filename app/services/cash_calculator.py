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

        # Calcular total general PRIMERO para validación
        total_general_disponible = sum(denom * cant for denom, cant in todas_denoms.items())

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

        # NUEVA VALIDACIÓN: Determinar el estado de la base
        if total_general_disponible == self.base_objetivo:
            # Caso 1: Total exacto de 450,000
            base_status = "exacta"
            diferencia_base = 0
            mensaje_base = f"La base es exacta: {format_cop(self.base_objetivo)}"

        elif total_general_disponible < self.base_objetivo:
            # Caso 2: Falta dinero para completar la base
            base_status = "faltante"
            diferencia_base = -(self.base_objetivo - total_general_disponible)
            faltante = self.base_objetivo - total_general_disponible
            mensaje_base = f"Falta {format_cop(faltante)} para completar la base de {format_cop(self.base_objetivo)}"

        else:
            # Caso 3: Sobra dinero por encima de la base
            base_status = "sobrante"
            diferencia_base = total_general_disponible - self.base_objetivo
            sobrante = total_general_disponible - self.base_objetivo
            mensaje_base = f"Sobra {format_cop(sobrante)} por encima de la base de {format_cop(self.base_objetivo)}"

        resultado = {
            'base_monedas': base_monedas,
            'base_billetes': base_billetes,
            'total_base_monedas': int(total_base_monedas),
            'total_base_billetes': int(total_base_billetes),
            'total_base': int(total_base),
            'total_base_formatted': format_cop(total_base),
            'exact_base_obtained': bool(exacto),
            'restante_para_base': int(restante_base),
            'base_status': base_status,
            'diferencia_base': int(diferencia_base),
            'diferencia_base_formatted': format_cop(abs(diferencia_base)),
            'mensaje_base': mensaje_base,
            'consignar_monedas': consignar_monedas,
            'consignar_billetes': consignar_billetes,
            'total_consignar_sin_ajustes': int(total_consignar_sin_ajustes),
            'total_consignar_sin_ajustes_formatted': format_cop(total_consignar_sin_ajustes)
        }

        # Logging mejorado
        logger.info(
            f"Validación de base: {mensaje_base}"
        )
        logger.info(
            f"Base calculada: {format_cop(total_base)} "
            f"({'exacta' if exacto else f'aproximada, restante knapsack: {format_cop(restante_base)}'})"
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

        NOTA IMPORTANTE:
        - Los gastos operativos NO se restan aquí porque ya fueron sacados
          físicamente del efectivo antes de contar
        - Solo se restan los préstamos del monto a consignar

        Args:
            total_consignar_sin_ajustes: Total antes de ajustes
            excedente: Dinero excedente
            gastos_operativos: Gastos del día (solo para logging, no se resta)
            prestamos: Préstamos realizados

        Returns:
            Monto final para consignar
        """
        efectivo_para_consignar_final = (
            total_consignar_sin_ajustes
            - prestamos
        )

        logger.info(
            f"Ajustes aplicados: "
            f"sin_ajustes={format_cop(total_consignar_sin_ajustes)}, "
            f"gastos={format_cop(gastos_operativos)} (ya descontados físicamente), "
            f"prestamos={format_cop(prestamos)}, "
            f"final={format_cop(efectivo_para_consignar_final)}"
        )

        return int(efectivo_para_consignar_final)

    def calcular_venta_efectivo_alegra(
        self,
        total_general: int,
        excedente: float,
        total_base: int,
        gastos_operativos: float
    ) -> int:
        """
        Calcula la venta en efectivo para comparar con Alegra

        NOTA IMPORTANTE:
        - El total_general es el efectivo contado DESPUÉS de sacar gastos operativos
        - Alegra reporta el efectivo vendido ANTES de sacar gastos operativos
        - Por lo tanto, sumamos los gastos operativos al resultado para comparar con Alegra

        Fórmula: TOTAL_GENERAL - EXCEDENTE - BASE + GASTOS_OPERATIVOS

        Args:
            total_general: Total de efectivo contado (ya con gastos descontados)
            excedente: Excedente del día (solo efectivo)
            total_base: Total de la base
            gastos_operativos: Gastos operativos que ya fueron sacados del efectivo

        Returns:
            Venta en efectivo calculada (para comparar con Alegra)
        """
        venta_efectivo = total_general - excedente - total_base + gastos_operativos

        logger.info(
            f"Venta efectivo calculada para Alegra: {format_cop(venta_efectivo)} "
            f"(total={format_cop(total_general)} - excedente={format_cop(excedente)} - "
            f"base={format_cop(total_base)} + gastos={format_cop(gastos_operativos)})"
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

        NOTA IMPORTANTE:
        - El parámetro 'excedente' debe ser solo el excedente en EFECTIVO
        - Los gastos operativos ya fueron sacados físicamente del efectivo antes de contar
        - El efectivo contado (total_general) ya refleja los gastos descontados

        Args:
            conteo_monedas: Dict {denominación: cantidad}
            conteo_billetes: Dict {denominación: cantidad}
            excedente: Excedente en EFECTIVO del día (no incluir datafono, nequi, etc)
            gastos_operativos: Gastos operativos que ya fueron sacados físicamente
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
            base_info['total_base'],
            gastos_operativos
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


def procesar_excedentes(excedentes_list):
    """
    Recibe una lista de excedentes y retorna los totales por tipo.

    Args:
        excedentes_list: [
            { "tipo": "efectivo", "subtipo": null, "valor": 10000 },
            { "tipo": "qr_transferencias", "subtipo": "nequi", "valor": 5000 }
        ]

    Returns:
        {
            "total_excedente": 15000,
            "excedente_efectivo": 10000,
            "excedente_datafono": 0,
            "excedente_nequi": 5000,
            "excedente_daviplata": 0,
            "excedente_qr": 0,
            "excedentes_detalle": [
                { "tipo": "Efectivo", "valor": 10000 },
                { "tipo": "Transferencia", "subtipo": "Nequi", "valor": 5000 }
            ]
        }
    """
    totales = {
        "total_excedente": 0,
        "excedente_efectivo": 0,
        "excedente_datafono": 0,
        "excedente_nequi": 0,
        "excedente_daviplata": 0,
        "excedente_qr": 0,
        "excedentes_detalle": []
    }

    for exc in excedentes_list:
        valor = int(exc.get("valor", 0))
        if valor > 0:
            totales["total_excedente"] += valor

            if exc["tipo"] == "efectivo":
                totales["excedente_efectivo"] += valor
                totales["excedentes_detalle"].append({
                    "tipo": "Efectivo",
                    "valor": valor
                })
            elif exc["tipo"] == "datafono":
                totales["excedente_datafono"] += valor
                totales["excedentes_detalle"].append({
                    "tipo": "Datafono",
                    "valor": valor
                })
            elif exc["tipo"] == "qr_transferencias":
                subtipo = exc.get("subtipo", "")
                if subtipo == "nequi":
                    totales["excedente_nequi"] += valor
                    totales["excedentes_detalle"].append({
                        "tipo": "Transferencia",
                        "subtipo": "Nequi",
                        "valor": valor
                    })
                elif subtipo == "daviplata":
                    totales["excedente_daviplata"] += valor
                    totales["excedentes_detalle"].append({
                        "tipo": "Transferencia",
                        "subtipo": "Daviplata",
                        "valor": valor
                    })
                elif subtipo == "qr":
                    totales["excedente_qr"] += valor
                    totales["excedentes_detalle"].append({
                        "tipo": "Transferencia",
                        "subtipo": "QR",
                        "valor": valor
                    })

    logger.info(
        f"Excedentes procesados: total={format_cop(totales['total_excedente'])}, "
        f"efectivo={format_cop(totales['excedente_efectivo'])}, "
        f"datafono={format_cop(totales['excedente_datafono'])}, "
        f"nequi={format_cop(totales['excedente_nequi'])}, "
        f"daviplata={format_cop(totales['excedente_daviplata'])}, "
        f"qr={format_cop(totales['excedente_qr'])}"
    )

    return totales


def calcular_totales_metodos_pago(metodos_pago):
    """
    Calcula los totales de transferencias y datafono.

    NOTA IMPORTANTE:
    - Alegra registra "Addi" como transferencia, pero en realidad va al datafono
    - total_transferencias_registradas: Incluye Addi (para validar con Alegra)
    - total_solo_tarjetas: Solo débito + crédito (lo que Alegra reporta en debit-card + credit-card)
    - total_datafono_real: Tarjetas + Addi (lo que realmente llega al datafono de Cristian)

    Args:
        metodos_pago: {
            "addi_datafono": 0,
            "nequi_luz_helena": 0,
            "daviplata_jose": 0,
            "qr_julieth": 0,
            "tarjeta_debito": 464000,
            "tarjeta_credito": 0
        }

    Returns:
        {
            **metodos_pago,
            "total_transferencias_registradas": nequi + daviplata + qr + addi (para validar con Alegra transfer),
            "total_solo_tarjetas": debito + credito (para validar con Alegra debit-card + credit-card),
            "total_datafono_real": debito + credito + addi (lo que realmente llega al datafono)
        }
    """
    addi = int(metodos_pago.get("addi_datafono", 0))
    nequi = int(metodos_pago.get("nequi_luz_helena", 0))
    daviplata = int(metodos_pago.get("daviplata_jose", 0))
    qr = int(metodos_pago.get("qr_julieth", 0))
    tarjeta_debito = int(metodos_pago.get("tarjeta_debito", 0))
    tarjeta_credito = int(metodos_pago.get("tarjeta_credito", 0))

    # Total transferencias para validar con Alegra (incluye Addi porque Alegra lo registra como transferencia)
    total_transferencias_registradas = nequi + daviplata + qr + addi

    # Total solo tarjetas (lo que Alegra reporta en debit-card + credit-card)
    total_solo_tarjetas = tarjeta_debito + tarjeta_credito

    # Total real que llega al datafono de Cristian (tarjetas + Addi)
    total_datafono_real = tarjeta_debito + tarjeta_credito + addi

    logger.info(
        f"Totales métodos de pago calculados: "
        f"transferencias_para_alegra={format_cop(total_transferencias_registradas)} "
        f"(nequi={format_cop(nequi)}, daviplata={format_cop(daviplata)}, "
        f"qr={format_cop(qr)}, addi={format_cop(addi)}), "
        f"solo_tarjetas={format_cop(total_solo_tarjetas)}, "
        f"datafono_real={format_cop(total_datafono_real)}"
    )

    return {
        **metodos_pago,
        "total_transferencias_registradas": total_transferencias_registradas,
        "total_solo_tarjetas": total_solo_tarjetas,
        "total_datafono_real": total_datafono_real
    }


def validar_cierre(datos_alegra, metodos_pago_calculados, cash_result=None, excedentes_procesados=None, gastos_operativos=0):
    """
    Valida si el cierre es exitoso comparando Alegra con lo registrado.

    LÓGICA DE VALIDACIÓN:
    1. Efectivo: Alegra "cash" + Excedente efectivo - Gastos operativos debe coincidir con Total a consignar
       - Esta es la validación principal del cierre
       - Los gastos operativos se restan porque Alegra reporta efectivo ANTES de sacarlos
       - El total a consignar ya tiene los gastos descontados (se sacaron físicamente antes de contar)
    2. Transferencias: Alegra "transfer" debe coincidir con (Nequi + Daviplata + QR + Addi)
       - Alegra registra Addi como transferencia aunque realmente va al datafono
    3. Datafono: Alegra "debit-card + credit-card" debe coincidir con (Tarjeta débito + Tarjeta crédito)
       - Alegra NO incluye Addi en las tarjetas
    4. Datafono Real: Se calcula como (Tarjetas + Addi) para mostrar lo que realmente llega al datafono

    Args:
        datos_alegra: Los datos obtenidos de Alegra
        metodos_pago_calculados: Los totales calculados de métodos de pago
        cash_result: Resultado del cálculo de caja (opcional, para validación de efectivo)
        excedentes_procesados: Excedentes procesados (opcional, para validación de efectivo)
        gastos_operativos: Gastos operativos del día (default: 0)

    Returns:
        {
            "cierre_validado": True/False,
            "validation_status": "success" | "warning" | "error",
            "diferencias": {
                "efectivo": {...},
                "transferencias": {...},
                "datafono": {...},
                "datafono_real": {...}
            },
            "mensaje_validacion": "..."
        }
    """
    # Obtener totales de Alegra
    efectivo_alegra = datos_alegra.get("results", {}).get("cash", {}).get("total", 0)
    transferencia_alegra = datos_alegra.get("results", {}).get("transfer", {}).get("total", 0)

    datafono_alegra = (
        datos_alegra.get("results", {}).get("debit-card", {}).get("total", 0) +
        datos_alegra.get("results", {}).get("credit-card", {}).get("total", 0)
    )

    # Obtener totales registrados
    transferencias_registradas = metodos_pago_calculados.get("total_transferencias_registradas", 0)  # Incluye Addi
    solo_tarjetas = metodos_pago_calculados.get("total_solo_tarjetas", 0)  # Solo débito + crédito
    datafono_real = metodos_pago_calculados.get("total_datafono_real", 0)  # Tarjetas + Addi

    # VALIDACIÓN DE EFECTIVO (Validación principal del cierre)
    # Efectivo de Alegra + Excedente de efectivo - Gastos operativos = Total a consignar
    efectivo_validado = True
    diff_efectivo = 0
    excedente_efectivo = 0
    efectivo_para_consignar = 0
    suma_efectivo_ajustada = 0

    if cash_result and excedentes_procesados:
        excedente_efectivo = excedentes_procesados.get("excedente_efectivo", 0)
        efectivo_para_consignar = cash_result.get("consignar", {}).get("efectivo_para_consignar_final", 0)

        # IMPORTANTE: Restar gastos operativos porque Alegra reporta efectivo ANTES de sacarlos
        # y el total a consignar ya tiene los gastos descontados
        suma_efectivo_ajustada = efectivo_alegra + excedente_efectivo - gastos_operativos

        # Calcular diferencia
        diff_efectivo = abs(suma_efectivo_ajustada - efectivo_para_consignar)

        # Validación: diferencia debe ser menor a 100 pesos
        efectivo_validado = diff_efectivo < 100

    # Calcular diferencias de otros métodos
    diff_transferencia = abs(transferencia_alegra - transferencias_registradas)
    diff_datafono = abs(datafono_alegra - solo_tarjetas)

    # VALIDACIÓN GLOBAL: El cierre es exitoso si:
    # 1. Efectivo validado correctamente (CRÍTICO)
    # 2. Transferencias y datafono con diferencias < 100 (ADVERTENCIA)
    cierre_validado = efectivo_validado and diff_transferencia < 100 and diff_datafono < 100

    # Determinar status:
    # - "success": Todo validado correctamente
    # - "warning": Efectivo OK pero hay diferencias en transferencias/datafono
    # - "error": Efectivo NO coincide (cierre fallido)
    if not efectivo_validado:
        validation_status = "error"
    elif diff_transferencia >= 100 or diff_datafono >= 100:
        validation_status = "warning"
    else:
        validation_status = "success"

    diferencias = {
        "efectivo": {
            "efectivo_alegra": efectivo_alegra,
            "efectivo_alegra_formatted": format_cop(efectivo_alegra),
            "excedente_efectivo": excedente_efectivo,
            "excedente_efectivo_formatted": format_cop(excedente_efectivo),
            "gastos_operativos": gastos_operativos,
            "gastos_operativos_formatted": format_cop(gastos_operativos),
            "suma_efectivo_ajustada": suma_efectivo_ajustada,
            "suma_efectivo_ajustada_formatted": format_cop(suma_efectivo_ajustada),
            "efectivo_para_consignar": efectivo_para_consignar,
            "efectivo_para_consignar_formatted": format_cop(efectivo_para_consignar),
            "diferencia": diff_efectivo,
            "diferencia_formatted": format_cop(diff_efectivo),
            "es_valido": efectivo_validado,
            "detalle": "Efectivo Alegra + Excedente efectivo - Gastos operativos = Total a consignar"
        },
        "transferencias": {
            "alegra": transferencia_alegra,
            "registrado": transferencias_registradas,
            "diferencia": diff_transferencia,
            "diferencia_formatted": format_cop(diff_transferencia),
            "es_significativa": diff_transferencia >= 100,
            "detalle": "Alegra transfer vs (Nequi + Daviplata + QR + Addi)"
        },
        "datafono": {
            "alegra": datafono_alegra,
            "registrado": solo_tarjetas,
            "diferencia": diff_datafono,
            "diferencia_formatted": format_cop(diff_datafono),
            "es_significativa": diff_datafono >= 100,
            "detalle": "Alegra debit+credit vs (Tarjeta débito + Tarjeta crédito)"
        },
        "datafono_real": {
            "total": datafono_real,
            "total_formatted": format_cop(datafono_real),
            "detalle": "Lo que realmente llega al datafono de Cristian (Tarjetas + Addi)"
        }
    }

    # Mensaje descriptivo mejorado con detalles específicos de cada método de pago
    mensajes = []
    medios_con_diferencia = []  # Lista de medios de pago con diferencias

    # CRÍTICO: Validación de efectivo
    if not diferencias["efectivo"]["es_valido"]:
        medios_con_diferencia.append("EFECTIVO")
        mensajes.append(
            f"⚠️ EFECTIVO NO COINCIDE: Diferencia de {diferencias['efectivo']['diferencia_formatted']} "
            f"(Alegra: {diferencias['efectivo']['efectivo_alegra_formatted']} + "
            f"Excedente: {diferencias['efectivo']['excedente_efectivo_formatted']} - "
            f"Gastos: {diferencias['efectivo']['gastos_operativos_formatted']} = "
            f"{diferencias['efectivo']['suma_efectivo_ajustada_formatted']} vs "
            f"Consignar: {diferencias['efectivo']['efectivo_para_consignar_formatted']})"
        )

    # ADVERTENCIAS: Diferencias en otros métodos
    if diferencias["transferencias"]["es_significativa"]:
        medios_con_diferencia.append("TRANSFERENCIAS")
        mensajes.append(
            f"⚠️ TRANSFERENCIAS NO COINCIDEN: Diferencia de {diferencias['transferencias']['diferencia_formatted']} "
            f"(Alegra: {format_cop(diferencias['transferencias']['alegra'])} vs "
            f"Registrado: {format_cop(diferencias['transferencias']['registrado'])})"
        )

    if diferencias["datafono"]["es_significativa"]:
        medios_con_diferencia.append("DATAFONO")
        mensajes.append(
            f"⚠️ DATAFONO NO COINCIDE: Diferencia de {diferencias['datafono']['diferencia_formatted']} "
            f"(Alegra: {format_cop(diferencias['datafono']['alegra'])} vs "
            f"Registrado: {format_cop(diferencias['datafono']['registrado'])})"
        )

    # Mensaje principal con lista de medios con diferencia
    if medios_con_diferencia:
        mensaje_validacion = f"Diferencias encontradas en: {', '.join(medios_con_diferencia)}"
    else:
        mensaje_validacion = "Cierre validado correctamente"

    logger.info(
        f"Validación de cierre: {validation_status.upper()} - {mensaje_validacion}"
    )
    logger.info(
        f"  EFECTIVO: Alegra {format_cop(efectivo_alegra)} + Excedente {format_cop(excedente_efectivo)} "
        f"- Gastos {format_cop(gastos_operativos)} = {format_cop(suma_efectivo_ajustada)} vs "
        f"Consignar {format_cop(efectivo_para_consignar)} (diff: {format_cop(diff_efectivo)}) "
        f"{'✓' if efectivo_validado else '✗'}"
    )
    logger.info(
        f"  Transferencias Alegra: {format_cop(transferencia_alegra)} vs "
        f"Registrado: {format_cop(transferencias_registradas)} (diff: {format_cop(diff_transferencia)})"
    )
    logger.info(
        f"  Datafono Alegra: {format_cop(datafono_alegra)} vs "
        f"Solo tarjetas: {format_cop(solo_tarjetas)} (diff: {format_cop(diff_datafono)})"
    )
    logger.info(
        f"  Datafono Real (con Addi): {format_cop(datafono_real)}"
    )

    # Imprimir mensajes detallados si hay diferencias
    if mensajes:
        logger.info("  DETALLES DE DIFERENCIAS:")
        for mensaje in mensajes:
            logger.info(f"    {mensaje}")

    return {
        "cierre_validado": cierre_validado,
        "validation_status": validation_status,
        "diferencias": diferencias,
        "mensaje_validacion": mensaje_validacion,
        "mensajes_detallados": mensajes  # Lista de mensajes detallados para el frontend
    }


def preparar_respuesta_completa(
    datos_alegra,
    cash_result,
    excedentes_procesados,
    metodos_pago_calculados,
    validacion_cierre,
    payload_original,
    datetime_info,
    tz_used,
    username
):
    """
    Prepara la respuesta final incluyendo todos los datos necesarios.

    Args:
        datos_alegra: Datos de Alegra
        cash_result: Resultado del cálculo de caja
        excedentes_procesados: Excedentes procesados con totales
        metodos_pago_calculados: Métodos de pago con totales calculados
        validacion_cierre: Resultado de la validación
        payload_original: Payload original del request
        datetime_info: Información de fecha/hora
        tz_used: Zona horaria utilizada
        username: Usuario de Alegra

    Returns:
        Dict con la respuesta completa
    """
    from app.utils.timezone import get_colombia_timestamp

    respuesta = {
        "success": True,
        "request_datetime": datetime_info['iso'],
        "request_date": datetime_info['date'],
        "request_time": datetime_info['time'],
        "request_tz": tz_used,
        "server_timestamp": get_colombia_timestamp(),
        "timezone": "America/Bogota",
        "date_requested": payload_original.get("date"),
        "username_used": username,
        "alegra": datos_alegra,
        "cash_count": cash_result,
        "excedentes_detalle": excedentes_procesados["excedentes_detalle"],
        "gastos_operativos_nota": payload_original.get("gastos_operativos_nota", ""),
        "prestamos_nota": payload_original.get("prestamos_nota", ""),
        "metodos_pago_registrados": metodos_pago_calculados,
        "validation": validacion_cierre
    }

    return respuesta
