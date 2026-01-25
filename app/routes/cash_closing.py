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
    procesar_desfases,
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
from app.middlewares.auth import token_required, get_current_user, role_required_any

bp = Blueprint('cash_closing', __name__)


@bp.route('/sum_payments', methods=['POST', 'OPTIONS'])
@token_required
@role_required_any(['admin', 'sales'])
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

    # Procesar desfases (nueva funcionalidad)
    desfases_list = data.get("desfases", [])
    desfases_procesados = procesar_desfases(desfases_list)

    # Calcular totales de métodos de pago (nueva lógica del backend)
    # Pasar excedentes_procesados para mostrar totales con excedentes
    metodos_pago = data.get("metodos_pago", {})
    metodos_pago_calculados = calcular_totales_metodos_pago(metodos_pago, excedentes_procesados)

    # Procesar cierre de caja (usando excedente_efectivo para cálculos de venta)
    # IMPORTANTE: Se usa excedente_efectivo porque la venta en efectivo de Alegra
    # debe compararse solo con el excedente en efectivo, no con otros excedentes
    # Usar base_objetivo personalizado si se proporciona, sino usar el valor por defecto de Config
    base_objetivo_a_usar = cash_request.base_objetivo if cash_request.base_objetivo else Config.BASE_OBJETIVO
    current_app.logger.info(f"Base objetivo a usar: {base_objetivo_a_usar}")

    calculator = CashCalculator(base_objetivo=base_objetivo_a_usar)
    cash_result = calculator.procesar_cierre_completo(
        conteo_monedas=conteo_monedas,
        conteo_billetes=conteo_billetes,
        excedente=excedente_efectivo,
        gastos_operativos=cash_request.gastos_operativos,
        prestamos=cash_request.prestamos,
        desfases=desfases_procesados['total_desfase']
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

    # Validar el cierre comparando Alegra con lo registrado (incluye validación de efectivo y desfases)
    validacion_cierre = validar_cierre(
        alegra_result,
        metodos_pago_calculados,
        cash_result,
        excedentes_procesados,
        cash_request.gastos_operativos,
        cash_request.prestamos,
        desfases_procesados
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
        username=Config.ALEGRA_USER,
        desfases_procesados=desfases_procesados
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
@role_required_any(['admin', 'sales'])
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


@bp.route('/sales_comparison_yoy', methods=['GET', 'OPTIONS'])
@token_required
@role_required_any(['admin', 'sales'])
def get_sales_comparison_yoy():
    """
    Obtiene comparación de ventas año sobre año (Year over Year)
    Compara ventas del día actual y mes actual con el mismo período del año anterior
    ---
    tags:
      - Ventas
    parameters:
      - in: query
        name: date
        type: string
        required: false
        description: Fecha para comparar (YYYY-MM-DD). Si no se proporciona, usa la fecha actual
    responses:
      200:
        description: Comparación de ventas año sobre año
        schema:
          type: object
          properties:
            success:
              type: boolean
            daily_comparison:
              type: object
              description: Comparación de ventas del día
            monthly_comparison:
              type: object
              description: Comparación de ventas del mes
      500:
        description: Error al consultar Alegra
    """
    # Manejar preflight OPTIONS request
    if request.method == "OPTIONS":
        return "", 204

    try:
        # Obtener fecha desde query params o usar fecha actual
        colombia_now = get_colombia_now()
        date_str = request.args.get('date')
        if not date_str:
            date_str = colombia_now.strftime('%Y-%m-%d')

        current_app.logger.info(f"Consultando comparación año sobre año para: {date_str}")

        # Crear cliente de Alegra
        alegra_client = AlegraClient(
            username=Config.ALEGRA_USER,
            password=Config.ALEGRA_PASS,
            base_url=Config.ALEGRA_API_BASE_URL,
            timeout=Config.ALEGRA_TIMEOUT
        )

        # Obtener comparación diaria
        daily_comparison = alegra_client.get_sales_comparison_year_over_year(date_str)

        # Calcular comparación mensual
        from datetime import datetime
        current_dt = datetime.strptime(date_str, '%Y-%m-%d')

        # Mes actual
        start_current_month = current_dt.replace(day=1).strftime('%Y-%m-%d')
        end_current_month = date_str

        # Mismo mes del año anterior
        previous_year_dt = current_dt.replace(year=current_dt.year - 1)
        start_previous_month = previous_year_dt.replace(day=1).strftime('%Y-%m-%d')
        end_previous_month = previous_year_dt.strftime('%Y-%m-%d')

        # Obtener ventas del mes actual
        current_month_sales = alegra_client.get_monthly_sales_summary(
            start_current_month,
            end_current_month
        )

        # Obtener ventas del mismo mes del año anterior
        previous_month_sales = alegra_client.get_monthly_sales_summary(
            start_previous_month,
            end_previous_month
        )

        # Calcular diferencia y porcentaje mensual
        current_month_total = current_month_sales.get('total_vendido', {}).get('total', 0)
        previous_month_total = previous_month_sales.get('total_vendido', {}).get('total', 0)
        month_difference = current_month_total - previous_month_total

        if previous_month_total > 0:
            month_percentage_change = ((current_month_total - previous_month_total) / previous_month_total) * 100
        else:
            month_percentage_change = 100.0 if current_month_total > 0 else 0.0

        from app.utils.formatting import format_cop

        monthly_comparison = {
            'current': {
                'period': f"{start_current_month} a {end_current_month}",
                'total': current_month_total,
                'formatted': format_cop(current_month_total),
                'invoices_count': current_month_sales.get('cantidad_facturas', 0)
            },
            'previous_year': {
                'period': f"{start_previous_month} a {end_previous_month}",
                'total': previous_month_total,
                'formatted': format_cop(previous_month_total),
                'invoices_count': previous_month_sales.get('cantidad_facturas', 0)
            },
            'comparison': {
                'difference': month_difference,
                'difference_formatted': format_cop(abs(month_difference)),
                'percentage_change': round(month_percentage_change, 2),
                'is_growth': month_difference >= 0,
                'growth_label': 'crecimiento' if month_difference >= 0 else 'decrecimiento'
            }
        }

        # ========================================
        # CALCULAR METAS (Ventas año anterior + 25%)
        # ========================================
        GROWTH_TARGET_PERCENTAGE = 25  # Meta de crecimiento del 25%

        # Meta Diaria: Ventas del mismo dia del año pasado + 25%
        previous_day_total = daily_comparison.get('previous_year', {}).get('total', 0)
        daily_goal = previous_day_total * (1 + GROWTH_TARGET_PERCENTAGE / 100)
        daily_goal_progress = (daily_comparison.get('current', {}).get('total', 0) / daily_goal * 100) if daily_goal > 0 else 0

        # Meta Mensual: Ventas del mismo mes del año pasado (hasta el mismo dia) + 25%
        monthly_goal = previous_month_total * (1 + GROWTH_TARGET_PERCENTAGE / 100)
        monthly_goal_progress = (current_month_total / monthly_goal * 100) if monthly_goal > 0 else 0

        goals = {
            'growth_target_percentage': GROWTH_TARGET_PERCENTAGE,
            'daily': {
                'base_previous_year': previous_day_total,
                'base_previous_year_formatted': format_cop(previous_day_total),
                'goal': daily_goal,
                'goal_formatted': format_cop(daily_goal),
                'current': daily_comparison.get('current', {}).get('total', 0),
                'current_formatted': daily_comparison.get('current', {}).get('formatted', '$0'),
                'progress_percentage': round(daily_goal_progress, 1),
                'remaining': max(0, daily_goal - daily_comparison.get('current', {}).get('total', 0)),
                'remaining_formatted': format_cop(max(0, daily_goal - daily_comparison.get('current', {}).get('total', 0))),
                'is_achieved': daily_comparison.get('current', {}).get('total', 0) >= daily_goal
            },
            'monthly': {
                'base_previous_year': previous_month_total,
                'base_previous_year_formatted': format_cop(previous_month_total),
                'goal': monthly_goal,
                'goal_formatted': format_cop(monthly_goal),
                'current': current_month_total,
                'current_formatted': format_cop(current_month_total),
                'progress_percentage': round(monthly_goal_progress, 1),
                'remaining': max(0, monthly_goal - current_month_total),
                'remaining_formatted': format_cop(max(0, monthly_goal - current_month_total)),
                'is_achieved': current_month_total >= monthly_goal
            }
        }

        response = {
            "success": True,
            "server_timestamp": get_colombia_timestamp(),
            "timezone": "America/Bogota",
            "daily_comparison": daily_comparison,
            "monthly_comparison": monthly_comparison,
            "goals": goals
        }

        current_app.logger.info("=" * 80)
        current_app.logger.info("COMPARACION ANO SOBRE ANO Y METAS")
        current_app.logger.info("-" * 80)
        current_app.logger.info(f"DIA ACTUAL ({daily_comparison['current']['date']}): {daily_comparison['current']['formatted']}")
        current_app.logger.info(f"MISMO DIA ANO ANTERIOR ({daily_comparison['previous_year']['date']}): {daily_comparison['previous_year']['formatted']}")
        current_app.logger.info(f"CAMBIO DIARIO: {daily_comparison['comparison']['percentage_change']}% ({daily_comparison['comparison']['growth_label']})")
        current_app.logger.info("-" * 80)
        current_app.logger.info(f"MES ACTUAL: {monthly_comparison['current']['formatted']}")
        current_app.logger.info(f"MISMO MES ANO ANTERIOR: {monthly_comparison['previous_year']['formatted']}")
        current_app.logger.info(f"CAMBIO MENSUAL: {monthly_comparison['comparison']['percentage_change']}% ({monthly_comparison['comparison']['growth_label']})")
        current_app.logger.info("-" * 80)
        current_app.logger.info("METAS (+25% sobre ano anterior)")
        current_app.logger.info(f"META DIARIA: {goals['daily']['goal_formatted']} | Progreso: {goals['daily']['progress_percentage']}%")
        current_app.logger.info(f"META MENSUAL: {goals['monthly']['goal_formatted']} | Progreso: {goals['monthly']['progress_percentage']}%")
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


@bp.route('/preconsulta', methods=['GET', 'OPTIONS'])
@token_required
@role_required_any(['admin', 'sales'])
def preconsulta_alegra():
    """
    Realiza una preconsulta a Alegra para obtener resumen de ventas del día
    antes de hacer el cierre de caja.

    Query Parameters:
        - date (str, required): Fecha en formato YYYY-MM-DD

    Returns:
        JSON con:
        - factura_inicial: Número de la primera factura del día
        - factura_final: Número de la última factura del día
        - totales por método de pago (efectivo, tarjeta crédito, débito, transferencia)
        - total de ventas
    """
    # Manejar preflight CORS
    if request.method == 'OPTIONS':
        return '', 204

    try:
        # Obtener fecha del parámetro
        date_str = request.args.get('date')

        if not date_str:
            return jsonify({
                'success': False,
                'error': 'El parámetro "date" es requerido'
            }), 400

        # Validar formato de fecha
        try:
            from datetime import datetime
            datetime.strptime(date_str, '%Y-%m-%d')
        except ValueError:
            return jsonify({
                'success': False,
                'error': 'Formato de fecha inválido. Use YYYY-MM-DD'
            }), 400

        # Validar que no sea fecha futura
        colombia_now = get_colombia_now()
        request_date = parse_colombia_date(date_str)
        if request_date.date() > colombia_now.date():
            return jsonify({
                'success': False,
                'error': 'No se puede consultar una fecha futura'
            }), 400

        current_app.logger.info("=" * 80)
        current_app.logger.info(f"PRECONSULTA ALEGRA para fecha: {date_str}")
        current_app.logger.info("=" * 80)

        # Verificar configuración
        if not Config.ALEGRA_USER or not Config.ALEGRA_PASS:
            return jsonify({
                'success': False,
                'error': 'Configuración de Alegra incompleta'
            }), 500

        # Crear cliente de Alegra y obtener facturas
        client = AlegraClient(
            Config.ALEGRA_USER,
            Config.ALEGRA_PASS,
            Config.ALEGRA_API_BASE_URL,
            Config.ALEGRA_TIMEOUT
        )

        # Obtener todas las facturas del día
        invoices = client.get_invoices_by_date(date_str)

        if not invoices:
            return jsonify({
                'success': True,
                'message': 'No hay facturas para esta fecha',
                'date': date_str,
                'factura_inicial': None,
                'factura_final': None,
                'cantidad_facturas': 0,
                'totales': {
                    'efectivo': {'total': 0, 'formatted': '$0'},
                    'tarjeta_credito': {'total': 0, 'formatted': '$0'},
                    'tarjeta_debito': {'total': 0, 'formatted': '$0'},
                    'transferencia': {'total': 0, 'formatted': '$0'}
                },
                'total_ventas': {'total': 0, 'formatted': '$0'},
                'server_timestamp': get_colombia_timestamp()
            }), 200

        # Procesar facturas para obtener totales
        process_result = client.process_invoices(invoices)
        totals = process_result['totals']
        voided_info = process_result['voided_info']

        # Filtrar facturas activas (no anuladas) para obtener números de factura
        from app.utils.formatters import filter_voided_invoices, format_cop
        import re
        filter_result = filter_voided_invoices(invoices)
        active_invoices = filter_result['active_invoices']

        # Separar facturas por tipo: electrónica (con letras) y principal (solo números)
        facturas_electronicas = []
        facturas_principales = []

        for inv in active_invoices:
            number = inv.get('numberTemplate', {}).get('fullNumber') or inv.get('number') or inv.get('id')
            if number:
                number_str = str(number)
                # Si tiene letras, es facturación electrónica
                if re.search(r'[a-zA-Z]', number_str):
                    facturas_electronicas.append(number_str)
                else:
                    # Solo números, es facturación principal
                    facturas_principales.append(number_str)

        # Ordenar facturas electrónicas
        facturas_electronicas_sorted = sorted(facturas_electronicas)
        factura_electronica_inicial = facturas_electronicas_sorted[0] if facturas_electronicas_sorted else None
        factura_electronica_final = facturas_electronicas_sorted[-1] if facturas_electronicas_sorted else None

        # Ordenar facturas principales (numéricamente)
        facturas_principales_sorted = sorted(facturas_principales, key=lambda x: int(x) if x.isdigit() else 0)
        factura_principal_inicial = facturas_principales_sorted[0] if facturas_principales_sorted else None
        factura_principal_final = facturas_principales_sorted[-1] if facturas_principales_sorted else None

        # Calcular total de ventas
        total_ventas = sum(totals.values())

        response = {
            'success': True,
            'date': date_str,
            'facturacion_electronica': {
                'factura_inicial': factura_electronica_inicial,
                'factura_final': factura_electronica_final,
                'cantidad': len(facturas_electronicas)
            },
            'facturacion_principal': {
                'factura_inicial': factura_principal_inicial,
                'factura_final': factura_principal_final,
                'cantidad': len(facturas_principales)
            },
            'cantidad_facturas': len(active_invoices),
            'facturas_anuladas': voided_info.get('voided_count', 0),
            'totales': {
                'efectivo': {
                    'total': int(totals.get('cash', 0)),
                    'formatted': format_cop(totals.get('cash', 0))
                },
                'tarjeta_credito': {
                    'total': int(totals.get('credit-card', 0)),
                    'formatted': format_cop(totals.get('credit-card', 0))
                },
                'tarjeta_debito': {
                    'total': int(totals.get('debit-card', 0)),
                    'formatted': format_cop(totals.get('debit-card', 0))
                },
                'transferencia': {
                    'total': int(totals.get('transfer', 0)),
                    'formatted': format_cop(totals.get('transfer', 0))
                }
            },
            'total_ventas': {
                'total': int(total_ventas),
                'formatted': format_cop(total_ventas)
            },
            'server_timestamp': get_colombia_timestamp(),
            'timezone': 'America/Bogota'
        }

        # Si hay facturas anuladas, incluir el detalle
        if voided_info.get('voided_count', 0) > 0:
            response['detalle_anuladas'] = {
                'cantidad': voided_info.get('voided_count', 0),
                'total_anulado': voided_info.get('total_voided_amount', 0),
                'total_anulado_formatted': voided_info.get('total_voided_amount_formatted', '$0')
            }

        current_app.logger.info(f"Preconsulta exitosa: {len(active_invoices)} facturas activas")
        current_app.logger.info(f"Facturación Electrónica: {factura_electronica_inicial} - {factura_electronica_final} ({len(facturas_electronicas)} facturas)")
        current_app.logger.info(f"Facturación Principal: {factura_principal_inicial} - {factura_principal_final} ({len(facturas_principales)} facturas)")
        current_app.logger.info(f"Total ventas: {format_cop(total_ventas)}")

        return jsonify(response), 200

    except AlegraConnectionError as e:
        current_app.logger.error(f"Error de conexión con Alegra: {str(e)}")
        return jsonify({
            'success': False,
            'error': 'Error al conectar con Alegra',
            'details': str(e),
            'server_timestamp': get_colombia_timestamp()
        }), 502

    except Exception as e:
        current_app.logger.error(f"Error inesperado en preconsulta: {str(e)}", exc_info=True)
        return jsonify({
            'success': False,
            'error': 'Error inesperado al procesar la preconsulta',
            'details': str(e),
            'server_timestamp': get_colombia_timestamp()
        }), 500
