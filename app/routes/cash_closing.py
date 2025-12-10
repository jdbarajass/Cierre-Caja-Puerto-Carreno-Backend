"""
Endpoint de cierre de caja
"""
from flask import Blueprint, request, jsonify, current_app
from pydantic import ValidationError as PydanticValidationError
from flasgger import swag_from

from app.config import Config
from app.models.requests import CashClosingRequest
from app.services.cash_calculator import (
    CashCalculator,
    procesar_excedentes,
    calcular_totales_metodos_pago,
    validar_cierre,
    preparar_respuesta_completa
)
from app.services.alegra_client import AlegraClient
from app.exceptions import (
    ValidationError,
    AlegraConnectionError,
    ConfigurationError
)
from app.utils.timezone import (
    get_current_datetime,
    format_datetime_info,
    get_colombia_now,
    parse_colombia_date,
    validate_date_is_colombia,
    format_colombia_datetime,
    get_colombia_timestamp
)
from app.middlewares.auth import token_required, get_current_user

bp = Blueprint('cash_closing', __name__)


@bp.route('/sum_payments', methods=['POST', 'OPTIONS'])
@token_required
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

    # ========================================
    # VALIDAR ZONA HORARIA
    # ========================================
    timezone = cash_request.timezone
    utc_offset = cash_request.utc_offset

    # Validar que la zona horaria sea de Colombia
    if not validate_date_is_colombia(str(cash_request.date), timezone):
        current_app.logger.error(f"Zona horaria inválida: {timezone}")
        raise ValidationError(
            f"Zona horaria inválida. Debe ser America/Bogota, se recibió: {timezone}"
        )

    # ========================================
    # PARSEAR Y VALIDAR FECHA
    # ========================================
    date_string = str(cash_request.date)
    request_timestamp = cash_request.request_timestamp

    # Convertir la fecha a datetime de Colombia
    try:
        cierre_date = parse_colombia_date(date_string)
    except Exception as e:
        current_app.logger.error(f"Error al parsear fecha: {e}")
        raise ValidationError(f"Formato de fecha inválido: {str(e)}")

    # ========================================
    # VALIDACIONES DE NEGOCIO
    # ========================================
    colombia_now = get_colombia_now()

    # Validar que la fecha no sea futura (ya validado en Pydantic, pero doble check)
    if cierre_date.date() > colombia_now.date():
        raise ValidationError(
            f"No se puede realizar un cierre con fecha futura. "
            f"Fecha cierre: {date_string}, Fecha actual Colombia: {colombia_now.strftime('%Y-%m-%d')}"
        )

    # Calcular días de diferencia para logging
    dias_diferencia = (colombia_now.date() - cierre_date.date()).days

    current_app.logger.info(f"✓ Fecha validada: {date_string} (Colombia timezone)")
    current_app.logger.info(f"✓ Días desde el cierre: {dias_diferencia}")

    # Normalizar conteos
    conteo_monedas = cash_request.get_normalized_coins(Config.DENOMINACIONES_MONEDAS)
    conteo_billetes = cash_request.get_normalized_bills(Config.DENOMINACIONES_BILLETES)

    # Procesar excedentes (nueva lógica del backend)
    excedentes_list = data.get("excedentes", [])
    excedentes_procesados = procesar_excedentes(excedentes_list)
    total_excedente = excedentes_procesados["total_excedente"]
    excedente_efectivo = excedentes_procesados["excedente_efectivo"]

    # Calcular totales de métodos de pago (nueva lógica del backend)
    metodos_pago = data.get("metodos_pago", {})
    metodos_pago_calculados = calcular_totales_metodos_pago(metodos_pago)

    # Procesar cierre de caja (usando excedente_efectivo para cálculos de venta)
    # IMPORTANTE: Se usa excedente_efectivo porque la venta en efectivo de Alegra
    # debe compararse solo con el excedente en efectivo, no con otros excedentes
    calculator = CashCalculator()
    cash_result = calculator.procesar_cierre_completo(
        conteo_monedas=conteo_monedas,
        conteo_billetes=conteo_billetes,
        excedente=excedente_efectivo,
        gastos_operativos=cash_request.gastos_operativos,
        prestamos=cash_request.prestamos
    )

    # Agregar los totales de excedentes al cash_result para incluir en adjustments
    cash_result['adjustments']['excedente_efectivo'] = excedentes_procesados['excedente_efectivo']
    cash_result['adjustments']['excedente_datafono'] = excedentes_procesados['excedente_datafono']
    cash_result['adjustments']['excedente_nequi'] = excedentes_procesados['excedente_nequi']
    cash_result['adjustments']['excedente_daviplata'] = excedentes_procesados['excedente_daviplata']
    cash_result['adjustments']['excedente_qr'] = excedentes_procesados['excedente_qr']

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
            "success": False,
            "request_datetime": datetime_info['iso'],
            "request_date": datetime_info['date'],
            "request_time": datetime_info['time'],
            "request_tz": tz_used,
            "server_timestamp": get_colombia_timestamp(),
            "timezone": "America/Bogota",
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
            "success": False,
            "request_datetime": datetime_info['iso'],
            "request_date": datetime_info['date'],
            "request_time": datetime_info['time'],
            "request_tz": tz_used,
            "server_timestamp": get_colombia_timestamp(),
            "timezone": "America/Bogota",
            "date_requested": str(cash_request.date),
            "username_used": Config.ALEGRA_USER,
            "cash_count": cash_result,
            "alegra": alegra_error
        }

        return jsonify(partial_response), 502

    # Validar el cierre comparando Alegra con lo registrado (incluye validación de efectivo)
    validacion_cierre = validar_cierre(
        alegra_result,
        metodos_pago_calculados,
        cash_result,
        excedentes_procesados,
        cash_request.gastos_operativos
    )

    # Construir respuesta completa exitosa usando la nueva función
    response = preparar_respuesta_completa(
        datos_alegra=alegra_result,
        cash_result=cash_result,
        excedentes_procesados=excedentes_procesados,
        metodos_pago_calculados=metodos_pago_calculados,
        validacion_cierre=validacion_cierre,
        payload_original=data,
        datetime_info=datetime_info,
        tz_used=tz_used,
        username=Config.ALEGRA_USER
    )

    # Log resumen del cierre
    current_app.logger.info("=" * 80)
    current_app.logger.info("RESUMEN DEL CIERRE")
    current_app.logger.info("-" * 80)
    current_app.logger.info(f"Fecha: {cash_request.date}")
    current_app.logger.info(f"Total efectivo: {cash_result['totals']['total_general_formatted']}")
    current_app.logger.info(f"Base: {cash_result['base']['total_base_formatted']}")
    current_app.logger.info(f"Estado de base: {cash_result['base']['mensaje_base']}")
    current_app.logger.info(f"A consignar: {cash_result['consignar']['efectivo_para_consignar_final_formatted']}")
    current_app.logger.info(f"Excedente: {cash_result['adjustments']['excedente_formatted']}")
    current_app.logger.info(f"Gastos: {cash_result['adjustments']['gastos_operativos_formatted']}")
    current_app.logger.info(f"Préstamos: {cash_result['adjustments']['prestamos_formatted']}")
    if alegra_result:
        current_app.logger.info(f"Total venta Alegra: {alegra_result['total_sale']['formatted']}")
        for method, data in alegra_result['results'].items():
            current_app.logger.info(f"  {data['label']}: {data['formatted']}")
    current_app.logger.info("-" * 80)
    current_app.logger.info(f"Validación del cierre: {validacion_cierre['validation_status'].upper()}")
    current_app.logger.info(f"  {validacion_cierre['mensaje_validacion']}")

    # Validación de EFECTIVO (crítica)
    diff_efectivo = validacion_cierre['diferencias']['efectivo']
    current_app.logger.info(
        f"  Efectivo: Alegra {diff_efectivo['efectivo_alegra_formatted']} + "
        f"Excedente {diff_efectivo['excedente_efectivo_formatted']} - "
        f"Gastos {diff_efectivo['gastos_operativos_formatted']} = "
        f"{diff_efectivo['suma_efectivo_ajustada_formatted']} vs "
        f"Consignar {diff_efectivo['efectivo_para_consignar_formatted']} "
        f"({'✓ VÁLIDO' if diff_efectivo['es_valido'] else '✗ NO COINCIDE'})"
    )

    # Otras diferencias
    if validacion_cierre['diferencias']['transferencias']['es_significativa']:
        current_app.logger.info(f"  Diferencia transferencias: {validacion_cierre['diferencias']['transferencias']['diferencia_formatted']}")
    if validacion_cierre['diferencias']['datafono']['es_significativa']:
        current_app.logger.info(f"  Diferencia datafono: {validacion_cierre['diferencias']['datafono']['diferencia_formatted']}")
    current_app.logger.info("=" * 80)

    return jsonify(response), 200


@bp.route('/monthly_sales', methods=['GET', 'OPTIONS'])
@token_required
def get_monthly_sales():
    """
    Obtiene las ventas totales del mes actual desde Alegra
    ---
    tags:
      - Ventas
    parameters:
      - in: query
        name: start_date
        type: string
        required: false
        description: Fecha de inicio (YYYY-MM-DD). Si no se proporciona, usa el día 1 del mes actual
      - in: query
        name: end_date
        type: string
        required: false
        description: Fecha de fin (YYYY-MM-DD). Si no se proporciona, usa la fecha actual
    responses:
      200:
        description: Resumen de ventas del mes
        schema:
          type: object
          properties:
            success:
              type: boolean
            date_range:
              type: object
              properties:
                start:
                  type: string
                end:
                  type: string
            total_vendido:
              type: object
              properties:
                label:
                  type: string
                total:
                  type: integer
                formatted:
                  type: string
            cantidad_facturas:
              type: integer
            payment_methods:
              type: object
      500:
        description: Error al consultar Alegra
    """
    # Manejar preflight OPTIONS request
    if request.method == "OPTIONS":
        return "", 204

    try:
        # Obtener fechas desde query params o usar valores por defecto (mes actual)
        colombia_now = get_colombia_now()

        # Si no se proporciona start_date, usar el día 1 del mes actual
        start_date = request.args.get('start_date')
        if not start_date:
            start_date = colombia_now.replace(day=1).strftime('%Y-%m-%d')

        # Si no se proporciona end_date, usar la fecha actual
        end_date = request.args.get('end_date')
        if not end_date:
            end_date = colombia_now.strftime('%Y-%m-%d')

        current_app.logger.info(f"Consultando ventas mensuales desde {start_date} hasta {end_date}")

        # Crear cliente de Alegra
        alegra_client = AlegraClient(
            username=Config.ALEGRA_USER,
            password=Config.ALEGRA_PASS,
            base_url=Config.ALEGRA_API_BASE_URL,
            timeout=Config.ALEGRA_TIMEOUT
        )

        # Obtener resumen de ventas mensuales
        sales_summary = alegra_client.get_monthly_sales_summary(start_date, end_date)

        # Agregar campos de éxito y timestamp
        response = {
            "success": True,
            "server_timestamp": get_colombia_timestamp(),
            "timezone": "America/Bogota",
            **sales_summary
        }

        current_app.logger.info("=" * 80)
        current_app.logger.info("RESUMEN DE VENTAS MENSUALES")
        current_app.logger.info("-" * 80)
        current_app.logger.info(f"Periodo: {start_date} hasta {end_date}")
        current_app.logger.info(f"Total vendido: {sales_summary['total_vendido']['formatted']}")
        current_app.logger.info(f"Cantidad de facturas: {sales_summary['cantidad_facturas']}")
        current_app.logger.info("Detalle por método de pago:")
        for method, data in sales_summary['payment_methods'].items():
            current_app.logger.info(f"  {data['label']}: {data['formatted']}")
        current_app.logger.info("=" * 80)

        return jsonify(response), 200

    except AlegraConnectionError as e:
        current_app.logger.error(f"Error de conexión con Alegra: {str(e)}")
        error_response = {
            "success": False,
            "error": "Error al conectar con Alegra",
            "details": str(e),
            "server_timestamp": get_colombia_timestamp(),
            "timezone": "America/Bogota"
        }
        return jsonify(error_response), 502

    except Exception as e:
        current_app.logger.error(f"Error inesperado: {str(e)}", exc_info=True)
        error_response = {
            "success": False,
            "error": "Error inesperado al procesar la solicitud",
            "details": str(e),
            "server_timestamp": get_colombia_timestamp(),
            "timezone": "America/Bogota"
        }
        return jsonify(error_response), 500
