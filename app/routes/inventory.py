"""
Rutas de API para análisis de inventario
"""
from flask import Blueprint, request, jsonify
import logging

from app.middlewares.auth import token_required, role_required
from app.services.alegra_client import AlegraClient
from app.services.inventory_analytics import InventoryAnalytics
from app.services.inventory_file_processor import InventoryFileProcessor
from app.config import Config
from app.exceptions import AlegraConnectionError, AlegraAuthError

logger = logging.getLogger(__name__)

bp = Blueprint('inventory', __name__)

# Inicializar cliente de Alegra
alegra_client = AlegraClient(
    Config.ALEGRA_USER,
    Config.ALEGRA_PASS,
    Config.ALEGRA_API_BASE_URL,
    Config.ALEGRA_TIMEOUT
)


@bp.route('/api/inventory/analysis', methods=['GET'])
@token_required
@role_required('admin')
def get_inventory_analysis():
    """
    Obtiene análisis completo del inventario

    Returns:
        JSON con análisis completo de inventario:
        - Resumen ejecutivo
        - Análisis por departamento (HOMBRE, MUJER, NIÑO, NIÑA)
        - Análisis por categoría
        - Análisis por talla
        - Productos sin stock
        - Productos con bajo stock
        - Top productos por valor
        - Análisis ABC

    Example:
        GET /api/inventory/analysis
    """
    try:
        # Obtener items activos de Alegra
        items = alegra_client.get_active_items()

        if not items:
            return jsonify({
                'success': True,
                'message': 'No se encontraron items activos',
                'data': {
                    'resumen_ejecutivo': {
                        'total_items': 0,
                        'total_unidades': 0,
                        'valor_total_inventario': 0
                    }
                }
            }), 200

        # Procesar análisis
        analytics = InventoryAnalytics(items)
        report = analytics.get_complete_analysis()

        return jsonify({
            'success': True,
            'data': report
        }), 200

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
        logger.exception("Error inesperado en análisis de inventario")
        return jsonify({
            'success': False,
            'error': 'Error interno del servidor',
            'details': str(e)
        }), 500


@bp.route('/api/inventory/summary', methods=['GET'])
@token_required
@role_required('admin')
def get_inventory_summary():
    """
    Obtiene resumen ejecutivo del inventario

    Returns:
        JSON con métricas principales:
        - Total de items
        - Total de unidades
        - Valor total del inventario
        - Valor potencial de venta
        - Margen esperado
        - Costos y precios promedio

    Example:
        GET /api/inventory/summary
    """
    try:
        items = alegra_client.get_active_items()

        if not items:
            return jsonify({
                'success': True,
                'message': 'No se encontraron items activos',
                'summary': {
                    'total_items': 0,
                    'total_unidades': 0,
                    'valor_total_inventario': 0
                }
            }), 200

        analytics = InventoryAnalytics(items)
        summary = analytics.get_executive_summary()

        return jsonify({
            'success': True,
            'summary': summary
        }), 200

    except Exception as e:
        logger.exception("Error en resumen de inventario")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@bp.route('/api/inventory/by-department', methods=['GET'])
@token_required
@role_required('admin')
def get_inventory_by_department():
    """
    Obtiene análisis de inventario por departamento

    Returns:
        JSON con inventario desglosado por departamento:
        - HOMBRE
        - MUJER
        - NIÑO
        - NIÑA
        - UNKNOWN (sin clasificar)

        Cada departamento incluye:
        - Total de items
        - Total de unidades
        - Valor de inventario
        - Valor potencial de venta
        - Margen
        - Desglose por categoría

    Example:
        GET /api/inventory/by-department
    """
    try:
        items = alegra_client.get_active_items()

        if not items:
            return jsonify({
                'success': True,
                'message': 'No se encontraron items activos',
                'data': {}
            }), 200

        analytics = InventoryAnalytics(items)
        by_department = analytics.get_by_department()

        return jsonify({
            'success': True,
            'data': by_department
        }), 200

    except Exception as e:
        logger.exception("Error en análisis por departamento")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@bp.route('/api/inventory/by-category', methods=['GET'])
@token_required
@role_required('admin')
def get_inventory_by_category():
    """
    Obtiene análisis de inventario por categoría de producto

    Returns:
        JSON con lista de categorías ordenadas por valor:
        [
            {
                'categoria': str,
                'total_items': int,
                'total_unidades': int,
                'valor_inventario': int,
                'porcentaje_valor': float
            },
            ...
        ]

    Example:
        GET /api/inventory/by-category
    """
    try:
        items = alegra_client.get_active_items()

        if not items:
            return jsonify({
                'success': True,
                'message': 'No se encontraron items activos',
                'categories': []
            }), 200

        analytics = InventoryAnalytics(items)
        categories = analytics.get_by_category()

        return jsonify({
            'success': True,
            'categories': categories
        }), 200

    except Exception as e:
        logger.exception("Error en análisis por categoría")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@bp.route('/api/inventory/by-size', methods=['GET'])
@token_required
@role_required('admin')
def get_inventory_by_size():
    """
    Obtiene análisis de inventario por talla

    Returns:
        JSON con lista de tallas ordenadas por cantidad de unidades:
        [
            {
                'talla': str,
                'total_unidades': int,
                'valor_inventario': int,
                'cantidad_items': int
            },
            ...
        ]

    Example:
        GET /api/inventory/by-size
    """
    try:
        items = alegra_client.get_active_items()

        if not items:
            return jsonify({
                'success': True,
                'message': 'No se encontraron items activos',
                'sizes': []
            }), 200

        analytics = InventoryAnalytics(items)
        sizes = analytics.get_by_size()

        return jsonify({
            'success': True,
            'sizes': sizes
        }), 200

    except Exception as e:
        logger.exception("Error en análisis por talla")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@bp.route('/api/inventory/out-of-stock', methods=['GET'])
@token_required
@role_required('admin')
def get_out_of_stock():
    """
    Obtiene productos sin stock (cantidad = 0)

    Returns:
        JSON con lista de productos sin stock:
        [
            {
                'id': str,
                'nombre': str,
                'categoria': str,
                'departamento': str,
                'precio_venta': int
            },
            ...
        ]

    Example:
        GET /api/inventory/out-of-stock
    """
    try:
        items = alegra_client.get_active_items()

        if not items:
            return jsonify({
                'success': True,
                'message': 'No se encontraron items activos',
                'products': []
            }), 200

        analytics = InventoryAnalytics(items)
        out_of_stock = analytics.get_out_of_stock()

        return jsonify({
            'success': True,
            'total': len(out_of_stock),
            'products': out_of_stock
        }), 200

    except Exception as e:
        logger.exception("Error al obtener productos sin stock")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@bp.route('/api/inventory/low-stock', methods=['GET'])
@token_required
@role_required('admin')
def get_low_stock():
    """
    Obtiene productos con bajo stock

    Query Parameters:
        - threshold (int, optional): Umbral de stock bajo (default: 5)

    Returns:
        JSON con lista de productos con bajo stock ordenados por cantidad:
        [
            {
                'id': str,
                'nombre': str,
                'categoria': str,
                'departamento': str,
                'cantidad_disponible': int,
                'precio_venta': int
            },
            ...
        ]

    Example:
        GET /api/inventory/low-stock?threshold=3
    """
    try:
        threshold = int(request.args.get('threshold', 5))

        items = alegra_client.get_active_items()

        if not items:
            return jsonify({
                'success': True,
                'message': 'No se encontraron items activos',
                'products': []
            }), 200

        analytics = InventoryAnalytics(items)
        low_stock = analytics.get_low_stock(threshold=threshold)

        return jsonify({
            'success': True,
            'threshold': threshold,
            'total': len(low_stock),
            'products': low_stock
        }), 200

    except ValueError as e:
        return jsonify({
            'success': False,
            'error': f'Parámetro threshold inválido: {str(e)}'
        }), 400
    except Exception as e:
        logger.exception("Error al obtener productos con bajo stock")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@bp.route('/api/inventory/top-by-value', methods=['GET'])
@token_required
@role_required('admin')
def get_top_by_value():
    """
    Obtiene top productos por valor de inventario

    Query Parameters:
        - limit (int, optional): Cantidad de productos (default: 20)

    Returns:
        JSON con lista de productos ordenados por valor de inventario:
        [
            {
                'id': str,
                'nombre': str,
                'categoria': str,
                'departamento': str,
                'cantidad': int,
                'costo_unitario': float,
                'precio_venta': int,
                'valor_inventario': int,
                'valor_potencial_venta': int
            },
            ...
        ]

    Example:
        GET /api/inventory/top-by-value?limit=10
    """
    try:
        limit = int(request.args.get('limit', 20))

        items = alegra_client.get_active_items()

        if not items:
            return jsonify({
                'success': True,
                'message': 'No se encontraron items activos',
                'products': []
            }), 200

        analytics = InventoryAnalytics(items)
        top_products = analytics.get_top_by_value(limit=limit)

        return jsonify({
            'success': True,
            'limit': limit,
            'total': len(top_products),
            'products': top_products
        }), 200

    except ValueError as e:
        return jsonify({
            'success': False,
            'error': f'Parámetro limit inválido: {str(e)}'
        }), 400
    except Exception as e:
        logger.exception("Error al obtener top productos")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@bp.route('/api/inventory/abc-analysis', methods=['GET'])
@token_required
@role_required('admin')
def get_abc_analysis():
    """
    Obtiene análisis ABC del inventario

    El análisis ABC clasifica productos según su contribución al valor total:
    - Clase A: ~20% de productos que representan ~80% del valor
    - Clase B: ~30% de productos que representan ~15% del valor
    - Clase C: ~50% de productos que representan ~5% del valor

    Returns:
        JSON con clasificación ABC:
        {
            'clase_A': {
                'cantidad_items': int,
                'porcentaje_items': float,
                'valor_inventario': int,
                'porcentaje_valor': float
            },
            'clase_B': {...},
            'clase_C': {...}
        }

    Example:
        GET /api/inventory/abc-analysis
    """
    try:
        items = alegra_client.get_active_items()

        if not items:
            return jsonify({
                'success': True,
                'message': 'No se encontraron items activos',
                'data': {
                    'clase_A': {'cantidad_items': 0, 'valor_inventario': 0},
                    'clase_B': {'cantidad_items': 0, 'valor_inventario': 0},
                    'clase_C': {'cantidad_items': 0, 'valor_inventario': 0}
                }
            }), 200

        analytics = InventoryAnalytics(items)
        abc_analysis = analytics.get_abc_analysis()

        return jsonify({
            'success': True,
            'data': abc_analysis
        }), 200

    except Exception as e:
        logger.exception("Error en análisis ABC")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@bp.route('/api/inventory/upload-file', methods=['POST'])
@token_required
@role_required('admin')
def upload_inventory_file():
    """
    Procesa un archivo de inventario (CSV o Excel) y retorna análisis completo

    Este endpoint recibe un archivo de inventario exportado desde Alegra
    (u otra fuente) y realiza un análisis completo organizado por departamentos.

    Request:
        - Content-Type: multipart/form-data
        - file: Archivo CSV o Excel (.csv, .xlsx, .xls)

    Formatos soportados:
        - CSV separado por coma (,)
        - CSV separado por punto y coma (;)
        - Excel (.xlsx, .xls)

    Returns:
        JSON con análisis completo del inventario:
        {
            'success': bool,
            'resumen_general': {
                'total_items': int,
                'valor_total_costo': float,
                'valor_total_precio': float,
                'margen_total': float,
                'margen_porcentaje': float,
                'total_categorias': int
            },
            'por_departamento': {
                'hombre': {
                    'cantidad': int,
                    'valor_costo': float,
                    'valor_precio': float,
                    'margen_total': float,
                    'margen_porcentaje': float,
                    'precio_promedio': float,
                    'costo_promedio': float,
                    'porcentaje_inventario': float,
                    'items': [...]  # Muestra de 10 items
                },
                'mujer': {...},
                'nino': {...},
                'nina': {...},
                'accesorios': {...},
                'otros': {...}
            },
            'top_categorias': [
                {'categoria': str, 'cantidad': int},
                ...
            ],
            'departamentos_ordenados': [
                {'nombre': str, 'cantidad': int, 'valor': float},
                ...
            ]
        }

    Example:
        POST /api/inventory/upload-file
        Content-Type: multipart/form-data

        FormData:
            file: [archivo.csv o archivo.xlsx]

    Error Responses:
        400: No se envió archivo o formato no soportado
        500: Error procesando el archivo
    """
    try:
        # Validar que se envió un archivo
        if 'file' not in request.files:
            return jsonify({
                'success': False,
                'error': 'No se envió ningún archivo'
            }), 400

        file = request.files['file']

        # Validar que el archivo tiene nombre
        if file.filename == '':
            return jsonify({
                'success': False,
                'error': 'El archivo no tiene nombre'
            }), 400

        # Validar formato del archivo
        allowed_extensions = {'.csv', '.xlsx', '.xls'}
        file_ext = '.' + file.filename.rsplit('.', 1)[-1].lower() if '.' in file.filename else ''

        if file_ext not in allowed_extensions:
            return jsonify({
                'success': False,
                'error': f'Formato de archivo no soportado. Use: {", ".join(allowed_extensions)}'
            }), 400

        logger.info(f"Procesando archivo de inventario: {file.filename}")

        # Procesar el archivo
        result = InventoryFileProcessor.process_file(file.stream, file.filename)

        logger.info(f"Archivo procesado exitosamente. Total items: {result.get('resumen_general', {}).get('total_items', 0)}")

        return jsonify(result), 200

    except ValueError as e:
        logger.error(f"Error de validación al procesar archivo: {e}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 400
    except Exception as e:
        logger.exception("Error inesperado al procesar archivo de inventario")
        return jsonify({
            'success': False,
            'error': 'Error interno al procesar el archivo',
            'details': str(e)
        }), 500
