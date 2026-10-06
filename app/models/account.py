"""
Modelos para el módulo de Cuentas (saldo por medio de pago, ajustes manuales,
transferencias entre cuentas y créditos automáticos desde el cierre de caja).
"""
from datetime import datetime
from app.models.user import db
from app.models.store_scoped import StoreScopedMixin

# Tipos válidos de movimiento (documentado aquí, no se fuerza con CHECK constraint
# para mantener el mismo estilo simple del resto del proyecto)
MOVEMENT_TYPES = (
    'manual_adjustment',
    'transfer_out',
    'transfer_in',
    'cash_closing',
    'repurchase_send',
    'expense',      # Cuentas → Gastos: salida (app/routes/expenses.py)
    'expense_in',   # Cuentas → Gastos: entrada que no es venta
)


def _iso_utc(dt):
    """
    Serializa un datetime naive (guardado con datetime.utcnow()) marcándolo
    explícitamente como UTC. Sin el sufijo 'Z', el parser de fechas de
    JavaScript en el frontend interpreta el string como hora LOCAL del
    navegador en vez de UTC, mostrando la hora desplazada.
    """
    if not dt:
        return None
    return dt.isoformat() + 'Z'


class Account(StoreScopedMixin, db.Model):
    __tablename__ = 'accounts'
    # Nombre y payment_key únicos POR TIENDA (cada tienda tiene su propio
    # EFECTIVO, NEQUI, etc.) - antes eran únicos globalmente, ver
    # _migrate_multi_store en app/__init__.py.
    __table_args__ = (
        db.Index('uq_accounts_store_name', 'store_code', 'name', unique=True),
        db.Index('uq_accounts_store_payment_key', 'store_code', 'payment_key', unique=True),
    )

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    payment_key = db.Column(db.String(50), nullable=False)
    color = db.Column(db.String(20), default='blue')
    balance = db.Column(db.Float, default=0, nullable=False)
    active = db.Column(db.Boolean, default=True, nullable=False)
    sort_order = db.Column(db.Integer, default=0, nullable=False)
    # Nota manual, editable desde la UI: hasta qué fecha el usuario contempla
    # que el saldo mostrado ya debería estar consignado (ej. ADDI paga días
    # después de la transacción). No afecta ningún cálculo - solo ayuda a
    # corroborar si ya tocaría revisar/actualizar el saldo.
    contemplated_until = db.Column(db.Date, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def to_dict(self):
        return {
            'id': self.id,
            'store_code': self.store_code,
            'name': self.name,
            'payment_key': self.payment_key,
            'color': self.color,
            'balance': self.balance,
            'active': self.active,
            'sort_order': self.sort_order,
            'contemplated_until': self.contemplated_until.isoformat() if self.contemplated_until else None,
            'created_at': _iso_utc(self.created_at),
            'updated_at': _iso_utc(self.updated_at),
        }


class AccountMovement(db.Model):
    __tablename__ = 'account_movements'

    id = db.Column(db.Integer, primary_key=True)
    account_id = db.Column(db.Integer, db.ForeignKey('accounts.id'), nullable=False, index=True)
    type = db.Column(db.String(30), nullable=False)
    amount = db.Column(db.Float, nullable=False)  # con signo: + entra, - sale
    description = db.Column(db.Text, nullable=True)
    reference_id = db.Column(db.String(64), nullable=True, index=True)
    cash_closing_id = db.Column(db.Integer, db.ForeignKey('cash_closings.id'), nullable=True)
    created_by = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, index=True)

    account = db.relationship('Account', foreign_keys=[account_id])
    creator = db.relationship('User', foreign_keys=[created_by], lazy='joined')

    def to_dict(self):
        return {
            'id': self.id,
            'account_id': self.account_id,
            'account_name': self.account.name if self.account else None,
            'type': self.type,
            'amount': self.amount,
            'description': self.description,
            'reference_id': self.reference_id,
            'cash_closing_id': self.cash_closing_id,
            'created_by_name': self.creator.name if self.creator else None,
            'created_at': _iso_utc(self.created_at),
        }
