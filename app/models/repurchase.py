"""
Modelo para Cuentas de Recompras (dinero enviado al socio para recompra de mercancía).
"""
from datetime import datetime
from app.models.user import db


class RepurchaseEntry(db.Model):
    __tablename__ = 'repurchase_entries'

    id = db.Column(db.Integer, primary_key=True)
    date = db.Column(db.Date, nullable=False, index=True)

    # Descripción de la fila (ej: "Recompra Jhonatan", "Préstamo a Camila")
    descripcion = db.Column(db.String(200), nullable=False, default='Recompra Jhonatan')

    # Dinero pendiente en tienda (aún no enviado al socio)
    valor_no_enviado = db.Column(db.Float, default=0, nullable=False)

    # Montos ya enviados/consignados al socio, por medio de pago
    efectivo   = db.Column(db.Float, default=0, nullable=False)
    datafono   = db.Column(db.Float, default=0, nullable=False)
    qr         = db.Column(db.Float, default=0, nullable=False)
    daviplata  = db.Column(db.Float, default=0, nullable=False)
    nequi      = db.Column(db.Float, default=0, nullable=False)
    bbva       = db.Column(db.Float, default=0, nullable=False)

    # Sobrante del mes anterior
    sobrante_mes_anterior = db.Column(db.Float, default=0, nullable=False)

    # Fecha de la factura de compra (sección derecha del Excel)
    fecha_compra = db.Column(db.Date, nullable=True)

    notes = db.Column(db.Text, nullable=True)
    created_by = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # True solo para envíos creados a partir de 2026-09-01, cuando se conectó
    # Cuentas Recompras con Resumen: solo esos descuentan/reponen saldo de
    # cuentas automáticamente al crear/editar/eliminar (ver _sync_entry_
    # account_movements en app/routes/repurchase.py). Los envíos anteriores
    # quedan sin tocar (nunca se sincronizaron, ni retroactivamente).
    synced_to_accounts = db.Column(db.Boolean, default=False, nullable=True)

    creator = db.relationship('User', foreign_keys=[created_by], lazy='joined')

    @property
    def total_enviado(self):
        return (self.efectivo + self.datafono + self.qr +
                self.daviplata + self.nequi + self.bbva)

    @property
    def fee_4mil(self):
        """Comisión 4 por mil sobre el total enviado."""
        return round(self.total_enviado * 4 / 1000)

    @property
    def valor_sobrante(self):
        """Total enviado menos la comisión 4‰."""
        return self.total_enviado - self.fee_4mil

    def to_dict(self):
        return {
            'id': self.id,
            'date': self.date.isoformat() if self.date else None,
            'descripcion': self.descripcion,
            'valor_no_enviado': self.valor_no_enviado,
            'efectivo': self.efectivo,
            'datafono': self.datafono,
            'qr': self.qr,
            'daviplata': self.daviplata,
            'nequi': self.nequi,
            'bbva': self.bbva,
            'sobrante_mes_anterior': self.sobrante_mes_anterior,
            'fecha_compra': self.fecha_compra.isoformat() if self.fecha_compra else None,
            'total_enviado': self.total_enviado,
            'fee_4mil': self.fee_4mil,
            'valor_sobrante': self.valor_sobrante,
            'notes': self.notes,
            'synced_to_accounts': bool(self.synced_to_accounts),
            'created_by_name': self.creator.name if self.creator else None,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None,
        }
