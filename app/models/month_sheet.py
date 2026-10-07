"""
Cuentas → Mes (Fase 2 de docs/PLAN_CUENTAS_DIARIAS.md): hoja del mes por
medio de pago.

- PaymentFact: copia de los recibos de pago de Alegra (uno por factura
  pagada), con el medio de pago ya clasificado (los 10 medios del Excel).
  Se carga con el cron de las 9 pm (junto con la copia de facturas).
- AccountReconciliation: saldo real que el usuario escribe por cuenta y mes
  (lo que dice el banco), para compararlo con el saldo calculado.
- MonthClose: "foto" del estado del mes al cerrarlo (se puede reabrir).
- SaleMethodCorrection: corrección a mano del medio de pago de un día ("se
  pasó por datáfono pero al final pagó en efectivo"): mueve un valor de un
  medio a otro sin tocar Alegra ni la copia de recibos.
"""
from datetime import datetime
from app.models.user import db
from app.models.store_scoped import StoreScopedMixin


class PaymentFact(StoreScopedMixin, db.Model):
    __tablename__ = 'payment_facts'
    __table_args__ = (
        db.Index('uq_payment_facts_store_payment_invoice', 'store_code', 'payment_id', 'invoice_id', unique=True),
    )

    id = db.Column(db.Integer, primary_key=True)
    payment_id = db.Column(db.String(30), nullable=False)
    invoice_id = db.Column(db.String(30), nullable=False)
    invoice_number = db.Column(db.String(40))
    # La venta cuenta el día de la FACTURA (un recibo del 6 puede ser de una factura del 5)
    invoice_date = db.Column(db.Date, nullable=False, index=True)
    payment_date = db.Column(db.Date, nullable=False)
    payment_method = db.Column(db.String(30))   # cash, transfer, debit-card, credit-card...
    bank_account = db.Column(db.String(120))    # nombre de la cuenta en Alegra (QR, ADDI, DATAFONO...)
    medio = db.Column(db.String(20), nullable=False)  # uno de SALE_MEDIOS o 'otro'
    needs_review = db.Column(db.Boolean, nullable=False, default=False)
    amount = db.Column(db.BigInteger, nullable=False, default=0)
    synced_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)


class AccountReconciliation(StoreScopedMixin, db.Model):
    __tablename__ = 'account_reconciliations'
    __table_args__ = (
        db.Index('uq_account_reconciliation_period', 'account_id', 'period', unique=True),
    )

    id = db.Column(db.Integer, primary_key=True)
    account_id = db.Column(db.Integer, db.ForeignKey('accounts.id'), nullable=False, index=True)
    period = db.Column(db.String(7), nullable=False)  # 'YYYY-MM'
    real_balance = db.Column(db.Float, nullable=False)
    note = db.Column(db.Text, nullable=True)
    updated_by = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class SaleMethodCorrection(StoreScopedMixin, db.Model):
    __tablename__ = 'sale_method_corrections'

    id = db.Column(db.Integer, primary_key=True)
    date = db.Column(db.Date, nullable=False, index=True)      # día de la venta
    from_medio = db.Column(db.String(20), nullable=False)      # uno de SALE_MEDIOS
    to_medio = db.Column(db.String(20), nullable=False)
    amount = db.Column(db.BigInteger, nullable=False)          # siempre > 0
    note = db.Column(db.Text, nullable=True)
    created_by = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def to_dict(self):
        return {
            'id': self.id, 'date': self.date.isoformat(), 'from_medio': self.from_medio,
            'to_medio': self.to_medio, 'amount': self.amount, 'note': self.note,
            'created_at': self.created_at.isoformat() + 'Z' if self.created_at else None,
        }


class MonthClose(StoreScopedMixin, db.Model):
    __tablename__ = 'month_closes'
    __table_args__ = (
        db.Index('uq_month_close_store_period', 'store_code', 'period', unique=True),
    )

    id = db.Column(db.Integer, primary_key=True)
    period = db.Column(db.String(7), nullable=False)
    notes = db.Column(db.Text, nullable=True)
    snapshot = db.Column(db.Text, nullable=False)  # JSON con el estado por cuenta y las ventas del mes
    closed_by = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    closed_at = db.Column(db.DateTime, default=datetime.utcnow)
