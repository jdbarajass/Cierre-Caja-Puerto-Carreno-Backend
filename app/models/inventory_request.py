"""
Solicitudes de ajuste de inventario (docs/PLAN_AJUSTES_INVENTARIO.md): las
vendedoras las registran en su tienda y NO tocan Alegra hasta que el admin las
acepta. Al aceptar se crea el ajuste en Alegra y se guarda su número.

Estados:
  pendiente  -> esperando al admin (también vuelve aquí si Alegra la rechazó)
  aplicando  -> el admin la aceptó y se está creando en Alegra
  revisar    -> Alegra no respondió: puede o no haberse creado (al reintentar
                se busca primero por la marca [KOAJ-AJ-<id>])
  aplicada   -> creada en Alegra (alegra_number)
  rechazada  -> el admin la rechazó (reject_reason)
  cancelada  -> la quitó quien la pidió antes de que se aplicara
"""
import json
from datetime import datetime

from app.models.user import db
from app.models.store_scoped import StoreScopedMixin

KINDS = ('conteo', 'tarjeta_regalo')
KIND_LABELS = {'conteo': 'Conteo de inventario', 'tarjeta_regalo': 'Redimir tarjeta regalo'}
STATUSES = ('pendiente', 'aplicando', 'revisar', 'aplicada', 'rechazada', 'cancelada')
OPEN_STATUSES = ('pendiente', 'revisar')


class InventoryRequest(StoreScopedMixin, db.Model):
    __tablename__ = 'inventory_requests'

    id = db.Column(db.Integer, primary_key=True)
    kind = db.Column(db.String(20), nullable=False)
    status = db.Column(db.String(20), nullable=False, default='pendiente', index=True)
    request_date = db.Column(db.Date, nullable=False)        # día Colombia: fecha del ajuste en Alegra
    requested_by = db.Column(db.String(100), nullable=False)  # empleada que lo pide
    notes = db.Column(db.Text, nullable=True)
    # Renglones [{code, item_id, name, type 'in'|'out', quantity, system_qty, physical_qty?}]
    lines_json = db.Column(db.Text, nullable=False, default='[]')
    # Tarjeta regalo: lo que pagó de más el cliente (solo nota; la plata entra por el cierre)
    excedente_valor = db.Column(db.Float, nullable=True)
    excedente_medio = db.Column(db.String(30), nullable=True)

    created_by_user_id = db.Column(db.Integer, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    reviewed_by_user_id = db.Column(db.Integer, nullable=True)
    reviewed_at = db.Column(db.DateTime, nullable=True)
    reject_reason = db.Column(db.Text, nullable=True)
    last_error = db.Column(db.Text, nullable=True)
    alegra_id = db.Column(db.String(64), nullable=True)
    alegra_number = db.Column(db.String(30), nullable=True)

    @property
    def lines(self):
        return json.loads(self.lines_json or '[]')

    @lines.setter
    def lines(self, value):
        self.lines_json = json.dumps(value, ensure_ascii=False)

    def to_dict(self):
        return {
            'id': self.id, 'kind': self.kind, 'kind_label': KIND_LABELS.get(self.kind, self.kind),
            'status': self.status, 'request_date': self.request_date.isoformat() if self.request_date else None,
            'requested_by': self.requested_by, 'notes': self.notes, 'lines': self.lines,
            'excedente_valor': self.excedente_valor, 'excedente_medio': self.excedente_medio,
            'created_at': self.created_at.isoformat() + 'Z' if self.created_at else None,
            'reviewed_at': self.reviewed_at.isoformat() + 'Z' if self.reviewed_at else None,
            'reject_reason': self.reject_reason, 'last_error': self.last_error,
            'alegra_id': self.alegra_id, 'alegra_number': self.alegra_number,
            'store_code': self.store_code,
        }
