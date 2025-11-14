"""
Utilidades de formateo
"""


def safe_int(x):
    """
    Convierte un valor a entero de forma segura

    Args:
        x: Valor a convertir

    Returns:
        int: Valor convertido a entero, 0 si falla
    """
    try:
        return int(x)
    except Exception:
        try:
            return int(float(x))
        except Exception:
            return 0


def safe_number(amount):
    """
    Convierte un valor a número (int o float) de forma segura

    Args:
        amount: Valor a convertir

    Returns:
        int|float: Valor convertido, 0 si falla
    """
    if amount is None:
        return 0

    if isinstance(amount, (int, float)):
        return amount

    try:
        s = str(amount).replace(",", "").strip()
        if "." in s:
            return float(s)
        return int(s)
    except Exception:
        try:
            return float(str(amount))
        except Exception:
            return 0


def format_cop(amount):
    """
    Formatea un número como pesos colombianos

    Args:
        amount: Cantidad a formatear

    Returns:
        str: Cadena formateada como "$X.XXX.XXX"

    Ejemplos:
        >>> format_cop(450000)
        '$450.000'
        >>> format_cop(1234567)
        '$1.234.567'
    """
    try:
        formatted = f"{int(round(amount, 0)):,}".replace(",", ".")
        return f"${formatted}"
    except Exception:
        return f"${amount}"


def normalize_payment_method(pm: str) -> str:
    """
    Normaliza métodos de pago a valores estándar

    Args:
        pm: Método de pago raw de Alegra

    Returns:
        str: Método normalizado ('credit-card', 'debit-card', 'transfer', 'cash', 'other')

    Ejemplos:
        >>> normalize_payment_method("Tarjeta de crédito")
        'credit-card'
        >>> normalize_payment_method("Efectivo")
        'cash'
    """
    if not pm:
        return "other"

    pm_low = pm.lower()

    if "credit" in pm_low or "crédito" in pm_low:
        return "credit-card"
    if "debit" in pm_low or "débito" in pm_low:
        return "debit-card"
    if "transfer" in pm_low or "transferencia" in pm_low:
        return "transfer"
    if "cash" in pm_low or "efectivo" in pm_low:
        return "cash"

    return "other"


def get_payment_method_label(method: str) -> str:
    """
    Obtiene la etiqueta en español para un método de pago

    Args:
        method: Método de pago normalizado

    Returns:
        str: Etiqueta en español
    """
    labels = {
        "credit-card": "Tarjeta crédito",
        "debit-card": "Tarjeta débito",
        "transfer": "Transferencia",
        "cash": "Efectivo",
        "other": "Otro"
    }
    return labels.get(method, method)
