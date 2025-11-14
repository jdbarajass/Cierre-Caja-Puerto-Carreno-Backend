"""
Utilidades de validación
"""
from typing import Dict
from app.exceptions import ValidationError


def validate_denominations(denominations: Dict[int, int], valid_denoms: list, denom_type: str = "denominación"):
    """
    Valida que las denominaciones sean válidas

    Args:
        denominations: Dict de denominaciones y cantidades
        valid_denoms: Lista de denominaciones válidas
        denom_type: Tipo de denominación para mensajes de error

    Raises:
        ValidationError: Si alguna denominación es inválida
    """
    for denom in denominations.keys():
        try:
            denom_int = int(denom)
            if denom_int not in valid_denoms:
                raise ValidationError(
                    f"{denom_type} inválida: {denom}. Valores válidos: {valid_denoms}",
                    field=denom_type
                )
        except ValueError:
            raise ValidationError(
                f"{denom_type} debe ser un número entero: {denom}",
                field=denom_type
            )


def validate_positive_number(value, field_name: str):
    """
    Valida que un valor sea un número positivo o cero

    Args:
        value: Valor a validar
        field_name: Nombre del campo para mensajes de error

    Raises:
        ValidationError: Si el valor es negativo
    """
    try:
        num = float(value)
        if num < 0:
            raise ValidationError(
                f"{field_name} no puede ser negativo: {value}",
                field=field_name
            )
    except (ValueError, TypeError):
        raise ValidationError(
            f"{field_name} debe ser un número válido: {value}",
            field=field_name
        )


def validate_date_format(date_str: str):
    """
    Valida que una fecha tenga formato válido YYYY-MM-DD

    Args:
        date_str: Fecha en formato string

    Raises:
        ValidationError: Si el formato es inválido
    """
    from datetime import datetime

    try:
        datetime.strptime(date_str, '%Y-%m-%d')
    except ValueError:
        raise ValidationError(
            f"Formato de fecha inválido: {date_str}. Use YYYY-MM-DD",
            field="date"
        )
