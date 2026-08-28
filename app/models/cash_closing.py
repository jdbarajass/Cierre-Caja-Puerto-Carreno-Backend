"""
Modelo para la persistencia del cierre de caja diario.

Antes de este modelo, POST /api/sum_payments era puramente transaccional
(calculaba y respondía, sin guardar nada). Este modelo guarda el resultado
de cada cierre para que el módulo de Cuentas pueda usarlo como fuente de
verdad al acreditar los saldos por medio de pago.
"""
from datetime import datetime
from app.models.user import db
from app.models.account import _iso_utc


class CashClosing(db.Model):
    __tablename__ = 'cash_closings'

    id = db.Column(db.Integer, primary_key=True)
    closing_date = db.Column(db.Date, unique=True, nullable=False, index=True)

    # Montos por medio de pago tal como se registraron en el cierre
    efectivo = db.Column(db.Float, default=0, nullable=False)
    nequi = db.Column(db.Float, default=0, nullable=False)
    daviplata = db.Column(db.Float, default=0, nullable=False)
    qr = db.Column(db.Float, default=0, nullable=False)
    addi_datafono = db.Column(db.Float, default=0, nullable=False)

    # Totales reportados por Alegra para ese día (para verificación, no para acreditar)
    alegra_total_efectivo = db.Column(db.Float, nullable=True)
    alegra_total_transferencia = db.Column(db.Float, nullable=True)
    alegra_total_tarjeta = db.Column(db.Float, nullable=True)

    # Resultado de la sincronización con Cuentas (ver app/routes/accounts.py)
    alegra_checked = db.Column(db.Boolean, default=False, nullable=False)
    alegra_discrepancy = db.Column(db.Float, nullable=True)
    synced_to_accounts = db.Column(db.Boolean, default=False, nullable=False)
    synced_at = db.Column(db.DateTime, nullable=True)

    created_by = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    creator = db.relationship('User', foreign_keys=[created_by], lazy='joined')

    def to_dict(self):
        return {
            'id': self.id,
            'closing_date': self.closing_date.isoformat() if self.closing_date else None,
            'efectivo': self.efectivo,
            'nequi': self.nequi,
            'daviplata': self.daviplata,
            'qr': self.qr,
            'addi_datafono': self.addi_datafono,
            'alegra_total_efectivo': self.alegra_total_efectivo,
            'alegra_total_transferencia': self.alegra_total_transferencia,
            'alegra_total_tarjeta': self.alegra_total_tarjeta,
            'alegra_checked': self.alegra_checked,
            'alegra_discrepancy': self.alegra_discrepancy,
            'synced_to_accounts': self.synced_to_accounts,
            'synced_at': _iso_utc(self.synced_at),
            'created_by_name': self.creator.name if self.creator else None,
            'created_at': _iso_utc(self.created_at),
            'updated_at': _iso_utc(self.updated_at),
        }
