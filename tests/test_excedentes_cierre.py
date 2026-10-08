"""
Excedentes del cierre de caja y bloqueo de la sincronización
(docs/PLAN_EXCEDENTES_Y_CARGA_EXCEL.md, Fase 1, 2026-10-08):

- El cierre guarda los excedentes por medio y si salió exitoso.
- Solo un Cierre exitoso pasa a Cuentas; los demás quedan pendientes y
  bloqueados hasta que se corrijan y se reenvíen.
- Al sincronizar, ventas y excedentes entran como movimientos separados
  (el efectivo físico ya trae su excedente adentro, los demás medios no).
- Cuentas → Mes muestra el subtotal de ventas, los excedentes y el total;
  Cuentas → Año muestra los excedentes aparte, sin cambiar ventas ni ganancia.

Base SQLite temporal y Alegra simulado (sin red).
"""
import pytest

from app.config import TestingConfig
from app.services.alegra_client import AlegraClient

DAY = '2026-10-07'


@pytest.fixture
def alegra():
    """Lo que 'Alegra' reporta ese día (se puede cambiar dentro del test)."""
    return {'cash': 50000, 'transfer': 100000, 'debit-card': 0}


@pytest.fixture
def app(tmp_path, monkeypatch, alegra):
    monkeypatch.setenv('ALEGRA_USER_CARRENO', 'carreno@test.com')
    monkeypatch.setenv('ALEGRA_PASS_CARRENO', 'tok-carreno')

    def fake_invoices(self, date):
        payments = [{'amount': v, 'paymentMethod': k} for k, v in alegra.items() if v]
        return [{'id': '1', 'status': 'open', 'total': sum(alegra.values()), 'payments': payments}]

    monkeypatch.setattr(AlegraClient, 'get_invoices_by_date', fake_invoices)

    class Cfg(TestingConfig):
        SQLALCHEMY_DATABASE_URI = f"sqlite:///{(tmp_path / 'excedentes.db').as_posix()}"
        SQLALCHEMY_ENGINE_OPTIONS = {}

    from app import create_app
    return create_app(Cfg)


@pytest.fixture
def h(app):
    from app.services.jwt_service import JWTService
    with app.app_context():
        token = JWTService.generate_token(1, 'admin1@test.com', 'admin', None)
    return {'Authorization': f'Bearer {token}'}


def _payload(qr=100000, excedentes=None, date=DAY):
    # 10 x 50.000 + 3 x 200 = 500.600; base 450.000 -> 50.600 a consignar
    return {
        'date': date,
        'coins': {'50': 0, '100': 0, '200': 3, '500': 0, '1000': 0},
        'bills': {'2000': 0, '5000': 0, '10000': 0, '20000': 0, '50000': 10, '100000': 0},
        'metodos_pago': {'qr_julieth': qr},
        'excedentes': excedentes if excedentes is not None else [
            {'tipo': 'efectivo', 'valor': 600},
            {'tipo': 'qr_transferencias', 'subtipo': 'qr', 'valor': 5000},
        ],
    }


def _close(client, h, **kw):
    r = client.post('/api/sum_payments', headers=h, json=_payload(**kw))
    assert r.status_code == 200, r.get_json()
    return r.get_json()


def _balances(client, h):
    return {a['payment_key']: a['balance'] for a in client.get('/api/accounts', headers=h).get_json()['accounts']}


def _movements(client, h):
    return client.get('/api/accounts/movements', headers=h).get_json()['movements']


def test_cierre_exitoso_guarda_excedentes_y_los_abona_aparte(app, client, h):
    body = _close(client, h)
    assert body['validation']['validation_status'] == 'success'

    from app.models.cash_closing import CashClosing
    with app.app_context():
        c = CashClosing.query.one()
        assert c.efectivo == 50600            # plata física, con el excedente adentro
        assert c.qr == 100000                 # lo registrado (= Alegra), sin excedente
        assert c.excedentes() == {'cash': 600, 'nequi': 0, 'daviplata': 0, 'qr': 5000, 'addi_datafono': 0}
        assert c.validation_status == 'success' and c.can_sync

    sync = client.post('/api/accounts/sync-daily', headers=h).get_json()
    assert sync['success'] and sync['synced_dates'] == [DAY] and sync['blocked'] == []
    kinds = sorted((c['account'], c['amount'], c['kind']) for c in sync['credited'])
    assert ('EFECTIVO', 50000, 'venta') in kinds and ('EFECTIVO', 600, 'excedente') in kinds

    bal = _balances(client, h)
    assert bal['cash'] == 50600 and bal['qr'] == 105000
    types = sorted((m['type'], m['amount']) for m in _movements(client, h))
    assert types == [('cash_closing', 50000), ('cash_closing', 100000), ('excedente', 600), ('excedente', 5000)]

    # Cuentas → Mes: subtotal ventas + excedentes = total
    sheet = client.get('/api/month-sheet?year=2026&month=10', headers=h).get_json()
    qr = next(r for r in sheet['statement'] if r['payment_key'] == 'qr')
    assert (qr['ventas'], qr['excedentes'], qr['ingresos_cierres']) == (100000, 5000, 105000)
    assert qr['final'] == 105000
    assert qr['days'][0]['excedentes'] == 5000

    # Cuentas → Año: excedentes aparte, sin tocar ventas ni ganancia
    year = client.get('/api/monthly-summary?year=2026', headers=h).get_json()
    octubre = next(m for m in year['months'] if m['month'] == 10)
    assert octubre['excedentes'] == 5600
    assert octubre['ventas_mas_excedentes'] == octubre['ventas'] + 5600
    assert octubre['ganancia_real'] == octubre['ventas'] - octubre['recompras'] - octubre['gastos_operativos']
    assert year['totals']['excedentes'] == 5600


def test_cierre_no_exitoso_no_se_sincroniza_hasta_corregirlo(app, client, h, alegra):
    # La vendedora escribió 90.000 en QR pero Alegra dice 100.000
    body = _close(client, h, qr=90000)
    assert body['validation']['validation_status'] != 'success'

    sync = client.post('/api/accounts/sync-daily', headers=h).get_json()
    assert sync['success'] and sync['credited'] == []
    assert [b['date'] for b in sync['blocked']] == [DAY]
    assert 'no salió exitoso' in sync['message']
    assert _balances(client, h)['qr'] == 0

    status = client.get('/api/accounts/sync-status', headers=h).get_json()
    assert status['pending_count'] == 1 and [b['date'] for b in status['blocked']] == [DAY]

    # Con fecha puntual también se bloquea
    r = client.post('/api/accounts/sync-daily', headers=h, json={'date': DAY})
    assert r.status_code == 409 and r.get_json()['blocked'][0]['date'] == DAY

    # Corrige y reenvía: ahora sí sale exitoso y se sincroniza
    assert _close(client, h)['validation']['validation_status'] == 'success'
    sync = client.post('/api/accounts/sync-daily', headers=h).get_json()
    assert sync['synced_dates'] == [DAY] and sync['blocked'] == []
    assert _balances(client, h)['qr'] == 105000
    assert client.get('/api/accounts/sync-status', headers=h).get_json()['blocked'] == []


def test_cierre_sin_excedentes_abona_igual_que_antes(app, client, h, alegra):
    alegra['cash'] = 50600
    _close(client, h, excedentes=[])
    client.post('/api/accounts/sync-daily', headers=h)
    assert sorted((m['type'], m['amount']) for m in _movements(client, h)) == [
        ('cash_closing', 50600), ('cash_closing', 100000)]


def test_cierre_guardado_antes_del_cambio_se_sigue_sincronizando(app, client, h):
    """Cierres viejos (sin estado guardado) no quedan bloqueados."""
    from datetime import date
    from app.models.cash_closing import CashClosing
    from app.models.user import db
    with app.app_context():
        db.session.add(CashClosing(store_code='carreno', closing_date=date(2026, 10, 6), efectivo=70000, qr=1000))
        db.session.commit()
        assert CashClosing.query.one().can_sync

    sync = client.post('/api/accounts/sync-daily', headers=h).get_json()
    assert sync['synced_dates'] == ['2026-10-06']
    assert _balances(client, h)['cash'] == 70000
