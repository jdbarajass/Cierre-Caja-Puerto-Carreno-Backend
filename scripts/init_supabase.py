#!/usr/bin/env python
"""
Script para inicializar usuarios en Supabase
Hashea las contrasenas y crea usuarios en la BD
Ejecutar: python scripts/init_supabase.py
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import bcrypt
from app import create_app
from app.config import get_config
from app.models.user import db, User


def hash_password(password: str) -> str:
    """Hashea una contrasena usando bcrypt"""
    return bcrypt.hashpw(
        password.encode('utf-8'),
        bcrypt.gensalt(rounds=12)
    ).decode('utf-8')


def init_users():
    """Inicializa los usuarios en Supabase"""
    users_data = [
        {
            'email': 'ventaspuertocarreno@gmail.com',
            'password': 'VentasCarreno2025.*',
            'name': 'Usuario Ventas Puerto Carreno',
            'role': 'sales'
        },
        {
            'email': 'koaj.puertocarreno@gmail.com',
            'password': 'Koaj.2025*',
            'name': 'Administrador KOAJ',
            'role': 'admin'
        }
    ]

    config = get_config(os.getenv('FLASK_ENV', 'production'))
    app = create_app(config)

    with app.app_context():
        print("=" * 60)
        print("INICIALIZACION DE USUARIOS EN SUPABASE")
        print("=" * 60)
        print(f"Database URL: {app.config['SQLALCHEMY_DATABASE_URI'][:50]}...")
        print()

        created_count = 0
        updated_count = 0

        for user_data in users_data:
            email = user_data['email'].lower()
            existing_user = User.query.filter_by(email=email).first()

            if existing_user:
                print(f"[UPDATE] Usuario '{email}' ya existe. Actualizando...")
                password_hash = hash_password(user_data['password'])
                existing_user.password_hash = password_hash
                existing_user.name = user_data['name']
                existing_user.role = user_data['role']
                existing_user.is_active = True
                existing_user.failed_login_attempts = 0
                existing_user.locked_until = None
                updated_count += 1
            else:
                password_hash = hash_password(user_data['password'])
                new_user = User(
                    email=email,
                    password_hash=password_hash,
                    name=user_data['name'],
                    role=user_data['role'],
                    is_active=True
                )
                db.session.add(new_user)
                created_count += 1
                print(f"[CREATE] Usuario '{email}' creado.")

        try:
            db.session.commit()
            print()
            print("=" * 60)
            print(f"EXITO: {created_count} creados, {updated_count} actualizados")
            print("=" * 60)

            all_users = User.query.all()
            print("\nUsuarios en la base de datos:")
            print("-" * 60)
            for user in all_users:
                status = "ACTIVO" if user.is_active else "INACTIVO"
                print(f"  - {user.email}")
                print(f"    Nombre: {user.name}")
                print(f"    Rol: {user.role}")
                print(f"    Estado: {status}")
                print()

        except Exception as e:
            db.session.rollback()
            print(f"ERROR: {str(e)}")
            sys.exit(1)


def test_connection():
    """Prueba la conexion a la base de datos"""
    config = get_config(os.getenv('FLASK_ENV', 'production'))
    app = create_app(config)

    with app.app_context():
        try:
            # Intentar una consulta simple
            User.query.first()
            print("Conexion a base de datos: OK")
            return True
        except Exception as e:
            print(f"Error de conexion: {str(e)}")
            return False


if __name__ == "__main__":
    print()
    print("Probando conexion a base de datos...")
    if test_connection():
        print()
        init_users()
    else:
        print("No se pudo conectar a la base de datos.")
        print("Verifica tu DATABASE_URL en el archivo .env")
        sys.exit(1)
