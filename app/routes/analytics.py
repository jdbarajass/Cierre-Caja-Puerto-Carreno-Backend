"""
Endpoints de análisis avanzado de ventas
"""
from flask import Blueprint, request, jsonify
from datetime import datetime
import logging

from app.middlewares.auth import token_required, role_required
from app.services.alegra_client import AlegraClient
from app.services.sales_analytics import SalesAnalytics
from app.config import Config
from app.exceptions import AlegraConnectionError, AlegraAuthError
from app.utils.timezone import get_colombia_timestamp

logger = logging.getLogger(__name__)

bp = Blueprint('analytics', __name__)

# Inicializar cliente de Alegra
alegra_client = AlegraClient(
    Config.ALEGRA_USER,
    Config.ALEGRA_PASS,
    Config.ALEGRA_API_BASE_URL,
    Config.ALEGRA_TIMEOUT
)


def get_invoices_from_params():
    """
    Función auxiliar para obtener facturas según parámetros de query

    Returns:
        Tuple[List[Dict], str]: (facturas, rango_de_fechas)
    """
    date_param = request.args.get('date')
    start_date_param = request.args.get('start_date')
    end_date_param = request.args.get('end_date')

    # Determinar rango de fechas
    if date_param:
        # Fecha específica
        datetime.strptime(date_param, '%Y-%m-%d')  # Validar formato
        target_date = datetime.strptime(date_param, '%Y-%m-%d').date()
        date_range = date_param
        invoices = alegra_client.get_invoices_by_date(target_date)
    elif start_date_param and end_date_param:
        # Rango de fechas
        datetime.strptime(start_date_param, '%Y-%m-%d')  # Validar
        datetime.strptime(end_date_param, '%Y-%m-%d')  # Validar
        date_range = f"{start_date_param} al {end_date_param}"
        invoices = alegra_client.get_all_invoices_in_range(start_date_param, end_date_param)
    else:
        # Día actual por defecto
        target_date = datetime.now().date()
        date_range = target_date.strftime('%Y-%m-%d')
        invoices = alegra_client.get_invoices_by_date(target_date)

    return invoices, date_range


def add_voided_info_to_response(response_dict: dict, analytics: SalesAnalytics) -> dict:
    """
    Agrega información sobre facturas anuladas a la respuesta si existen

    Args:
        response_dict: Diccionario de respuesta a modificar
        analytics: Instancia de SalesAnalytics con información de facturas

    Returns:
        dict: Respuesta modificada con información de facturas anuladas
    """
    voided_info = analytics.get_voided_invoices_info()

    # Agregar resumen de facturas
    response_dict['invoices_summary'] = {
        'total_invoices_received': voided_info['total_invoices_received'],
        'active_invoices_analyzed': voided_info['active_invoices_analyzed'],
        'voided_invoices_excluded': voided_info['voided_count']
    }

    # Si hay facturas anuladas, agregar detalles
    if voided_info['voided_count'] > 0:
        response_dict['voided_invoices'] = {
            'count': voided_info['voided_count'],
            'total_amount': voided_info['total_voided_amount'],
            'total_amount_formatted': voided_info['total_voided_amount_formatted'],
            'details': voided_info['voided_summary']
        }

    return response_dict


# ============================================================
# 1. ENDPOINT: HORAS PICO DE VENTAS
# ============================================================

@bp.route('/api/analytics/peak-hours', methods=['GET'])
@token_required
@role_required('admin')
def get_peak_hours():
    """
    Obtiene análisis de horas pico de ventas

    Query Parameters:
        - date (str, optional): Fecha específica (YYYY-MM-DD)
        - start_date (str, optional): Fecha inicio (YYYY-MM-DD)
        - end_date (str, optional): Fecha fin (YYYY-MM-DD)

    Returns:
        JSON con análisis de horas pico

    Example:
        GET /api/analytics/peak-hours?date=2025-11-28
        GET /api/analytics/peak-hours?start_date=2025-11-01&end_date=2025-11-30
    """
    try:
        invoices, date_range = get_invoices_from_params()

        if not invoices:
            return jsonify({
                'success': True,
                'message': 'No se encontraron facturas para el período especificado',
                'date_range': date_range,
                'data': {
                    'summary': {
                        'total_revenue': 0,
                        'total_invoices': 0,
                        'hours_with_sales': 0
                    }
                }
            }), 200

        # Analizar horas pico
        analytics = SalesAnalytics(invoices)
        peak_hours_data = analytics.get_peak_hours_analysis()

        response = {
            'success': True,
            'date_range': date_range,
            'server_timestamp': get_colombia_timestamp(),
            'data': peak_hours_data
        }

        # Agregar información de facturas anuladas
        response = add_voided_info_to_response(response, analytics)

        return jsonify(response), 200

    except ValueError as e:
        return jsonify({
            'success': False,
            'error': f'Formato de fecha inválido: {str(e)}. Use YYYY-MM-DD'
        }), 400
    except AlegraConnectionError as e:
        logger.error(f"Error de conexión con Alegra: {e}")
        return jsonify({
            'success': False,
            'error': 'Error de conexión con Alegra',
            'details': str(e)
        }), 502
    except AlegraAuthError as e:
        logger.error(f"Error de autenticación con Alegra: {e}")
        return jsonify({
            'success': False,
            'error': 'Error de autenticación con Alegra'
        }), 502
    except Exception as e:
        logger.exception("Error inesperado en análisis de horas pico")
        return jsonify({
            'success': False,
            'error': 'Error interno del servidor',
            'details': str(e)
        }), 500


# ============================================================
# 2. ENDPOINT: TOP CLIENTES
# ============================================================

@bp.route('/api/analytics/top-customers', methods=['GET'])
@token_required
@role_required('admin')
def get_top_customers():
    """
    Obtiene análisis de clientes que más compran

    Query Parameters:
        - date (str, optional): Fecha específica (YYYY-MM-DD)
        - start_date (str, optional): Fecha inicio (YYYY-MM-DD)
        - end_date (str, optional): Fecha fin (YYYY-MM-DD)
        - limit (int, optional): Número de clientes a retornar (default: 10)

    Returns:
        JSON con top clientes

    Example:
        GET /api/analytics/top-customers?date=2025-11-28&limit=10
        GET /api/analytics/top-customers?start_date=2025-11-01&end_date=2025-11-30
    """
    try:
        limit = int(request.args.get('limit', 10))
        invoices, date_range = get_invoices_from_params()

        if not invoices:
            return jsonify({
                'success': True,
                'message': 'No se encontraron facturas para el período especificado',
                'date_range': date_range,
                'data': {
                    'summary': {
                        'total_unique_customers': 0,
                        'total_revenue': 0
                    },
                    'top_customers': []
                }
            }), 200

        # Analizar top clientes
        analytics = SalesAnalytics(invoices)
        top_customers_data = analytics.get_top_customers_analysis(limit=limit)

        response = {
            'success': True,
            'date_range': date_range,
            'server_timestamp': get_colombia_timestamp(),
            'data': top_customers_data
        }

        # Agregar información de facturas anuladas
        response = add_voided_info_to_response(response, analytics)

        return jsonify(response), 200

    except ValueError as e:
        return jsonify({
            'success': False,
            'error': f'Parámetro inválido: {str(e)}'
        }), 400
    except AlegraConnectionError as e:
        logger.error(f"Error de conexión con Alegra: {e}")
        return jsonify({
            'success': False,
            'error': 'Error de conexión con Alegra',
            'details': str(e)
        }), 502
    except AlegraAuthError as e:
        logger.error(f"Error de autenticación con Alegra: {e}")
        return jsonify({
            'success': False,
            'error': 'Error de autenticación con Alegra'
        }), 502
    except Exception as e:
        logger.exception("Error inesperado en análisis de top clientes")
        return jsonify({
            'success': False,
            'error': 'Error interno del servidor',
            'details': str(e)
        }), 500


# ============================================================
# 3. ENDPOINT: TOP VENDEDORAS
# ============================================================

@bp.route('/api/analytics/top-sellers', methods=['GET'])
@token_required
@role_required('admin')
def get_top_sellers():
    """
    Obtiene análisis de vendedoras que más venden

    Query Parameters:
        - date (str, optional): Fecha específica (YYYY-MM-DD)
        - start_date (str, optional): Fecha inicio (YYYY-MM-DD)
        - end_date (str, optional): Fecha fin (YYYY-MM-DD)
        - limit (int, optional): Número de vendedoras a retornar (default: 10)

    Returns:
        JSON con top vendedoras

    Example:
        GET /api/analytics/top-sellers?date=2025-11-28&limit=5
        GET /api/analytics/top-sellers?start_date=2025-11-01&end_date=2025-11-30
    """
    try:
        limit = int(request.args.get('limit', 10))
        invoices, date_range = get_invoices_from_params()

        if not invoices:
            return jsonify({
                'success': True,
                'message': 'No se encontraron facturas para el período especificado',
                'date_range': date_range,
                'data': {
                    'summary': {
                        'total_sellers': 0,
                        'total_revenue': 0
                    },
                    'top_sellers': []
                }
            }), 200

        # Analizar top vendedoras
        analytics = SalesAnalytics(invoices)
        top_sellers_data = analytics.get_top_sellers_analysis(limit=limit)

        response = {
            'success': True,
            'date_range': date_range,
            'server_timestamp': get_colombia_timestamp(),
            'data': top_sellers_data
        }

        # Agregar información de facturas anuladas
        response = add_voided_info_to_response(response, analytics)

        return jsonify(response), 200

    except ValueError as e:
        return jsonify({
            'success': False,
            'error': f'Parámetro inválido: {str(e)}'
        }), 400
    except AlegraConnectionError as e:
        logger.error(f"Error de conexión con Alegra: {e}")
        return jsonify({
            'success': False,
            'error': 'Error de conexión con Alegra',
            'details': str(e)
        }), 502
    except AlegraAuthError as e:
        logger.error(f"Error de autenticación con Alegra: {e}")
        return jsonify({
            'success': False,
            'error': 'Error de autenticación con Alegra'
        }), 502
    except Exception as e:
        logger.exception("Error inesperado en análisis de top vendedoras")
        return jsonify({
            'success': False,
            'error': 'Error interno del servidor',
            'details': str(e)
        }), 500


# ============================================================
# 6. ENDPOINT: RETENCIÓN DE CLIENTES
# ============================================================

@bp.route('/api/analytics/customer-retention', methods=['GET'])
@token_required
@role_required('admin')
def get_customer_retention():
    """
    Obtiene análisis de retención de clientes (RFM Analysis)

    Query Parameters:
        - date (str, optional): Fecha específica (YYYY-MM-DD)
        - start_date (str, optional): Fecha inicio (YYYY-MM-DD)
        - end_date (str, optional): Fecha fin (YYYY-MM-DD)

    Returns:
        JSON con análisis de retención (Recency, Frequency, Monetary)

    Example:
        GET /api/analytics/customer-retention?start_date=2025-11-01&end_date=2025-11-30
    """
    try:
        invoices, date_range = get_invoices_from_params()

        if not invoices:
            return jsonify({
                'success': True,
                'message': 'No se encontraron facturas para el período especificado',
                'date_range': date_range,
                'data': {
                    'summary': {
                        'total_customers': 0,
                        'retention_rate': 0
                    }
                }
            }), 200

        # Analizar retención
        analytics = SalesAnalytics(invoices)
        retention_data = analytics.get_customer_retention_analysis()

        response = {
            'success': True,
            'date_range': date_range,
            'server_timestamp': get_colombia_timestamp(),
            'data': retention_data
        }

        # Agregar información de facturas anuladas
        response = add_voided_info_to_response(response, analytics)

        return jsonify(response), 200

    except ValueError as e:
        return jsonify({
            'success': False,
            'error': f'Formato de fecha inválido: {str(e)}. Use YYYY-MM-DD'
        }), 400
    except AlegraConnectionError as e:
        logger.error(f"Error de conexión con Alegra: {e}")
        return jsonify({
            'success': False,
            'error': 'Error de conexión con Alegra',
            'details': str(e)
        }), 502
    except AlegraAuthError as e:
        logger.error(f"Error de autenticación con Alegra: {e}")
        return jsonify({
            'success': False,
            'error': 'Error de autenticación con Alegra'
        }), 502
    except Exception as e:
        logger.exception("Error inesperado en análisis de retención")
        return jsonify({
            'success': False,
            'error': 'Error interno del servidor',
            'details': str(e)
        }), 500


# ============================================================
# 7. ENDPOINT: TENDENCIAS DE VENTAS
# ============================================================

@bp.route('/api/analytics/sales-trends', methods=['GET'])
@token_required
@role_required('admin')
def get_sales_trends():
    """
    Obtiene análisis de tendencias de ventas por día y día de la semana

    Query Parameters:
        - date (str, optional): Fecha específica (YYYY-MM-DD)
        - start_date (str, optional): Fecha inicio (YYYY-MM-DD)
        - end_date (str, optional): Fecha fin (YYYY-MM-DD)

    Returns:
        JSON con análisis de tendencias diarias y semanales

    Example:
        GET /api/analytics/sales-trends?start_date=2025-11-01&end_date=2025-11-30
    """
    try:
        invoices, date_range = get_invoices_from_params()

        if not invoices:
            return jsonify({
                'success': True,
                'message': 'No se encontraron facturas para el período especificado',
                'date_range': date_range,
                'data': {
                    'summary': {
                        'total_revenue': 0,
                        'total_days_with_sales': 0
                    }
                }
            }), 200

        # Analizar tendencias
        analytics = SalesAnalytics(invoices)
        trends_data = analytics.get_sales_trends_analysis()

        response = {
            'success': True,
            'date_range': date_range,
            'server_timestamp': get_colombia_timestamp(),
            'data': trends_data
        }

        # Agregar información de facturas anuladas
        response = add_voided_info_to_response(response, analytics)

        return jsonify(response), 200

    except ValueError as e:
        return jsonify({
            'success': False,
            'error': f'Formato de fecha inválido: {str(e)}. Use YYYY-MM-DD'
        }), 400
    except AlegraConnectionError as e:
        logger.error(f"Error de conexión con Alegra: {e}")
        return jsonify({
            'success': False,
            'error': 'Error de conexión con Alegra',
            'details': str(e)
        }), 502
    except AlegraAuthError as e:
        logger.error(f"Error de autenticación con Alegra: {e}")
        return jsonify({
            'success': False,
            'error': 'Error de autenticación con Alegra'
        }), 502
    except Exception as e:
        logger.exception("Error inesperado en análisis de tendencias")
        return jsonify({
            'success': False,
            'error': 'Error interno del servidor',
            'details': str(e)
        }), 500


# ============================================================
# 8. ENDPOINT: CROSS-SELLING (PRODUCTOS QUE SE VENDEN JUNTOS)
# ============================================================

@bp.route('/api/analytics/cross-selling', methods=['GET'])
@token_required
@role_required('admin')
def get_cross_selling():
    """
    Obtiene análisis de productos que se compran juntos (market basket analysis)

    Query Parameters:
        - date (str, optional): Fecha específica (YYYY-MM-DD)
        - start_date (str, optional): Fecha inicio (YYYY-MM-DD)
        - end_date (str, optional): Fecha fin (YYYY-MM-DD)
        - min_support (int, optional): Mínimo de veces que deben aparecer juntos (default: 2)

    Returns:
        JSON con análisis de productos que se venden juntos

    Example:
        GET /api/analytics/cross-selling?start_date=2025-11-01&end_date=2025-11-30&min_support=3
    """
    try:
        min_support = int(request.args.get('min_support', 2))
        invoices, date_range = get_invoices_from_params()

        if not invoices:
            return jsonify({
                'success': True,
                'message': 'No se encontraron facturas para el período especificado',
                'date_range': date_range,
                'data': {
                    'summary': {
                        'total_product_pairs': 0
                    },
                    'top_product_pairs': []
                }
            }), 200

        # Analizar cross-selling
        analytics = SalesAnalytics(invoices)
        cross_selling_data = analytics.get_cross_selling_analysis(min_support=min_support)

        response = {
            'success': True,
            'date_range': date_range,
            'server_timestamp': get_colombia_timestamp(),
            'data': cross_selling_data
        }

        # Agregar información de facturas anuladas
        response = add_voided_info_to_response(response, analytics)

        return jsonify(response), 200

    except ValueError as e:
        return jsonify({
            'success': False,
            'error': f'Parámetro inválido: {str(e)}'
        }), 400
    except AlegraConnectionError as e:
        logger.error(f"Error de conexión con Alegra: {e}")
        return jsonify({
            'success': False,
            'error': 'Error de conexión con Alegra',
            'details': str(e)
        }), 502
    except AlegraAuthError as e:
        logger.error(f"Error de autenticación con Alegra: {e}")
        return jsonify({
            'success': False,
            'error': 'Error de autenticación con Alegra'
        }), 502
    except Exception as e:
        logger.exception("Error inesperado en análisis de cross-selling")
        return jsonify({
            'success': False,
            'error': 'Error interno del servidor',
            'details': str(e)
        }), 500


# ============================================================
# ENDPOINT: ANÁLISIS COMPLETO (DASHBOARD)
# ============================================================

@bp.route('/api/analytics/dashboard', methods=['GET'])
@token_required
@role_required('admin')
def get_analytics_dashboard():
    """
    Obtiene un resumen completo con todos los análisis disponibles

    Query Parameters:
        - date (str, optional): Fecha específica (YYYY-MM-DD)
        - start_date (str, optional): Fecha inicio (YYYY-MM-DD)
        - end_date (str, optional): Fecha fin (YYYY-MM-DD)

    Returns:
        JSON con todos los análisis combinados

    Example:
        GET /api/analytics/dashboard?start_date=2025-11-01&end_date=2025-11-30
    """
    try:
        invoices, date_range = get_invoices_from_params()

        if not invoices:
            return jsonify({
                'success': True,
                'message': 'No se encontraron facturas para el período especificado',
                'date_range': date_range,
                'data': {}
            }), 200

        # Ejecutar todos los análisis
        analytics = SalesAnalytics(invoices)

        dashboard_data = {
            'peak_hours': analytics.get_peak_hours_analysis(),
            'top_customers': analytics.get_top_customers_analysis(limit=10),
            'top_sellers': analytics.get_top_sellers_analysis(limit=10),
            'customer_retention': analytics.get_customer_retention_analysis(),
            'sales_trends': analytics.get_sales_trends_analysis(),
            'cross_selling': analytics.get_cross_selling_analysis(min_support=2)
        }

        response = {
            'success': True,
            'date_range': date_range,
            'server_timestamp': get_colombia_timestamp(),
            'data': dashboard_data
        }

        # Agregar información de facturas anuladas
        response = add_voided_info_to_response(response, analytics)

        return jsonify(response), 200

    except ValueError as e:
        return jsonify({
            'success': False,
            'error': f'Formato de fecha inválido: {str(e)}. Use YYYY-MM-DD'
        }), 400
    except AlegraConnectionError as e:
        logger.error(f"Error de conexión con Alegra: {e}")
        return jsonify({
            'success': False,
            'error': 'Error de conexión con Alegra',
            'details': str(e)
        }), 502
    except AlegraAuthError as e:
        logger.error(f"Error de autenticación con Alegra: {e}")
        return jsonify({
            'success': False,
            'error': 'Error de autenticación con Alegra'
        }), 502
    except Exception as e:
        logger.exception("Error inesperado en dashboard de analytics")
        return jsonify({
            'success': False,
            'error': 'Error interno del servidor',
            'details': str(e)
        }), 500
