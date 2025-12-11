"""
Rutas de autenticación
Credenciales hardcodeadas (sin base de datos)
"""
from flask import Blueprint, request, jsonify, current_app
import bcrypt
import re
import logging
from datetime import datetime

from app.services.jwt_service import JWTService

logger = logging.getLogger(__name__)

bp = Blueprint('auth', __name__)

# ===================================
# CREDENCIALES HARDCODEADAS
# ===================================
# Diccionario de usuarios con sus credenciales y roles
USERS = {
    'ventaspuertocarreno@gmail.com': {
        'password': 'VentasCarreno2025.*',
        'name': 'Usuario Ventas Puerto Carreño',
        'role': 'sales'
    },
    'koaj.puertocarreno@gmail.com': {
        'password': 'Koaj.2025*',
        'name': 'Administrador KOAJ',
        'role': 'admin'
    }
}

# Control de intentos fallidos (en memoria)
failed_attempts = {}
locked_until = {}


def validate_email(email: str) -> bool:
    """Valida el formato del email"""
    pattern = r'^[^\s@]+@[^\s@]+\.[^\s@]+$'
    return bool(re.match(pattern, email))


def validate_password(password: str) -> bool:
    """Valida la longitud del password"""
    return 8 <= len(password) <= 128


def is_account_locked(email: str) -> bool:
    """Verifica si la cuenta está bloqueada"""
    if email not in locked_until:
        return False
    if datetime.utcnow() < locked_until[email]:
        return True
    # Si ya pasó el tiempo, desbloquear
    del locked_until[email]
    if email in failed_attempts:
        del failed_attempts[email]
    return False


def increment_failed_attempts(email: str) -> int:
    """Incrementa y retorna el número de intentos fallidos"""
    if email not in failed_attempts:
        failed_attempts[email] = 0
    failed_attempts[email] += 1
    return failed_attempts[email]


def lock_account(email: str, minutes: int = 15):
    """Bloquea la cuenta por un tiempo determinado"""
    from datetime import timedelta
    locked_until[email] = datetime.utcnow() + timedelta(minutes=minutes)


def reset_failed_attempts(email: str):
    """Resetea los intentos fallidos"""
    if email in failed_attempts:
        del failed_attempts[email]
    if email in locked_until:
        del locked_until[email]


@bp.route('/login', methods=['POST', 'OPTIONS'])
def login():
    """
    Endpoint de autenticación
    ---
    tags:
      - Autenticación
    parameters:
      - name: body
        in: body
        required: true
        schema:
          type: object
          required:
            - email
            - password
          properties:
            email:
              type: string
              example: ventaspuertocarreno@gmail.com
            password:
              type: string
              example: VentasCarreno2025.*
    responses:
      200:
        description: Login exitoso
        schema:
          type: object
          properties:
            success:
              type: boolean
              example: true
            token:
              type: string
              example: eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...
            user:
              type: object
              properties:
                email:
                  type: string
                name:
                  type: string
                role:
                  type: string
      400:
        description: Datos de entrada inválidos
      401:
        description: Credenciales incorrectas
      403:
        description: Cuenta bloqueada
      500:
        description: Error interno del servidor
    """
    # Manejar preflight CORS
    if request.method == 'OPTIONS':
        return '', 204

    try:
        data = request.get_json()

        if not data:
            return jsonify({
                'success': False,
                'message': 'No se recibieron datos'
            }), 400

        email = data.get('email', '').strip().lower()
        password = data.get('password', '')

        # Validaciones básicas
        if not email or not password:
            return jsonify({
                'success': False,
                'message': 'Email y contraseña son requeridos'
            }), 400

        if not validate_email(email):
            logger.warning(f"Intento de login con email inválido: {email} - IP: {request.remote_addr}")
            return jsonify({
                'success': False,
                'message': 'Formato de email inválido'
            }), 400

        if not validate_password(password):
            return jsonify({
                'success': False,
                'message': 'La contraseña debe tener entre 8 y 128 caracteres'
            }), 400

        # Verificar si la cuenta está bloqueada
        if is_account_locked(email):
            logger.warning(f"Intento de login en cuenta bloqueada: {email} - IP: {request.remote_addr}")
            return jsonify({
                'success': False,
                'message': 'Cuenta bloqueada temporalmente. Intente más tarde.'
            }), 403

        # Verificar credenciales contra el diccionario de usuarios
        max_attempts = current_app.config.get('MAX_LOGIN_ATTEMPTS', 5)
        lockout_time = current_app.config.get('LOCKOUT_TIME_MINUTES', 15)

        # Buscar usuario en el diccionario
        user_data = USERS.get(email)
        
        # Validar que el usuario existe y la contraseña coincide
        if not user_data or user_data['password'] != password:
            # Incrementar intentos fallidos
            attempts = increment_failed_attempts(email)

            if attempts >= max_attempts:
                lock_account(email, minutes=lockout_time)
                logger.warning(
                    f"Cuenta bloqueada por múltiples intentos fallidos: {email} "
                    f"- IP: {request.remote_addr}"
                )
                return jsonify({
                    'success': False,
                    'message': f'Cuenta bloqueada por {lockout_time} minutos debido a múltiples intentos fallidos'
                }), 403

            logger.warning(
                f"Login fallido - Credenciales incorrectas: {email} "
                f"- Intentos: {attempts}/{max_attempts} - IP: {request.remote_addr}"
            )

            return jsonify({
                'success': False,
                'message': f'Credenciales incorrectas ({attempts}/{max_attempts} intentos)'
            }), 401

        # Login exitoso - Resetear intentos fallidos
        reset_failed_attempts(email)

        # Obtener datos del usuario autenticado
        user_id = 1 if user_data['role'] == 'sales' else 2  # IDs distintos para cada usuario
        user_role = user_data['role']
        user_name = user_data['name']

        # Generar token JWT
        token = JWTService.generate_token(
            user_id=user_id,
            email=email,
            role=user_role
        )

        logger.info(
            f"Login exitoso: {email} (rol: {user_role}) - IP: {request.remote_addr} "
            f"- Timestamp: {datetime.utcnow().isoformat()}"
        )

        return jsonify({
            'success': True,
            'token': token,
            'user': {
                'email': email,
                'name': user_name,
                'role': user_role
            }
        }), 200

    except Exception as e:
        logger.error(f"Error en login: {str(e)} - IP: {request.remote_addr}")
        return jsonify({
            'success': False,
            'message': 'Error interno del servidor'
        }), 500


@bp.route('/verify', methods=['GET', 'OPTIONS'])
def verify_token():
    """
    Verifica si el token es válido
    ---
    tags:
      - Autenticación
    parameters:
      - name: Authorization
        in: header
        type: string
        required: true
        description: Bearer token
    responses:
      200:
        description: Token válido
      401:
        description: Token inválido o expirado
    """
    from app.middlewares.auth import token_required, get_current_user

    @token_required
    def _verify():
        user = get_current_user()
        return jsonify({
            'success': True,
            'message': 'Token válido',
            'user': user
        }), 200

    return _verify()
