"""
Modelos Pydantic para requests
"""
from pydantic import BaseModel, Field, field_validator, ConfigDict
from datetime import date as date_type
from typing import Dict, List


class CashClosingRequest(BaseModel):
    """Modelo para el request de cierre de caja"""

    model_config = ConfigDict(str_strip_whitespace=True)

    date: date_type = Field(
        ...,
        description="Fecha del cierre de caja en formato YYYY-MM-DD"
    )

    coins: Dict[str, int] = Field(
        default_factory=dict,
        description="Diccionario de monedas por denominación {denominación: cantidad}"
    )

    bills: Dict[str, int] = Field(
        default_factory=dict,
        description="Diccionario de billetes por denominación {denominación: cantidad}"
    )

    excedente: float = Field(
        default=0,
        ge=0,
        description="Dinero excedente que no pertenece a las ventas del día (deprecado, usar excedentes)"
    )

    excedentes: List[Dict] = Field(
        default_factory=list,
        description="Lista de excedentes categorizados [{tipo, subtipo, valor}]"
    )

    gastos_operativos: float = Field(
        default=0,
        ge=0,
        description="Gastos operativos del día"
    )

    gastos_operativos_nota: str = Field(
        default="",
        description="Nota descriptiva de los gastos operativos"
    )

    prestamos: float = Field(
        default=0,
        ge=0,
        description="Préstamos realizados"
    )

    prestamos_nota: str = Field(
        default="",
        description="Nota descriptiva de los préstamos"
    )

    desfases: List[Dict] = Field(
        default_factory=list,
        description="Lista de desfases en caja [{tipo, valor, nota}]"
    )

    metodos_pago: Dict = Field(
        default_factory=dict,
        description="Métodos de pago registrados manualmente"
    )

    # Nuevos campos para timezone
    timezone: str = Field(
        default="America/Bogota",
        description="Zona horaria del frontend (debe ser America/Bogota)"
    )

    utc_offset: str = Field(
        default="-05:00",
        description="Offset UTC de la zona horaria"
    )

    request_timestamp: str = Field(
        default="",
        description="Timestamp completo ISO 8601 con zona horaria desde el frontend"
    )

    base_objetivo: int = Field(
        default=None,
        ge=1,
        description="Base de caja objetivo personalizable (por defecto usa Config.BASE_OBJETIVO)"
    )

    @field_validator('coins', 'bills')
    @classmethod
    def validate_non_negative(cls, v):
        """Valida que todas las cantidades sean no negativas"""
        for denom, qty in v.items():
            if qty < 0:
                raise ValueError(f"La cantidad para denominación {denom} no puede ser negativa: {qty}")
        return v

    @field_validator('date')
    @classmethod
    def validate_date_not_future(cls, v):
        """Valida que la fecha no sea futura (usando zona horaria de Colombia)"""
        from app.utils.timezone import get_colombia_now
        today_colombia = get_colombia_now().date()
        if v > today_colombia:
            raise ValueError(f"La fecha no puede ser futura: {v} (hoy en Colombia: {today_colombia})")
        return v

    def get_normalized_coins(self, valid_denominations: list) -> Dict[int, int]:
        """
        Normaliza las monedas a un dict con claves int

        Args:
            valid_denominations: Lista de denominaciones válidas

        Returns:
            Dict con claves int y valores int
        """
        result = {d: 0 for d in valid_denominations}
        for key, value in self.coins.items():
            denom = int(key)
            if denom in valid_denominations:
                result[denom] = max(0, int(value))
        return result

    def get_normalized_bills(self, valid_denominations: list) -> Dict[int, int]:
        """
        Normaliza los billetes a un dict con claves int

        Args:
            valid_denominations: Lista de denominaciones válidas

        Returns:
            Dict con claves int y valores int
        """
        result = {d: 0 for d in valid_denominations}
        for key, value in self.bills.items():
            denom = int(key)
            if denom in valid_denominations:
                result[denom] = max(0, int(value))
        return result
