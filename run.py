"""
Entry point para la aplicación Flask
"""
import os
from app import create_app
from app.config import get_config

# Determinar ambiente
config_name = os.getenv('FLASK_ENV', 'production')
config = get_config(config_name)

# Crear aplicación
app = create_app(config)

if __name__ == "__main__":
    # Configuración para desarrollo local
    # En producción (Render), usar 0.0.0.0
    # En desarrollo local, puedes especificar tu IP en .env como HOST=10.28.168.57
    host = os.getenv('HOST', '0.0.0.0')
    port = int(os.getenv('PORT', 5000))
    debug = config.DEBUG

    app.logger.info(f"Iniciando servidor en {host}:{port}")
    app.logger.info(f"Modo debug: {debug}")

    app.run(
        host=host,
        port=port,
        debug=debug,
        use_reloader=False,
        threaded=True
    )
