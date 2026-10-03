"""
Alertas diarias para el admin (Fase D4 de docs/PLAN_ESTADISTICAS.md), por tienda.

Las calcula app/services/daily_alerts.py (cron de las 9 pm o botón) y se
muestran en el Dashboard. Una fila por (tienda, día analizado, tipo): volver
a calcular el mismo día actualiza la alerta y respeta si ya se descartó.
`data` = JSON con el detalle (facturas, prendas...). Fechas de control en UTC.
"""
from datetime import datetime

from app.models.store_scoped import StoreScopedMixin
from app.models.user import db


class DailyAlert(StoreScopedMixin, db.Model):
    __tablename__ = 'daily_alerts'
    __table_args__ = (
        db.Index('uq_daily_alerts_store_date_kind', 'store_code', 'date', 'kind', unique=True),
    )

    id = db.Column(db.Integer, primary_key=True)
    date = db.Column(db.Date, nullable=False)          # día analizado
    kind = db.Column(db.String(40), nullable=False)    # low_day, high_discounts, best_sellers_out, goal_pace
    severity = db.Column(db.String(20), nullable=False, default='info')  # warning | info
    title = db.Column(db.String(200), nullable=False)
    message = db.Column(db.Text)
    data = db.Column(db.Text)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    dismissed_at = db.Column(db.DateTime)
    dismissed_by = db.Column(db.String(120))
