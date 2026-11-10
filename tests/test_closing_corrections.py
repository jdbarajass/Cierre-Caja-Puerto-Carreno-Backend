"""
Tests de la corrección de cierres por el admin (Cuentas → Corrección de
cierres, 2026-11-09): el caso real del 6-nov de Carreño (una venta de $59.900
pagada en efectivo quedó como transferencia en Alegra), la regla del total de
Alegra, el reparto en Cuentas → Mes, el paso a Cuentas, el rastro, el aviso de
Cierre de Caja y que solo el admin pueda hacerlo.

Base SQLite temporal, sin red.
"""
from datetime import date, datetime

import pytest

from tests.test_radiografia_month import app, h  # noqa: F401  (fixtures)

DAY = date(2026, 11, 6)
# Alegra del 6-nov de Carreño (receipts reales): efectivo, QR, débito, crédito
ALEGRA = [('efectivo', 159800), ('qr', 1233715), ('ahorro', 703600), ('credito', 199800)]


@pytest.fixture
def today(monkeypatch):
    import app.routes.closing_corrections as routes
    import app.routes.cash_closing as cc
    fixed = lambda: datetime(2026, 11, 9, 12, 0)  # noqa: E731
    monkeypatch.setattr(routes, 'get_colombia_now', fixed)
    monkeypatch.setattr(cc, 'get_colombia_now', fixed)


def _seed(app, store='carreno', status='error'):
    from app.models.cash_closing import CashClosing
    from app.models.month_sheet import PaymentFact
    from app.models.user import db
    with app.app_context():
        for i, (medio, amount) in enumerate(ALEGRA):
            db.session.add(PaymentFact(store_code=store, payment_id=f'p{i}', invoice_id=f'i{i}', invoice_date=DAY,
                                       payment_date=DAY, medio=medio, amount=amount))
        # Lo que la vendedora envió: cuadró contra el Excel, no contra Alegra
        db.session.add(CashClosing(store_code=store, closing_date=DAY, efectivo=216000, qr=1173815,
                                   addi_datafono=903400, excedente_datafono=39800, validation_status=status,
                                   validation_message='Diferencias encontradas en: EFECTIVO (diferencia: $59.900)'))
        db.session.commit()


def _balances(client, headers):
    accounts = client.get('/api/accounts', headers=headers).get_json()
    accounts = accounts.get('accounts', accounts)
    return {a['payment_key']: a['balance'] for a in accounts}


REAL = {'efectivo': 219700, 'qr': 1173815, 'nequi': 0, 'daviplata': 0, 'datafono': 903400,
        'excedentes': {'datafono': 39800}, 'note': 'KPC4868 se pagó en efectivo y quedó como transferencia; '
                                                  'los 3.700 del préstamo a Rita ya se repusieron'}


def test_caso_real_del_6_de_noviembre(app, client, h, today):
    _seed(app)
    # Antes: no exitoso, bloqueado y con aviso en Cierre de Caja
    pend = client.get('/api/cash_closing/pending-dates', headers=h()).get_json()
    assert [u['date'] for u in pend['unsuccessful_closings']] == ['2026-11-06']
    listing = client.get('/api/closing-corrections', headers=h()).get_json()
    item = listing['pending'][0]
    assert item['alegra']['total'] == 2296915 and item['alegra']['efectivo'] == 159800 and item['alegra']['datafono'] == 903400

    resp = client.post('/api/closing-corrections/2026-11-06', headers=h(), json=REAL)
    assert resp.status_code == 200, resp.get_json()
    out = resp.get_json()
    assert out['efectivo_consignar'] == 219700                       # sin el préstamo de 3.700
    assert out['moves'] == [{'from': 'qr', 'to': 'efectivo', 'amount': 59900}]

    # Pasó a Cuentas: efectivo y QR reales; el datáfono llega solo (plata real del banco) o con el cierre
    bal = _balances(client, h())
    assert bal['cash'] == 219700 and bal['qr'] == 1173815
    assert bal['addi_datafono'] in (903400 + 39800, 39800)          # excedente aparte, nunca como venta

    # Cuentas → Mes ya muestra el reparto real ese día
    sheet = client.get('/api/month-sheet?year=2026&month=11', headers=h()).get_json()
    sheet = sheet.get('sheet', sheet)
    day = next(d for d in sheet['sales']['days'] if d['date'] == '2026-11-06')
    assert day['medios']['efectivo'] == 219700 and day['medios']['qr'] == 1173815 and day['total'] == 2296915

    # Rastro y el aviso desaparece
    listing = client.get('/api/closing-corrections', headers=h()).get_json()
    assert listing['pending'] == []
    hist = listing['corrected'][0]['history'][0]
    assert hist['before']['efectivo_consignar'] == 216000 and hist['after']['efectivo_consignar'] == 219700
    assert 'KPC4868' in hist['note'] and hist['by'] == 'admin1@test.com'
    assert client.get('/api/cash_closing/pending-dates', headers=h()).get_json()['unsuccessful_closings'] == []
    # Ya sincronizado: no se puede volver a corregir por aquí
    assert client.post('/api/closing-corrections/2026-11-06', headers=h(), json=REAL).status_code == 400


def test_el_total_debe_ser_el_de_alegra(app, client, h, today):
    _seed(app)
    bad = {**REAL, 'efectivo': 219700 + 1000}
    resp = client.post('/api/closing-corrections/2026-11-06', headers=h(), json=bad)
    assert resp.status_code == 400 and 'Alegra' in resp.get_json()['message']
    assert client.post('/api/closing-corrections/2026-11-06', headers=h(), json={**REAL, 'note': ''}).status_code == 400
    assert client.post('/api/closing-corrections/2026-11-07', headers=h(), json=REAL).status_code == 400   # no hay cierre
    # Nada cambió
    assert _balances(client, h())['cash'] == 0
    assert client.get('/api/closing-corrections', headers=h()).get_json()['pending'][0]['status'] == 'error'


def test_solo_el_admin_y_por_tienda(app, client, h, today):
    _seed(app)
    assert client.get('/api/closing-corrections', headers=h(role='viewer')).status_code == 403
    assert client.post('/api/closing-corrections/2026-11-06', headers=h(role='viewer'), json=REAL).status_code == 403
    # Primavera no ve el cierre de Carreño
    assert client.get('/api/closing-corrections', headers=h('primavera')).get_json()['pending'] == []
    assert client.post('/api/closing-corrections/2026-11-06', headers=h('primavera'), json=REAL).status_code == 400
