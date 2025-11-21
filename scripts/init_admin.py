#!/usr/bin/env python
"""
Script para inicializar el usuario administrador
Ejecutar: python scripts/init_admin.py
"""
import sys
import os

# Agregar el directorio raíz al path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import bcrypt
from app import create_app
from app.config import get_config
from app.models.user import db, User


def create_admin_user(email, password, name, role='admin'):
    """
    Crea un usuario administrador en la base de datos

    Args:
        email: Email del usuario
        password: Contraseña en texto plano (será hasheada)
        name: Nombre del usuario
        role: Rol del usuario (default: admin)
    """
    # Crear aplicación con contexto
    config = get_config(os.getenv('FLASK_ENV', 'production'))
    app = create_app(config)

    with app.app_context():
        # Verificar si el usuario ya existe
        existing_user = User.query.filter_by(email=email.lower()).first()

        if existing_user:
            print(f"⚠️  El usuario '{email}' ya existe en la base de datos.")
            update = input("¿Desea actualizar la contraseña? (s/n): ").strip().lower()

            if update == 's':
                # Hashear nueva contraseña
                password_hash = bcrypt.hashpw(
                    password.encode('utf-8'),
                    bcrypt.gensalt(rounds=12)
                ).decode('utf-8')

                existing_user.password_hash = password_hash
                existing_user.name = name
                existing_user.role = role
                existing_user.is_active = True
                existing_user.failed_login_attempts = 0
                existing_user.locked_until = None

                db.session.commit()
                print(f"✅ Usuario '{email}' actualizado exitosamente.")
            else:
                print("❌ Operación cancelada.")
            return

        # Hashear contraseña
        password_hash = bcrypt.hashpw(
            password.encode('utf-8'),
            bcrypt.gensalt(rounds=12)
        ).decode('utf-8')

        # Crear usuario
        new_user = User(
            email=email.lower(),
            password_hash=password_hash,
            name=name,
            role=role,
            is_active=True
        )

        db.session.add(new_user)
        db.session.commit()

        print(f"✅ Usuario administrador creado exitosamente:")
        print(f"   Email: {email}")
        print(f"   Nombre: {name}")
        print(f"   Rol: {role}")


def main():
    """Función principal"""
    print("=" * 60)
    print("INICIALIZACIÓN DE USUARIO ADMINISTRADOR")
    print("Sistema de Cierre de Caja - KOAJ Puerto Carreño")
    print("=" * 60)
    print()

    # Valores por defecto (del requerimiento del frontend)
    default_email = "ventaspuertocarreno@gmail.com"
    default_password = "VentasCarreno2025.*"
    default_name = "Usuario Ventas Puerto Carreño"

    print("Configuración por defecto:")
    print(f"  Email: {default_email}")
    print(f"  Password: {'*' * len(default_password)}")
    print(f"  Nombre: {default_name}")
    print()

    use_defaults = input("¿Usar configuración por defecto? (s/n): ").strip().lower()

    if use_defaults == 's':
        email = default_email
        password = default_password
        name = default_name
    else:
        email = input(f"Email [{default_email}]: ").strip() or default_email
        password = input(f"Password [{default_password}]: ").strip() or default_password
        name = input(f"Nombre [{default_name}]: ").strip() or default_name

    print()
    print("Creando usuario...")
    create_admin_user(email, password, name)

    print()
    print("=" * 60)
    print("SIGUIENTE PASO:")
    print("Ahora puedes hacer login con estas credenciales desde el frontend")
    print("=" * 60)


if __name__ == "__main__":
    main()
