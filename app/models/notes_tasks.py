"""
Modelos para Notas y Pendientes: Resurtido (Por Pedir) y Tareas Operativas.
Checklist simple: cualquier usuario crea y marca completado; solo admin edita/elimina.
"""
from datetime import datetime
from app.models.user import db


class RestockItem(db.Model):
    """Items por pedir / resurtir en la tienda"""
    __tablename__ = 'restock_items'

    id = db.Column(db.Integer, primary_key=True)
    item = db.Column(db.String(255), nullable=False)
    quantity = db.Column(db.Integer, nullable=True)
    completed = db.Column(db.Boolean, default=False, index=True)
    created_by = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    completed_at = db.Column(db.DateTime, nullable=True)

    creator = db.relationship('User', foreign_keys=[created_by], lazy='joined')

    def to_dict(self):
        return {
            'id': self.id,
            'item': self.item,
            'quantity': self.quantity,
            'completed': self.completed,
            'created_by_name': self.creator.name if self.creator else None,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'completed_at': self.completed_at.isoformat() if self.completed_at else None,
        }


class OperationalTask(db.Model):
    """Tareas operativas del local"""
    __tablename__ = 'operational_tasks'

    PRIORITIES = ['alta', 'media', 'baja']

    id = db.Column(db.Integer, primary_key=True)
    description = db.Column(db.Text, nullable=False)
    priority = db.Column(db.String(10), nullable=False, default='media')
    completed = db.Column(db.Boolean, default=False, index=True)
    created_by = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    completed_at = db.Column(db.DateTime, nullable=True)

    creator = db.relationship('User', foreign_keys=[created_by], lazy='joined')

    def to_dict(self):
        return {
            'id': self.id,
            'description': self.description,
            'priority': self.priority,
            'completed': self.completed,
            'created_by_name': self.creator.name if self.creator else None,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'completed_at': self.completed_at.isoformat() if self.completed_at else None,
        }
