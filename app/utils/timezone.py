"""
Utilidades de zona horaria - Colombia (America/Bogota)
"""
from datetime import datetime
import pytz
from dateutil import parser
import logging

logger = logging.getLogger(__name__)

# Zona horaria de Colombia
COLOMBIA_TZ = pytz.timezone('America/Bogota')


def get_colombia_now():
    """
    Obtiene la fecha y hora actual de Colombia

    Returns:
        datetime: Objeto datetime en zona horaria de Colombia
    """
    return datetime.now(COLOMBIA_TZ)


def get_colombia_today_string():
    """
    Obtiene la fecha actual de Colombia en formato YYYY-MM-DD

    Returns:
        str: Fecha en formato YYYY-MM-DD
    """
    return get_colombia_now().strftime('%Y-%m-%d')


def parse_colombia_date(date_string):
    """
    Convierte un string de fecha a datetime en zona horaria de Colombia

    Args:
        date_string (str): Fecha en formato YYYY-MM-DD o ISO 8601

    Returns:
        datetime: Objeto datetime en zona horaria de Colombia
    """
    try:
        # Intentar parsear como ISO 8601 primero
        dt = parser.isoparse(date_string)
        if dt.tzinfo is None:
            # Sin offset explícito (ej. "2026-09-08" o "2026-09-08T00:00:00"):
            # se asume que YA representa hora de Colombia, nunca la hora
            # local del SERVIDOR. datetime.astimezone() sobre un datetime
            # naive asume la zona horaria del sistema operativo - en Render
            # (contenedores Linux, sin TZ configurada) eso es UTC, así que
            # convertir de "UTC" a Colombia (-5h) recorría la fecha un día
            # hacia atrás para CUALQUIER cierre de caja (bug real encontrado
            # en producción el 2026-09-09: un cierre para "2026-09-08" se
            # guardaba con closing_date=2026-09-07). Bug presente desde que
            # se creó esta función (commit 4461655, 2025-11-16).
            return COLOMBIA_TZ.localize(dt)
        # Si el string SÍ trae un offset explícito (ej. "...T10:00:00-05:00"),
        # ahí sí corresponde convertir desde esa zona conocida a Colombia.
        return dt.astimezone(COLOMBIA_TZ)
    except Exception:
        # Si falla, intentar como formato simple YYYY-MM-DD
        dt = datetime.strptime(date_string, '%Y-%m-%d')
        # Localizar a zona horaria de Colombia
        return COLOMBIA_TZ.localize(dt)


def validate_date_is_colombia(date_string, timezone_string):
    """
    Valida que la fecha recibida esté en zona horaria de Colombia

    Args:
        date_string (str): Fecha recibida
        timezone_string (str): Zona horaria declarada

    Returns:
        bool: True si es válida, False si no
    """
    return timezone_string == 'America/Bogota'


def format_colombia_datetime(dt=None):
    """
    Formatea un datetime en formato legible de Colombia

    Args:
        dt (datetime, optional): Datetime a formatear. Si es None, usa la hora actual

    Returns:
        str: Fecha formateada (ej: "16/11/2025 02:30:45 PM")
    """
    if dt is None:
        dt = get_colombia_now()
    return dt.strftime('%d/%m/%Y %I:%M:%S %p')


def get_colombia_timestamp():
    """
    Obtiene timestamp ISO 8601 con zona horaria de Colombia

    Returns:
        str: Timestamp en formato ISO 8601
    """
    return get_colombia_now().isoformat()


# Funciones de compatibilidad con el código anterior
def get_current_datetime(tz_name: str = "America/Bogota"):
    """
    Obtiene el datetime actual en la zona horaria especificada
    (Función de compatibilidad con código existente)

    Args:
        tz_name: Nombre de la zona horaria (ej: "America/Bogota")

    Returns:
        tuple: (datetime, timezone_used_string)

    Ejemplos:
        >>> dt, tz = get_current_datetime()
        >>> print(f"Hora actual: {dt}, Zona: {tz}")
    """
    if tz_name != "America/Bogota":
        logger.warning(f"Se solicitó zona horaria '{tz_name}' pero solo se soporta 'America/Bogota'")

    now = get_colombia_now()
    return now, "America/Bogota"


def format_datetime_info(dt: datetime):
    """
    Formatea información de un datetime

    Args:
        dt: Datetime a formatear

    Returns:
        dict: Diccionario con iso, date, time
    """
    return {
        "iso": dt.isoformat(),
        "date": dt.date().isoformat(),
        "time": dt.strftime("%H:%M:%S")
    }
