"""
Incentivos por meta (Fase 4 de docs/PLAN_CUENTAS_DIARIAS.md): "si la venta
del mes pasa la META 1 (o la META 2), se paga este valor". Como los
INCENTIVO 1 e INCENTIVO 2 del Excel. El pago se registra como un gasto en
Cuentas → Gastos (marcado en notes 'auto:incentivo:<id>:<AAAA-MM>').
"""
from datetime import datetime
from app.models.user import db
from app.models.store_scoped import StoreScopedMixin

THRESHOLDS = ('meta1', 'meta2')


class IncentiveRule(StoreScopedMixin, db.Model):
    __tablename__ = 'incentive_rules'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(150), nullable=False)
    amount = db.Column(db.Float, nullable=False, default=0)
    threshold = db.Column(db.String(10), nullable=False, default='meta1')   # 'meta1' | 'meta2'
    category = db.Column(db.String(30), nullable=False, default='sueldo')  # categoría del gasto al pagarlo
    active = db.Column(db.Boolean, nullable=False, default=True)
    sort_order = db.Column(db.Integer, nullable=False, default=0)
    notes = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def to_dict(self):
        return {
            'id': self.id, 'name': self.name, 'amount': self.amount, 'threshold': self.threshold,
            'category': self.category, 'active': bool(self.active), 'sort_order': self.sort_order,
            'notes': self.notes,
        }
