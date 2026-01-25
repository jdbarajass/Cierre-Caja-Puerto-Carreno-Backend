"""
Configuración centralizada de la aplicación
"""
import os
from dotenv import load_dotenv

# Cargar variables de entorno desde .env
load_dotenv()


class Config:
    """Configuración base de la aplicación"""

    # Flask
    SECRET_KEY = os.getenv('SECRET_KEY', 'dev-secret-key-CHANGE-IN-PRODUCTION')
    DEBUG = os.getenv('DEBUG', 'False').lower() == 'true'
    TESTING = os.getenv('TESTING', 'False').lower() == 'true'

    # Credenciales Alegra
    ALEGRA_USER = os.getenv('ALEGRA_USER', '')
    ALEGRA_PASS = os.getenv('ALEGRA_PASS', '')
    ALEGRA_API_BASE_URL = os.getenv(
        'ALEGRA_API_BASE_URL',
        'https://api.alegra.com/api/v1'
    )
    ALEGRA_TIMEOUT = int(os.getenv('ALEGRA_TIMEOUT', '180'))  # 3 minutos para consultas de inventario completo

    # Configuración de negocio - Cierre de caja
    BASE_OBJETIVO = int(os.getenv('BASE_OBJETIVO', '450000'))
    UMBRAL_MENUDO = int(os.getenv('UMBRAL_MENUDO', '10000'))

    # Denominaciones de dinero colombiano
    DENOMINACIONES_MONEDAS = [50, 100, 200, 500, 1000]
    DENOMINACIONES_BILLETES = [2000, 5000, 10000, 20000, 50000, 100000]

    # CORS - Orígenes permitidos
    ALLOWED_ORIGINS = [
        origin.strip()
        for origin in os.getenv(
            'ALLOWED_ORIGINS',
            'http://localhost:5173,'
            'http://localhost:5174,'
            'http://localhost:5175,'
            'http://localhost:5176,'
            'http://localhost:5000,'
            'http://10.28.168.57:5000,'
            'http://10.28.168.57:5175,'
            'https://jdbarajass.pythonanywhere.com,'
            'https://cierre-caja-api.onrender.com'
        ).split(',')
        if origin.strip()  # Eliminar elementos vacíos
    ]

    # Zona horaria
    TIMEZONE = os.getenv('TIMEZONE', 'America/Bogota')

    # Frontend path - Ruta al directorio dist del frontend
    # En PythonAnywhere, configurar esta variable de entorno con la ruta correcta
    # Ejemplo: /home/jdbarajass/cierre-caja-frontend/dist
    FRONTEND_DIST_PATH = os.getenv('FRONTEND_DIST_PATH', None)

    # Rate Limiting
    RATELIMIT_STORAGE_URL = os.getenv('RATELIMIT_STORAGE_URL', 'memory://')
    RATELIMIT_DEFAULT = os.getenv('RATELIMIT_DEFAULT', '200 per day;50 per hour')

    # JWT Authentication
    JWT_SECRET_KEY = os.getenv('JWT_SECRET_KEY', 'dev-jwt-secret-CHANGE-IN-PRODUCTION-min-32-chars')
    JWT_EXPIRATION_HOURS = int(os.getenv('JWT_EXPIRATION_HOURS', '8'))
    JWT_ALGORITHM = 'HS256'

    # Database
    SQLALCHEMY_DATABASE_URI = os.getenv(
        'DATABASE_URL',
        'sqlite:///cierre_caja.db'
    )
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    # Database connection pooling (para PostgreSQL/Supabase)
    SQLALCHEMY_ENGINE_OPTIONS = {
        'pool_size': 10,
        'pool_recycle': 3600,
        'pool_pre_ping': True,
        'max_overflow': 20,
        'pool_timeout': 30
    }

    # Security
    MAX_LOGIN_ATTEMPTS = int(os.getenv('MAX_LOGIN_ATTEMPTS', '5'))
    LOCKOUT_TIME_MINUTES = int(os.getenv('LOCKOUT_TIME_MINUTES', '15'))

    @classmethod
    def validate(cls):
        """Valida que la configuración crítica esté presente"""
        errors = []

        if not cls.ALEGRA_USER:
            errors.append("ALEGRA_USER no está configurado")

        if not cls.ALEGRA_PASS:
            errors.append("ALEGRA_PASS no está configurado")

        if cls.BASE_OBJETIVO <= 0:
            errors.append("BASE_OBJETIVO debe ser mayor a 0")

        if cls.UMBRAL_MENUDO <= 0:
            errors.append("UMBRAL_MENUDO debe ser mayor a 0")

        return errors

    @classmethod
    def get_all_denominations(cls):
        """Retorna todas las denominaciones en un dict"""
        return {
            'monedas': cls.DENOMINACIONES_MONEDAS,
            'billetes': cls.DENOMINACIONES_BILLETES
        }


class DevelopmentConfig(Config):
    """Configuración para ambiente de desarrollo"""
    DEBUG = True


class ProductionConfig(Config):
    """Configuración para ambiente de producción"""
    DEBUG = False


class TestingConfig(Config):
    """Configuración para tests"""
    TESTING = True
    DEBUG = True


# Mapeo de configuraciones
config_by_name = {
    'development': DevelopmentConfig,
    'production': ProductionConfig,
    'testing': TestingConfig,
    'default': Config
}


def get_config(config_name=None):
    """
    Obtiene la configuración según el nombre

    Args:
        config_name: Nombre de la configuración ('development', 'production', 'testing')

    Returns:
        Clase de configuración correspondiente
    """
    if config_name is None:
        config_name = os.getenv('FLASK_ENV', 'production')

    return config_by_name.get(config_name, Config)
