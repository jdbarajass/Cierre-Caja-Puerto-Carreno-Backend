"""
Rutas para códigos y precios KOAJ
Accesible para todos los usuarios autenticados (admin y sales)
"""
from flask import Blueprint, request, jsonify
import logging

from app.middlewares.auth import token_required, role_required
from app.models.user import db
from app.models.koaj_code import KoajCode

logger = logging.getLogger(__name__)

bp = Blueprint('koaj_codes', __name__)


# Guía de lectura de códigos de barras KOAJ
BARCODE_GUIDE = {
    'structure': '10 / GÉNERO / CÓDIGO / PRECIO / TALLA',
    'example': {
        'barcode': '1051421099032',
        'breakdown': {
            'prefix': '10',
            'gender': '51',
            'category_code': '42',
            'price': '10990',
            'size': '32'
        },
        'interpretation': {
            'prefix': 'Prefijo estándar KOAJ',
            'gender': 'Hombre',
            'category': 'Bermudas',
            'price': '$109,900',
            'size': 'Talla 32'
        }
    },
    'gender_prefixes': [
        {'code': '1051', 'gender': 'Hombre'},
        {'code': '1052', 'gender': 'Mujer'},
        {'code': '1053', 'gender': 'Niño'},
        {'code': '1054', 'gender': 'Niña'}
    ],
    'size_codes': [
        {'code': '1', 'size': 'XS'},
        {'code': '2', 'size': 'S'},
        {'code': '3', 'size': 'M'},
        {'code': '4', 'size': 'L'},
        {'code': '5', 'size': 'XL'},
        {'code': '6', 'size': '2XL'},
        {'code': '28', 'size': 'Talla 28'},
        {'code': '30', 'size': 'Talla 30'},
        {'code': '32', 'size': 'Talla 32'},
        {'code': '34', 'size': 'Talla 34'},
        {'code': '36', 'size': 'Talla 36'},
        {'code': '38', 'size': 'Talla 38'},
        {'code': '40', 'size': 'Talla 40'}
    ],
    'notes': [
        'El prefijo 10 es estándar para todos los productos KOAJ',
        'El precio se lee en centenas (10990 = $109,900)',
        'Las tallas numéricas (28-40) se usan principalmente para pantalones',
        'Las tallas alfabéticas (1-6) corresponden a XS-2XL'
    ]
}


@bp.route('/api/koaj-codes', methods=['GET', 'OPTIONS'])
@token_required
def list_koaj_codes():
    """
    Listar todos los códigos KOAJ
    ---
    tags:
      - Códigos KOAJ
    security:
      - Bearer: []
    parameters:
      - name: search
        in: query
        type: string
        required: false
        description: Buscar por código o categoría
      - name: applies_to
        in: query
        type: string
        required: false
        description: Filtrar por género (hombre, mujer, niño, niña, todos)
    responses:
      200:
        description: Lista de códigos KOAJ
      401:
        description: No autorizado
    """
    if request.method == 'OPTIONS':
        return '', 204

    try:
        query = KoajCode.query.filter_by(is_active=True)

        # Filtrar por búsqueda
        search = request.args.get('search', '').strip()
        if search:
            search_pattern = f'%{search}%'
            query = query.filter(
                db.or_(
                    KoajCode.code.ilike(search_pattern),
                    KoajCode.category.ilike(search_pattern)
                )
            )

        # Filtrar por género
        applies_to = request.args.get('applies_to', '').strip().lower()
        if applies_to and applies_to != 'todos':
            query = query.filter(
                db.or_(
                    KoajCode.applies_to == applies_to,
                    KoajCode.applies_to == 'todos'
                )
            )

        # Ordenar por código numérico
        codes = query.order_by(KoajCode.code.cast(db.Integer)).all()

        return jsonify({
            'success': True,
            'codes': [code.to_dict() for code in codes],
            'total': len(codes)
        }), 200

    except Exception as e:
        logger.error(f"Error listando códigos KOAJ: {str(e)}")
        return jsonify({
            'success': False,
            'message': 'Error al obtener códigos KOAJ'
        }), 500


@bp.route('/api/koaj-codes/guide', methods=['GET', 'OPTIONS'])
@token_required
def get_code_guide():
    """
    Obtener guía de lectura de códigos de barras KOAJ
    ---
    tags:
      - Códigos KOAJ
    security:
      - Bearer: []
    responses:
      200:
        description: Guía de interpretación de códigos
      401:
        description: No autorizado
    """
    if request.method == 'OPTIONS':
        return '', 204

    return jsonify({
        'success': True,
        'guide': BARCODE_GUIDE
    }), 200


@bp.route('/api/koaj-codes', methods=['POST', 'OPTIONS'])
@token_required
@role_required('admin')
def create_koaj_code():
    """
    Crear un nuevo código KOAJ (solo admin)
    ---
    tags:
      - Códigos KOAJ
    security:
      - Bearer: []
    parameters:
      - name: body
        in: body
        required: true
        schema:
          type: object
          required:
            - code
            - category
          properties:
            code:
              type: string
            category:
              type: string
            description:
              type: string
            applies_to:
              type: string
              enum: [hombre, mujer, niño, niña, todos]
    responses:
      201:
        description: Código creado exitosamente
      400:
        description: Datos inválidos
      409:
        description: Código ya existe
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

        code = data.get('code', '').strip()
        category = data.get('category', '').strip()

        if not code or not category:
            return jsonify({
                'success': False,
                'message': 'Código y categoría son requeridos'
            }), 400

        # Verificar si el código ya existe
        existing = KoajCode.query.filter_by(code=code).first()
        if existing:
            return jsonify({
                'success': False,
                'message': f'El código {code} ya existe'
            }), 409

        new_code = KoajCode(
            code=code,
            category=category,
            description=data.get('description', '').strip() or None,
            applies_to=data.get('applies_to', 'todos').strip().lower()
        )

        db.session.add(new_code)
        db.session.commit()

        logger.info(f"Código KOAJ creado: {code} - {category}")

        return jsonify({
            'success': True,
            'message': 'Código creado exitosamente',
            'code': new_code.to_dict()
        }), 201

    except Exception as e:
        db.session.rollback()
        logger.error(f"Error creando código KOAJ: {str(e)}")
        return jsonify({
            'success': False,
            'message': 'Error al crear código'
        }), 500


@bp.route('/api/koaj-codes/<int:code_id>', methods=['PUT', 'OPTIONS'])
@token_required
@role_required('admin')
def update_koaj_code(code_id):
    """
    Actualizar un código KOAJ (solo admin)
    ---
    tags:
      - Códigos KOAJ
    security:
      - Bearer: []
    parameters:
      - name: code_id
        in: path
        type: integer
        required: true
      - name: body
        in: body
        schema:
          type: object
          properties:
            code:
              type: string
            category:
              type: string
            description:
              type: string
            applies_to:
              type: string
            is_active:
              type: boolean
    responses:
      200:
        description: Código actualizado
      404:
        description: Código no encontrado
    """
    if request.method == 'OPTIONS':
        return '', 204

    try:
        koaj_code = KoajCode.query.get(code_id)
        if not koaj_code:
            return jsonify({
                'success': False,
                'message': 'Código no encontrado'
            }), 404

        data = request.get_json()
        if not data:
            return jsonify({
                'success': False,
                'message': 'No se recibieron datos'
            }), 400

        if 'code' in data and data['code']:
            new_code = data['code'].strip()
            # Verificar que no exista otro código con el mismo valor
            existing = KoajCode.query.filter(
                KoajCode.code == new_code,
                KoajCode.id != code_id
            ).first()
            if existing:
                return jsonify({
                    'success': False,
                    'message': f'El código {new_code} ya está en uso'
                }), 409
            koaj_code.code = new_code

        if 'category' in data and data['category']:
            koaj_code.category = data['category'].strip()

        if 'description' in data:
            koaj_code.description = data['description'].strip() if data['description'] else None

        if 'applies_to' in data and data['applies_to']:
            koaj_code.applies_to = data['applies_to'].strip().lower()

        if 'is_active' in data:
            koaj_code.is_active = bool(data['is_active'])

        db.session.commit()

        logger.info(f"Código KOAJ actualizado: {koaj_code.code}")

        return jsonify({
            'success': True,
            'message': 'Código actualizado exitosamente',
            'code': koaj_code.to_dict()
        }), 200

    except Exception as e:
        db.session.rollback()
        logger.error(f"Error actualizando código KOAJ {code_id}: {str(e)}")
        return jsonify({
            'success': False,
            'message': 'Error al actualizar código'
        }), 500


@bp.route('/api/koaj-codes/<int:code_id>', methods=['DELETE', 'OPTIONS'])
@token_required
@role_required('admin')
def delete_koaj_code(code_id):
    """
    Desactivar un código KOAJ (soft delete - solo admin)
    ---
    tags:
      - Códigos KOAJ
    security:
      - Bearer: []
    parameters:
      - name: code_id
        in: path
        type: integer
        required: true
    responses:
      200:
        description: Código desactivado
      404:
        description: Código no encontrado
    """
    if request.method == 'OPTIONS':
        return '', 204

    try:
        koaj_code = KoajCode.query.get(code_id)
        if not koaj_code:
            return jsonify({
                'success': False,
                'message': 'Código no encontrado'
            }), 404

        koaj_code.is_active = False
        db.session.commit()

        logger.info(f"Código KOAJ desactivado: {koaj_code.code}")

        return jsonify({
            'success': True,
            'message': 'Código desactivado exitosamente'
        }), 200

    except Exception as e:
        db.session.rollback()
        logger.error(f"Error desactivando código KOAJ {code_id}: {str(e)}")
        return jsonify({
            'success': False,
            'message': 'Error al desactivar código'
        }), 500
