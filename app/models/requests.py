"""
Modelos Pydantic para requests
"""
from pydantic import BaseModel, Field, field_validator, ConfigDict, EmailStr
from datetime import date as date_type
from typing import Dict, List, Optional
import re


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


class UserCreateRequest(BaseModel):
    """Modelo para la creación de usuario"""

    model_config = ConfigDict(str_strip_whitespace=True)

    email: str = Field(
        ...,
        min_length=5,
        max_length=255,
        description="Email del usuario"
    )

    password: str = Field(
        ...,
        min_length=8,
        max_length=128,
        description="Contraseña del usuario"
    )

    name: str = Field(
        ...,
        min_length=2,
        max_length=100,
        description="Nombre completo del usuario"
    )

    role: str = Field(
        default="sales",
        description="Rol del usuario (admin o sales)"
    )

    @field_validator('email')
    @classmethod
    def validate_email(cls, v):
        """Valida el formato del email"""
        pattern = r'^[^\s@]+@[^\s@]+\.[^\s@]+$'
        if not re.match(pattern, v):
            raise ValueError('Formato de email inválido')
        return v.lower()

    @field_validator('password')
    @classmethod
    def validate_password(cls, v):
        """Valida la fortaleza de la contraseña"""
        if not re.search(r'[A-Z]', v):
            raise ValueError('La contraseña debe contener al menos una mayúscula')
        if not re.search(r'[a-z]', v):
            raise ValueError('La contraseña debe contener al menos una minúscula')
        if not re.search(r'\d', v):
            raise ValueError('La contraseña debe contener al menos un número')
        return v

    @field_validator('role')
    @classmethod
    def validate_role(cls, v):
        """Valida que el rol sea válido"""
        allowed_roles = ['admin', 'sales']
        if v.lower() not in allowed_roles:
            raise ValueError(f'Rol inválido. Debe ser uno de: {", ".join(allowed_roles)}')
        return v.lower()


class UserUpdateRequest(BaseModel):
    """Modelo para la actualización de usuario"""

    model_config = ConfigDict(str_strip_whitespace=True)

    email: Optional[str] = Field(
        default=None,
        min_length=5,
        max_length=255,
        description="Email del usuario"
    )

    name: Optional[str] = Field(
        default=None,
        min_length=2,
        max_length=100,
        description="Nombre completo del usuario"
    )

    role: Optional[str] = Field(
        default=None,
        description="Rol del usuario (admin o sales)"
    )

    is_active: Optional[bool] = Field(
        default=None,
        description="Estado del usuario"
    )

    @field_validator('email')
    @classmethod
    def validate_email(cls, v):
        """Valida el formato del email"""
        if v is None:
            return v
        pattern = r'^[^\s@]+@[^\s@]+\.[^\s@]+$'
        if not re.match(pattern, v):
            raise ValueError('Formato de email inválido')
        return v.lower()

    @field_validator('role')
    @classmethod
    def validate_role(cls, v):
        """Valida que el rol sea válido"""
        if v is None:
            return v
        allowed_roles = ['admin', 'sales']
        if v.lower() not in allowed_roles:
            raise ValueError(f'Rol inválido. Debe ser uno de: {", ".join(allowed_roles)}')
        return v.lower()


class DateRangeRequest(BaseModel):
    """Modelo para validación de rangos de fechas"""

    model_config = ConfigDict(str_strip_whitespace=True)

    start_date: date_type = Field(
        ...,
        description="Fecha de inicio en formato YYYY-MM-DD"
    )

    end_date: date_type = Field(
        ...,
        description="Fecha de fin en formato YYYY-MM-DD"
    )

    @field_validator('start_date', 'end_date')
    @classmethod
    def validate_date_range(cls, v):
        """Valida que las fechas estén en un rango razonable"""
        from datetime import date
        if v.year < 2020:
            raise ValueError('La fecha debe ser posterior a 2020')
        if v > date.today():
            raise ValueError('La fecha no puede ser futura')
        return v

    def model_post_init(self, __context):
        """Valida que start_date <= end_date"""
        if self.start_date > self.end_date:
            raise ValueError('La fecha de inicio no puede ser posterior a la fecha de fin')


class ChangePasswordRequest(BaseModel):
    """Modelo para cambio de contraseña"""

    model_config = ConfigDict(str_strip_whitespace=True)

    current_password: str = Field(
        ...,
        min_length=1,
        description="Contraseña actual"
    )

    new_password: str = Field(
        ...,
        min_length=8,
        max_length=128,
        description="Nueva contraseña"
    )

    @field_validator('new_password')
    @classmethod
    def validate_new_password(cls, v):
        """Valida la fortaleza de la nueva contraseña"""
        if not re.search(r'[A-Z]', v):
            raise ValueError('La contraseña debe contener al menos una mayúscula')
        if not re.search(r'[a-z]', v):
            raise ValueError('La contraseña debe contener al menos una minúscula')
        if not re.search(r'\d', v):
            raise ValueError('La contraseña debe contener al menos un número')
        return v
