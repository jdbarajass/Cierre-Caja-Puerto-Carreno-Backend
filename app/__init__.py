"""
Sistema de Cierre de Caja - KOAJ Puerto Carreño
Flask Application Factory
"""
from flask import Flask, request
from flask_cors import CORS
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from flasgger import Swagger
import logging
import os

from app.config import Config
from app.exceptions import setup_error_handlers


def create_app(config_class=Config):
    """
    Factory para crear la aplicación Flask

    Args:
        config_class: Clase de configuración a usar

    Returns:
        app: Aplicación Flask configurada
    """
    app = Flask(__name__)
    app.config.from_object(config_class)

    # Configurar CORS - SOLUCIÓN MEJORADA Y ROBUSTA
    # Leer los orígenes permitidos de la configuración
    allowed_origins = config_class.ALLOWED_ORIGINS

    # Configurar CORS para todas las rutas de la API
    CORS(app, resources={
        r"/*": {
            "origins": allowed_origins,
            "methods": ["GET", "POST", "PUT", "DELETE", "OPTIONS", "PATCH"],
            "allow_headers": [
                "Content-Type",
                "Authorization",
                "Accept",
                "X-Requested-With",
                "X-HTTP-Method-Override",
                "Accept-Language",
                "Cache-Control"
            ],
            "expose_headers": [
                "Content-Type",
                "X-Total-Count",
                "X-Page",
                "X-Per-Page"
            ],
            "supports_credentials": True,  # Cambiado a True para cookies/auth
            "max_age": 3600
        }
    })

    # Agregar headers CORS manualmente en cada respuesta como backup
    @app.after_request
    def after_request(response):
        """Agregar headers CORS a todas las respuestas como medida de seguridad"""
        origin = request.headers.get('Origin')

        # Si el origen está en la lista permitida, agregarlo
        if origin in allowed_origins:
            response.headers['Access-Control-Allow-Origin'] = origin
            response.headers['Access-Control-Allow-Credentials'] = 'true'
            response.headers['Access-Control-Allow-Methods'] = 'GET, POST, PUT, DELETE, OPTIONS, PATCH'
            response.headers['Access-Control-Allow-Headers'] = 'Content-Type, Authorization, Accept, X-Requested-With, X-HTTP-Method-Override, Accept-Language, Cache-Control'
            response.headers['Access-Control-Expose-Headers'] = 'Content-Type, X-Total-Count, X-Page, X-Per-Page'
            response.headers['Access-Control-Max-Age'] = '3600'

        return response

    # Configurar Rate Limiting
    limiter = Limiter(
        app=app,
        key_func=get_remote_address,
        default_limits=["200 per day", "50 per hour"],
        storage_uri="memory://"
    )

    # Configurar Swagger
    swagger_config = {
        "headers": [],
        "specs": [
            {
                "endpoint": 'apispec',
                "route": '/apispec.json',
                "rule_filter": lambda rule: True,
                "model_filter": lambda tag: True,
            }
        ],
        "static_url_path": "/flasgger_static",
        "swagger_ui": True,
        "specs_route": "/api/docs",
        "title": "API Cierre de Caja KOAJ",
        "version": "2.0.0",
        "description": "API para procesar cierres de caja con integración Alegra"
    }
    Swagger(app, config=swagger_config)

    # Configurar logging
    setup_logging(app)

    # Registrar blueprints
    from app.routes.cash_closing import bp as cash_bp
    from app.routes.health import bp as health_bp

    app.register_blueprint(cash_bp, url_prefix='/api')
    app.register_blueprint(health_bp)

    # Configurar manejadores de errores
    setup_error_handlers(app)

    # Log de inicio
    app.logger.info("=" * 60)
    app.logger.info("Sistema de Cierre de Caja - KOAJ Puerto Carreño")
    app.logger.info(f"Versión: 2.0.0")
    app.logger.info(f"Ambiente: {'Producción' if not app.config['DEBUG'] else 'Desarrollo'}")
    app.logger.info(f"CORS Origins: {allowed_origins}")
    app.logger.info("=" * 60)

    return app


def setup_logging(app):
    """Configura el sistema de logging de la aplicación"""
    from logging.handlers import RotatingFileHandler

    log_level = logging.DEBUG if app.config['DEBUG'] else logging.INFO

    # Formato detallado para logs
    formatter = logging.Formatter(
        '[%(asctime)s] %(levelname)s en %(module)s.%(funcName)s:%(lineno)d - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )

    # Handler de consola (siempre activo)
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)
    console_handler.setLevel(log_level)
    app.logger.addHandler(console_handler)

    # Handler de archivo (solo si NO estamos en Render o similar)
    # En Render/Heroku los logs van a stdout
    if not os.environ.get('RENDER'):
        try:
            os.makedirs('logs', exist_ok=True)
            file_handler = RotatingFileHandler(
                'logs/cierre_caja.log',
                maxBytes=10240000,  # 10MB
                backupCount=10
            )
            file_handler.setFormatter(formatter)
            file_handler.setLevel(log_level)
            app.logger.addHandler(file_handler)
        except Exception as e:
            app.logger.warning(f"No se pudo crear archivo de log: {e}")

    app.logger.setLevel(log_level)

    # Reducir ruido de otros loggers
    logging.getLogger('werkzeug').setLevel(logging.WARNING)
    logging.getLogger('urllib3').setLevel(logging.WARNING)