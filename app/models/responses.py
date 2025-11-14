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
