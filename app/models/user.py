"""
Modelo de Usuario para autenticación
"""
from datetime import datetime
from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()


class User(db.Model):
    """Modelo de usuario para autenticación"""
    __tablename__ = 'users'

    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(255), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(255), nullable=False)
    name = db.Column(db.String(255), nullable=False)
    role = db.Column(db.String(50), default='user')
    # Multi-tienda: tienda que opera el usuario (ver app/stores.py). El admin
    # opera todas sin importar este valor.
    store_code = db.Column(db.String(20), nullable=False, default='carreno', server_default='carreno')
    is_active = db.Column(db.Boolean, default=True, index=True)
    failed_login_attempts = db.Column(db.Integer, default=0)
    locked_until = db.Column(db.DateTime, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def __repr__(self):
        return f'<User {self.email}>'

    def to_dict(self):
        """Convierte el usuario a diccionario (sin datos sensibles)"""
        return {
            'id': self.id,
            'email': self.email,
            'name': self.name,
            'role': self.role,
            'store_code': self.store_code,
            'is_active': self.is_active,
            'created_at': self.created_at.isoformat() if self.created_at else None
        }

    def is_locked(self):
        """Verifica si la cuenta está bloqueada"""
        if self.locked_until is None:
            return False
        return datetime.utcnow() < self.locked_until

    def increment_failed_attempts(self):
        """Incrementa el contador de intentos fallidos"""
        self.failed_login_attempts += 1

    def reset_failed_attempts(self):
        """Resetea el contador de intentos fallidos"""
        self.failed_login_attempts = 0
        self.locked_until = None

    def lock_account(self, minutes=15):
        """Bloquea la cuenta por un tiempo determinado"""
        from datetime import timedelta
        self.locked_until = datetime.utcnow() + timedelta(minutes=minutes)
