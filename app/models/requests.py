"""
Modelos Pydantic para requests
"""
from pydantic import BaseModel, Field, field_validator, ConfigDict
from datetime import date as date_type
from typing import Dict


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
        description="Dinero excedente que no pertenece a las ventas del día"
    )

    gastos_operativos: float = Field(
        default=0,
        ge=0,
        description="Gastos operativos del día"
    )

    prestamos: float = Field(
        default=0,
        ge=0,
        description="Préstamos realizados"
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
        """Valida que la fecha no sea futura"""
        from datetime import date as date_module
        today = date_module.today()
        if v > today:
            raise ValueError(f"La fecha no puede ser futura: {v}")
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
