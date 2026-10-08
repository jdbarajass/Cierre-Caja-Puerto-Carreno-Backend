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
    from app.models.app_setting import AppSetting  # Import to ensure table is created
    from app.models.invoice_fact import InvoiceFact, InvoiceSyncDay, InvoiceItemFact, InvoiceVoidItem, VoidOverride  # Clientes (fase 4), Prendas y reconstrucción 2025
    from app.models.purchase_fact import PurchaseItemFact  # Estadísticas → Llegadas (Fase D1)
    from app.models.seller_goal import SellerGoal  # Estadísticas → Metas (Fase D3)
    from app.models.daily_alert import DailyAlert  # Alertas diarias (Fase D4)
    from app.models.expense import Expense, FixedExpense  # Cuentas → Gastos (docs/PLAN_CUENTAS_DIARIAS.md, Fase 1)
    from app.models.month_sheet import PaymentFact, AccountReconciliation, MonthClose, SaleMethodCorrection  # Cuentas → Mes (Fase 2)
    from app.models.monthly_summary import InventorySnapshot, MonthlySummaryOverride  # Cuentas → Año (Fase 3)
    from app.models.incentive import IncentiveRule  # Incentivos por meta (Fase 4)

    db.init_app(app)

    # Create tables and run migrations if needed
    with app.app_context():
        try:
            _migrate_employee_tables(db, app)
            _migrate_multi_store(db, app)
            db.create_all()
            app.logger.info("Database tables created/verified successfully")

            from app.routes.accounts import seed_default_accounts
            seed_default_accounts()

            _fix_historical_closing_dates_timezone_bug(db, app)
        except Exception as e:
            app.logger.error(f"Error creating database tables: {e}")
            # Sin la migración multi-tienda TODAS las consultas a cierres/
            # cuentas/etc. fallarían (el código ya espera store_code). En
            # producción es mejor no arrancar: Render sigue sirviendo el
            # deploy anterior en vez de uno roto.
            if isinstance(e, MultiStoreMigrationError) and not app.config['DEBUG'] and not app.config.get('TESTING'):
                raise

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
                "Cache-Control",
                "X-Store"
            ],
            "expose_headers": [
                "Content-Type",
                "X-Total-Count",
                "X-Page",
                "X-Per-Page",
                "X-Alegra-Failed-Days"
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

    # Multi-tienda: fija la tienda activa del request (header X-Store; sin
    # header = Carreño). El permiso del usuario sobre esa tienda se valida
    # después, en token_required. Ver app/stores.py.
    @app.before_request
    def assign_store():
        from app.stores import resolve_request_store, InvalidStoreError, DEFAULT_STORE
        try:
            requested = resolve_request_store()
            g.store_explicit = requested is not None
            g.store_code = requested or DEFAULT_STORE
        except InvalidStoreError as e:
            return {'success': False, 'message': str(e)}, 400

    # Agregar headers CORS manualmente en cada respuesta como backup
    @app.after_request
    def after_request(response):
        """Agregar headers CORS a todas las respuestas como medida de seguridad"""
        response.headers['X-Request-Id'] = getattr(g, 'request_id', '')
        # Días que Alegra no entregó al armar esta respuesta (ver
        # AlegraClient.get_all_invoices_in_range): el frontend muestra un aviso.
        failed_days = getattr(g, 'alegra_failed_days', None)
        if failed_days:
            response.headers['X-Alegra-Failed-Days'] = ','.join(sorted(failed_days))
        origin = request.headers.get('Origin')

        # Si el origen está en la lista permitida, agregarlo
        if origin in allowed_origins:
            response.headers['Access-Control-Allow-Origin'] = origin
            response.headers['Access-Control-Allow-Credentials'] = 'true'
            response.headers['Access-Control-Allow-Methods'] = 'GET, POST, PUT, DELETE, OPTIONS, PATCH'
            response.headers['Access-Control-Allow-Headers'] = 'Content-Type, Authorization, Accept, X-Requested-With, X-HTTP-Method-Override, Accept-Language, Cache-Control, X-Store'
            response.headers['Access-Control-Expose-Headers'] = 'Content-Type, X-Total-Count, X-Page, X-Per-Page, X-Alegra-Failed-Days'
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
    from app.routes.stores import bp as stores_bp
    from app.routes.customer_insights import bp as customer_insights_bp
    from app.routes.invoice_facts import bp as invoice_facts_bp
    from app.routes.garment_insights import bp as garment_insights_bp
    from app.routes.arrivals import bp as arrivals_bp
    from app.routes.sales_patterns import bp as sales_patterns_bp
    from app.routes.seller_goals import bp as seller_goals_bp
    from app.routes.daily_alerts import bp as daily_alerts_bp
    from app.routes.expenses import bp as expenses_bp
    from app.routes.month_sheet import bp as month_sheet_bp
    from app.routes.monthly_summary import bp as monthly_summary_bp
    from app.routes.history_2025 import bp as history_2025_bp
    from app.routes.finance import bp as finance_bp

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
    app.register_blueprint(stores_bp)  # Multi-tienda: tiendas del usuario
    app.register_blueprint(customer_insights_bp)  # Dashboard de clientes (Alegra)
    app.register_blueprint(invoice_facts_bp)  # Resumen de facturas por tienda (fase 4)
    app.register_blueprint(garment_insights_bp)  # Estadísticas → Prendas (Fase C)
    app.register_blueprint(arrivals_bp)  # Estadísticas → Llegadas (Fase D1)
    app.register_blueprint(sales_patterns_bp)  # Estadísticas → Día y hora (Fase D2)
    app.register_blueprint(seller_goals_bp)  # Estadísticas → Metas por vendedora (Fase D3)
    app.register_blueprint(daily_alerts_bp)  # Alertas diarias en el Dashboard (Fase D4)
    app.register_blueprint(expenses_bp)  # Cuentas → Gastos (PLAN_CUENTAS_DIARIAS, Fase 1)
    app.register_blueprint(month_sheet_bp)  # Cuentas → Mes (PLAN_CUENTAS_DIARIAS, Fase 2)
    app.register_blueprint(monthly_summary_bp)  # Cuentas → Año (PLAN_CUENTAS_DIARIAS, Fase 3)
    app.register_blueprint(history_2025_bp)  # Reconstrucción 2025 (docs/PLAN_RECONSTRUCCION_2025.md)
    app.register_blueprint(finance_bp)  # Configuración financiera e incentivos (PLAN_CUENTAS_DIARIAS, Fase 4)

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


def _fix_historical_closing_dates_timezone_bug(db, app):
    """
    Corrección de datos, UNA SOLA VEZ (no un cambio de esquema): desde que se
    creó `parse_colombia_date()` (2025-11-16), un cierre para una fecha simple
    como "2026-09-08" se guardaba con `closing_date` un día ANTES en cualquier
    servidor que no corra en hora de Colombia - y Render corre en UTC. El bug
    ya se corrigió en app/utils/timezone.py; esto repara los cierres que ya
    existían en la base ANTES de ese fix.

    Los MONTOS de esos cierres siempre fueron correctos (la comparación con
    Alegra usa el string de fecha crudo, no pasa por la función con el bug) -
    solo la etiqueta `closing_date` estaba corrida. Se le suma 1 día a cada
    cierre que ya existía.

    Se procesa del más reciente al más antiguo (closing_date DESC), con un
    flush por fila: como `closing_date` es única, sumar 1 día en cualquier
    otro orden puede chocar momentáneamente con el cierre del día siguiente
    (ej. 06→07 mientras el 07 original sigue sin tocar). Yendo de más
    reciente a más antiguo, la fecha destino siempre queda libre antes de
    escribirla.

    Guardada en app_settings con una bandera para que NUNCA se repita, ni
    siquiera en el próximo reinicio - los cierres creados con el código ya
    corregido no deben tocarse.
    """
    from datetime import timedelta, datetime as dt_module
    from app.models.app_setting import AppSetting
    from app.models.cash_closing import CashClosing

    MIGRATION_KEY = 'closing_date_timezone_offset_fix_applied'

    if AppSetting.query.get(MIGRATION_KEY):
        return

    closings = CashClosing.query.order_by(CashClosing.closing_date.desc()).all()
    for closing in closings:
        old_date = closing.closing_date
        closing.closing_date = old_date + timedelta(days=1)
        db.session.flush()

    db.session.add(AppSetting(
        key=MIGRATION_KEY,
        value=f'applied_to_{len(closings)}_rows',
        updated_at=dt_module.utcnow()
    ))
    db.session.commit()

    if closings:
        app.logger.warning(
            f"Migración única aplicada: se corrigió la fecha (+1 día) de "
            f"{len(closings)} cierre(s) histórico(s) - bug de zona horaria "
            f"de parse_colombia_date (activo desde 2025-11-16, corregido ahora)"
        )


class MultiStoreMigrationError(RuntimeError):
    """Falló la migración de esquema multi-tienda (ver _migrate_multi_store)."""


# Tablas cuyos datos pertenecen a una tienda (modelos con StoreScopedMixin).
# account_movements NO está: un movimiento pertenece a la tienda de su cuenta.
STORE_SCOPED_TABLES = (
    'cash_closings', 'accounts',
    'repurchase_entries', 'repurchase_purchases',
    'employee_clothing', 'employee_loans', 'employee_permissions',
    'employee_vacations', 'employee_payments',
    'restock_items', 'operational_tasks',
)

# Tablas que reciben la columna store_code: las de datos por tienda + users
# (tienda asignada al usuario; no usa StoreScopedMixin porque NO se filtra
# por la tienda del request - los usuarios son compartidos).
TABLES_WITH_STORE_COLUMN = STORE_SCOPED_TABLES + ('users',)

# Columnas que antes eran únicas por sí solas y ahora son únicas POR TIENDA
# (los nuevos índices únicos compuestos están declarados en cada modelo).
LEGACY_SINGLE_COLUMN_UNIQUES = {
    'cash_closings': ('closing_date',),
    'accounts': ('name', 'payment_key'),
}

# Llave arbitraria (fija) del advisory lock de Postgres que serializa la
# migración entre los workers de gunicorn que arrancan al mismo tiempo.
MULTI_STORE_MIGRATION_LOCK_KEY = 7420261001


def _migrate_multi_store(db, app):
    """
    Migración multi-tienda (2026-10-01), idempotente y NO destructiva:

    1. Agrega `store_code` (NOT NULL, DEFAULT 'carreno') a cada tabla de
       TABLES_WITH_STORE_COLUMN que no la tenga: todos los datos y usuarios
       existentes quedan asignados a Carreño, la única tienda que existía.
    2. Quita la unicidad GLOBAL de cash_closings.closing_date y de
       accounts.name/payment_key (cada tienda tiene su cierre del día y sus
       propias cuentas EFECTIVO, NEQUI, ...).
    3. Crea los índices declarados en los modelos que falten (incluidos los
       únicos compuestos por tienda que reemplazan a los del paso 2).

    Todo corre en UNA transacción: o queda todo aplicado o nada. En Postgres,
    un advisory lock evita que los 2 workers de gunicorn la ejecuten a la vez;
    el que espera vuelve a inspeccionar el esquema y no encuentra nada que hacer.
    """
    from sqlalchemy import inspect, text
    from app.stores import DEFAULT_STORE

    try:
        with db.engine.begin() as conn:
            if conn.dialect.name == 'postgresql':
                conn.execute(text('SELECT pg_advisory_xact_lock(:key)'),
                             {'key': MULTI_STORE_MIGRATION_LOCK_KEY})

            existing_tables = set(inspect(conn).get_table_names())
            changes = []

            for table_name in TABLES_WITH_STORE_COLUMN:
                if table_name not in existing_tables:
                    continue  # tabla nueva: db.create_all() la crea ya con el esquema nuevo
                table = db.metadata.tables[table_name]

                columns = {c['name'] for c in inspect(conn).get_columns(table_name)}
                if 'store_code' not in columns:
                    conn.execute(text(
                        f"ALTER TABLE {table_name} ADD COLUMN store_code "
                        f"VARCHAR(20) NOT NULL DEFAULT '{DEFAULT_STORE}'"
                    ))
                    changes.append(f"{table_name}.store_code")

                for column in LEGACY_SINGLE_COLUMN_UNIQUES.get(table_name, ()):
                    if _drop_single_column_unique(conn, table, column):
                        changes.append(f"{table_name}.{column} ya no es única global")

                existing_indexes = {i['name'] for i in inspect(conn).get_indexes(table_name)}
                for index in table.indexes:
                    if index.name not in existing_indexes:
                        index.create(bind=conn)
                        changes.append(f"índice {index.name}")

            if changes:
                app.logger.warning(f"Migración multi-tienda aplicada: {changes}")
    except Exception as e:
        raise MultiStoreMigrationError(f"Falló la migración multi-tienda: {e}") from e


def _drop_single_column_unique(conn, table, column):
    """
    Quita la restricción/índice UNIQUE que exista solo sobre `column`.
    Devuelve True si quitó algo.

    Postgres: puede ser una constraint (`unique=True`) o un índice único
    (`unique=True, index=True`) - se busca por introspección en vez de asumir
    nombres. SQLite no permite DROP CONSTRAINT: si la unicidad está declarada
    dentro del CREATE TABLE, se reconstruye la tabla (procedimiento oficial de
    SQLite; solo aplica a bases locales de desarrollo).
    """
    from sqlalchemy import inspect, text

    inspector = inspect(conn)
    is_sqlite = conn.dialect.name == 'sqlite'
    dropped = False

    for constraint in inspector.get_unique_constraints(table.name):
        if constraint['column_names'] == [column]:
            if is_sqlite:
                _sqlite_rebuild_table(conn, table)
                return True
            conn.execute(text(f'ALTER TABLE {table.name} DROP CONSTRAINT "{constraint["name"]}"'))
            dropped = True

    for index in inspector.get_indexes(table.name):
        if (index.get('unique') and index['column_names'] == [column]
                and not index.get('duplicates_constraint')):
            conn.execute(text(f'DROP INDEX "{index["name"]}"'))
            dropped = True

    return dropped


def _sqlite_rebuild_table(conn, table):
    """
    Recrea `table` en SQLite con el esquema actual del modelo conservando
    todas sus filas (crear nueva -> copiar -> borrar vieja -> renombrar). Las
    FKs de otras tablas apuntan por NOMBRE, así que siguen siendo válidas.
    Los índices del modelo los crea luego _migrate_multi_store.
    """
    from sqlalchemy import inspect, text
    from sqlalchemy.schema import CreateTable

    tmp_name = f"{table.name}__multistore_tmp"
    ddl = str(CreateTable(table).compile(dialect=conn.dialect))
    ddl = ddl.replace(f"CREATE TABLE {table.name} (", f"CREATE TABLE {tmp_name} (", 1)

    old_columns = {c['name'] for c in inspect(conn).get_columns(table.name)}
    columns = ', '.join(c.name for c in table.columns if c.name in old_columns)

    conn.execute(text(ddl))
    conn.execute(text(f"INSERT INTO {tmp_name} ({columns}) SELECT {columns} FROM {table.name}"))
    conn.execute(text(f"DROP TABLE {table.name}"))
    conn.execute(text(f"ALTER TABLE {tmp_name} RENAME TO {table.name}"))


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

        # Conexión Cuentas Recompras <-> Resumen (2026-09-01): marca qué envíos
        # descuentan saldo de cuentas automáticamente. Sin DEFAULT a propósito:
        # los envíos existentes quedan en NULL (equivalente a False al leerlos
        # por el ORM), para que la conexión no aplique retroactivamente.
        add_column_if_missing(conn, 'repurchase_entries', 'synced_to_accounts', 'BOOLEAN')

        # Comisión editable por envío (2026-09-01): NULL = sigue calculando el
        # 4‰ automático de siempre; un número = el usuario lo sobrescribió.
        add_column_if_missing(conn, 'repurchase_entries', 'fee_override', 'FLOAT')

        # Fecha "hasta cuándo se contempla" el saldo de una cuenta (2026-09-14):
        # nota manual editable, ej. ADDI + DATÁFONO, sin impacto en cálculos.
        add_column_if_missing(conn, 'accounts', 'contemplated_until', 'DATE')

        # Estadísticas → Prendas (2026-10-02): marca qué días ya tienen sus
        # prendas guardadas. Sin DEFAULT: los días ya cargados quedan en NULL
        # (= faltan prendas) y se completan en las siguientes cargas.
        add_column_if_missing(conn, 'invoice_sync_days', 'items_synced', 'BOOLEAN')

        # Estadísticas → Día y hora (Fase D2, 2026-10-03): hora de cada factura
        # y versión de los datos del día. Sin DEFAULT: los días ya cargados
        # quedan en NULL y se vuelven a cargar en las siguientes tandas.
        add_column_if_missing(conn, 'invoice_facts', 'hour', 'SMALLINT')
        add_column_if_missing(conn, 'invoice_sync_days', 'fact_version', 'INTEGER')

        # Reconstrucción de 2025 (docs/PLAN_RECONSTRUCCION_2025.md, 2026-10-07):
        # factura electrónica o POS, lo pagado y la fecha-hora completa. Sin
        # DEFAULT: las ya cargadas quedan en NULL hasta recargar su día.
        add_column_if_missing(conn, 'invoice_facts', 'is_electronic', 'BOOLEAN')
        add_column_if_missing(conn, 'invoice_facts', 'total_paid', 'BIGINT')
        add_column_if_missing(conn, 'invoice_facts', 'issued_at', 'VARCHAR(19)')

        # Incentivos por empleada (Fase 4 de PLAN_CUENTAS_DIARIAS, 2026-10-07):
        # NULL = incentivo de la tienda, sin empleada.
        add_column_if_missing(conn, 'incentive_rules', 'employee_name', 'VARCHAR(100)')

        # Excedentes por medio y resultado de la validación del cierre
        # (docs/PLAN_EXCEDENTES_Y_CARGA_EXCEL.md, 2026-10-08). Sin DEFAULT:
        # los cierres ya guardados quedan en NULL (= sin excedentes guardados y
        # se pueden sincronizar como antes).
        for column in ('excedente_efectivo', 'excedente_nequi', 'excedente_daviplata',
                       'excedente_qr', 'excedente_datafono'):
            add_column_if_missing(conn, 'cash_closings', column, 'FLOAT')
        add_column_if_missing(conn, 'cash_closings', 'validation_status', 'VARCHAR(10)')
        add_column_if_missing(conn, 'cash_closings', 'validation_message', 'VARCHAR(500)')
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