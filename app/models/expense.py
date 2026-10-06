"""
Gastos y otros movimientos de plata (Cuentas → Gastos), Fase 1 del plan
docs/PLAN_CUENTAS_DIARIAS.md.

Cada registro es una salida (gasto, préstamo, retiro de socio, inversión...)
o una entrada que no es venta (devolución de un préstamo, ingreso extra),
con el monto por medio de pago. Según `account_mode` mueve o no el saldo de
las cuentas de Resumen (ver _sync_expense_account_movements en
app/routes/expenses.py).
"""
from datetime import datetime
from app.models.user import db
from app.models.store_scoped import StoreScopedMixin

# Medio de pago del gasto -> payment_key de la cuenta (Account) de donde sale
# o a donde entra la plata. 'datafono' es la cuenta Bancolombia …6018 donde
# llegan el datáfono y Addi (ADDI + DATÁFONO en Resumen).
EXPENSE_ACCOUNT_MAP = {
    'efectivo':  'cash',
    'datafono':  'addi_datafono',
    'qr':        'qr',
    'daviplata': 'daviplata',
    'nequi':     'nequi',
    'bbva':      'bbva',
    'ahorro':    'ahorro',
}
EXPENSE_METHODS = tuple(EXPENSE_ACCOUNT_MAP)

OUT_CATEGORIES = (
    'operativo',          # arriendo, servicios, aseo, bolsas, transporte...
    'sueldo',             # sueldos (con empleada -> Empleadas → Pagos)
    'flete',              # flete de mercancía (costo de la ropa)
    'financiero',         # 4x1000, cuota de manejo, intereses
    'cuota_credito',      # cuotas de créditos (Scotiabank, Davivienda)
    'inversion',          # activos: equipos, herrajería, cámaras
    'prestamo_empleada',  # con empleada -> Empleadas → Préstamos
    'prestamo_tienda',    # plata de esta tienda para otra (Carreño -> Primavera)
    'retiro_socio',       # ganancia que retira un socio
    'otro',
)
IN_CATEGORIES = (
    'devolucion_prestamo',        # una empleada u otra persona devuelve plata
    'devolucion_prestamo_tienda', # la otra tienda devuelve lo que se le prestó
    'ingreso_extra',              # plata que entra y no es venta
)

# cuentas: mueve el saldo de las cuentas de Resumen (por defecto).
# caja: salió de la caja del día; el cierre de caja YA abonó a EFECTIVO lo que
#       quedó después de sacarlo, así que no se vuelve a descontar.
# sin_mover: no toca cuentas (históricos o algo ya descontado por otro lado).
ACCOUNT_MODES = ('cuentas', 'caja', 'sin_mover')


class Expense(StoreScopedMixin, db.Model):
    __tablename__ = 'expenses'

    id = db.Column(db.Integer, primary_key=True)
    # Fecha en que salió/entró la plata (la que mueve las cuentas)
    date = db.Column(db.Date, nullable=False, index=True)
    # Mes al que corresponde para la ganancia ('YYYY-MM'); por defecto el de date
    period = db.Column(db.String(7), nullable=False, index=True)
    concept = db.Column(db.String(255), nullable=False)
    category = db.Column(db.String(30), nullable=False, default='operativo')
    direction = db.Column(db.String(3), nullable=False, default='out')  # 'out' | 'in'

    efectivo  = db.Column(db.Float, default=0, nullable=False)
    datafono  = db.Column(db.Float, default=0, nullable=False)
    qr        = db.Column(db.Float, default=0, nullable=False)
    daviplata = db.Column(db.Float, default=0, nullable=False)
    nequi     = db.Column(db.Float, default=0, nullable=False)
    bbva      = db.Column(db.Float, default=0, nullable=False)
    ahorro    = db.Column(db.Float, default=0, nullable=False)

    # 4x1000: automático sobre lo que no es efectivo (solo salidas) si
    # apply_fee; fee_override manda si el banco cobró distinto.
    apply_fee = db.Column(db.Boolean, default=True, nullable=False)
    fee_override = db.Column(db.Float, nullable=True)

    account_mode = db.Column(db.String(10), nullable=False, default='cuentas')

    # Préstamos entre tiendas: la otra tienda (la que recibe el préstamo o la
    # que devuelve)
    related_store_code = db.Column(db.String(20), nullable=True, index=True)

    # Enlace con Empleadas (préstamos y sueldos)
    employee_name = db.Column(db.String(100), nullable=True)
    employee_loan_id = db.Column(db.Integer, nullable=True)
    employee_payment_id = db.Column(db.Integer, nullable=True)

    fixed_expense_id = db.Column(db.Integer, db.ForeignKey('fixed_expenses.id'), nullable=True, index=True)

    notes = db.Column(db.Text, nullable=True)
    created_by = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    creator = db.relationship('User', foreign_keys=[created_by], lazy='joined')

    @property
    def total(self):
        return sum(getattr(self, m) or 0 for m in EXPENSE_METHODS)

    @property
    def non_cash_total(self):
        return self.total - (self.efectivo or 0)

    @property
    def fee_auto(self):
        if self.direction != 'out' or not self.apply_fee:
            return 0
        return round(self.non_cash_total * 4 / 1000)

    @property
    def fee(self):
        if self.direction != 'out':
            return 0
        if self.fee_override is not None:
            return self.fee_override
        return self.fee_auto

    @property
    def total_with_fee(self):
        return self.total + self.fee

    def to_dict(self):
        data = {
            'id': self.id,
            'store_code': self.store_code,
            'date': self.date.isoformat() if self.date else None,
            'period': self.period,
            'concept': self.concept,
            'category': self.category,
            'direction': self.direction,
            'apply_fee': bool(self.apply_fee),
            'fee_override': self.fee_override,
            'fee': self.fee,
            'total': self.total,
            'total_with_fee': self.total_with_fee,
            'account_mode': self.account_mode,
            'related_store_code': self.related_store_code,
            'employee_name': self.employee_name,
            'employee_loan_id': self.employee_loan_id,
            'employee_payment_id': self.employee_payment_id,
            'fixed_expense_id': self.fixed_expense_id,
            'notes': self.notes,
            'created_by_name': self.creator.name if self.creator else None,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None,
        }
        for m in EXPENSE_METHODS:
            data[m] = getattr(self, m) or 0
        return data


class FixedExpense(StoreScopedMixin, db.Model):
    """Gasto que se paga todos los meses (arriendo, sueldos, internet...)."""
    __tablename__ = 'fixed_expenses'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(150), nullable=False)
    amount = db.Column(db.Float, default=0, nullable=False)  # valor de referencia
    due_day = db.Column(db.Integer, nullable=False, default=30)  # día de pago (1-31)
    category = db.Column(db.String(30), nullable=False, default='operativo')
    default_method = db.Column(db.String(20), nullable=True)
    active = db.Column(db.Boolean, default=True, nullable=False)
    sort_order = db.Column(db.Integer, default=0, nullable=False)
    notes = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def to_dict(self):
        return {
            'id': self.id,
            'name': self.name,
            'amount': self.amount,
            'due_day': self.due_day,
            'category': self.category,
            'default_method': self.default_method,
            'active': bool(self.active),
            'sort_order': self.sort_order,
            'notes': self.notes,
        }
