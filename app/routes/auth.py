"""
Rutas de autenticacion
Autenticacion basada en base de datos con bcrypt
"""
from flask import Blueprint, request, jsonify, current_app
import bcrypt
import re
import logging
from datetime import datetime

from app.services.jwt_service import JWTService
from app.models.user import db, User

logger = logging.getLogger(__name__)

bp = Blueprint('auth', __name__)


def validate_email(email: str) -> bool:
    """Valida el formato del email"""
    pattern = r'^[^\s@]+@[^\s@]+\.[^\s@]+$'
    return bool(re.match(pattern, email))


def validate_password(password: str) -> bool:
    """Valida la longitud del password"""
    return 8 <= len(password) <= 128


@bp.route('/login', methods=['POST', 'OPTIONS'])
def login():
    """
    Endpoint de autenticacion con base de datos
    ---
    tags:
      - Autenticacion
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
        description: Datos de entrada invalidos
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

        # Validaciones basicas
        if not email or not password:
            return jsonify({
                'success': False,
                'message': 'Email y contrasena son requeridos'
            }), 400

        if not validate_email(email):
            logger.warning(f"Intento de login con email invalido: {email} - IP: {request.remote_addr}")
            return jsonify({
                'success': False,
                'message': 'Formato de email invalido'
            }), 400

        if not validate_password(password):
            return jsonify({
                'success': False,
                'message': 'La contrasena debe tener entre 8 y 128 caracteres'
            }), 400

        # Buscar usuario en la base de datos
        user = User.query.filter_by(email=email).first()

        if not user:
            logger.warning(f"Usuario no existe: {email} - IP: {request.remote_addr}")
            return jsonify({
                'success': False,
                'message': 'Credenciales incorrectas'
            }), 401

        # Verificar cuenta activa
        if not user.is_active:
            logger.warning(f"Cuenta inactiva: {email} - IP: {request.remote_addr}")
            return jsonify({
                'success': False,
                'message': 'Cuenta inactiva. Contacte al administrador.'
            }), 403

        # Verificar si la cuenta esta bloqueada
        if user.is_locked():
            logger.warning(f"Intento de login en cuenta bloqueada: {email} - IP: {request.remote_addr}")
            return jsonify({
                'success': False,
                'message': 'Cuenta bloqueada temporalmente. Intente mas tarde.'
            }), 403

        # Verificar contrasena con bcrypt
        max_attempts = current_app.config.get('MAX_LOGIN_ATTEMPTS', 5)
        lockout_time = current_app.config.get('LOCKOUT_TIME_MINUTES', 15)

        if not bcrypt.checkpw(password.encode('utf-8'), user.password_hash.encode('utf-8')):
            # Incrementar intentos fallidos
            user.increment_failed_attempts()

            if user.failed_login_attempts >= max_attempts:
                user.lock_account(minutes=lockout_time)
                db.session.commit()
                logger.warning(
                    f"Cuenta bloqueada por multiples intentos fallidos: {email} "
                    f"- IP: {request.remote_addr}"
                )
                return jsonify({
                    'success': False,
                    'message': f'Cuenta bloqueada por {lockout_time} minutos debido a multiples intentos fallidos'
                }), 403

            db.session.commit()
            logger.warning(
                f"Login fallido - Contrasena incorrecta: {email} "
                f"- Intentos: {user.failed_login_attempts}/{max_attempts} - IP: {request.remote_addr}"
            )

            return jsonify({
                'success': False,
                'message': f'Credenciales incorrectas ({user.failed_login_attempts}/{max_attempts} intentos)'
            }), 401

        # Login exitoso - Resetear intentos fallidos
        user.reset_failed_attempts()
        db.session.commit()

        # Generar token JWT
        token = JWTService.generate_token(
            user_id=user.id,
            email=user.email,
            role=user.role
        )

        logger.info(
            f"Login exitoso: {user.email} (rol: {user.role}) - IP: {request.remote_addr} "
            f"- Timestamp: {datetime.utcnow().isoformat()}"
        )

        return jsonify({
            'success': True,
            'token': token,
            'user': {
                'email': user.email,
                'name': user.name,
                'role': user.role
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
    Verifica si el token es valido
    ---
    tags:
      - Autenticacion
    parameters:
      - name: Authorization
        in: header
        type: string
        required: true
        description: Bearer token
    responses:
      200:
        description: Token valido
      401:
        description: Token invalido o expirado
    """
    from app.middlewares.auth import token_required, get_current_user

    @token_required
    def _verify():
        user = get_current_user()
        return jsonify({
            'success': True,
            'message': 'Token valido',
            'user': user
        }), 200

    return _verify()
