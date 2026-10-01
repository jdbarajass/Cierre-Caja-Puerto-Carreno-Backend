"""
Multi-tienda: tiendas disponibles para el usuario actual (alimenta el
selector de tienda del frontend). Ver app/stores.py.
"""
from flask import Blueprint, jsonify, request

from app.middlewares.auth import token_required, get_current_user
from app.stores import get_current_store, get_store_info, stores_for_user

bp = Blueprint('stores', __name__)


@bp.route('/api/stores', methods=['GET', 'OPTIONS'])
@token_required
def list_user_stores():
    if request.method == 'OPTIONS':
        return '', 204

    codes = stores_for_user(get_current_user())
    return jsonify({
        'success': True,
        'stores': [get_store_info(code) for code in codes],
        'current_store': get_current_store(),
        'default_store': codes[0],
    }), 200
