"""
Modelos Pydantic para responses
"""
from pydantic import BaseModel, Field, ConfigDict
from typing import Dict, Any


class PaymentMethodTotal(BaseModel):
    """Total por método de pago"""

    model_config = ConfigDict(from_attributes=True)

    label: str = Field(..., description="Etiqueta del método de pago")
    total: int = Field(..., description="Total en valor numérico")
    formatted: str = Field(..., description="Total formateado como COP")


class AlegraResults(BaseModel):
    """Resultados de la consulta a Alegra"""

    model_config = ConfigDict(from_attributes=True)

    date_requested: str = Field(..., description="Fecha consultada")
    username_used: str = Field(..., description="Usuario utilizado")
    results: Dict[str, PaymentMethodTotal] = Field(
        ...,
        description="Totales por método de pago"
    )
    total_sale: PaymentMethodTotal = Field(
        ...,
        description="Total de ventas del día"
    )


class CashTotals(BaseModel):
    """Totales de efectivo contado"""

    model_config = ConfigDict(from_attributes=True)

    total_monedas: int
    total_billetes: int
    total_general: int
    total_general_formatted: str


class BaseInfo(BaseModel):
    """Información de la base de caja"""

    model_config = ConfigDict(from_attributes=True)

    base_monedas: Dict[int, int]
    base_billetes: Dict[int, int]
    total_base_monedas: int
    total_base_billetes: int
    total_base: int
    total_base_formatted: str
    exact_base_obtained: bool
    restante_para_base: int
    base_status: str = Field(
        ...,
        description="Estado de la base: 'exacta', 'faltante', o 'sobrante'"
    )
    diferencia_base: int = Field(
        ...,
        description="Diferencia con respecto a 450,000 (positivo si sobra, negativo si falta, 0 si es exacto)"
    )
    diferencia_base_formatted: str = Field(
        ...,
        description="Diferencia formateada como COP"
    )
    mensaje_base: str = Field(
        ...,
        description="Mensaje descriptivo del estado de la base para mostrar en el frontend"
    )


class ConsignarInfo(BaseModel):
    """Información de efectivo para consignar"""

    model_config = ConfigDict(from_attributes=True)

    consignar_monedas: Dict[int, int]
    consignar_billetes: Dict[int, int]
    total_consignar_sin_ajustes: int
    total_consignar_sin_ajustes_formatted: str
    efectivo_para_consignar_final: int
    efectivo_para_consignar_final_formatted: str


class Adjustments(BaseModel):
    """Ajustes aplicados al cierre"""

    model_config = ConfigDict(from_attributes=True)

    excedente: int
    excedente_formatted: str
    excedente_efectivo: int | None = Field(default=0, description="Excedente en efectivo")
    excedente_datafono: int | None = Field(default=0, description="Excedente en datafono")
    excedente_nequi: int | None = Field(default=0, description="Excedente en nequi")
    excedente_daviplata: int | None = Field(default=0, description="Excedente en daviplata")
    excedente_qr: int | None = Field(default=0, description="Excedente en QR")
    gastos_operativos: int
    gastos_operativos_formatted: str
    prestamos: int
    prestamos_formatted: str
    venta_efectivo_diaria_alegra: int
    venta_efectivo_diaria_alegra_formatted: str


class CashCount(BaseModel):
    """Información completa del conteo de caja"""

    model_config = ConfigDict(from_attributes=True)

    input_coins: Dict[int, int]
    input_bills: Dict[int, int]
    totals: CashTotals
    base: BaseInfo
    consignar: ConsignarInfo
    adjustments: Adjustments


class ExcedenteDetalle(BaseModel):
    """Detalle de un excedente"""

    model_config = ConfigDict(from_attributes=True)

    tipo: str = Field(..., description="Tipo de excedente (Efectivo, Transferencia, Datafono)")
    subtipo: str | None = Field(default=None, description="Subtipo de excedente (Nequi, Daviplata, QR)")
    valor: int = Field(..., description="Valor del excedente")


class MetodosPagoRegistrados(BaseModel):
    """Métodos de pago registrados con totales calculados"""

    model_config = ConfigDict(from_attributes=True)

    addi_datafono: int = Field(default=0)
    nequi_luz_helena: int = Field(default=0)
    daviplata_jose: int = Field(default=0)
    qr_julieth: int = Field(default=0)
    tarjeta_debito: int = Field(default=0)
    tarjeta_credito: int = Field(default=0)
    total_transferencias_registradas: int = Field(..., description="Total de transferencias registradas")
    total_datafono_registrado: int = Field(..., description="Total de datafono registrado")


class DiferenciaValidacion(BaseModel):
    """Diferencia detectada en la validación"""

    model_config = ConfigDict(from_attributes=True)

    alegra: int = Field(..., description="Valor reportado por Alegra")
    registrado: int = Field(..., description="Valor registrado manualmente")
    diferencia: int = Field(..., description="Diferencia absoluta")
    diferencia_formatted: str = Field(..., description="Diferencia formateada")
    es_significativa: bool = Field(..., description="Si la diferencia es >= 100")


class Diferencias(BaseModel):
    """Diferencias detectadas entre Alegra y lo registrado"""

    model_config = ConfigDict(from_attributes=True)

    transferencias: DiferenciaValidacion
    datafono: DiferenciaValidacion


class Validation(BaseModel):
    """Información de validación del cierre"""

    model_config = ConfigDict(from_attributes=True)

    cierre_validado: bool = Field(..., description="Si el cierre fue validado correctamente")
    validation_status: str = Field(..., description="Estado de validación: success, warning, error")
    diferencias: Diferencias = Field(..., description="Diferencias detectadas")
    mensaje_validacion: str = Field(..., description="Mensaje descriptivo de la validación")


class CashClosingResponse(BaseModel):
    """Response completo del cierre de caja"""

    model_config = ConfigDict(from_attributes=True)

    request_datetime: str
    request_date: str
    request_time: str
    request_tz: str
    date_requested: str
    username_used: str
    cash_count: CashCount
    alegra: AlegraResults
    excedentes_detalle: list[ExcedenteDetalle] = Field(
        default_factory=list,
        description="Detalle de excedentes categorizados"
    )
    gastos_operativos_nota: str = Field(default="", description="Nota de gastos operativos")
    prestamos_nota: str = Field(default="", description="Nota de préstamos")
    metodos_pago_registrados: MetodosPagoRegistrados | None = Field(
        default=None,
        description="Métodos de pago registrados con totales calculados"
    )
    validation: Validation | None = Field(
        default=None,
        description="Información de validación del cierre"
    )


class HealthCheckResponse(BaseModel):
    """Response del health check"""

    model_config = ConfigDict(from_attributes=True)

    status: str = Field(..., description="Estado del servicio")
    service: str = Field(..., description="Nombre del servicio")
    version: str = Field(..., description="Versión del servicio")
    alegra: str = Field(default="unknown", description="Estado de conexión con Alegra")


class ErrorResponse(BaseModel):
    """Response de error genérico"""

    model_config = ConfigDict(from_attributes=True)

    error: str = Field(..., description="Mensaje de error")
    status_code: int = Field(..., description="Código HTTP")
    type: str = Field(default="error", description="Tipo de error")
    field: str | None = Field(default=None, description="Campo que causó el error")
    details: Any | None = Field(default=None, description="Detalles adicionales")
