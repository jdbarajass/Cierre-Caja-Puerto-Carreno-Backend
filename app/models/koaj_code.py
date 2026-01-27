"""
Modelo de Código KOAJ para catálogo de códigos de barras
"""
from datetime import datetime
from app.models.user import db


class KoajCode(db.Model):
    """Modelo para almacenar los códigos de categorías KOAJ"""
    __tablename__ = 'koaj_codes'

    id = db.Column(db.Integer, primary_key=True)
    code = db.Column(db.String(10), unique=True, nullable=False, index=True)
    category = db.Column(db.String(100), nullable=False)
    description = db.Column(db.Text, nullable=True)
    applies_to = db.Column(db.String(50), nullable=True, default='todos')
    is_active = db.Column(db.Boolean, default=True, index=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def __repr__(self):
        return f'<KoajCode {self.code}: {self.category}>'

    def to_dict(self):
        """Convierte el código a diccionario"""
        return {
            'id': self.id,
            'code': self.code,
            'category': self.category,
            'description': self.description,
            'applies_to': self.applies_to,
            'is_active': self.is_active,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None
        }
