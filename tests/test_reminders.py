"""
Recordatorios del administrador (app/services/reminders.py): congelar la
copia en diciembre, cerrar el mes anterior y bajar el respaldo. Base SQLite
temporal, sin red; la fecha de "hoy" se simula.
"""
from datetime import date, datetime

import pytest

from app.config import TestingConfig


@pytest.fixture
def app(tmp_path):
    class RemindersTestConfig(TestingConfig):
        SQLALCHEMY_DATABASE_URI = f"sqlite:///{(tmp_path / 'reminders.db').as_posix()}"
        SQLALCHEMY_ENGINE_OPTIONS = {}

    from app import create_app
    return create_app(RemindersTestConfig)


@pytest.fixture
def h(app):
    from app.services.jwt_service import JWTService
    with app.app_context():
        token = JWTService.generate_token(1, 'admin1@test.com', 'admin', None)
    return lambda store=None: {'Authorization': f'Bearer {token}', **({'X-Store': store} if store else {})}


def _at(monkeypatch, d):
    import app.routes.reminders as routes
    monkeypatch.setattr(routes, 'get_colombia_now', lambda: datetime(d.year, d.month, d.day, 9, 0))


def _keys(client, h, store=None):
    return [r['key'] for r in client.get('/api/reminders', headers=h(store)).get_json()['reminders']]


def test_diciembre_pide_congelar_hasta_que_se_congele(app, client, h, monkeypatch):
    _at(monkeypatch, date(2026, 10, 20))
    assert _keys(client, h) == []                                  # octubre: nada
    _at(monkeypatch, date(2026, 12, 15))
    data = client.get('/api/reminders', headers=h()).get_json()['reminders']
    assert [r['key'] for r in data] == ['freeze-2026']
    assert data[0]['path'] == '/estadisticas-estandar/respaldo-facturas'
    assert any('CONGELAR' in s for s in data[0]['steps'])
    _at(monkeypatch, date(2027, 1, 4))
    assert 'freeze-2026' in _keys(client, h)                       # sigue en enero
    # ya congelada hasta el 31-dic: desaparece sola
    from app.services import facts_freeze
    with app.app_context():
        facts_freeze._save('carreno', {'until': '2026-12-31', 'frozen_at': 'x'})
    assert 'freeze-2026' not in _keys(client, h)
    assert 'freeze-2026' in _keys(client, h, 'primavera')          # cada tienda aparte


def test_posponer_y_ya_lo_hice(app, client, h, monkeypatch):
    _at(monkeypatch, date(2026, 12, 15))
    assert client.post('/api/reminders/freeze-2026/snooze', headers=h(), json={'days': 3}).status_code == 200
    assert _keys(client, h) == []
    _at(monkeypatch, date(2026, 12, 18))
    assert _keys(client, h) == ['freeze-2026']
    assert client.post('/api/reminders/freeze-2026/done', headers=h()).status_code == 200
    assert _keys(client, h) == []
    assert client.post('/api/reminders/otro/done', headers=h()).status_code == 404


def test_cerrar_mes_y_respaldo(app, client, h, monkeypatch):
    _at(monkeypatch, date(2026, 11, 3))
    assert _keys(client, h) == ['month-close-2026-10', 'backup-2026-11']
    # el cierre del mes no se marca a mano: se quita al cerrar octubre
    assert client.post('/api/reminders/month-close-2026-10/done', headers=h()).status_code == 400
    from app.models.month_sheet import MonthClose
    from app.models.user import db
    with app.app_context():
        db.session.add(MonthClose(store_code='carreno', period='2026-10', snapshot='{}'))
        db.session.commit()
    assert _keys(client, h) == ['backup-2026-11']
    assert client.post('/api/reminders/backup-2026-11/done', headers=h()).status_code == 200
    assert _keys(client, h) == []
    _at(monkeypatch, date(2026, 11, 15))                           # después del día 10: nada
    assert _keys(client, h, 'primavera') == []


def test_solo_admin(app, client):
    from app.services.jwt_service import JWTService
    with app.app_context():
        token = JWTService.generate_token(2, 'vende@test.com', 'sales', None)
    assert client.get('/api/reminders', headers={'Authorization': f'Bearer {token}'}).status_code == 403
