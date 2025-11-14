"""
Utilidades de zona horaria
"""
from datetime import datetime, timezone, timedelta
import logging

logger = logging.getLogger(__name__)

# Intentar importar zoneinfo (Python 3.9+)
try:
    from zoneinfo import ZoneInfo
    HAVE_ZONEINFO = True
except ImportError:
    ZoneInfo = None
    HAVE_ZONEINFO = False


def get_current_datetime(tz_name: str = "America/Bogota"):
    """
    Obtiene el datetime actual en la zona horaria especificada

    Args:
        tz_name: Nombre de la zona horaria (ej: "America/Bogota")

    Returns:
        tuple: (datetime, timezone_used_string)

    Ejemplos:
        >>> dt, tz = get_current_datetime()
        >>> print(f"Hora actual: {dt}, Zona: {tz}")
    """
    if HAVE_ZONEINFO:
        try:
            now = datetime.now(ZoneInfo(tz_name))
            return now, tz_name
        except Exception as e:
            logger.warning(f"No se pudo usar ZoneInfo para {tz_name}: {e}. Usando fallback UTC-5")
            now = datetime.now(timezone(timedelta(hours=-5)))
            return now, "UTC-05:00 (fallback)"
    else:
        logger.debug("zoneinfo no disponible. Usando fallback UTC-5")
        now = datetime.now(timezone(timedelta(hours=-5)))
        return now, "UTC-05:00 (fallback)"


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
