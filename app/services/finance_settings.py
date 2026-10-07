"""
Configuración financiera por tienda (Fase 4 de docs/PLAN_CUENTAS_DIARIAS.md),
guardada en app_settings ('finance_settings', JSON, una clave por tienda):

- goal_growth_pct: % de crecimiento de la meta de la tienda sobre el mismo mes
  del año anterior (Estadísticas → Metas; antes fijo en 15; el Excel usa 25).
- meta2_extra: META 2 = META 1 + este valor (Excel: $300.000).
- resurtido_pct: % de la venta que debe ir a resurtido (regla 70/30).
- margin_pct: margen para pasar plata de resurtido a ropa a precio de venta
  (Excel: valor / (1 − 0,35)).
"""
import json
from datetime import datetime
from typing import Any, Dict

from app.models.app_setting import AppSetting
from app.models.user import db
from app.stores import store_setting_key

SETTING_KEY = 'finance_settings'

DEFAULTS = {
    'goal_growth_pct': 15,
    'meta2_extra': 300000,
    'resurtido_pct': 70,
    'margin_pct': 35,
}
LIMITS = {
    'goal_growth_pct': (-50, 200),
    'meta2_extra': (0, 1_000_000_000),
    'resurtido_pct': (0, 100),
    'margin_pct': (0, 95),
}


def get_settings(store: str) -> Dict[str, Any]:
    row = AppSetting.query.get(store_setting_key(SETTING_KEY, store))
    saved = {}
    if row and row.value:
        try:
            saved = json.loads(row.value)
        except ValueError:
            saved = {}
    return {k: saved.get(k, v) for k, v in DEFAULTS.items()}


def save_settings(store: str, data: Dict[str, Any]) -> Dict[str, Any]:
    """Valida y guarda solo las claves conocidas que vengan en data."""
    current = get_settings(store)
    for key, (low, high) in LIMITS.items():
        if key not in data:
            continue
        try:
            value = float(data[key])
        except (TypeError, ValueError):
            raise ValueError(f'Valor inválido para {key}')
        if not low <= value <= high:
            raise ValueError(f'{key} debe estar entre {low} y {high}')
        current[key] = int(value) if value == int(value) else value
    key = store_setting_key(SETTING_KEY, store)
    row = AppSetting.query.get(key)
    if row is None:
        row = AppSetting(key=key)
        db.session.add(row)
    row.value = json.dumps(current)
    row.updated_at = datetime.utcnow()
    db.session.commit()
    return current
