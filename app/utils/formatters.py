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


# Forma de pago de la factura en Alegra (paymentForm) -> método normalizado.
# OJO: "DEBIT_TRANSFER" contiene "debit" y normalize_payment_method lo leería
# como tarjeta débito; por eso este mapa va aparte y se revisa primero.
PAYMENT_FORM_METHODS = {
    'CASH': 'cash',
    'DEBIT_CARD': 'debit-card',
    'CREDIT_CARD': 'credit-card',
    'DEBIT_TRANSFER': 'transfer',
    'CREDIT_TRANSFER': 'transfer',
    'TRANSFER': 'transfer',
}


def payment_form_method(form) -> str:
    return PAYMENT_FORM_METHODS.get(str(form or '').upper(), 'other')


def ensure_invoice_payments(invoices):
    """
    Desde el 2026-11-09 Alegra devuelve /invoices SIN el detalle `payments`
    (verificado en producción: ninguna factura del 6 al 9-nov lo trae), así que
    el cierre de caja, la preconsulta y Estadísticas sumaban $0 por medio de
    pago. Cada factura sí trae `paymentForm` (CASH, DEBIT_CARD, CREDIT_CARD,
    DEBIT_TRANSFER) y `totalPaid`: si falta el detalle, se arma un pago con eso
    (`synthesized: True`). Una factura pagada con dos medios queda en el de su
    paymentForm (Alegra ya no manda la división). Si Alegra vuelve a mandar
    `payments`, se usan tal cual. Modifica y devuelve la misma lista.
    """
    for inv in invoices or []:
        if not isinstance(inv, dict) or inv.get('payments'):
            continue
        if str(inv.get('status') or '').lower() == 'void':
            continue
        paid = inv.get('totalPaid')
        if paid in (None, ''):
            paid = inv.get('total') if (inv.get('balance') in (0, '0', None)) else 0
        try:
            paid = float(paid or 0)
        except (TypeError, ValueError):
            paid = 0
        if paid <= 0 or not inv.get('paymentForm'):
            continue
        inv['payments'] = [{
            'amount': paid,
            'paymentMethod': payment_form_method(inv.get('paymentForm')),
            'date': inv.get('date'),
            'synthesized': True,
        }]
    return invoices


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


def is_invoice_void(invoice: dict) -> bool:
    """
    Detecta si una factura está anulada usando criterios múltiples y robustos

    Esta función implementa una lógica combinada y ordenada por confianza para
    detectar facturas anuladas, considerando varios campos que pueden indicar
    el estado de anulación.

    Criterios aplicados (en orden de confianza):
    1. Campo status con valores: "void", "cancelled", "annulled", "reversed"
    2. Campos de fecha/usuario de anulación: voided_at, cancelled_at, deleted_at, voided_by
    3. Relación payments con status "refunded" o "cancelled"
    4. Búsqueda de palabras clave en observations/anotation/notes
    5. Validación adicional: totalPaid == 0 y payments vacío (solo como indicador secundario)

    Args:
        invoice: Diccionario con los datos de la factura de Alegra

    Returns:
        bool: True si la factura está anulada, False si está activa

    Ejemplos:
        >>> is_invoice_void({"status": "void"})
        True
        >>> is_invoice_void({"status": "closed", "voided_at": "2025-11-27"})
        True
        >>> is_invoice_void({"status": "closed", "observations": "Factura anulada"})
        True
        >>> is_invoice_void({"status": "closed"})
        False
    """
    if not invoice:
        return False

    # 1. Verificar campo status (criterio más confiable)
    status = str(invoice.get('status', '')).lower().strip()
    if status in ['void', 'cancelled', 'annulled', 'reversed']:
        return True

    # 2. Verificar campos de fecha/usuario de anulación
    voided_fields = ['voided_at', 'cancelled_at', 'deleted_at', 'voided_by', 'cancelled_by']
    for field in voided_fields:
        if invoice.get(field):
            return True

    # 3. Verificar payments con status de reembolso/cancelación
    payments = invoice.get('payments', []) or []
    for payment in payments:
        payment_status = str(payment.get('status', '')).lower().strip()
        if payment_status in ['refunded', 'cancelled', 'void', 'reversed']:
            return True

    # 4. Buscar palabras clave en campos de texto
    text_fields = [
        invoice.get('observations', ''),
        invoice.get('anotation', ''),
        invoice.get('notes', ''),
        invoice.get('termsConditions', '')
    ]

    void_keywords = ['anulad', 'anul', 'void', 'cancel', 'revers']

    for text_field in text_fields:
        if text_field:
            text_lower = str(text_field).lower()
            for keyword in void_keywords:
                if keyword in text_lower:
                    return True

    # 5. Criterio adicional (menos confiable): totalPaid == 0 con payments vacío
    # Solo se usa como indicador si también hay otras señales débiles
    total_paid = safe_number(invoice.get('totalPaid', 0))
    total = safe_number(invoice.get('total', 0))

    if total > 0 and total_paid == 0 and not payments:
        # Esto podría ser una factura no pagada o anulada
        # Solo retornamos True si hay algún otro indicador
        # Por ahora, no lo consideramos suficiente solo
        pass

    # Si llegamos aquí, la factura está activa
    return False


def filter_voided_invoices(invoices: list) -> dict:
    """
    Filtra facturas anuladas de una lista y retorna un resumen

    Args:
        invoices: Lista de facturas de Alegra

    Returns:
        dict con:
            - active_invoices: Lista de facturas activas (no anuladas)
            - voided_invoices: Lista de facturas anuladas
            - voided_count: Cantidad de facturas anuladas
            - active_count: Cantidad de facturas activas
            - total_voided_amount: Total en pesos de facturas anuladas
            - voided_summary: Resumen detallado de facturas anuladas

    Ejemplos:
        >>> invoices = [
        ...     {"id": "1", "status": "closed", "total": 100000},
        ...     {"id": "2", "status": "void", "total": 50000}
        ... ]
        >>> result = filter_voided_invoices(invoices)
        >>> result['active_count']
        1
        >>> result['voided_count']
        1
    """
    if not invoices:
        return {
            'active_invoices': [],
            'voided_invoices': [],
            'voided_count': 0,
            'active_count': 0,
            'total_voided_amount': 0,
            # Sin esta clave, un día SIN facturas (ej. el primer día de una
            # tienda nueva) tumbaba el cierre con KeyError en process_invoices.
            'total_voided_amount_formatted': format_cop(0),
            'voided_summary': []
        }

    active_invoices = []
    voided_invoices = []
    total_voided_amount = 0

    for invoice in invoices:
        if is_invoice_void(invoice):
            voided_invoices.append(invoice)
            total_voided_amount += safe_number(invoice.get('total', 0))
        else:
            active_invoices.append(invoice)

    # Crear resumen de facturas anuladas
    voided_summary = []
    for invoice in voided_invoices:
        voided_summary.append({
            'id': invoice.get('id'),
            'number': invoice.get('numberTemplate', {}).get('fullNumber', 'N/A'),
            'date': invoice.get('date'),
            'client_name': invoice.get('client', {}).get('name', 'Desconocido'),
            'total': int(safe_number(invoice.get('total', 0))),
            'total_formatted': format_cop(safe_number(invoice.get('total', 0))),
            'status': invoice.get('status')
        })

    return {
        'active_invoices': active_invoices,
        'voided_invoices': voided_invoices,
        'voided_count': len(voided_invoices),
        'active_count': len(active_invoices),
        'total_voided_amount': int(total_voided_amount),
        'total_voided_amount_formatted': format_cop(total_voided_amount),
        'voided_summary': voided_summary
    }
