"""
4x1000 de las recompras (2026-11-18): lo enviado en EFECTIVO no paga 4x1000,
igual que en Gastos. Solo para envíos creados desde CASH_FEE_EXEMPT_SINCE
(app/models/repurchase.py); los anteriores conservan su comisión.

Base SQLite temporal, sin red.
"""
from datetime import datetime

import pytest

from app.config import TestingConfig


@pytest.fixture
def app(tmp_path):
    class FeeTestConfig(TestingConfig):
        SQLALCHEMY_DATABASE_URI = f"sqlite:///{(tmp_path / 'fee.db').as_posix()}"
        SQLALCHEMY_ENGINE_OPTIONS = {}

    from app import create_app
    return create_app(FeeTestConfig)


@pytest.fixture
def client(app):
    return app.test_client()


@pytest.fixture
def h(app):
    from app.services.jwt_service import JWTService
    with app.app_context():
        token = JWTService.generate_token(1, 'admin1@test.com', 'admin', None)
    return lambda store=None: {
        'Authorization': f'Bearer {token}', **({'X-Store': store} if store else {})
    }


def _balances(client, headers):
    accounts = client.get('/api/accounts', headers=headers).get_json()['accounts']
    return {a['payment_key']: a['balance'] for a in accounts}


@pytest.mark.parametrize('store', [None, 'primavera'])
def test_recompra_en_efectivo_no_paga_4x1000(client, h, store):
    resp = client.post('/api/repurchase', headers=h(store), json={'date': '2026-11-18', 'efectivo': 2009900})
    assert resp.status_code == 201, resp.get_json()
    entry = resp.get_json()['entry']
    assert entry['fee_4mil'] == 0 and entry['total_a_descontar'] == 2009900
    assert entry['cash_fee_exempt'] is True
    assert _balances(client, h(store))['cash'] == -2009900


def test_recompra_mixta_cobra_4x1000_solo_a_los_bancos(client, h):
    resp = client.post('/api/repurchase', headers=h(), json={
        'date': '2026-11-18', 'efectivo': 1000000, 'qr': 300000, 'nequi': 200000})
    entry = resp.get_json()['entry']
    assert entry['fee_4mil'] == 2000                       # 4x1000 de 500.000
    b = _balances(client, h())
    assert b['cash'] == -1000000
    assert b['qr'] == -(300000 + 1200)
    assert b['nequi'] == -(200000 + 800)


def test_comision_a_mano_en_efectivo_sale_del_efectivo(client, h):
    client.post('/api/repurchase', headers=h(), json={'date': '2026-11-18', 'efectivo': 100000, 'fee_override': 500})
    assert _balances(client, h())['cash'] == -100500


def test_envio_viejo_conserva_su_comision_al_editarlo(app, client, h):
    from app.models.user import db
    from app.models.repurchase import RepurchaseEntry
    entry_id = client.post('/api/repurchase', headers=h(), json={'date': '2026-11-02', 'efectivo': 1000000}).get_json()['entry']['id']
    with app.app_context():
        e = db.session.get(RepurchaseEntry, entry_id)
        e.created_at = datetime(2026, 11, 2, 15, 0)
        db.session.commit()
    resp = client.put(f'/api/repurchase/{entry_id}', headers=h(), json={'notes': 'editado'})
    assert resp.get_json()['entry']['fee_4mil'] == 4000
    assert _balances(client, h())['cash'] == -1004000      # sigue como estaba
