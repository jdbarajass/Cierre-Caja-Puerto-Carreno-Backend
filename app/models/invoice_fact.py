"""
Resumen de cada factura de venta de Alegra, por tienda (fase 4 del
dashboard de clientes).

El reporte agregado de Alegra que usa la plataforma (/api/v1/reports/
sales-by-client) no trae cédula ni descuento y no separa por vendedora. Las
facturas sí: aquí se guarda lo necesario de cada una para calcular el % de
venta con cliente por vendedora, los descuentos y la cédula sin volver a
consultar Alegra.

- `InvoiceFact`: una fila por factura (anuladas incluidas, marcadas).
- `InvoiceSyncDay`: qué días de cada tienda ya están cargados. Un rango solo
  se calcula con InvoiceFact si TODOS sus días están aquí; si no, el
  dashboard sigue con el reporte agregado.

Montos en pesos enteros (COP, sin decimales en estas tiendas). synced_at en UTC,
como created_at en los demás modelos.
Ver app/services/invoice_facts.py.
"""
from datetime import datetime

from app.models.store_scoped import StoreScopedMixin
from app.models.user import db


class InvoiceFact(StoreScopedMixin, db.Model):
    __tablename__ = 'invoice_facts'
    __table_args__ = (
        db.Index('uq_invoice_facts_store_alegra_id', 'store_code', 'alegra_id', unique=True),
        db.Index('ix_invoice_facts_store_date', 'store_code', 'date'),
        db.Index('ix_invoice_facts_store_client', 'store_code', 'client_id'),
    )

    id = db.Column(db.Integer, primary_key=True)
    alegra_id = db.Column(db.String(30), nullable=False)
    date = db.Column(db.Date, nullable=False)
    number = db.Column(db.String(40))
    client_id = db.Column(db.String(30))
    client_name = db.Column(db.String(200))
    client_identification = db.Column(db.String(40))
    seller_id = db.Column(db.String(30))
    seller_name = db.Column(db.String(120))
    subtotal = db.Column(db.BigInteger, nullable=False, default=0)
    discount = db.Column(db.BigInteger, nullable=False, default=0)
    total = db.Column(db.BigInteger, nullable=False, default=0)
    voided = db.Column(db.Boolean, nullable=False, default=False)
    synced_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)


class InvoiceSyncDay(StoreScopedMixin, db.Model):
    __tablename__ = 'invoice_sync_days'
    __table_args__ = (
        db.Index('uq_invoice_sync_days_store_date', 'store_code', 'date', unique=True),
    )

    id = db.Column(db.Integer, primary_key=True)
    date = db.Column(db.Date, nullable=False)
    invoice_count = db.Column(db.Integer, nullable=False, default=0)
    synced_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
