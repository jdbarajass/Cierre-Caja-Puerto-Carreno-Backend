"""
Meta mensual de una vendedora AJUSTADA por el admin (Estadísticas → Metas,
Fase D3 de docs/PLAN_ESTADISTICAS.md), por tienda.

Solo se guardan los ajustes: la meta automática (mes del año anterior +15 %,
repartida por la venta de los últimos 3 meses) se calcula cada vez en
app/services/seller_goals.py. Borrar la fila = volver a la automática.
`month` = día 1 del mes. Monto en pesos enteros. updated_at en UTC.
"""
from datetime import datetime

from app.models.store_scoped import StoreScopedMixin
from app.models.user import db


class SellerGoal(StoreScopedMixin, db.Model):
    __tablename__ = 'seller_goals'
    __table_args__ = (
        db.Index('uq_seller_goals_store_month_seller', 'store_code', 'month', 'seller_id', unique=True),
    )

    id = db.Column(db.Integer, primary_key=True)
    month = db.Column(db.Date, nullable=False)
    seller_id = db.Column(db.String(30), nullable=False)
    seller_name = db.Column(db.String(120))
    amount = db.Column(db.BigInteger, nullable=False)
    updated_by = db.Column(db.String(120))
    updated_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
