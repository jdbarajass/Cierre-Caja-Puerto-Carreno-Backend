"""
Modelo para la persistencia del cierre de caja diario.

Antes de este modelo, POST /api/sum_payments era puramente transaccional
(calculaba y respondía, sin guardar nada). Este modelo guarda el resultado
de cada cierre para que el módulo de Cuentas pueda usarlo como fuente de
verdad al acreditar los saldos por medio de pago.
"""
from datetime import datetime
from app.models.user import db
from app.models.store_scoped import StoreScopedMixin
from app.models.account import _iso_utc


class CashClosing(StoreScopedMixin, db.Model):
    __tablename__ = 'cash_closings'

    # Un cierre por día POR TIENDA (antes closing_date era única globalmente -
    # ver _migrate_multi_store en app/__init__.py).
    __table_args__ = (
        db.Index('uq_cash_closings_store_date', 'store_code', 'closing_date', unique=True),
    )

    id = db.Column(db.Integer, primary_key=True)
    closing_date = db.Column(db.Date, nullable=False, index=True)

    # Montos por medio de pago tal como se registraron en el cierre
    efectivo = db.Column(db.Float, default=0, nullable=False)
    nequi = db.Column(db.Float, default=0, nullable=False)
    daviplata = db.Column(db.Float, default=0, nullable=False)
    qr = db.Column(db.Float, default=0, nullable=False)
    addi_datafono = db.Column(db.Float, default=0, nullable=False)

    # Excedentes del día por medio (2026-10-08, docs/PLAN_EXCEDENTES_Y_CARGA_EXCEL.md):
    # plata que entró pero NO es venta de Alegra (diferencia de un cambio de
    # prenda, de una tarjeta regalo, vueltas que deja un cliente). OJO:
    # `efectivo` es la plata física a consignar y YA incluye excedente_efectivo;
    # nequi/daviplata/qr/addi_datafono son lo registrado (= Alegra) y NO
    # incluyen su excedente. Al sincronizar (accounts.py) cada excedente se
    # abona aparte, como movimiento 'excedente'. NULL en cierres anteriores.
    excedente_efectivo = db.Column(db.Float, default=0, nullable=True)
    excedente_nequi = db.Column(db.Float, default=0, nullable=True)
    excedente_daviplata = db.Column(db.Float, default=0, nullable=True)
    excedente_qr = db.Column(db.Float, default=0, nullable=True)
    excedente_datafono = db.Column(db.Float, default=0, nullable=True)

    # Resultado de la validación contra Alegra al enviar el cierre
    # ('success' | 'warning' | 'error'). Solo un cierre 'success' (Cierre
    # exitoso) se puede sincronizar con Cuentas. NULL = cierre guardado antes
    # de este cambio: se deja sincronizar como siempre.
    validation_status = db.Column(db.String(10), nullable=True)
    validation_message = db.Column(db.String(500), nullable=True)

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

    # payment_key de la cuenta de Resumen -> excedente de ese medio
    EXCEDENTE_FIELDS = (
        ('cash', 'excedente_efectivo'),
        ('nequi', 'excedente_nequi'),
        ('daviplata', 'excedente_daviplata'),
        ('qr', 'excedente_qr'),
        ('addi_datafono', 'excedente_datafono'),
    )

    def excedentes(self):
        """Excedentes por payment_key (0 si el cierre es de antes del cambio)."""
        return {key: float(getattr(self, field) or 0) for key, field in self.EXCEDENTE_FIELDS}

    @property
    def can_sync(self):
        """Solo un Cierre exitoso pasa a Cuentas (NULL = cierre antiguo, se permite)."""
        return self.validation_status in (None, 'success')

    def to_dict(self):
        return {
            'id': self.id,
            'store_code': self.store_code,
            'closing_date': self.closing_date.isoformat() if self.closing_date else None,
            'efectivo': self.efectivo,
            'nequi': self.nequi,
            'daviplata': self.daviplata,
            'qr': self.qr,
            'addi_datafono': self.addi_datafono,
            'excedentes': self.excedentes(),
            'total_excedentes': sum(self.excedentes().values()),
            'validation_status': self.validation_status,
            'validation_message': self.validation_message,
            'can_sync': self.can_sync,
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
