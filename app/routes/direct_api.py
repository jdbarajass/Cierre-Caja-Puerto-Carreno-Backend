"""
Rutas para APIs directas de Alegra
Endpoints que usan las APIs no documentadas pero más completas
Solo accesibles para usuarios con rol 'admin'
"""
from flask import Blueprint, request, jsonify, current_app
from datetime import datetime
import logging

from app.middlewares.auth import token_required, role_required
from app.services.alegra_direct_client import AlegraDirectClient
from app.config import Config
from app.exceptions import AlegraConnectionError
from app.utils.timezone import get_colombia_timestamp

logger = logging.getLogger(__name__)

bp = Blueprint('direct_api', __name__)

# Inicializar cliente de API directa
direct_client = AlegraDirectClient(
    Config.ALEGRA_USER,
    Config.ALEGRA_PASS,
    Config.ALEGRA_API_BASE_URL,
    Config.ALEGRA_TIMEOUT
)



@bp.route('/api/direct/inventory/value-report', methods=['GET', 'OPTIONS'])
@token_required
@role_required('admin')
def get_inventory_value_report():
    """
    Obtiene el reporte de valor de inventario desde la API directa de Alegra

    IMPORTANTE: Filtra automáticamente items con nombres que empiezan con asteriscos (*)
    y items deshabilitados, ya que son productos obsoletos que no deben aparecer.

    Query Parameters:
        - toDate (str, optional): Fecha hasta la cual generar el reporte (YYYY-MM-DD). Default: hoy
        - limit (int, optional): Número de items por página (default: 3000, max: 3000)
        - page (int, optional): Número de página (default: 1)
        - query (str, optional): Filtro de búsqueda

    Returns:
        JSON con reporte de inventario filtrado y metadata de paginación
        La metadata incluye:
            - total_received: Items recibidos de Alegra
            - total_filtered_asterisk: Items filtrados (asteriscos)
            - total_filtered_disabled: Items filtrados (deshabilitados)
            - total_filtered: Total items filtrados
            - total_returned: Items enviados al frontend

    Example:
        GET /api/direct/inventory/value-report?toDate=2025-12-10&limit=3000&page=1
    """
    # Manejar preflight CORS
    if request.method == 'OPTIONS':
        return '', 204

    try:
        # Obtener parámetros
        to_date = request.args.get('toDate')
        if not to_date:
            to_date = datetime.now().strftime('%Y-%m-%d')
        
        max_items = int(request.args.get('limit', 3000))
        page_size = int(request.args.get('pageSize', 200))
        query = request.args.get('query', '')

        # Validar límites razonables
        if max_items > 3000:
            return jsonify({
                'success': False,
                'error': 'El límite máximo es 3000 items'
            }), 400

        if page_size > 300:
            return jsonify({
                'success': False,
                'error': 'El tamaño de página máximo es 300 items'
            }), 400

        logger.info(f"Obteniendo inventory value report paginado - toDate: {to_date}, max_items: {max_items}, page_size: {page_size}")

        # Obtener datos usando paginación automática
        result = direct_client.get_inventory_value_report_paginated(
            to_date=to_date,
            max_items=max_items,
            page_size=page_size,
            query=query
        )

        if not result.get('success'):
            return jsonify({
                'success': False,
                'error': 'Error obteniendo datos de Alegra',
                'details': result.get('error')
            }), 502

        response = {
            'success': True,
            'server_timestamp': get_colombia_timestamp(),
            'data': result.get('data', []),
            'metadata': result.get('metadata', {})
        }

        return jsonify(response), 200

    except ValueError as e:
        return jsonify({
            'success': False,
            'error': f'Parámetro inválido: {str(e)}'
        }), 400
    except Exception as e:
        logger.exception("Error inesperado en inventory value report")
        return jsonify({
            'success': False,
            'error': 'Error interno del servidor',
            'details': str(e)
        }), 500


@bp.route('/api/direct/sales/totals', methods=['GET', 'OPTIONS'])
@token_required
@role_required('admin')
def get_sales_totals():
    """
    Obtiene totales de ventas agrupados por día o mes desde la API directa
    
    Query Parameters:
        - from (str, required): Fecha de inicio (YYYY-MM-DD)
        - to (str, required): Fecha de fin (YYYY-MM-DD)
        - groupBy (str, optional): Agrupación ('day' o 'month'). Default: 'day'
        - limit (int, optional): Número de registros (default: 10)
        - start (int, optional): Offset para paginación (default: 0)
    
    Returns:
        JSON con totales de ventas agrupados
    
    Example:
        GET /api/direct/sales/totals?from=2025-12-01&to=2025-12-10&groupBy=day
    """
    # Manejar preflight CORS
    if request.method == 'OPTIONS':
        return '', 204

    try:
        # Obtener parámetros
        from_date = request.args.get('from')
        to_date = request.args.get('to')
        
        if not from_date or not to_date:
            return jsonify({
                'success': False,
                'error': 'Los parámetros "from" y "to" son requeridos'
            }), 400

        # Validar formato de fechas
        try:
            datetime.strptime(from_date, '%Y-%m-%d')
            datetime.strptime(to_date, '%Y-%m-%d')
        except ValueError:
            return jsonify({
                'success': False,
                'error': 'Formato de fecha inválido. Use YYYY-MM-DD'
            }), 400

        group_by = request.args.get('groupBy', 'day')
        limit = int(request.args.get('limit', 10))
        start = int(request.args.get('start', 0))

        # Validar group_by
        if group_by not in ['day', 'month']:
            return jsonify({
                'success': False,
                'error': 'groupBy debe ser "day" o "month"'
            }), 400

        logger.info(f"Obteniendo sales totals - from: {from_date}, to: {to_date}, groupBy: {group_by}")

        # Obtener datos de la API directa
        result = direct_client.get_sales_totals(
            from_date=from_date,
            to_date=to_date,
            group_by=group_by,
            limit=limit,
            start=start
        )

        if not result.get('success'):
            return jsonify({
                'success': False,
                'error': 'Error obteniendo datos de Alegra',
                'details': result.get('error')
            }), 502

        response = {
            'success': True,
            'server_timestamp': get_colombia_timestamp(),
            'data': result.get('data', []),
            'metadata': result.get('metadata', {})
        }

        return jsonify(response), 200

    except ValueError as e:
        return jsonify({
            'success': False,
            'error': f'Parámetro inválido: {str(e)}'
        }), 400
    except Exception as e:
        logger.exception("Error inesperado en sales totals")
        return jsonify({
            'success': False,
            'error': 'Error interno del servidor',
            'details': str(e)
        }), 500


@bp.route('/api/direct/sales/documents', methods=['GET', 'OPTIONS'])
@token_required
@role_required('admin')
def get_sales_documents():
    """
    Obtiene TODOS los documentos de ventas para un rango de fechas con paginación automática

    Este endpoint ahora obtiene TODAS las facturas del rango de fechas especificado,
    haciendo múltiples llamadas a la API de Alegra si es necesario (30 en 30).

    Query Parameters:
        - from (str, required): Fecha de inicio (YYYY-MM-DD)
        - to (str, required): Fecha de fin (YYYY-MM-DD)

    Returns:
        JSON con TODOS los documentos de ventas del rango de fechas

    Example:
        GET /api/direct/sales/documents?from=2025-12-01&to=2025-12-23
    """
    # Manejar preflight CORS
    if request.method == 'OPTIONS':
        return '', 204

    try:
        # Obtener parámetros
        from_date = request.args.get('from')
        to_date = request.args.get('to')

        if not from_date or not to_date:
            return jsonify({
                'success': False,
                'error': 'Los parámetros "from" y "to" son requeridos'
            }), 400

        # Validar formato de fechas
        try:
            datetime.strptime(from_date, '%Y-%m-%d')
            datetime.strptime(to_date, '%Y-%m-%d')
        except ValueError:
            return jsonify({
                'success': False,
                'error': 'Formato de fecha inválido. Use YYYY-MM-DD'
            }), 400

        logger.info(f"Obteniendo TODAS las facturas - from: {from_date}, to: {to_date}")

        # Usar el nuevo método que obtiene TODAS las facturas con paginación automática
        result = direct_client.get_all_invoices_for_date_range(
            from_date=from_date,
            to_date=to_date
        )

        if not result.get('success'):
            return jsonify({
                'success': False,
                'error': 'Error obteniendo datos de Alegra',
                'details': result.get('error')
            }), 502

        response = {
            'success': True,
            'server_timestamp': get_colombia_timestamp(),
            'data': result.get('data', []),
            'metadata': result.get('metadata', {})
        }

        logger.info(f"Retornando {len(result.get('data', []))} facturas en total")

        return jsonify(response), 200

    except ValueError as e:
        return jsonify({
            'success': False,
            'error': f'Parámetro inválido: {str(e)}'
        }), 400
    except Exception as e:
        logger.exception("Error inesperado en sales documents")
        return jsonify({
            'success': False,
            'error': 'Error interno del servidor',
            'details': str(e)
        }), 500


@bp.route('/api/sales/quick-summary', methods=['GET', 'OPTIONS'])
@token_required
def get_quick_sales_summary():
    """
    Obtiene un resumen rápido del total de ventas para un rango de fechas
    Optimizado para ser usado en el header del dashboard

    OPTIMIZADO: Usa el endpoint /invoices/sales-totals de Alegra que retorna
    totales agregados sin detalles de facturas (2-4x más rápido)

    Query Parameters:
        - from (str, required): Fecha de inicio (YYYY-MM-DD)
        - to (str, required): Fecha de fin (YYYY-MM-DD)

    Returns:
        JSON con total de ventas

    Example:
        GET /api/sales/quick-summary?from=2025-12-13&to=2025-12-13

    Response:
        {
            "success": true,
            "total_sales": 1234567,
            "total_sales_formatted": "$ 1.234.567",
            "days_count": 1,
            "date_range": {
                "from": "2025-12-13",
                "to": "2025-12-13"
            }
        }
    """
    # Manejar preflight CORS
    if request.method == 'OPTIONS':
        return '', 204

    try:
        # Obtener parámetros
        from_date = request.args.get('from')
        to_date = request.args.get('to')

        if not from_date or not to_date:
            return jsonify({
                'success': False,
                'error': 'Los parámetros "from" y "to" son requeridos'
            }), 400

        # Validar formato de fechas
        try:
            datetime.strptime(from_date, '%Y-%m-%d')
            datetime.strptime(to_date, '%Y-%m-%d')
        except ValueError:
            return jsonify({
                'success': False,
                'error': 'Formato de fecha inválido. Use YYYY-MM-DD'
            }), 400

        logger.info(f"Quick summary - from: {from_date}, to: {to_date}")

        # Obtener totales de ventas usando el endpoint rápido de Alegra
        # Este endpoint retorna totales agregados sin detalles de facturas (mucho más rápido)
        result = direct_client.get_sales_totals(
            from_date=from_date,
            to_date=to_date,
            group_by='day',  # Agrupa por día
            limit=100,       # Suficiente para 100 días
            start=0
        )

        if not result.get('success'):
            return jsonify({
                'success': False,
                'error': 'Error obteniendo datos de Alegra',
                'details': result.get('error')
            }), 502

        # Calcular el total de ventas sumando los totales de cada día
        # La respuesta tiene estructura: [{'date': '2025-12-10', 'total': 3330350, ...}, ...]
        sales_data = result.get('data', [])
        total_sales = sum(float(day.get('total', 0)) for day in sales_data)

        # Formatear el total
        from app.utils.formatters import format_cop
        total_sales_formatted = format_cop(total_sales)

        logger.info(f"Quick summary calculado: {total_sales_formatted} ({len(sales_data)} días procesados)")

        return jsonify({
            'success': True,
            'total_sales': total_sales,
            'total_sales_formatted': total_sales_formatted,
            'days_count': len(sales_data),
            'date_range': {
                'from': from_date,
                'to': to_date
            }
        }), 200

    except ValueError as e:
        logger.error(f"Error de validación en quick summary: {str(e)}")
        return jsonify({
            'success': False,
            'error': f'Parámetro inválido: {str(e)}'
        }), 400
    except Exception as e:
        logger.exception("Error inesperado en quick summary")
        return jsonify({
            'success': False,
            'error': 'Error interno del servidor',
            'details': str(e)
        }), 500


@bp.route('/api/inventory/quick-total', methods=['GET', 'OPTIONS'])
@token_required
def get_quick_inventory_total():
    """
    Obtiene el total del valor del inventario para una fecha específica
    Optimizado para ser usado en el dashboard

    OPTIMIZADO: Usa el endpoint /reports/inventory-value-totals de Alegra
    que retorna solo el total agregado (extremadamente rápido)

    Query Parameters:
        - to_date (str, optional): Fecha hasta la cual calcular (YYYY-MM-DD).
                                   Si no se proporciona, usa la fecha actual

    Returns:
        JSON con total del inventario

    Example:
        GET /api/inventory/quick-total?to_date=2026-01-21

    Response:
        {
            "success": true,
            "total_value": 123456789,
            "total_value_formatted": "$ 123.456.789",
            "to_date": "2026-01-21"
        }

    Nota:
        Alegra solo retorna el valor total del inventario, no la cantidad de unidades.
    """
    # Manejar preflight CORS
    if request.method == 'OPTIONS':
        return '', 204

    try:
        # Obtener parámetro (opcional, por defecto fecha actual)
        from app.utils.timezone import get_colombia_now
        to_date = request.args.get('to_date')

        if not to_date:
            colombia_now = get_colombia_now()
            to_date = colombia_now.strftime('%Y-%m-%d')

        # Validar formato de fecha
        try:
            datetime.strptime(to_date, '%Y-%m-%d')
        except ValueError:
            return jsonify({
                'success': False,
                'error': 'Formato de fecha inválido. Use YYYY-MM-DD'
            }), 400

        logger.info(f"Quick inventory total - to_date: {to_date}")

        # Obtener total del inventario usando el endpoint rápido de Alegra
        result = direct_client.get_inventory_value_totals(
            to_date=to_date,
            query="",
            force_inventory_parallel=False
        )

        if not result.get('success'):
            return jsonify({
                'success': False,
                'error': 'Error obteniendo datos de Alegra',
                'details': result.get('error')
            }), 502

        # Extraer datos de la respuesta
        data = result.get('data', {})

        # Alegra retorna {'total': 145967454.87072}
        # NO retorna cantidad de unidades en este endpoint
        total_value = float(data.get('total', 0))

        # Formatear el total
        from app.utils.formatters import format_cop
        total_value_formatted = format_cop(total_value)

        logger.info(f"✅ Quick inventory total calculado: {total_value_formatted}")

        return jsonify({
            'success': True,
            'total_value': total_value,
            'total_value_formatted': total_value_formatted,
            'to_date': to_date
        }), 200

    except ValueError as e:
        logger.error(f"Error de validación en quick inventory total: {str(e)}")
        return jsonify({
            'success': False,
            'error': f'Parámetro inválido: {str(e)}'
        }), 400
    except Exception as e:
        logger.exception("Error inesperado en quick inventory total")
        return jsonify({
            'success': False,
            'error': 'Error interno del servidor',
            'details': str(e)
        }), 500


@bp.route('/api/bills/open-totals', methods=['GET', 'OPTIONS'])
@token_required
def get_bills_open_totals():
    """
    Obtiene el total de cuentas por pagar pendientes para un rango de fechas
    Optimizado para ser usado en el dashboard

    OPTIMIZADO: Usa el endpoint /reports/bills-open-totals de Alegra
    que retorna solo totales agregados (extremadamente rápido)

    Query Parameters:
        - from_date (str, optional): Fecha de inicio (YYYY-MM-DD).
                                     Si no se proporciona, usa el primer día del mes actual
        - to_date (str, optional): Fecha de fin (YYYY-MM-DD).
                                   Si no se proporciona, usa el último día del mes actual

    Returns:
        JSON con total de cuentas por pagar

    Example:
        GET /api/bills/open-totals?from_date=2026-01-01&to_date=2026-01-31

    Response:
        {
            "success": true,
            "missing_amount": 13699200,
            "missing_amount_formatted": "$ 13.699.200",
            "total_documents": 4,
            "from_date": "2026-01-01",
            "to_date": "2026-01-31"
        }
    """
    # Manejar preflight CORS
    if request.method == 'OPTIONS':
        return '', 204

    try:
        # Obtener parámetros (opcional, por defecto mes actual)
        from app.utils.timezone import get_colombia_now
        colombia_now = get_colombia_now()

        from_date = request.args.get('from_date')
        to_date = request.args.get('to_date')

        if not from_date:
            # Primer día del mes actual
            year = colombia_now.year
            month = colombia_now.month
            from_date = f"{year}-{month:02d}-01"

        if not to_date:
            # Último día del mes actual
            import calendar
            year = colombia_now.year
            month = colombia_now.month
            last_day = calendar.monthrange(year, month)[1]
            to_date = f"{year}-{month:02d}-{last_day:02d}"

        # Validar formato de fechas
        try:
            datetime.strptime(from_date, '%Y-%m-%d')
            datetime.strptime(to_date, '%Y-%m-%d')
        except ValueError:
            return jsonify({
                'success': False,
                'error': 'Formato de fecha inválido. Use YYYY-MM-DD'
            }), 400

        logger.info(f"Bills open totals - from: {from_date}, to: {to_date}")

        # Obtener total de cuentas por pagar usando el endpoint rápido de Alegra
        result = direct_client.get_bills_open_totals(
            from_date=from_date,
            to_date=to_date
        )

        if not result.get('success'):
            return jsonify({
                'success': False,
                'error': 'Error obteniendo datos de Alegra',
                'details': result.get('error')
            }), 502

        # Extraer datos de la respuesta
        # Alegra retorna {'missingAmount': 13699200, 'totalDocuments': 4}
        data = result.get('data', {})
        missing_amount = float(data.get('missingAmount', 0))
        total_documents = int(data.get('totalDocuments', 0))

        # Formatear el total
        from app.utils.formatters import format_cop
        missing_amount_formatted = format_cop(missing_amount)

        logger.info(f"✅ Bills open totals calculado: {missing_amount_formatted} ({total_documents} documentos)")

        return jsonify({
            'success': True,
            'missing_amount': missing_amount,
            'missing_amount_formatted': missing_amount_formatted,
            'total_documents': total_documents,
            'from_date': from_date,
            'to_date': to_date
        }), 200

    except ValueError as e:
        logger.error(f"Error de validación en bills open totals: {str(e)}")
        return jsonify({
            'success': False,
            'error': f'Parámetro inválido: {str(e)}'
        }), 400
    except Exception as e:
        logger.exception("Error inesperado en bills open totals")
        return jsonify({
            'success': False,
            'error': 'Error interno del servidor',
            'details': str(e)
        }), 500
