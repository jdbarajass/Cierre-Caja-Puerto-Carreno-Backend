#!/usr/bin/env python3
"""
Script para generar una SECRET_KEY segura para Flask
Ejecutar: python generate_secret_key.py
"""

import secrets

def generate_secret_key(length=32):
    """
    Genera una clave secreta segura usando secrets

    Args:
        length: Longitud en bytes (por defecto 32, resultará en 64 caracteres hex)

    Returns:
        str: Clave secreta en formato hexadecimal
    """
    return secrets.token_hex(length)

if __name__ == "__main__":
    print("\n" + "="*60)
    print("GENERADOR DE SECRET_KEY PARA FLASK")
    print("="*60)

    # Generar 3 opciones diferentes
    print("\nAquí tienes 3 opciones de SECRET_KEY seguras:\n")

    for i in range(1, 4):
        key = generate_secret_key()
        print(f"Opción {i}:")
        print(f"{key}\n")

    print("="*60)
    print("Copia cualquiera de estas claves y agrégala como")
    print("SECRET_KEY en las variables de entorno de Render")
    print("="*60 + "\n")
