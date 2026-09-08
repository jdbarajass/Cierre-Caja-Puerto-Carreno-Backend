"""
Tabla de configuración genérica (clave -> valor de texto) para banderas y
anclas que el sistema necesita recordar entre reinicios/despliegues, pero que
no ameritan su propia tabla dedicada.

Uso actual:
- 'pending_closings_tracking_start_date': fecha (YYYY-MM-DD) desde la cual el
  aviso de "cierre de caja pendiente" empieza a marcar días como faltantes.
  Se fija sola la primera vez que se consulta ese aviso (normalmente el día
  que se despliega esta funcionalidad) y nunca se mueve hacia atrás - así los
  días anteriores (llevados a mano o simplemente de antes de que existiera
  este aviso) nunca aparecen marcados como pendientes.
- 'last_sync_failure': JSON de texto con el detalle de la última corrida
  fallida del cron de sincronización diaria (ver app/routes/accounts.py).
  Se borra automáticamente en la siguiente sincronización exitosa.
"""
from app.models.user import db


class AppSetting(db.Model):
    __tablename__ = 'app_settings'

    key = db.Column(db.String(100), primary_key=True)
    value = db.Column(db.Text, nullable=True)
    updated_at = db.Column(db.DateTime, nullable=True)
