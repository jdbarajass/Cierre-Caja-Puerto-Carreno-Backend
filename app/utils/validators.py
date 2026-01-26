"""
Decoradores de validación para endpoints
"""
from functools import wraps
from flask import request, jsonify
from datetime import datetime, date
import logging
import re

logger = logging.getLogger(__name__)

# Extensiones de archivo permitidas
ALLOWED_FILE_EXTENSIONS = {'xlsx', 'xls', 'csv'}
MAX_FILE_SIZE = 10 * 1024 * 1024  # 10MB


def validate_date_params(date_params=None, required=False):
    """
    Decorador para validar parámetros de fecha en query params

    Args:
        date_params: Lista de nombres de parámetros de fecha a validar
                    Por defecto: ['date', 'start_date', 'end_date']
        required: Si True, los parámetros son obligatorios

    Usage:
        @app.route('/api/sales')
        @validate_date_params(['start_date', 'end_date'], required=True)
        def get_sales():
            ...
    """
    if date_params is None:
        date_params = ['date', 'start_date', 'end_date']

    def decorator(f):
        @wraps(f)
        def decorated(*args, **kwargs):
            errors = []

            for param in date_params:
                value = request.args.get(param)

                if not value:
                    if required:
                        errors.append(f"El parámetro '{param}' es requerido")
                    continue

                # Validar formato de fecha (YYYY-MM-DD)
                try:
                    parsed_date = datetime.strptime(value, '%Y-%m-%d').date()

                    # Validar que la fecha no sea futura
                    if parsed_date > date.today():
                        errors.append(
                            f"El parámetro '{param}' no puede ser una fecha futura"
                        )

                    # Validar rango razonable (no antes de 2020)
                    if parsed_date.year < 2020:
                        errors.append(
                            f"El parámetro '{param}' debe ser posterior a 2020"
                        )

                except ValueError:
                    errors.append(
                        f"El parámetro '{param}' tiene formato inválido. "
                        f"Use YYYY-MM-DD"
                    )

            # Validar que start_date <= end_date si ambos están presentes
            start = request.args.get('start_date')
            end = request.args.get('end_date')

            if start and end:
                try:
                    start_date = datetime.strptime(start, '%Y-%m-%d').date()
                    end_date = datetime.strptime(end, '%Y-%m-%d').date()

                    if start_date > end_date:
                        errors.append(
                            "La fecha de inicio no puede ser posterior a "
                            "la fecha de fin"
                        )
                except ValueError:
                    pass  # Ya se validó arriba

            if errors:
                return jsonify({
                    'success': False,
                    'message': 'Errores de validación',
                    'errors': errors
                }), 400

            return f(*args, **kwargs)
        return decorated
    return decorator


def validate_file_upload(
    file_param='file',
    allowed_extensions=None,
    max_size=None,
    required=True
):
    """
    Decorador para validar archivos subidos

    Args:
        file_param: Nombre del parámetro del archivo en el request
        allowed_extensions: Set de extensiones permitidas
        max_size: Tamaño máximo en bytes
        required: Si True, el archivo es obligatorio

    Usage:
        @app.route('/api/upload', methods=['POST'])
        @validate_file_upload('inventory_file', {'xlsx', 'csv'}, 5*1024*1024)
        def upload_inventory():
            ...
    """
    if allowed_extensions is None:
        allowed_extensions = ALLOWED_FILE_EXTENSIONS
    if max_size is None:
        max_size = MAX_FILE_SIZE

    def decorator(f):
        @wraps(f)
        def decorated(*args, **kwargs):
            # Verificar que es multipart/form-data
            if 'multipart/form-data' not in request.content_type:
                if required:
                    return jsonify({
                        'success': False,
                        'message': 'Se esperaba contenido multipart/form-data'
                    }), 400
                return f(*args, **kwargs)

            # Verificar presencia del archivo
            if file_param not in request.files:
                if required:
                    return jsonify({
                        'success': False,
                        'message': f"No se encontró el archivo '{file_param}'"
                    }), 400
                return f(*args, **kwargs)

            file = request.files[file_param]

            # Verificar que se seleccionó un archivo
            if file.filename == '':
                if required:
                    return jsonify({
                        'success': False,
                        'message': 'No se seleccionó ningún archivo'
                    }), 400
                return f(*args, **kwargs)

            # Validar extensión
            if '.' not in file.filename:
                return jsonify({
                    'success': False,
                    'message': 'El archivo debe tener una extensión'
                }), 400

            ext = file.filename.rsplit('.', 1)[1].lower()
            if ext not in allowed_extensions:
                return jsonify({
                    'success': False,
                    'message': f"Extensión no permitida. "
                               f"Extensiones válidas: {', '.join(allowed_extensions)}"
                }), 400

            # Validar tamaño
            file.seek(0, 2)  # Ir al final del archivo
            file_size = file.tell()
            file.seek(0)  # Volver al inicio

            if file_size > max_size:
                max_size_mb = max_size / (1024 * 1024)
                return jsonify({
                    'success': False,
                    'message': f"El archivo excede el tamaño máximo permitido "
                               f"({max_size_mb:.1f} MB)"
                }), 400

            if file_size == 0:
                return jsonify({
                    'success': False,
                    'message': 'El archivo está vacío'
                }), 400

            return f(*args, **kwargs)
        return decorated
    return decorator


def validate_json_body(schema_class):
    """
    Decorador para validar el cuerpo JSON usando un modelo Pydantic

    Args:
        schema_class: Clase Pydantic para validar el body

    Usage:
        @app.route('/api/users', methods=['POST'])
        @validate_json_body(UserCreateRequest)
        def create_user():
            ...
    """
    def decorator(f):
        @wraps(f)
        def decorated(*args, **kwargs):
            if not request.is_json:
                return jsonify({
                    'success': False,
                    'message': 'Se esperaba contenido JSON'
                }), 400

            try:
                data = request.get_json()
                if not data:
                    return jsonify({
                        'success': False,
                        'message': 'No se recibieron datos JSON'
                    }), 400

                # Validar con Pydantic
                validated = schema_class(**data)

                # Guardar los datos validados en el request
                request.validated_data = validated

            except Exception as e:
                error_msg = str(e)
                # Formatear errores de Pydantic
                if 'validation error' in error_msg.lower():
                    return jsonify({
                        'success': False,
                        'message': 'Errores de validación',
                        'errors': error_msg
                    }), 400
                return jsonify({
                    'success': False,
                    'message': f'Error de validación: {error_msg}'
                }), 400

            return f(*args, **kwargs)
        return decorated
    return decorator


def validate_pagination_params(max_limit=100, default_limit=20):
    """
    Decorador para validar parámetros de paginación

    Args:
        max_limit: Límite máximo permitido por página
        default_limit: Límite por defecto si no se especifica

    Usage:
        @app.route('/api/items')
        @validate_pagination_params(max_limit=50)
        def get_items():
            page = request.args.get('page', 1, type=int)
            limit = request.args.get('limit', 20, type=int)
            ...
    """
    def decorator(f):
        @wraps(f)
        def decorated(*args, **kwargs):
            errors = []

            # Validar page
            page = request.args.get('page', '1')
            try:
                page = int(page)
                if page < 1:
                    errors.append("El parámetro 'page' debe ser mayor a 0")
            except ValueError:
                errors.append("El parámetro 'page' debe ser un número entero")

            # Validar limit
            limit = request.args.get('limit', str(default_limit))
            try:
                limit = int(limit)
                if limit < 1:
                    errors.append("El parámetro 'limit' debe ser mayor a 0")
                elif limit > max_limit:
                    errors.append(
                        f"El parámetro 'limit' no puede exceder {max_limit}"
                    )
            except ValueError:
                errors.append("El parámetro 'limit' debe ser un número entero")

            if errors:
                return jsonify({
                    'success': False,
                    'message': 'Errores de validación',
                    'errors': errors
                }), 400

            return f(*args, **kwargs)
        return decorated
    return decorator


def sanitize_string(value, max_length=255, allow_html=False):
    """
    Función helper para sanitizar strings

    Args:
        value: String a sanitizar
        max_length: Longitud máxima permitida
        allow_html: Si permite tags HTML

    Returns:
        String sanitizado
    """
    if not value:
        return ''

    # Convertir a string si no lo es
    value = str(value)

    # Remover tags HTML si no están permitidos
    if not allow_html:
        value = re.sub(r'<[^>]+>', '', value)

    # Truncar a longitud máxima
    value = value[:max_length]

    # Strip whitespace
    value = value.strip()

    return value


def validate_email_format(email):
    """
    Valida el formato de un email

    Args:
        email: String con el email

    Returns:
        bool: True si el formato es válido
    """
    if not email:
        return False
    pattern = r'^[^\s@]+@[^\s@]+\.[^\s@]+$'
    return bool(re.match(pattern, email))


def validate_password_strength(password):
    """
    Valida la fortaleza de una contraseña

    Args:
        password: String con la contraseña

    Returns:
        tuple: (is_valid, error_message)
    """
    if not password:
        return False, "La contraseña es requerida"

    if len(password) < 8:
        return False, "La contraseña debe tener al menos 8 caracteres"

    if len(password) > 128:
        return False, "La contraseña no puede exceder 128 caracteres"

    if not re.search(r'[A-Z]', password):
        return False, "La contraseña debe contener al menos una mayúscula"

    if not re.search(r'[a-z]', password):
        return False, "La contraseña debe contener al menos una minúscula"

    if not re.search(r'\d', password):
        return False, "La contraseña debe contener al menos un número"

    return True, None
