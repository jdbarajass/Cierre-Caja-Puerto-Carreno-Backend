"""
Rutas de gestion de usuarios
Solo accesible para administradores
"""
from flask import Blueprint, request, jsonify, g
import bcrypt
import re
import logging
from datetime import datetime

from app.middlewares.auth import token_required, role_required, get_current_user
from app.models.user import db, User

logger = logging.getLogger(__name__)

bp = Blueprint('users', __name__)


def validate_email(email: str) -> bool:
    """Valida el formato del email"""
    pattern = r'^[^\s@]+@[^\s@]+\.[^\s@]+$'
    return bool(re.match(pattern, email))


def validate_password(password: str) -> tuple:
    """
    Valida la fortaleza del password
    Returns: (is_valid, error_message)
    """
    if len(password) < 8:
        return False, "La contrasena debe tener al menos 8 caracteres"
    if len(password) > 128:
        return False, "La contrasena no puede exceder 128 caracteres"
    if not re.search(r'[A-Z]', password):
        return False, "La contrasena debe contener al menos una mayuscula"
    if not re.search(r'[a-z]', password):
        return False, "La contrasena debe contener al menos una minuscula"
    if not re.search(r'\d', password):
        return False, "La contrasena debe contener al menos un numero"
    return True, None


@bp.route('/api/users', methods=['GET', 'OPTIONS'])
@token_required
@role_required('admin')
def list_users():
    """
    Listar todos los usuarios
    ---
    tags:
      - Usuarios
    security:
      - Bearer: []
    responses:
      200:
        description: Lista de usuarios
      401:
        description: No autorizado
      403:
        description: Sin permisos
    """
    if request.method == 'OPTIONS':
        return '', 204

    try:
        users = User.query.all()
        users_data = [{
            'id': u.id,
            'email': u.email,
            'name': u.name,
            'role': u.role,
            'is_active': u.is_active,
            'created_at': u.created_at.isoformat() if u.created_at else None
        } for u in users]

        return jsonify({
            'success': True,
            'users': users_data,
            'total': len(users_data)
        }), 200

    except Exception as e:
        logger.error(f"Error listando usuarios: {str(e)}")
        return jsonify({
            'success': False,
            'message': 'Error al obtener usuarios'
        }), 500


@bp.route('/api/users/<int:user_id>', methods=['GET', 'OPTIONS'])
@token_required
@role_required('admin')
def get_user(user_id):
    """
    Obtener un usuario por ID
    ---
    tags:
      - Usuarios
    security:
      - Bearer: []
    parameters:
      - name: user_id
        in: path
        type: integer
        required: true
    responses:
      200:
        description: Usuario encontrado
      404:
        description: Usuario no encontrado
    """
    if request.method == 'OPTIONS':
        return '', 204

    try:
        user = User.query.get(user_id)
        if not user:
            return jsonify({
                'success': False,
                'message': 'Usuario no encontrado'
            }), 404

        return jsonify({
            'success': True,
            'user': {
                'id': user.id,
                'email': user.email,
                'name': user.name,
                'role': user.role,
                'is_active': user.is_active,
                'created_at': user.created_at.isoformat() if user.created_at else None
            }
        }), 200

    except Exception as e:
        logger.error(f"Error obteniendo usuario {user_id}: {str(e)}")
        return jsonify({
            'success': False,
            'message': 'Error al obtener usuario'
        }), 500


@bp.route('/api/users', methods=['POST', 'OPTIONS'])
@token_required
@role_required('admin')
def create_user():
    """
    Crear un nuevo usuario
    ---
    tags:
      - Usuarios
    security:
      - Bearer: []
    parameters:
      - name: body
        in: body
        required: true
        schema:
          type: object
          required:
            - email
            - password
            - name
            - role
          properties:
            email:
              type: string
            password:
              type: string
            name:
              type: string
            role:
              type: string
              enum: [admin, sales]
    responses:
      201:
        description: Usuario creado exitosamente
      400:
        description: Datos invalidos
      409:
        description: Email ya existe
    """
    if request.method == 'OPTIONS':
        return '', 204

    try:
        data = request.get_json()

        if not data:
            return jsonify({
                'success': False,
                'message': 'No se recibieron datos'
            }), 400

        # Validar campos requeridos
        required_fields = ['email', 'password', 'name', 'role']
        for field in required_fields:
            if not data.get(field):
                return jsonify({
                    'success': False,
                    'message': f'El campo {field} es requerido'
                }), 400

        email = data['email'].strip().lower()
        password = data['password']
        name = data['name'].strip()
        role = data['role'].strip().lower()

        # Validar email
        if not validate_email(email):
            return jsonify({
                'success': False,
                'message': 'Formato de email invalido'
            }), 400

        # Validar password
        is_valid, error_msg = validate_password(password)
        if not is_valid:
            return jsonify({
                'success': False,
                'message': error_msg
            }), 400

        # Validar rol
        if role not in ['admin', 'sales']:
            return jsonify({
                'success': False,
                'message': 'Rol invalido. Debe ser admin o sales'
            }), 400

        # Verificar si el email ya existe
        existing_user = User.query.filter_by(email=email).first()
        if existing_user:
            return jsonify({
                'success': False,
                'message': 'El email ya esta registrado'
            }), 409

        # Hashear la contrasena
        password_hash = bcrypt.hashpw(
            password.encode('utf-8'),
            bcrypt.gensalt()
        ).decode('utf-8')

        # Crear usuario
        new_user = User(
            email=email,
            password_hash=password_hash,
            name=name,
            role=role,
            is_active=True
        )

        db.session.add(new_user)
        db.session.commit()

        current_user = get_current_user()
        logger.info(
            f"Usuario creado: {email} por {current_user.get('email')} "
            f"- IP: {request.remote_addr}"
        )

        return jsonify({
            'success': True,
            'message': 'Usuario creado exitosamente',
            'user': {
                'id': new_user.id,
                'email': new_user.email,
                'name': new_user.name,
                'role': new_user.role,
                'is_active': new_user.is_active
            }
        }), 201

    except Exception as e:
        db.session.rollback()
        logger.error(f"Error creando usuario: {str(e)}")
        return jsonify({
            'success': False,
            'message': 'Error al crear usuario'
        }), 500


@bp.route('/api/users/<int:user_id>', methods=['PUT', 'OPTIONS'])
@token_required
@role_required('admin')
def update_user(user_id):
    """
    Actualizar un usuario
    ---
    tags:
      - Usuarios
    security:
      - Bearer: []
    parameters:
      - name: user_id
        in: path
        type: integer
        required: true
      - name: body
        in: body
        schema:
          type: object
          properties:
            email:
              type: string
            name:
              type: string
            role:
              type: string
            is_active:
              type: boolean
    responses:
      200:
        description: Usuario actualizado
      404:
        description: Usuario no encontrado
    """
    if request.method == 'OPTIONS':
        return '', 204

    try:
        user = User.query.get(user_id)
        if not user:
            return jsonify({
                'success': False,
                'message': 'Usuario no encontrado'
            }), 404

        data = request.get_json()
        if not data:
            return jsonify({
                'success': False,
                'message': 'No se recibieron datos'
            }), 400

        # Actualizar campos si estan presentes
        if 'email' in data and data['email']:
            new_email = data['email'].strip().lower()
            if not validate_email(new_email):
                return jsonify({
                    'success': False,
                    'message': 'Formato de email invalido'
                }), 400

            # Verificar que el email no este en uso por otro usuario
            existing = User.query.filter(
                User.email == new_email,
                User.id != user_id
            ).first()
            if existing:
                return jsonify({
                    'success': False,
                    'message': 'El email ya esta en uso'
                }), 409
            user.email = new_email

        if 'name' in data and data['name']:
            user.name = data['name'].strip()

        if 'role' in data and data['role']:
            role = data['role'].strip().lower()
            if role not in ['admin', 'sales']:
                return jsonify({
                    'success': False,
                    'message': 'Rol invalido'
                }), 400
            user.role = role

        if 'is_active' in data:
            user.is_active = bool(data['is_active'])

        db.session.commit()

        current_user = get_current_user()
        logger.info(
            f"Usuario actualizado: {user.email} por {current_user.get('email')} "
            f"- IP: {request.remote_addr}"
        )

        return jsonify({
            'success': True,
            'message': 'Usuario actualizado exitosamente',
            'user': {
                'id': user.id,
                'email': user.email,
                'name': user.name,
                'role': user.role,
                'is_active': user.is_active
            }
        }), 200

    except Exception as e:
        db.session.rollback()
        logger.error(f"Error actualizando usuario {user_id}: {str(e)}")
        return jsonify({
            'success': False,
            'message': 'Error al actualizar usuario'
        }), 500


@bp.route('/api/users/<int:user_id>', methods=['DELETE', 'OPTIONS'])
@token_required
@role_required('admin')
def delete_user(user_id):
    """
    Desactivar un usuario (soft delete)
    ---
    tags:
      - Usuarios
    security:
      - Bearer: []
    parameters:
      - name: user_id
        in: path
        type: integer
        required: true
    responses:
      200:
        description: Usuario desactivado
      404:
        description: Usuario no encontrado
    """
    if request.method == 'OPTIONS':
        return '', 204

    try:
        user = User.query.get(user_id)
        if not user:
            return jsonify({
                'success': False,
                'message': 'Usuario no encontrado'
            }), 404

        # No permitir auto-desactivacion
        current_user = get_current_user()
        if user.id == current_user.get('userId'):
            return jsonify({
                'success': False,
                'message': 'No puede desactivar su propia cuenta'
            }), 400

        # Soft delete - solo desactivar
        user.is_active = False
        db.session.commit()

        logger.info(
            f"Usuario desactivado: {user.email} por {current_user.get('email')} "
            f"- IP: {request.remote_addr}"
        )

        return jsonify({
            'success': True,
            'message': 'Usuario desactivado exitosamente'
        }), 200

    except Exception as e:
        db.session.rollback()
        logger.error(f"Error desactivando usuario {user_id}: {str(e)}")
        return jsonify({
            'success': False,
            'message': 'Error al desactivar usuario'
        }), 500


@bp.route('/api/users/change-password', methods=['POST', 'OPTIONS'])
@token_required
def change_own_password():
    """
    Cambiar la contrasena propia del usuario autenticado
    ---
    tags:
      - Usuarios
    security:
      - Bearer: []
    parameters:
      - name: body
        in: body
        required: true
        schema:
          type: object
          required:
            - current_password
            - new_password
          properties:
            current_password:
              type: string
            new_password:
              type: string
    responses:
      200:
        description: Contrasena cambiada exitosamente
      400:
        description: Contrasena actual incorrecta o nueva contrasena invalida
    """
    if request.method == 'OPTIONS':
        return '', 204

    try:
        data = request.get_json()
        if not data:
            return jsonify({
                'success': False,
                'message': 'No se recibieron datos'
            }), 400

        current_password = data.get('current_password')
        new_password = data.get('new_password')

        if not current_password or not new_password:
            return jsonify({
                'success': False,
                'message': 'Contrasena actual y nueva son requeridas'
            }), 400

        # Validar nueva contrasena
        is_valid, error_msg = validate_password(new_password)
        if not is_valid:
            return jsonify({
                'success': False,
                'message': error_msg
            }), 400

        current_user = get_current_user()
        user = User.query.get(current_user.get('userId'))

        if not user:
            return jsonify({
                'success': False,
                'message': 'Usuario no encontrado'
            }), 404

        # Verificar contrasena actual
        if not bcrypt.checkpw(
            current_password.encode('utf-8'),
            user.password_hash.encode('utf-8')
        ):
            return jsonify({
                'success': False,
                'message': 'Contrasena actual incorrecta'
            }), 400

        # Actualizar contrasena
        user.password_hash = bcrypt.hashpw(
            new_password.encode('utf-8'),
            bcrypt.gensalt()
        ).decode('utf-8')

        db.session.commit()

        logger.info(
            f"Contrasena cambiada: {user.email} - IP: {request.remote_addr}"
        )

        return jsonify({
            'success': True,
            'message': 'Contrasena actualizada exitosamente'
        }), 200

    except Exception as e:
        db.session.rollback()
        logger.error(f"Error cambiando contrasena: {str(e)}")
        return jsonify({
            'success': False,
            'message': 'Error al cambiar contrasena'
        }), 500


@bp.route('/api/users/<int:user_id>/reset-password', methods=['POST', 'OPTIONS'])
@token_required
@role_required('admin')
def reset_password(user_id):
    """
    Resetear la contrasena de un usuario (solo admin)
    ---
    tags:
      - Usuarios
    security:
      - Bearer: []
    parameters:
      - name: user_id
        in: path
        type: integer
        required: true
      - name: body
        in: body
        required: true
        schema:
          type: object
          required:
            - new_password
          properties:
            new_password:
              type: string
    responses:
      200:
        description: Contrasena reseteada exitosamente
      404:
        description: Usuario no encontrado
    """
    if request.method == 'OPTIONS':
        return '', 204

    try:
        user = User.query.get(user_id)
        if not user:
            return jsonify({
                'success': False,
                'message': 'Usuario no encontrado'
            }), 404

        data = request.get_json()
        if not data or not data.get('new_password'):
            return jsonify({
                'success': False,
                'message': 'Nueva contrasena es requerida'
            }), 400

        new_password = data['new_password']

        # Validar nueva contrasena
        is_valid, error_msg = validate_password(new_password)
        if not is_valid:
            return jsonify({
                'success': False,
                'message': error_msg
            }), 400

        # Actualizar contrasena
        user.password_hash = bcrypt.hashpw(
            new_password.encode('utf-8'),
            bcrypt.gensalt()
        ).decode('utf-8')

        # Resetear intentos fallidos y desbloquear
        user.failed_login_attempts = 0
        user.locked_until = None

        db.session.commit()

        current_user = get_current_user()
        logger.info(
            f"Contrasena reseteada para {user.email} por {current_user.get('email')} "
            f"- IP: {request.remote_addr}"
        )

        return jsonify({
            'success': True,
            'message': 'Contrasena reseteada exitosamente'
        }), 200

    except Exception as e:
        db.session.rollback()
        logger.error(f"Error reseteando contrasena para usuario {user_id}: {str(e)}")
        return jsonify({
            'success': False,
            'message': 'Error al resetear contrasena'
        }), 500
