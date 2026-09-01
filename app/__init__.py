"""
Sistema de Cierre de Caja - KOAJ Puerto Carreño
Flask Application Factory
"""
from flask import Flask, request, g, send_from_directory, send_file
from flask_cors import CORS
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from flask_talisman import Talisman
from flasgger import Swagger
import logging
import os
import uuid

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

    # Validar configuración crítica ANTES de continuar. En producción, un
    # despliegue con credenciales de Alegra o secretos JWT faltantes/por defecto
    # debe fallar rápido en vez de arrancar "roto" en silencio.
    # NOTA: config_class.validate() (sin el "_security") también se usa por
    # request en cash_closing.py - por eso los checks de secretos viven en
    # validate_security(), que solo corre aquí, una vez, al arrancar.
    config_errors = config_class.validate() + config_class.validate_security()
    if config_errors:
        for error in config_errors:
            logging.error(f"Configuración inválida: {error}")
        if not app.config['DEBUG'] and not app.config.get('TESTING'):
            raise RuntimeError(
                "La aplicación no puede arrancar por errores de configuración: "
                + "; ".join(config_errors)
            )
        logging.warning(
            "Continuando en modo DEBUG/TESTING pese a errores de configuración "
            "(esto abortaría el arranque en producción)"
        )

    # Initialize SQLAlchemy database
    from app.models.user import db
    from app.models.koaj_code import KoajCode  # Import to ensure table is created
    from app.models.employee_records import (  # Import to ensure tables are created
        EmployeeClothing, EmployeeLoan, EmployeePermission,
        EmployeeVacation, EmployeePayment
    )
    from app.models.repurchase import RepurchaseEntry  # Import to ensure table is created
    from app.models.repurchase_purchase import RepurchasePurchase  # Import to ensure table is created
    from app.models.notes_tasks import RestockItem, OperationalTask  # Import to ensure tables are created
    from app.models.cash_closing import CashClosing  # Import to ensure table is created
    from app.models.account import Account, AccountMovement  # Import to ensure tables are created

    db.init_app(app)

    # Create tables and run migrations if needed
    with app.app_context():
        try:
            _migrate_employee_tables(db, app)
            db.create_all()
            app.logger.info("Database tables created/verified successfully")

            from app.routes.accounts import seed_default_accounts
            seed_default_accounts()
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

    # Request ID: correlaciona todos los logs de una misma petición y permite
    # rastrear un fallo puntual reportado por una vendedora en los logs de Render.
    @app.before_request
    def assign_request_id():
        g.request_id = request.headers.get('X-Request-Id') or uuid.uuid4().hex

    # Agregar headers CORS manualmente en cada respuesta como backup
    @app.after_request
    def after_request(response):
        """Agregar headers CORS a todas las respuestas como medida de seguridad"""
        response.headers['X-Request-Id'] = getattr(g, 'request_id', '')
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

    # Configurar Flask-Talisman para headers de seguridad
    # Solo habilitar en producción (cuando no está en modo DEBUG)
    if not app.config['DEBUG']:
        # Content Security Policy
        csp = {
            'default-src': "'self'",
            'script-src': ["'self'", "'unsafe-inline'", "'unsafe-eval'"],
            'style-src': ["'self'", "'unsafe-inline'", "https://fonts.googleapis.com"],
            'font-src': ["'self'", "https://fonts.gstatic.com"],
            'img-src': ["'self'", "data:", "blob:"],
            'connect-src': ["'self'"] + allowed_origins,
        }

        Talisman(
            app,
            force_https=False,  # Manejar HTTPS a nivel de proxy/Render
            strict_transport_security=True,
            strict_transport_security_max_age=31536000,  # 1 año
            strict_transport_security_include_subdomains=True,
            content_security_policy=csp,
            content_security_policy_nonce_in=['script-src'],
            referrer_policy='strict-origin-when-cross-origin',
            session_cookie_secure=True,
            session_cookie_http_only=True,
        )
        app.logger.info("Flask-Talisman habilitado con headers de seguridad")
    else:
        app.logger.info("Flask-Talisman deshabilitado en modo DEBUG")

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
    setup_sentry(app)

    # Registrar blueprints
    from app.routes.cash_closing import bp as cash_bp
    from app.routes.health import bp as health_bp
    from app.routes.auth import bp as auth_bp
    from app.routes.products import bp as products_bp
    from app.routes.analytics import bp as analytics_bp
    from app.routes.inventory import bp as inventory_bp
    from app.routes.direct_api import bp as direct_api_bp
    from app.routes.users import bp as users_bp
    from app.routes.koaj_codes import bp as koaj_codes_bp
    from app.routes.employee_records import bp as employee_records_bp
    from app.routes.repurchase import bp as repurchase_bp
    from app.routes.notes_tasks import bp as notes_tasks_bp
    from app.routes.accounts import bp as accounts_bp

    app.register_blueprint(cash_bp, url_prefix='/api')
    app.register_blueprint(health_bp)
    app.register_blueprint(auth_bp, url_prefix='/auth')
    app.register_blueprint(products_bp)
    app.register_blueprint(analytics_bp)
    app.register_blueprint(inventory_bp)
    app.register_blueprint(direct_api_bp)  # APIs directas de Alegra
    app.register_blueprint(users_bp)  # CRUD de usuarios (admin)
    app.register_blueprint(koaj_codes_bp)  # Códigos y precios KOAJ
    app.register_blueprint(employee_records_bp)  # Control de empleadas
    app.register_blueprint(repurchase_bp)  # Cuentas de recompras
    app.register_blueprint(notes_tasks_bp)  # Notas y pendientes
    app.register_blueprint(accounts_bp)  # Cuentas (saldo por medio de pago)

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
    app.logger.info(f"Versión: 2.3.0")
    app.logger.info(f"Ambiente: {'Producción' if not app.config['DEBUG'] else 'Desarrollo'}")
    app.logger.info(f"CORS Origins: {allowed_origins}")
    app.logger.info(f"Sirviendo frontend desde: {frontend_dist}")
    app.logger.info("=" * 60)

    return app


def _migrate_employee_tables(db, app):
    """
    Migraciones SEGURAS: solo agrega columnas nuevas, NUNCA borra tablas ni datos.
    Patrón: inspeccionar columnas existentes → ALTER TABLE ADD COLUMN si falta.
    Agregar aquí cualquier cambio de esquema futuro.
    """
    from sqlalchemy import inspect, text

    inspector = inspect(db.engine)
    tables = inspector.get_table_names()

    def add_column_if_missing(conn, table, column, col_type, default=None):
        """Agrega una columna solo si no existe. NO borra datos."""
        if table not in tables:
            return
        existing = [c['name'] for c in inspector.get_columns(table)]
        if column in existing:
            return
        default_clause = f" DEFAULT '{default}'" if default is not None else ""
        try:
            conn.execute(text(f'ALTER TABLE {table} ADD COLUMN {column} {col_type}{default_clause}'))
            app.logger.info(f"Migración: columna '{column}' agregada a '{table}'")
        except Exception as e:
            app.logger.warning(f"Migración: no se pudo agregar '{column}' a '{table}': {e}")

    with db.engine.connect() as conn:
        # ── Ejemplo de migración futura (referencia): ──────────────────────────
        # Si en el futuro se agrega un campo 'talla' a employee_clothing:
        # add_column_if_missing(conn, 'employee_clothing', 'talla', 'VARCHAR(20)')
        #
        # Si se agrega 'aprobado_por' a employee_loans:
        # add_column_if_missing(conn, 'employee_loans', 'aprobado_por', 'VARCHAR(100)')
        # ──────────────────────────────────────────────────────────────────────

        # Categoría de compra ('ropa' | 'operacional') para Cuentas Recompras (2026-09-01)
        add_column_if_missing(conn, 'repurchase_purchases', 'category', 'VARCHAR(20)', default='ropa')
        conn.commit()


def setup_logging(app):
    """
    Configura el sistema de logging de la aplicación.

    Formato controlado por la variable de entorno LOG_FORMAT ('json' o 'text').
    Por defecto: 'json' en producción (más fácil de indexar en Render/Sentry/etc.),
    'text' en modo DEBUG (más legible en la terminal local).
    """
    from logging.handlers import RotatingFileHandler
    from app.utils.logging_utils import JsonFormatter, RequestIdFilter

    log_level = logging.DEBUG if app.config['DEBUG'] else logging.INFO
    log_format = os.getenv('LOG_FORMAT', 'text' if app.config['DEBUG'] else 'json')

    if log_format == 'json':
        formatter = JsonFormatter()
    else:
        formatter = logging.Formatter(
            '[%(asctime)s] %(levelname)s en %(module)s.%(funcName)s:%(lineno)d '
            '[req=%(request_id)s] - %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )

    request_id_filter = RequestIdFilter()

    # Handler de consola (siempre activo)
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)
    console_handler.setLevel(log_level)
    console_handler.addFilter(request_id_filter)
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
            file_handler.addFilter(request_id_filter)
            app.logger.addHandler(file_handler)
        except Exception as e:
            app.logger.warning(f"No se pudo crear archivo de log: {e}")

    app.logger.setLevel(log_level)

    # Reducir ruido de otros loggers
    logging.getLogger('werkzeug').setLevel(logging.WARNING)
    logging.getLogger('urllib3').setLevel(logging.WARNING)


def setup_sentry(app):
    """
    Inicializa Sentry SOLO si se configura la variable de entorno SENTRY_DSN.
    Si sentry-sdk no está instalado o no hay DSN, no hace nada (no rompe el arranque).
    """
    sentry_dsn = os.getenv('SENTRY_DSN')
    if not sentry_dsn:
        app.logger.info("SENTRY_DSN no configurado: Sentry deshabilitado")
        return

    try:
        import sentry_sdk
        from sentry_sdk.integrations.flask import FlaskIntegration

        sentry_sdk.init(
            dsn=sentry_dsn,
            integrations=[FlaskIntegration()],
            environment=os.getenv('FLASK_ENV', 'production'),
            traces_sample_rate=float(os.getenv('SENTRY_TRACES_SAMPLE_RATE', '0.0')),
            send_default_pii=False,
        )
        app.logger.info("Sentry inicializado correctamente")
    except ImportError:
        app.logger.warning(
            "SENTRY_DSN configurado pero 'sentry-sdk' no está instalado. "
            "Ejecuta: pip install -r requirements.txt"
        )
    except Exception as e:
        app.logger.warning(f"No se pudo inicializar Sentry: {e}")