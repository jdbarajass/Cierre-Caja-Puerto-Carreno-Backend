"""
ADDI + DATÁFONO = plata real del banco (app/services/card_arrivals.py,
2026-10-14): al activarlo la cuenta queda igual al banco, el cierre ya no
suma las ventas por datáfono/Addi, cada venta entra sola el día que llega y
ya sin comisión, y la comisión del mes queda como gasto informativo.

Base SQLite temporal, Alegra simulado (mismos recibos de tests/test_month_sheet.py).
"""
from datetime import date, datetime

import pytest

from app.config import TestingConfig
from app.services.payment_facts import net_amount
from tests.test_month_sheet import OCT5, FakeAlegra, _pay

DATAFONO_OCT5 = 170000 + 69900 + 36900 + 87150     # débito + crédito del 5-oct, llega el 6-oct
ADDI_OCT5 = 204700                                  # llega el 4-nov


@pytest.fixture
def app(tmp_path):
    class Cfg(TestingConfig):
        SQLALCHEMY_DATABASE_URI = f"sqlite:///{(tmp_path / 'card_arrivals.db').as_posix()}"
        SQLALCHEMY_ENGINE_OPTIONS = {}

    from app import create_app
    return create_app(Cfg)


@pytest.fixture
def h(app):
    from app.services.jwt_service import JWTService
    with app.app_context():
        token = JWTService.generate_token(1, 'admin1@test.com', 'admin', None)
    return {'Authorization': f'Bearer {token}'}


@pytest.fixture
def today(monkeypatch):
    """Cambia el "hoy" de Colombia de las rutas de Cuentas y de Mes."""
    import app.routes.accounts as acc_routes
    import app.routes.month_sheet as ms_routes
    state = {}

    def set_today(d):
        state['now'] = datetime(d.year, d.month, d.day, 12, 0)

    monkeypatch.setattr(acc_routes, 'get_colombia_now', lambda: state['now'])
    monkeypatch.setattr(ms_routes, 'get_colombia_now', lambda: state['now'])
    set_today(date(2026, 10, 5))
    return set_today


def _load(app, payments=OCT5):
    from app.services.payment_facts import sync_payments
    with app.app_context():
        sync_payments(FakeAlegra(payments), 'carreno', date(2026, 10, 1))


def _card(client, h):
    data = client.get('/api/accounts', headers=h).get_json()
    acc = next(a for a in data['accounts'] if a['payment_key'] == 'addi_datafono')
    return acc, data


def _start(client, h, real):
    return client.post('/api/accounts/card-arrivals/start', headers=h, json={'real_balance': real})


def test_activar_deja_la_cuenta_igual_al_banco(app, client, h, today):
    acc, data = _card(client, h)
    assert data['card_arrivals_since'] is None
    client.post('/api/accounts/manual-adjustment', headers=h,
                json={'account_id': acc['id'], 'amount': 3408559, 'direction': 'in'})

    r = _start(client, h, 3121660)
    assert r.status_code == 200
    assert r.get_json()['adjustment'] == 3121660 - 3408559
    acc, data = _card(client, h)
    assert acc['balance'] == 3121660
    assert data['card_arrivals_since'] == '2026-10-05'
    assert _start(client, h, 1).status_code == 409          # solo una vez
    assert client.post('/api/accounts/card-arrivals/start', headers=h, json={}).status_code == 409


def test_validaciones_al_activar(app, client, h, today):
    assert _start(client, h, None).status_code == 400
    assert _start(client, h, -5).status_code == 400
    assert _card(client, h)[1]['card_arrivals_since'] is None


def test_pagos_entran_solos_el_dia_que_llegan_y_netos(app, client, h, today):
    _load(app)
    _start(client, h, 1000000)          # 5-oct: el datáfono del 5 llega el 6

    assert _card(client, h)[0]['balance'] == 1000000           # nada llegó todavía
    today(date(2026, 10, 6))
    datafono = round(net_amount('ahorro', 170000)) + round(net_amount('credito', 69900 + 36900 + 87150))
    assert _card(client, h)[0]['balance'] == 1000000 + datafono
    assert _card(client, h)[0]['balance'] == 1000000 + datafono  # consultar otra vez no duplica

    today(date(2026, 11, 4))                                    # Addi paga a los 30 días
    addi = round(net_amount('addi', ADDI_OCT5))
    assert addi == 188866
    assert _card(client, h)[0]['balance'] == 1000000 + datafono + addi


def test_lo_que_llego_el_dia_de_activar_no_se_suma(app, client, h, today):
    _load(app)
    today(date(2026, 10, 6))            # el datáfono del 5 ya llegó y está en el saldo del banco
    _start(client, h, 500000)
    today(date(2026, 10, 7))
    assert _card(client, h)[0]['balance'] == 500000


def test_correccion_a_efectivo_quita_lo_que_habia_llegado(app, client, h, today):
    _load(app)
    _start(client, h, 0)
    today(date(2026, 10, 6))
    before = _card(client, h)[0]['balance']
    r = client.post('/api/month-sheet/corrections', headers=h,
                    json={'date': '2026-10-05', 'from_medio': 'ahorro', 'to_medio': 'efectivo', 'amount': 170000})
    assert r.status_code == 201, r.get_json()
    assert _card(client, h)[0]['balance'] == before - round(net_amount('ahorro', 170000))


def test_el_cierre_ya_no_suma_datafono_ni_addi(app, client, h, today):
    from app.models.cash_closing import CashClosing
    from app.models.user import db
    from app.routes.accounts import _claim_and_credit_closing

    def credit(day):
        with app.app_context():
            c = CashClosing(store_code='carreno', closing_date=day, efectivo=0, qr=10000,
                            addi_datafono=500000, validation_status='success')
            db.session.add(c)
            db.session.commit()
            _claim_and_credit_closing(c, None)

    credit(date(2026, 10, 3))
    assert _card(client, h)[0]['balance'] == 500000             # antes de activar: como siempre
    _start(client, h, 800000)
    credit(date(2026, 10, 4))
    assert _card(client, h)[0]['balance'] == 800000             # después: solo entra cuando llega


def test_hoja_del_mes_llegadas_aparte_y_comision_informativa(app, client, h, today):
    _load(app)
    _start(client, h, 1000000)
    today(date(2026, 10, 6))
    r = client.post('/api/month-sheet/commissions', headers=h, json={'year': 2026, 'month': 10})
    assert r.status_code == 200
    expense = client.get('/api/expenses?year=2026&month=10', headers=h).get_json()['items'][0]
    assert expense['account_mode'] == 'sin_mover'              # no descuenta otra vez la comisión

    sheet = client.get('/api/month-sheet?year=2026&month=10', headers=h).get_json()
    row = next(r for r in sheet['statement'] if r['payment_key'] == 'addi_datafono')
    datafono = round(net_amount('ahorro', 170000)) + round(net_amount('credito', 69900 + 36900 + 87150))
    assert row['llegadas'] == datafono
    assert row['gastos'] == 0
    assert row['final'] == 1000000 + datafono
    assert row['estimated_available'] == row['final']
    assert row['in_transit_net_apart'] == 188866               # Addi por llegar: aparte, no en el saldo
    day6 = next(d for d in row['days'] if d['date'] == '2026-10-06')
    assert day6['llegadas'] == datafono                        # cuenta el día que llegó
    assert sheet['card_arrivals_since'] == '2026-10-05'


def test_comision_del_mes_ya_registrada_pasa_a_informativa_al_activar(app, client, h, today):
    _load(app)
    client.post('/api/month-sheet/commissions', headers=h, json={'year': 2026, 'month': 10})
    _start(client, h, 700000)
    assert _card(client, h)[0]['balance'] == 700000
    expense = client.get('/api/expenses?year=2026&month=10', headers=h).get_json()['items'][0]
    assert expense['account_mode'] == 'sin_mover'


def test_bold_entra_el_mismo_dia_completo(app, client, h, today):
    _load(app, [_pay(1, '2026-10-07', 90000, 'transfer', 'BOLD')])
    from app.models.month_sheet import PaymentFact
    with app.app_context():
        medios = {f.medio for f in PaymentFact.query}
    if medios != {'bold'}:
        pytest.skip(f'La cuenta BOLD de prueba se clasifica como {medios}')
    _start(client, h, 0)
    today(date(2026, 10, 7))
    assert _card(client, h)[0]['balance'] == 90000


def test_otra_tienda_no_se_activa(app, client, h, today):
    _start(client, h, 100)
    data = client.get('/api/accounts', headers={**h, 'X-Store': 'primavera'}).get_json()
    assert data['card_arrivals_since'] is None
