"""
Cuentas → Año (Fase 3 de docs/PLAN_CUENTAS_DIARIAS.md): resumen mensual y
anual (lo que eran las hojas CierreGeneral2026 y DATOS_ANUALES_2026 del Excel).

- InventorySnapshot: valor del inventario de la tienda al último día de cada
  mes (o a hoy, para el mes en curso), traído del reporte de valor de
  inventario de Alegra.
- MonthlySummaryOverride: un valor escrito a mano para un dato de un mes
  (ventas, recompras, gastos, inventario...), para meses que el sistema no
  tiene completos (ej. septiembre, cuyos gastos están en el Excel) o para
  corregir. Manda sobre el valor calculado; el calculado se sigue mostrando.
"""
from datetime import datetime
from app.models.user import db
from app.models.store_scoped import StoreScopedMixin


class InventorySnapshot(StoreScopedMixin, db.Model):
    __tablename__ = 'inventory_snapshots'
    __table_args__ = (
        db.Index('uq_inventory_snapshot_store_period', 'store_code', 'period', unique=True),
    )

    id = db.Column(db.Integer, primary_key=True)
    period = db.Column(db.String(7), nullable=False)  # 'YYYY-MM'
    value = db.Column(db.Float, nullable=False)
    as_of = db.Column(db.Date, nullable=False)        # fecha de corte usada en Alegra
    fetched_at = db.Column(db.DateTime, default=datetime.utcnow)


class MonthlySummaryOverride(StoreScopedMixin, db.Model):
    __tablename__ = 'monthly_summary_overrides'
    __table_args__ = (
        db.Index('uq_monthly_override_store_period_field', 'store_code', 'period', 'field', unique=True),
    )

    id = db.Column(db.Integer, primary_key=True)
    period = db.Column(db.String(7), nullable=False)
    field = db.Column(db.String(30), nullable=False)
    value = db.Column(db.Float, nullable=False)
    note = db.Column(db.Text, nullable=True)
    updated_by = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
