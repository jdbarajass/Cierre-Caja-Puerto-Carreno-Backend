"""
Middleware de autenticación JWT
"""
from functools import wraps
from flask import request, jsonify, g
import jwt
import logging

from app.services.jwt_service import JWTService

logger = logging.getLogger(__name__)


def get_current_user():
    """Obtiene el usuario actual del contexto de la petición"""
    return getattr(g, 'current_user', None)


def token_required(f):
    """
    Decorador que requiere un token JWT válido para acceder al endpoint

    Usage:
        @app.route('/protected')
        @token_required
        def protected_route():
            user = get_current_user()
            return jsonify({'user': user})
    """
    @wraps(f)
    def decorated(*args, **kwargs):
        # IMPORTANTE: Permitir OPTIONS sin validación (CORS preflight)
        if request.method == 'OPTIONS':
            return '', 204  # Respuesta vacía exitosa para preflight

        token = None

        # PRIORIDAD 1: Intentar obtener el token de la cookie httpOnly
        token = request.cookies.get('access_token')

        # PRIORIDAD 2 (fallback): Obtener el token del header Authorization
        if not token:
            auth_header = request.headers.get('Authorization')

            if auth_header:
                # Formato esperado: "Bearer <token>"
                parts = auth_header.split()
                if len(parts) == 2 and parts[0].lower() == 'bearer':
                    token = parts[1]
                elif len(parts) == 1:
                    # Por si envían solo el token sin "Bearer"
                    token = parts[0]

        if not token:
            logger.warning(f"Token no proporcionado - IP: {request.remote_addr}")
            return jsonify({
                'success': False,
                'message': 'Token no proporcionado'
            }), 401

        try:
            # Verificar y decodificar el token
            payload = JWTService.verify_token(token)

            # Guardar la información del usuario en el contexto
            g.current_user = {
                'userId': payload.get('userId'),
                'email': payload.get('email'),
                'role': payload.get('role')
            }

            logger.debug(f"Token válido para usuario: {payload.get('email')}")

        except jwt.ExpiredSignatureError:
            logger.warning(f"Token expirado - IP: {request.remote_addr}")
            return jsonify({
                'success': False,
                'message': 'Token expirado. Por favor inicie sesión nuevamente.'
            }), 401

        except jwt.InvalidTokenError as e:
            logger.warning(f"Token inválido: {str(e)} - IP: {request.remote_addr}")
            return jsonify({
                'success': False,
                'message': 'Token inválido'
            }), 401

        except Exception as e:
            logger.error(f"Error validando token: {str(e)}")
            return jsonify({
                'success': False,
                'message': 'Error al validar token'
            }), 500

        return f(*args, **kwargs)

    return decorated


def role_required(required_role):
    """
    Decorador que requiere un rol específico

    Usage:
        @app.route('/admin')
        @token_required
        @role_required('admin')
        def admin_route():
            return jsonify({'message': 'Admin access granted'})
    """
    def decorator(f):
        @wraps(f)
        def decorated(*args, **kwargs):
            user = get_current_user()

            if not user:
                return jsonify({
                    'success': False,
                    'message': 'Usuario no autenticado'
                }), 401

            if user.get('role') != required_role:
                logger.warning(
                    f"Acceso denegado - Usuario: {user.get('email')} "
                    f"- Rol requerido: {required_role} - Rol actual: {user.get('role')}"
                )
                return jsonify({
                    'success': False,
                    'message': 'No tiene permisos para acceder a este recurso'
                }), 403

            return f(*args, **kwargs)
        return decorated
    return decorator


def role_required_any(allowed_roles):
    """
    Decorador que permite acceso si el usuario tiene cualquiera de los roles especificados

    Args:
        allowed_roles: Lista de roles permitidos (ej: ['admin', 'sales'])

    Usage:
        @app.route('/sales')
        @token_required
        @role_required_any(['admin', 'sales'])
        def sales_route():
            return jsonify({'message': 'Access granted'})
    """
    def decorator(f):
        @wraps(f)
        def decorated(*args, **kwargs):
            user = get_current_user()

            if not user:
                return jsonify({
                    'success': False,
                    'message': 'Usuario no autenticado'
                }), 401

            user_role = user.get('role')
            if user_role not in allowed_roles:
                logger.warning(
                    f"Acceso denegado - Usuario: {user.get('email')} "
                    f"- Roles permitidos: {', '.join(allowed_roles)} - Rol actual: {user_role}"
                )
                return jsonify({
                    'success': False,
                    'message': 'No tiene permisos para acceder a este recurso'
                }), 403

            return f(*args, **kwargs)
        return decorated
    return decorator
