"""
Prendas de cada compra de mercancía (factura de proveedor en Alegra), por
tienda: Estadísticas → Llegadas (Fase D1 de docs/PLAN_ESTADISTICAS.md).

Alegra trae las prendas de cada compra en `/bills` (`purchases.items`). Son
pocas (~140 compras en 2026), así que en cada carga se reemplazan TODAS las
del periodo guardado (recoge compras editadas, anuladas o registradas tarde).

`unit_price` es el que trae la compra, que en estas tiendas es el precio de
VENTA (no el costo): no sirve para margen.
Una fila por renglón de cada compra no anulada. synced_at en UTC.
Ver app/services/purchase_facts.py.
"""
from datetime import datetime

from app.models.store_scoped import StoreScopedMixin
from app.models.user import db


class PurchaseItemFact(StoreScopedMixin, db.Model):
    __tablename__ = 'purchase_item_facts'
    __table_args__ = (
        db.Index('uq_purchase_item_facts_store_bill_line', 'store_code', 'bill_alegra_id', 'line', unique=True),
        db.Index('ix_purchase_item_facts_store_date', 'store_code', 'date'),
    )

    id = db.Column(db.Integer, primary_key=True)
    bill_alegra_id = db.Column(db.String(30), nullable=False)
    bill_number = db.Column(db.String(40))
    line = db.Column(db.Integer, nullable=False)  # posición del renglón en la compra
    date = db.Column(db.Date, nullable=False)
    provider_id = db.Column(db.String(30))
    provider_name = db.Column(db.String(200))
    item_id = db.Column(db.String(30))
    name = db.Column(db.String(200), nullable=False)
    quantity = db.Column(db.Integer, nullable=False, default=0)
    unit_price = db.Column(db.BigInteger, nullable=False, default=0)
    synced_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
