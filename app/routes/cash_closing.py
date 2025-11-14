"""
Endpoint de cierre de caja
"""
from flask import Blueprint, request, jsonify, current_app
from pydantic import ValidationError as PydanticValidationError
from flasgger import swag_from

from app.config import Config
from app.models.requests import CashClosingRequest
from app.services.cash_calculator import CashCalculator
from app.services.alegra_client import AlegraClient
from app.exceptions import (
    ValidationError,
    AlegraConnectionError,
    ConfigurationError
)
from app.utils.timezone import get_current_datetime, format_datetime_info

bp = Blueprint('cash_closing', __name__)


@bp.route('/sum_payments', methods=['POST', 'OPTIONS'])
def sum_payments():
    """
    Procesa un cierre de caja con integración a Alegra
    ---
    tags:
      - Cierre de Caja
    parameters:
      - in: body
        name: body
        required: true
        schema:
          type: object
          required:
            - date
          properties:
            date:
              type: string
              format: date
              example: "2025-11-06"
              description: Fecha del cierre en formato YYYY-MM-DD
            coins:
              type: object
              description: Monedas por denominación
              example:
                "50": 0
                "100": 6
                "200": 40
                "500": 1
                "1000": 0
            bills:
              type: object
              description: Billetes por denominación
              example:
                "2000": 16
                "5000": 7
                "10000": 7
                "20000": 12
                "50000": 12
                "100000": 9
            excedente:
              type: number
              minimum: 0
              example: 13500
              description: Dinero excedente que no pertenece a ventas del día
            gastos_operativos:
              type: number
              minimum: 0
              example: 0
              description: Gastos operativos del día
            prestamos:
              type: number
              minimum: 0
              example: 0
              description: Préstamos realizados
    responses:
      200:
        description: Cierre procesado exitosamente
      400:
        description: Error de validación
      500:
        description: Error interno del servidor
      502:
        description: Error al conectar con Alegra (respuesta parcial)
    """
    # Manejar preflight OPTIONS request
    if request.method == "OPTIONS":
        return "", 204

    # Obtener timestamp de la petición
    now, tz_used = get_current_datetime(Config.TIMEZONE)
    datetime_info = format_datetime_info(now)

    current_app.logger.info("=" * 80)
    current_app.logger.info(f"Nueva petición de cierre de caja: {datetime_info['iso']}")

    # Validar configuración
    config_errors = Config.validate()
    if config_errors:
        current_app.logger.error(f"Errores de configuración: {config_errors}")
        raise ConfigurationError(
            f"Configuración incompleta: {', '.join(config_errors)}"
        )

    # Obtener y validar datos del request
    try:
        data = request.get_json(force=True)
    except Exception as e:
        current_app.logger.error(f"Error al parsear JSON: {e}")
        raise ValidationError("JSON inválido en el body del request")

    if not data:
        raise ValidationError("Debe enviar JSON en el body con los datos del cierre")

    # Validar con Pydantic
    try:
        cash_request = CashClosingRequest(**data)
    except PydanticValidationError as e:
        current_app.logger.error(f"Error de validación Pydantic: {e}")
        errors = []
        for error in e.errors():
            field = '.'.join(str(x) for x in error['loc'])
            msg = error['msg']
            errors.append(f"{field}: {msg}")
        raise ValidationError(f"Errores de validación: {'; '.join(errors)}")

    current_app.logger.info(f"Fecha solicitada: {cash_request.date}")

    # Normalizar conteos
    conteo_monedas = cash_request.get_normalized_coins(Config.DENOMINACIONES_MONEDAS)
    conteo_billetes = cash_request.get_normalized_bills(Config.DENOMINACIONES_BILLETES)

    # Procesar cierre de caja
    calculator = CashCalculator()
    cash_result = calculator.procesar_cierre_completo(
        conteo_monedas=conteo_monedas,
        conteo_billetes=conteo_billetes,
        excedente=cash_request.excedente,
        gastos_operativos=cash_request.gastos_operativos,
        prestamos=cash_request.prestamos
    )

    # Obtener datos de Alegra
    alegra_result = None
    alegra_error = None

    try:
        current_app.logger.info("Consultando datos de Alegra...")
        client = AlegraClient(
            Config.ALEGRA_USER,
            Config.ALEGRA_PASS,
            Config.ALEGRA_API_BASE_URL,
            Config.ALEGRA_TIMEOUT
        )
        alegra_result = client.get_sales_summary(str(cash_request.date))
        current_app.logger.info("✓ Datos de Alegra obtenidos exitosamente")

    except AlegraConnectionError as e:
        current_app.logger.error(f"Error al conectar con Alegra: {e.message}")
        alegra_error = {
            "error": e.message,
            "details": e.payload
        }

        # Si falla Alegra, devolver respuesta parcial con código 502
        partial_response = {
            "request_datetime": datetime_info['iso'],
            "request_date": datetime_info['date'],
            "request_time": datetime_info['time'],
            "request_tz": tz_used,
            "date_requested": str(cash_request.date),
            "username_used": Config.ALEGRA_USER,
            "cash_count": cash_result,
            "alegra": alegra_error
        }

        current_app.logger.warning("Devolviendo respuesta parcial sin datos de Alegra")
        return jsonify(partial_response), 502

    except Exception as e:
        current_app.logger.error(f"Error inesperado con Alegra: {str(e)}", exc_info=True)
        alegra_error = {
            "error": f"Error inesperado: {str(e)}"
        }

        # Respuesta parcial para errores inesperados
        partial_response = {
            "request_datetime": datetime_info['iso'],
            "request_date": datetime_info['date'],
            "request_time": datetime_info['time'],
            "request_tz": tz_used,
            "date_requested": str(cash_request.date),
            "username_used": Config.ALEGRA_USER,
            "cash_count": cash_result,
            "alegra": alegra_error
        }

        return jsonify(partial_response), 502

    # Construir respuesta completa exitosa
    response = {
        "request_datetime": datetime_info['iso'],
        "request_date": datetime_info['date'],
        "request_time": datetime_info['time'],
        "request_tz": tz_used,
        "date_requested": str(cash_request.date),
        "username_used": Config.ALEGRA_USER,
        "cash_count": cash_result,
        "alegra": alegra_result
    }

    # Log resumen del cierre
    current_app.logger.info("=" * 80)
    current_app.logger.info("RESUMEN DEL CIERRE")
    current_app.logger.info("-" * 80)
    current_app.logger.info(f"Fecha: {cash_request.date}")
    current_app.logger.info(f"Total efectivo: {cash_result['totals']['total_general_formatted']}")
    current_app.logger.info(f"Base: {cash_result['base']['total_base_formatted']}")
    current_app.logger.info(f"A consignar: {cash_result['consignar']['efectivo_para_consignar_final_formatted']}")
    current_app.logger.info(f"Excedente: {cash_result['adjustments']['excedente_formatted']}")
    current_app.logger.info(f"Gastos: {cash_result['adjustments']['gastos_operativos_formatted']}")
    current_app.logger.info(f"Préstamos: {cash_result['adjustments']['prestamos_formatted']}")
    if alegra_result:
        current_app.logger.info(f"Total venta Alegra: {alegra_result['total_sale']['formatted']}")
        for method, data in alegra_result['results'].items():
            current_app.logger.info(f"  {data['label']}: {data['formatted']}")
    current_app.logger.info("=" * 80)

    return jsonify(response), 200
