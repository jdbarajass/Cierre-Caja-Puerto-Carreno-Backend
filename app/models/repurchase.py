"""
Modelo para Cuentas de Recompras (dinero enviado al socio para recompra de mercancía).
Replica la estructura del cuadro Excel de seguimiento.
"""
from datetime import datetime
from app.models.user import db


class RepurchaseEntry(db.Model):
    """Una fila del cuadro de recompras: envío de dinero al socio por fecha"""
    __tablename__ = 'repurchase_entries'

    id = db.Column(db.Integer, primary_key=True)
    date = db.Column(db.Date, nullable=False, index=True)

    # Dinero pendiente en tienda (aún no enviado al socio)
    valor_no_enviado = db.Column(db.Float, default=0, nullable=False)

    # Montos ya enviados/consignados al socio, por medio de pago
    efectivo   = db.Column(db.Float, default=0, nullable=False)
    datafono   = db.Column(db.Float, default=0, nullable=False)
    qr         = db.Column(db.Float, default=0, nullable=False)
    daviplata  = db.Column(db.Float, default=0, nullable=False)
    nequi      = db.Column(db.Float, default=0, nullable=False)
    bbva       = db.Column(db.Float, default=0, nullable=False)

    # Sobrante del mes anterior (se registra manualmente al inicio de cada mes)
    sobrante_mes_anterior = db.Column(db.Float, default=0, nullable=False)

    notes = db.Column(db.Text, nullable=True)
    created_by = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    creator = db.relationship('User', foreign_keys=[created_by], lazy='joined')

    @property
    def total_enviado(self):
        """Suma de todos los medios de pago enviados en esta fila"""
        return (self.efectivo + self.datafono + self.qr +
                self.daviplata + self.nequi + self.bbva)

    def to_dict(self):
        return {
            'id': self.id,
            'date': self.date.isoformat() if self.date else None,
            'valor_no_enviado': self.valor_no_enviado,
            'efectivo': self.efectivo,
            'datafono': self.datafono,
            'qr': self.qr,
            'daviplata': self.daviplata,
            'nequi': self.nequi,
            'bbva': self.bbva,
            'sobrante_mes_anterior': self.sobrante_mes_anterior,
            'total_enviado': self.total_enviado,
            'notes': self.notes,
            'created_by_name': self.creator.name if self.creator else None,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None,
        }
