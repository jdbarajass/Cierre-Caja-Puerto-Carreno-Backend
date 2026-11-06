"""
Préstamos de cada tienda (Radiografía Fase 0c, docs/PLAN_RADIOGRAFIA.md).

Pedido del usuario (2026-11-06): una tarjeta por deuda que baja con cada pago
y, al darle clic, el detalle (valor prestado, pagos hechos, lo que falta).
- Carreño: mamá de Angie (deuda de la apertura).
- Primavera: don Miguel (BBVA), 3 préstamos en una misma tarjeta (`group_name`);
  al pagar se escoge a cuál préstamo va.

Monto, plazo, tasa y cuota son editables: si se cambia el plazo o la tasa se
recalcula la cuota; si se cambia la cuota se recalcula la tasa. La tabla de
pagos (interés y capital de cada uno) se recalcula siempre con los valores de
hoy (app/services/loans.py). Cada edición deja rastro en `history` (JSON).

Los pagos son `LoanPayment`:
- kind='pago': salió plata de la tienda; está ligado a un gasto de Cuentas →
  Gastos (`expense_id`, cuota de crédito) que mueve las cuentas. Se registra
  desde la tarjeta o desde Gastos, siempre un solo gasto.
- kind='descontado': la cuota se descontó del mismo préstamo (no salió plata
  de las cuentas, no es gasto del mes).
- kind='ajuste': "Ajustar saldo" para igualar con el banco (con nota); no es
  pago ni gasto.
"""
from datetime import datetime

from app.models.store_scoped import StoreScopedMixin
from app.models.user import db

PAYMENT_KINDS = ('pago', 'descontado', 'ajuste')


class Loan(StoreScopedMixin, db.Model):
    __tablename__ = 'loans'

    id = db.Column(db.Integer, primary_key=True)
    group_name = db.Column(db.String(100), nullable=False)   # la tarjeta ("Don Miguel (BBVA)")
    name = db.Column(db.String(150), nullable=False)         # el préstamo ("Préstamo de $20.000.000")
    principal = db.Column(db.Float, nullable=False)          # valor prestado (o saldo de partida)
    start_date = db.Column(db.Date, nullable=False)          # desde cuándo cuentan los pagos
    term_months = db.Column(db.Integer, nullable=True)       # plazo
    monthly_rate_pct = db.Column(db.Float, nullable=True)    # interés mensual %
    rate_estimated = db.Column(db.Boolean, default=True, nullable=False)
    installment = db.Column(db.Float, nullable=True)         # cuota (None = libre)
    due_day = db.Column(db.Integer, default=25, nullable=False)  # el aviso sale desde este día
    fixed_expense_id = db.Column(db.Integer, nullable=True)  # gasto fijo de la cuota
    active = db.Column(db.Boolean, default=True, nullable=False)
    notes = db.Column(db.Text, nullable=True)
    history = db.Column(db.Text, nullable=True)              # JSON: cambios con rastro
    sort_order = db.Column(db.Integer, default=0, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class LoanPayment(StoreScopedMixin, db.Model):
    __tablename__ = 'loan_payments'

    id = db.Column(db.Integer, primary_key=True)
    loan_id = db.Column(db.Integer, db.ForeignKey('loans.id'), nullable=False, index=True)
    date = db.Column(db.Date, nullable=False, index=True)
    kind = db.Column(db.String(12), nullable=False, default='pago')
    amount = db.Column(db.Float, nullable=False)   # ajuste: + baja el saldo, − lo sube
    expense_id = db.Column(db.Integer, nullable=True, index=True, unique=True)
    note = db.Column(db.Text, nullable=True)
    created_by = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
