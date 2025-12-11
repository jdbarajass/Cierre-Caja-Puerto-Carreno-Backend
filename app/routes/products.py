"""
Rutas de API para análisis de productos
"""
from flask import Blueprint, request, jsonify, send_file
from datetime import datetime, timedelta
import logging

from app.middlewares.auth import token_required, role_required
from app.services.alegra_client import AlegraClient
from app.services.product_analytics import ProductAnalytics
from app.services.pdf_generator import ProductReportPDFGenerator
from app.config import Config
from app.exceptions import AlegraConnectionError, AlegraAuthError

logger = logging.getLogger(__name__)

bp = Blueprint('products', __name__)

# Inicializar cliente de Alegra
alegra_client = AlegraClient(
    Config.ALEGRA_USER,
    Config.ALEGRA_PASS,
    Config.ALEGRA_API_BASE_URL,
    Config.ALEGRA_TIMEOUT
)


@bp.route('/api/products/analysis', methods=['GET'])
@token_required
@role_required('admin')
def get_products_analysis():
    """
    Obtiene análisis completo de productos en formato JSON

    Query Parameters:
        - date (str, optional): Fecha específica (YYYY-MM-DD)
        - start_date (str, optional): Fecha inicio (YYYY-MM-DD)
        - end_date (str, optional): Fecha fin (YYYY-MM-DD)

    Si no se especifica ninguna fecha, usa el día actual

    Returns:
        JSON con análisis completo de productos

    Example:
        GET /api/products/analysis?date=2025-11-20
        GET /api/products/analysis?start_date=2025-11-01&end_date=2025-11-30
    """
    try:
        # Obtener parámetros
        date_param = request.args.get('date')
        start_date_param = request.args.get('start_date')
        end_date_param = request.args.get('end_date')

        # Determinar rango de fechas
        if date_param:
            # Fecha específica
            # Validar formato
            datetime.strptime(date_param, '%Y-%m-%d')
            target_date = datetime.strptime(date_param, '%Y-%m-%d').date()
            date_range = date_param
            invoices = alegra_client.get_invoices_by_date(target_date)
        elif start_date_param and end_date_param:
            # Rango de fechas
            # Validar formato de fechas
            datetime.strptime(start_date_param, '%Y-%m-%d')
            datetime.strptime(end_date_param, '%Y-%m-%d')
            date_range = f"{start_date_param} al {end_date_param}"
            # Pasar strings directamente, no objetos date
            invoices = alegra_client.get_all_invoices_in_range(start_date_param, end_date_param)
        else:
            # Día actual por defecto
            target_date = datetime.now().date()
            date_range = target_date.strftime('%Y-%m-%d')
            invoices = alegra_client.get_invoices_by_date(target_date)

        if not invoices:
            return jsonify({
                'success': True,
                'message': 'No se encontraron facturas para el período especificado',
                'date_range': date_range,
                'data': {
                    'resumen_ejecutivo': {
                        'total_productos_vendidos': 0,
                        'ingresos_totales': 0,
                        'numero_facturas': 0
                    }
                }
            }), 200

        # Procesar análisis
        analytics = ProductAnalytics(invoices)
        report = analytics.get_complete_report()

        return jsonify({
            'success': True,
            'date_range': date_range,
            'data': report
        }), 200

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
        logger.exception("Error inesperado en análisis de productos")
        return jsonify({
            'success': False,
            'error': 'Error interno del servidor',
            'details': str(e)
        }), 500


@bp.route('/api/products/analysis/pdf', methods=['GET'])
@token_required
@role_required('admin')
def download_products_analysis_pdf():
    """
    Descarga reporte de productos en formato PDF

    Query Parameters:
        - date (str, optional): Fecha específica (YYYY-MM-DD)
        - start_date (str, optional): Fecha inicio (YYYY-MM-DD)
        - end_date (str, optional): Fecha fin (YYYY-MM-DD)

    Si no se especifica ninguna fecha, usa el día actual

    Returns:
        PDF descargable con reporte completo

    Example:
        GET /api/products/analysis/pdf?date=2025-11-20
        GET /api/products/analysis/pdf?start_date=2025-11-01&end_date=2025-11-30
    """
    try:
        # Obtener parámetros
        date_param = request.args.get('date')
        start_date_param = request.args.get('start_date')
        end_date_param = request.args.get('end_date')

        # Determinar rango de fechas
        if date_param:
            # Validar formato
            datetime.strptime(date_param, '%Y-%m-%d')
            target_date = datetime.strptime(date_param, '%Y-%m-%d').date()
            date_range = date_param
            filename_date = date_param
            invoices = alegra_client.get_invoices_by_date(target_date)
        elif start_date_param and end_date_param:
            # Validar formato de fechas
            datetime.strptime(start_date_param, '%Y-%m-%d')
            datetime.strptime(end_date_param, '%Y-%m-%d')
            date_range = f"{start_date_param} al {end_date_param}"
            filename_date = f"{start_date_param}_al_{end_date_param}"
            # Pasar strings directamente, no objetos date
            invoices = alegra_client.get_all_invoices_in_range(start_date_param, end_date_param)
        else:
            target_date = datetime.now().date()
            date_range = target_date.strftime('%Y-%m-%d')
            filename_date = date_range
            invoices = alegra_client.get_invoices_by_date(target_date)

        if not invoices:
            return jsonify({
                'success': False,
                'error': 'No se encontraron facturas para el período especificado'
            }), 404

        # Procesar análisis
        analytics = ProductAnalytics(invoices)
        report = analytics.get_complete_report()

        # Generar PDF
        pdf_generator = ProductReportPDFGenerator()
        pdf_buffer = pdf_generator.generate_report(report, date_range)

        # Nombre del archivo
        filename = f"reporte_productos_KOAJ_{filename_date}.pdf"

        return send_file(
            pdf_buffer,
            mimetype='application/pdf',
            as_attachment=True,
            download_name=filename
        )

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
        logger.exception("Error inesperado generando PDF")
        return jsonify({
            'success': False,
            'error': 'Error interno del servidor',
            'details': str(e)
        }), 500


@bp.route('/api/products/top-sellers', methods=['GET'])
@token_required
@role_required('admin')
def get_top_sellers():
    """
    Obtiene top productos más vendidos

    Query Parameters:
        - date (str, optional): Fecha específica (YYYY-MM-DD)
        - start_date (str, optional): Fecha inicio (YYYY-MM-DD)
        - end_date (str, optional): Fecha fin (YYYY-MM-DD)
        - limit (int, optional): Número de productos (default: 10)
        - unified (bool, optional): Si True, unifica variantes (default: false)

    Returns:
        JSON con top productos

    Example:
        GET /api/products/top-sellers?date=2025-11-20&limit=10
        GET /api/products/top-sellers?start_date=2025-11-01&end_date=2025-11-30&unified=true
    """
    try:
        # Obtener parámetros
        date_param = request.args.get('date')
        start_date_param = request.args.get('start_date')
        end_date_param = request.args.get('end_date')
        limit = int(request.args.get('limit', 10))
        unified = request.args.get('unified', 'false').lower() == 'true'

        # Determinar rango de fechas
        if date_param:
            # Validar formato
            datetime.strptime(date_param, '%Y-%m-%d')
            target_date = datetime.strptime(date_param, '%Y-%m-%d').date()
            date_range = date_param
            invoices = alegra_client.get_invoices_by_date(target_date)
        elif start_date_param and end_date_param:
            # Validar formato de fechas
            datetime.strptime(start_date_param, '%Y-%m-%d')
            datetime.strptime(end_date_param, '%Y-%m-%d')
            date_range = f"{start_date_param} al {end_date_param}"
            # Pasar strings directamente, no objetos date
            invoices = alegra_client.get_all_invoices_in_range(start_date_param, end_date_param)
        else:
            target_date = datetime.now().date()
            date_range = target_date.strftime('%Y-%m-%d')
            invoices = alegra_client.get_invoices_by_date(target_date)

        if not invoices:
            return jsonify({
                'success': True,
                'message': 'No se encontraron facturas',
                'date_range': date_range,
                'products': []
            }), 200

        # Procesar análisis
        analytics = ProductAnalytics(invoices)

        if unified:
            products = analytics.get_top_products_unified(limit=limit, exclude_bolsa=True)
        else:
            products = analytics.get_top_products(limit=limit, exclude_bolsa=True)

        return jsonify({
            'success': True,
            'date_range': date_range,
            'unified': unified,
            'products': products
        }), 200

    except ValueError as e:
        return jsonify({
            'success': False,
            'error': f'Parámetro inválido: {str(e)}'
        }), 400
    except Exception as e:
        logger.exception("Error en top-sellers")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@bp.route('/api/products/categories', methods=['GET'])
@token_required
@role_required('admin')
def get_categories_analysis():
    """
    Obtiene análisis de productos por categorías

    Query Parameters:
        - date (str, optional): Fecha específica (YYYY-MM-DD)
        - start_date (str, optional): Fecha inicio (YYYY-MM-DD)
        - end_date (str, optional): Fecha fin (YYYY-MM-DD)

    Returns:
        JSON con análisis por categorías (CAMISETA, JEAN, BLUSA, etc.)

    Example:
        GET /api/products/categories?date=2025-11-20
    """
    try:
        # Obtener parámetros
        date_param = request.args.get('date')
        start_date_param = request.args.get('start_date')
        end_date_param = request.args.get('end_date')

        # Determinar rango de fechas
        if date_param:
            # Validar formato
            datetime.strptime(date_param, '%Y-%m-%d')
            target_date = datetime.strptime(date_param, '%Y-%m-%d').date()
            date_range = date_param
            invoices = alegra_client.get_invoices_by_date(target_date)
        elif start_date_param and end_date_param:
            # Validar formato de fechas
            datetime.strptime(start_date_param, '%Y-%m-%d')
            datetime.strptime(end_date_param, '%Y-%m-%d')
            date_range = f"{start_date_param} al {end_date_param}"
            # Pasar strings directamente, no objetos date
            invoices = alegra_client.get_all_invoices_in_range(start_date_param, end_date_param)
        else:
            target_date = datetime.now().date()
            date_range = target_date.strftime('%Y-%m-%d')
            invoices = alegra_client.get_invoices_by_date(target_date)

        if not invoices:
            return jsonify({
                'success': True,
                'message': 'No se encontraron facturas',
                'date_range': date_range,
                'data': {'categorias': [], 'total_categorias': 0}
            }), 200

        # Procesar análisis
        analytics = ProductAnalytics(invoices)
        categories = analytics.get_category_analysis()

        return jsonify({
            'success': True,
            'date_range': date_range,
            'data': categories
        }), 200

    except ValueError as e:
        return jsonify({
            'success': False,
            'error': f'Formato de fecha inválido: {str(e)}'
        }), 400
    except Exception as e:
        logger.exception("Error en análisis de categorías")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@bp.route('/api/products/summary', methods=['GET'])
@token_required
@role_required('admin')
def get_products_summary():
    """
    Obtiene resumen ejecutivo de productos (métricas principales)

    Query Parameters:
        - date (str, optional): Fecha específica (YYYY-MM-DD)
        - start_date (str, optional): Fecha inicio (YYYY-MM-DD)
        - end_date (str, optional): Fecha fin (YYYY-MM-DD)

    Returns:
        JSON con resumen ejecutivo

    Example:
        GET /api/products/summary?date=2025-11-20
    """
    try:
        # Obtener parámetros
        date_param = request.args.get('date')
        start_date_param = request.args.get('start_date')
        end_date_param = request.args.get('end_date')

        # Determinar rango de fechas
        if date_param:
            # Validar formato
            datetime.strptime(date_param, '%Y-%m-%d')
            target_date = datetime.strptime(date_param, '%Y-%m-%d').date()
            date_range = date_param
            invoices = alegra_client.get_invoices_by_date(target_date)
        elif start_date_param and end_date_param:
            # Validar formato de fechas
            datetime.strptime(start_date_param, '%Y-%m-%d')
            datetime.strptime(end_date_param, '%Y-%m-%d')
            date_range = f"{start_date_param} al {end_date_param}"
            # Pasar strings directamente, no objetos date
            invoices = alegra_client.get_all_invoices_in_range(start_date_param, end_date_param)
        else:
            target_date = datetime.now().date()
            date_range = target_date.strftime('%Y-%m-%d')
            invoices = alegra_client.get_invoices_by_date(target_date)

        if not invoices:
            return jsonify({
                'success': True,
                'message': 'No se encontraron facturas',
                'date_range': date_range,
                'summary': {
                    'total_productos_vendidos': 0,
                    'ingresos_totales': 0,
                    'numero_facturas': 0
                }
            }), 200

        # Procesar análisis
        analytics = ProductAnalytics(invoices)
        summary = analytics.get_summary()

        return jsonify({
            'success': True,
            'date_range': date_range,
            'summary': summary
        }), 200

    except ValueError as e:
        return jsonify({
            'success': False,
            'error': f'Formato de fecha inválido: {str(e)}'
        }), 400
    except Exception as e:
        logger.exception("Error en resumen de productos")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@bp.route('/api/products/analysis/sizes', methods=['GET'])
@token_required
@role_required('admin')
def get_size_analysis():
    """
    Obtiene análisis global de ventas por talla

    Query Parameters:
        - date (str, optional): Fecha específica (YYYY-MM-DD)
        - start_date (str, optional): Fecha inicio (YYYY-MM-DD)
        - end_date (str, optional): Fecha fin (YYYY-MM-DD)

    Returns:
        JSON con análisis de ventas por talla

    Example:
        GET /api/products/analysis/sizes?date=2025-11-20
        GET /api/products/analysis/sizes?start_date=2025-11-01&end_date=2025-11-30
    """
    try:
        # Obtener parámetros
        date_param = request.args.get('date')
        start_date_param = request.args.get('start_date')
        end_date_param = request.args.get('end_date')

        # Determinar rango de fechas
        if date_param:
            datetime.strptime(date_param, '%Y-%m-%d')
            target_date = datetime.strptime(date_param, '%Y-%m-%d').date()
            date_range = date_param
            invoices = alegra_client.get_invoices_by_date(target_date)
        elif start_date_param and end_date_param:
            datetime.strptime(start_date_param, '%Y-%m-%d')
            datetime.strptime(end_date_param, '%Y-%m-%d')
            date_range = f"{start_date_param} al {end_date_param}"
            invoices = alegra_client.get_all_invoices_in_range(start_date_param, end_date_param)
        else:
            target_date = datetime.now().date()
            date_range = target_date.strftime('%Y-%m-%d')
            invoices = alegra_client.get_invoices_by_date(target_date)

        if not invoices:
            return jsonify({
                'success': True,
                'message': 'No se encontraron facturas para el período especificado',
                'date_range': date_range,
                'data': {
                    'total_units': 0,
                    'total_revenue': 0,
                    'sizes': []
                }
            }), 200

        # Procesar análisis
        analytics = ProductAnalytics(invoices)
        size_analysis = analytics.get_sales_by_size()

        return jsonify({
            'success': True,
            'date_range': date_range,
            'data': size_analysis
        }), 200

    except ValueError as e:
        return jsonify({
            'success': False,
            'error': f'Formato de fecha inválido: {str(e)}'
        }), 400
    except Exception as e:
        logger.exception("Error en análisis por talla")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@bp.route('/api/products/analysis/category-sizes', methods=['GET'])
@token_required
@role_required('admin')
def get_category_size_analysis():
    """
    Obtiene análisis de ventas por categoría, desglosado por talla

    Query Parameters:
        - date (str, optional): Fecha específica (YYYY-MM-DD)
        - start_date (str, optional): Fecha inicio (YYYY-MM-DD)
        - end_date (str, optional): Fecha fin (YYYY-MM-DD)

    Returns:
        JSON con análisis por categoría y talla

    Example:
        GET /api/products/analysis/category-sizes?date=2025-11-20
        GET /api/products/analysis/category-sizes?start_date=2025-11-01&end_date=2025-11-30
    """
    try:
        # Obtener parámetros
        date_param = request.args.get('date')
        start_date_param = request.args.get('start_date')
        end_date_param = request.args.get('end_date')

        # Determinar rango de fechas
        if date_param:
            datetime.strptime(date_param, '%Y-%m-%d')
            target_date = datetime.strptime(date_param, '%Y-%m-%d').date()
            date_range = date_param
            invoices = alegra_client.get_invoices_by_date(target_date)
        elif start_date_param and end_date_param:
            datetime.strptime(start_date_param, '%Y-%m-%d')
            datetime.strptime(end_date_param, '%Y-%m-%d')
            date_range = f"{start_date_param} al {end_date_param}"
            invoices = alegra_client.get_all_invoices_in_range(start_date_param, end_date_param)
        else:
            target_date = datetime.now().date()
            date_range = target_date.strftime('%Y-%m-%d')
            invoices = alegra_client.get_invoices_by_date(target_date)

        if not invoices:
            return jsonify({
                'success': True,
                'message': 'No se encontraron facturas para el período especificado',
                'date_range': date_range,
                'data': {
                    'categories': [],
                    'total_categories': 0
                }
            }), 200

        # Procesar análisis
        analytics = ProductAnalytics(invoices)
        category_size_analysis = analytics.get_sales_by_category_and_size()

        return jsonify({
            'success': True,
            'date_range': date_range,
            'data': category_size_analysis
        }), 200

    except ValueError as e:
        return jsonify({
            'success': False,
            'error': f'Formato de fecha inválido: {str(e)}'
        }), 400
    except Exception as e:
        logger.exception("Error en análisis por categoría y talla")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@bp.route('/api/products/analysis/department-sizes', methods=['GET'])
@token_required
@role_required('admin')
def get_department_size_analysis():
    """
    Obtiene análisis por departamento (género) y talla

    Query Parameters:
        - date (str, optional): Fecha específica (YYYY-MM-DD)
        - start_date (str, optional): Fecha inicio (YYYY-MM-DD)
        - end_date (str, optional): Fecha fin (YYYY-MM-DD)

    Returns:
        JSON con análisis por departamento y talla

    Example:
        GET /api/products/analysis/department-sizes?date=2025-11-20
        GET /api/products/analysis/department-sizes?start_date=2025-11-01&end_date=2025-11-30
    """
    try:
        # Obtener parámetros
        date_param = request.args.get('date')
        start_date_param = request.args.get('start_date')
        end_date_param = request.args.get('end_date')

        # Determinar rango de fechas
        if date_param:
            datetime.strptime(date_param, '%Y-%m-%d')
            target_date = datetime.strptime(date_param, '%Y-%m-%d').date()
            date_range = date_param
            invoices = alegra_client.get_invoices_by_date(target_date)
        elif start_date_param and end_date_param:
            datetime.strptime(start_date_param, '%Y-%m-%d')
            datetime.strptime(end_date_param, '%Y-%m-%d')
            date_range = f"{start_date_param} al {end_date_param}"
            invoices = alegra_client.get_all_invoices_in_range(start_date_param, end_date_param)
        else:
            target_date = datetime.now().date()
            date_range = target_date.strftime('%Y-%m-%d')
            invoices = alegra_client.get_invoices_by_date(target_date)

        if not invoices:
            return jsonify({
                'success': True,
                'message': 'No se encontraron facturas para el período especificado',
                'date_range': date_range,
                'data': {
                    'departments': [],
                    'total_departments': 0
                }
            }), 200

        # Procesar análisis
        analytics = ProductAnalytics(invoices)
        department_size_analysis = analytics.get_sales_by_department_and_size()

        return jsonify({
            'success': True,
            'date_range': date_range,
            'data': department_size_analysis
        }), 200

    except ValueError as e:
        return jsonify({
            'success': False,
            'error': f'Formato de fecha inválido: {str(e)}'
        }), 400
    except Exception as e:
        logger.exception("Error en análisis por departamento y talla")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500
