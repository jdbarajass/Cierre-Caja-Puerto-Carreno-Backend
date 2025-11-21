#!/usr/bin/env python
"""
Script para generar una clave secreta segura para JWT
Ejecutar: python scripts/generate_jwt_secret.py
"""
import secrets
import string


def generate_secret_key(length=64):
    """
    Genera una clave secreta segura

    Args:
        length: Longitud de la clave (default: 64 caracteres)

    Returns:
        String con la clave generada
    """
    # Usar caracteres alfanuméricos y algunos especiales seguros
    alphabet = string.ascii_letters + string.digits + '-_'
    return ''.join(secrets.choice(alphabet) for _ in range(length))


def main():
    print("=" * 70)
    print("GENERADOR DE CLAVE SECRETA JWT")
    print("=" * 70)
    print()

    # Generar clave
    secret_key = generate_secret_key(64)

    print("Tu nueva clave secreta JWT:")
    print()
    print(f"  {secret_key}")
    print()
    print("=" * 70)
    print("INSTRUCCIONES:")
    print("=" * 70)
    print()
    print("1. Copia la clave generada arriba")
    print()
    print("2. Agrégala a tu archivo .env:")
    print(f"   JWT_SECRET_KEY={secret_key}")
    print()
    print("3. En Render/producción, configúrala como variable de entorno")
    print()
    print("⚠️  IMPORTANTE:")
    print("   - Nunca compartas esta clave")
    print("   - Nunca la subas al repositorio")
    print("   - Si se compromete, genera una nueva inmediatamente")
    print("=" * 70)


if __name__ == "__main__":
    main()
