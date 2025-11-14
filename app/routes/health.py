"""
Health check endpoint
"""
from flask import Blueprint, jsonify, current_app
from flasgger import swag_from

from app.config import Config
from app.services.alegra_client import AlegraClient

bp = Blueprint('health', __name__)


@bp.route('/health', methods=['GET'])
def health_check():
    """
    Health check endpoint para monitoreo
    ---
    tags:
      - Health
    responses:
      200:
        description: Servicio saludable
        schema:
          type: object
          properties:
            status:
              type: string
              example: healthy
            service:
              type: string
              example: cierre-caja-api
            version:
              type: string
              example: 2.0.0
            alegra:
              type: string
              example: connected
    """
    status = {
        "status": "healthy",
        "service": "cierre-caja-api",
        "version": "2.0.0"
    }

    # Check opcional de Alegra (sin bloquear)
    try:
        if Config.ALEGRA_USER and Config.ALEGRA_PASS:
            client = AlegraClient(
                Config.ALEGRA_USER,
                Config.ALEGRA_PASS,
                Config.ALEGRA_API_BASE_URL,
                timeout=5
            )
            is_healthy = client.health_check()
            status["alegra"] = "connected" if is_healthy else "disconnected"
        else:
            status["alegra"] = "not_configured"
    except Exception as e:
        current_app.logger.warning(f"Error en health check de Alegra: {e}")
        status["alegra"] = "error"
        status["status"] = "degraded"

    return jsonify(status), 200


@bp.route('/', methods=['GET'])
def root():
    """
    Root endpoint - información básica
    ---
    tags:
      - Info
    responses:
      200:
        description: Información del servicio
    """
    return jsonify({
        "service": "API Cierre de Caja KOAJ - Puerto Carreño",
        "version": "2.0.0",
        "status": "running",
        "documentation": "/api/docs",
        "endpoints": {
            "health": "/health",
            "sum_payments": "/sum_payments (POST)"
        }
    }), 200
