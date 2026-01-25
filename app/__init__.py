"""
Sistema de Cierre de Caja - KOAJ Puerto Carreño
Flask Application Factory
"""
from flask import Flask, request, send_from_directory, send_file
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

    # Initialize SQLAlchemy database
    from app.models.user import db

    db.init_app(app)

    # Create tables if they don't exist
    with app.app_context():
        try:
            db.create_all()
            app.logger.info("Database tables created/verified successfully")
        except Exception as e:
            app.logger.error(f"Error creating database tables: {e}")

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
        default_limits=["50000 per day", "12000 per hour"],
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
    from app.routes.auth import bp as auth_bp
    from app.routes.products import bp as products_bp
    from app.routes.analytics import bp as analytics_bp
    from app.routes.inventory import bp as inventory_bp
    from app.routes.direct_api import bp as direct_api_bp

    app.register_blueprint(cash_bp, url_prefix='/api')
    app.register_blueprint(health_bp)
    app.register_blueprint(auth_bp, url_prefix='/auth')
    app.register_blueprint(products_bp)
    app.register_blueprint(analytics_bp)
    app.register_blueprint(inventory_bp)
    app.register_blueprint(direct_api_bp)  # APIs directas de Alegra

    # Configurar manejadores de errores
    setup_error_handlers(app)

    # Configurar servido del frontend (React SPA)
    # Determinar la ruta absoluta del directorio dist del frontend
    # Prioridad: 1) Variable de entorno FRONTEND_DIST_PATH, 2) Ruta relativa por defecto
    if config_class.FRONTEND_DIST_PATH:
        frontend_dist = config_class.FRONTEND_DIST_PATH
        app.logger.info(f"Usando frontend desde variable de entorno: {frontend_dist}")
    else:
        # Ruta por defecto en desarrollo local: ../cierre-caja-frontend/dist
        frontend_dist = os.path.join(os.path.dirname(os.path.dirname(__file__)), '..', 'cierre-caja-frontend', 'dist')
        frontend_dist = os.path.abspath(frontend_dist)
        app.logger.info(f"Usando frontend desde ruta relativa: {frontend_dist}")

    # Verificar si el directorio existe
    if not os.path.isdir(frontend_dist):
        app.logger.warning(f"ADVERTENCIA: Directorio del frontend no encontrado: {frontend_dist}")
        app.logger.warning("El servidor API funcionará, pero las rutas del frontend devolverán error 404")
        app.logger.warning("Configura la variable de entorno FRONTEND_DIST_PATH con la ruta correcta")

    # Servir archivos estáticos del frontend (JS, CSS, imágenes, etc.)
    @app.route('/assets/<path:path>')
    def serve_static_assets(path):
        """Sirve archivos estáticos (JS, CSS, etc.) desde la carpeta dist/assets"""
        try:
            return send_from_directory(os.path.join(frontend_dist, 'assets'), path)
        except Exception as e:
            app.logger.error(f"Error sirviendo asset {path}: {e}")
            return {"error": "Asset no encontrado"}, 404

    # Catch-all route: sirve index.html para todas las rutas que no sean de la API
    # Esto permite que React Router maneje el enrutamiento del lado del cliente
    @app.route('/', defaults={'path': ''})
    @app.route('/<path:path>')
    def serve_frontend(path):
        """
        Sirve el frontend React para todas las rutas no-API.
        Esto permite que React Router maneje la navegación del lado del cliente.
        """
        # Si la ruta es de la API, dejar que Flask la maneje (no debería llegar aquí)
        api_prefixes = [
            'api/', 'auth/', 'health', 'flasgger_static/',
            'apispec.json', 'api/docs', 'apidocs'
        ]
        if any(path.startswith(prefix) for prefix in api_prefixes):
            # Esto no debería ejecutarse ya que los blueprints tienen prioridad
            return {"error": "Ruta de API no encontrada"}, 404

        # Si la ruta apunta a un archivo específico que existe, servirlo
        if path and '.' in path:
            file_path = os.path.join(frontend_dist, path)
            if os.path.isfile(file_path):
                try:
                    return send_file(file_path)
                except Exception as e:
                    app.logger.error(f"Error sirviendo archivo {path}: {e}")

        # Para todas las demás rutas (incluyendo /dashboard, /monthly-sales, etc.)
        # servir index.html y dejar que React Router maneje la navegación
        try:
            index_path = os.path.join(frontend_dist, 'index.html')
            if os.path.isfile(index_path):
                return send_file(index_path)
            else:
                app.logger.error(f"index.html no encontrado en {frontend_dist}")
                return {"error": "Frontend no encontrado. Verifica que el build esté desplegado."}, 404
        except Exception as e:
            app.logger.error(f"Error sirviendo index.html: {e}")
            return {"error": "Error interno del servidor"}, 500

    # Log de inicio
    app.logger.info("=" * 60)
    app.logger.info("Sistema de Cierre de Caja - KOAJ Puerto Carreño")
    app.logger.info(f"Versión: 2.0.0")
    app.logger.info(f"Ambiente: {'Producción' if not app.config['DEBUG'] else 'Desarrollo'}")
    app.logger.info(f"CORS Origins: {allowed_origins}")
    app.logger.info(f"Sirviendo frontend desde: {frontend_dist}")
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