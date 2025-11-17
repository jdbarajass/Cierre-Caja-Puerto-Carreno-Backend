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
    ALEGRA_TIMEOUT = int(os.getenv('ALEGRA_TIMEOUT', '30'))

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
            'https://jdbarajass.pythonanywhere.com,'
            'http://localhost:5173,'
            'http://localhost:5174,'
            'http://localhost:5000,'
            'http://10.28.168.57:5000'
        ).split(',')
        if origin.strip()  # Eliminar elementos vacíos
    ]

    # Zona horaria
    TIMEZONE = os.getenv('TIMEZONE', 'America/Bogota')

    # Rate Limiting
    RATELIMIT_STORAGE_URL = os.getenv('RATELIMIT_STORAGE_URL', 'memory://')
    RATELIMIT_DEFAULT = os.getenv('RATELIMIT_DEFAULT', '200 per day;50 per hour')

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
