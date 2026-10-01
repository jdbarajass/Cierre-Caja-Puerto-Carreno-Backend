"""
Tests de multi-tienda (Carreño / Primavera): cada tienda ve y modifica SOLO
sus datos, sin header X-Store todo sigue funcionando como Carreño, y solo
quien tiene permiso puede operar otra tienda. Ver app/stores.py.

Usan una base SQLite temporal (nunca instance/cierre_caja.db) y simulan
Alegra (no hacen llamadas reales).
"""
import pytest

from app.config import TestingConfig
from app.services.alegra_client import AlegraClient


@pytest.fixture
def app(tmp_path, monkeypatch):
    monkeypatch.setenv('ALEGRA_USER_CARRENO', 'carreno@test.com')
    monkeypatch.setenv('ALEGRA_PASS_CARRENO', 'tok-carreno')
    monkeypatch.delenv('ALEGRA_USER_PRIMAVERA', raising=False)
    monkeypatch.delenv('ALEGRA_PASS_PRIMAVERA', raising=False)
    # Sin facturas en Alegra: el cierre se calcula igual, sin red.
    monkeypatch.setattr(AlegraClient, 'get_invoices_by_date', lambda self, date: [])

    class MultiStoreTestConfig(TestingConfig):
        SQLALCHEMY_DATABASE_URI = f"sqlite:///{(tmp_path / 'multi_store.db').as_posix()}"
        SQLALCHEMY_ENGINE_OPTIONS = {}

    from app import create_app
    return create_app(MultiStoreTestConfig)


def _token(app, user_id, role, store_code=None):
    from app.services.jwt_service import JWTService
    with app.app_context():
        return JWTService.generate_token(user_id, f'{role}{user_id}@test.com', role, store_code)


def _headers(token, store=None):
    return {'Authorization': f'Bearer {token}', **({'X-Store': store} if store else {})}


@pytest.fixture
def admin_headers(app):
    token = _token(app, 1, 'admin')
    return lambda store=None: {
        'Authorization': f'Bearer {token}', **({'X-Store': store} if store else {})
    }


@pytest.fixture
def sales_headers(app):
    token = _token(app, 2, 'sales')
    return lambda store=None: {
        'Authorization': f'Bearer {token}', **({'X-Store': store} if store else {})
    }


def _closing_payload(date='2026-09-30'):
    return {
        'date': date,
        'coins': {'50': 0, '100': 0, '200': 0, '500': 0, '1000': 0},
        'bills': {'2000': 0, '5000': 0, '10000': 0, '20000': 0, '50000': 10, '100000': 0},
        'metodos_pago': {'nequi_luz_helena': 20000},
    }


# ─── Resolución de tienda y permisos ─────────────────────────────────────────

def test_stores_endpoint_admin_ve_todas_y_vendedora_solo_carreno(client, admin_headers, sales_headers):
    admin = client.get('/api/stores', headers=admin_headers()).get_json()
    assert [s['code'] for s in admin['stores']] == ['carreno', 'primavera']
    assert admin['current_store'] == 'carreno'
    primavera = next(s for s in admin['stores'] if s['code'] == 'primavera')
    assert primavera['alegra_configured'] is False
    assert primavera['base_objetivo'] == 450000

    sales = client.get('/api/stores', headers=sales_headers()).get_json()
    assert [s['code'] for s in sales['stores']] == ['carreno']


def test_tienda_desconocida_400(client, admin_headers):
    resp = client.get('/api/accounts', headers=admin_headers('bogota'))
    assert resp.status_code == 400


def test_vendedora_no_puede_operar_otra_tienda(client, sales_headers):
    assert client.get('/api/notes-tasks/restock', headers=sales_headers()).status_code == 200
    assert client.get('/api/notes-tasks/restock', headers=sales_headers('carreno')).status_code == 200
    assert client.get('/api/notes-tasks/restock', headers=sales_headers('primavera')).status_code == 403


# ─── Cuentas ─────────────────────────────────────────────────────────────────

def test_cada_tienda_tiene_sus_propias_cuentas(client, admin_headers):
    carreno = client.get('/api/accounts', headers=admin_headers()).get_json()['accounts']
    primavera = client.get('/api/accounts', headers=admin_headers('primavera')).get_json()['accounts']

    assert {a['payment_key'] for a in carreno} == {a['payment_key'] for a in primavera}
    assert {a['store_code'] for a in carreno} == {'carreno'}
    assert {a['store_code'] for a in primavera} == {'primavera'}
    assert not {a['id'] for a in carreno} & {a['id'] for a in primavera}


def test_no_se_puede_tocar_una_cuenta_de_otra_tienda(client, admin_headers):
    carreno_cash = next(a for a in client.get('/api/accounts', headers=admin_headers()).get_json()['accounts']
                        if a['payment_key'] == 'cash')

    resp = client.post('/api/accounts/manual-adjustment', headers=admin_headers('primavera'), json={
        'account_id': carreno_cash['id'], 'amount': 1000, 'direction': 'in'
    })
    assert resp.status_code == 404

    resp = client.patch(f"/api/accounts/{carreno_cash['id']}/contemplated-until",
                        headers=admin_headers('primavera'), json={'contemplated_until': '2026-10-01'})
    assert resp.status_code == 404


def test_movimientos_solo_de_la_tienda(client, admin_headers):
    cash = next(a for a in client.get('/api/accounts', headers=admin_headers('primavera')).get_json()['accounts']
                if a['payment_key'] == 'cash')
    client.post('/api/accounts/manual-adjustment', headers=admin_headers('primavera'), json={
        'account_id': cash['id'], 'amount': 5000, 'direction': 'in'
    })
    assert client.get('/api/accounts/movements', headers=admin_headers('primavera')).get_json()['count'] == 1
    assert client.get('/api/accounts/movements', headers=admin_headers()).get_json()['count'] == 0


# ─── Cierre de caja + sincronización con cuentas ─────────────────────────────

def test_mismo_dia_cierre_en_ambas_tiendas_y_sync_independiente(client, admin_headers, monkeypatch):
    monkeypatch.setenv('ALEGRA_USER_PRIMAVERA', 'primavera@test.com')
    monkeypatch.setenv('ALEGRA_PASS_PRIMAVERA', 'tok-primavera')

    r1 = client.post('/api/sum_payments', headers=admin_headers(), json=_closing_payload())
    r2 = client.post('/api/sum_payments', headers=admin_headers('primavera'), json=_closing_payload())
    assert r1.status_code == 200, r1.get_json()
    assert r2.status_code == 200, r2.get_json()
    assert r1.get_json()['username_used'] == 'carreno@test.com'
    assert r2.get_json()['username_used'] == 'primavera@test.com'

    # Solo Primavera sincroniza: las cuentas de Carreño no se tocan
    sync = client.post('/api/accounts/sync-daily', headers=admin_headers('primavera')).get_json()
    assert sync['success'] and sync['synced_dates'] == ['2026-09-30']

    def balances(store):
        accounts = client.get('/api/accounts', headers=admin_headers(store)).get_json()['accounts']
        return {a['payment_key']: a['balance'] for a in accounts}

    assert balances('primavera')['nequi'] == 20000
    assert balances('carreno')['nequi'] == 0
    assert client.get('/api/accounts/sync-status', headers=admin_headers()).get_json()['pending_count'] == 1
    assert client.get('/api/accounts/sync-status', headers=admin_headers('primavera')).get_json()['pending_count'] == 0


def test_cierre_sin_alegra_configurado_falla_claro(client, admin_headers):
    resp = client.post('/api/sum_payments', headers=admin_headers('primavera'), json=_closing_payload())
    assert resp.status_code == 502
    assert 'Primavera' in resp.get_json()['alegra']['error']


def test_base_objetivo_por_tienda(client, admin_headers, monkeypatch):
    monkeypatch.setenv('ALEGRA_USER_PRIMAVERA', 'primavera@test.com')
    monkeypatch.setenv('ALEGRA_PASS_PRIMAVERA', 'tok-primavera')
    monkeypatch.setenv('BASE_OBJETIVO_PRIMAVERA', '300000')

    from app.stores import get_base_objetivo
    assert get_base_objetivo('primavera') == 300000
    assert get_base_objetivo('carreno') == 450000


# ─── Recompras, empleadas, notas ─────────────────────────────────────────────

def test_recompra_descuenta_solo_cuentas_de_su_tienda(client, admin_headers):
    resp = client.post('/api/repurchase', headers=admin_headers('primavera'), json={
        'date': '2026-09-30', 'efectivo': 1000000
    })
    assert resp.status_code == 201
    entry = resp.get_json()['entry']

    def cash_balance(store):
        accounts = client.get('/api/accounts', headers=admin_headers(store)).get_json()['accounts']
        return next(a['balance'] for a in accounts if a['payment_key'] == 'cash')

    assert cash_balance('primavera') == -(1000000 + 4000)  # envío + comisión 4x1000
    assert cash_balance('carreno') == 0
    assert client.get('/api/repurchase', headers=admin_headers()).get_json()['count'] == 0
    assert client.get('/api/repurchase', headers=admin_headers('primavera')).get_json()['count'] == 1

    # Desde otra tienda no se puede editar ni borrar
    assert client.delete(f"/api/repurchase/{entry['id']}", headers=admin_headers()).status_code == 404
    assert client.delete(f"/api/repurchase/{entry['id']}", headers=admin_headers('primavera')).status_code == 200
    assert cash_balance('primavera') == 0


def test_compras_del_socio_separadas(client, admin_headers):
    client.post('/api/repurchase/purchases', headers=admin_headers('primavera'), json={
        'date': '2026-09-30', 'store': 'Distribuidora XYZ', 'amount': 500000
    })
    assert client.get('/api/repurchase/purchases', headers=admin_headers()).get_json()['count'] == 0
    data = client.get('/api/repurchase/purchases', headers=admin_headers('primavera')).get_json()
    assert data['count'] == 1 and data['purchases'][0]['store'] == 'Distribuidora XYZ'


def test_empleadas_separadas(client, admin_headers):
    resp = client.post('/api/employee-records/loans', headers=admin_headers('primavera'), json={
        'nombre_empleada': 'Laura', 'date': '2026-09-30', 'amount': 50000
    })
    assert resp.status_code == 201, resp.get_json()
    loan_id = resp.get_json()['item']['id']

    assert client.get('/api/employee-records/loans', headers=admin_headers()).get_json()['items'] == []
    assert len(client.get('/api/employee-records/loans', headers=admin_headers('primavera')).get_json()['items']) == 1

    def summary_names(store):
        employees = client.get('/api/employee-records/summary', headers=admin_headers(store)).get_json()['employees']
        return [e['nombre_empleada'] for e in employees]

    assert summary_names('carreno') == []
    assert summary_names('primavera') == ['Laura']
    assert client.delete(f'/api/employee-records/loans/{loan_id}', headers=admin_headers()).status_code == 404
    assert client.delete(f'/api/employee-records/loans/{loan_id}', headers=admin_headers('primavera')).status_code == 200


def test_notas_separadas(client, admin_headers):
    resp = client.post('/api/notes-tasks/restock', headers=admin_headers('primavera'), json={'item': 'Jeans talla 8'})
    assert resp.status_code == 201, resp.get_json()
    assert client.get('/api/notes-tasks/restock', headers=admin_headers()).get_json()['items'] == []
    assert len(client.get('/api/notes-tasks/restock', headers=admin_headers('primavera')).get_json()['items']) == 1


# ─── Caché de Alegra ─────────────────────────────────────────────────────────

def test_cache_de_facturas_no_se_cruza_entre_cuentas_de_alegra():
    from app.services.alegra_client import _invoices_cache
    a = AlegraClient('carreno@test.com', 'x', 'https://example.invalid')
    b = AlegraClient('primavera@test.com', 'x', 'https://example.invalid')
    _invoices_cache.set(a._invoices_cache_key('2026-09-01'), ['factura-carreno'], 60)
    assert _invoices_cache.get(b._invoices_cache_key('2026-09-01')) is None
    assert _invoices_cache.get(a._invoices_cache_key('2026-09-01')) == ['factura-carreno']


# ─── Fase 2: usuarios con tienda asignada ────────────────────────────────────

def test_vendedora_de_primavera_opera_solo_primavera(app, client, admin_headers):
    token = _token(app, 3, 'sales', 'primavera')
    client.post('/api/notes-tasks/restock', headers=admin_headers('primavera'), json={'item': 'Item Primavera'})

    # Sin header: su propia tienda (no Carreño), ej. frontend viejo en caché
    items = client.get('/api/notes-tasks/restock', headers=_headers(token)).get_json()['items']
    assert [i['item'] for i in items] == ['Item Primavera']
    assert client.get('/api/notes-tasks/restock', headers=_headers(token, 'primavera')).status_code == 200
    assert client.get('/api/notes-tasks/restock', headers=_headers(token, 'carreno')).status_code == 403

    stores = client.get('/api/stores', headers=_headers(token)).get_json()
    assert [s['code'] for s in stores['stores']] == ['primavera']
    assert stores['current_store'] == 'primavera'


def test_token_viejo_sin_tienda_es_de_carreno(app, client):
    import jwt
    from datetime import datetime, timedelta
    with app.app_context():
        old_token = jwt.encode({
            'userId': 9, 'email': 'vieja@test.com', 'role': 'sales',
            'iat': datetime.utcnow(), 'exp': datetime.utcnow() + timedelta(hours=1)
        }, app.config['JWT_SECRET_KEY'], algorithm='HS256')
    assert client.get('/api/stores', headers=_headers(old_token)).get_json()['current_store'] == 'carreno'
    assert client.get('/api/notes-tasks/restock', headers=_headers(old_token, 'primavera')).status_code == 403


def test_verify_no_se_rompe_con_header_de_otra_tienda(app, client):
    token = _token(app, 3, 'sales', 'primavera')
    resp = client.get('/auth/verify', headers=_headers(token, 'carreno'))
    assert resp.status_code == 200
    user = resp.get_json()['user']
    assert user['store_code'] == 'primavera'
    assert [s['code'] for s in user['stores']] == ['primavera']


def test_crud_usuarios_con_tienda(client, admin_headers):
    base = {'email': 'laura@test.com', 'password': 'Clave123', 'name': 'Laura', 'role': 'sales'}

    bad = client.post('/api/users', headers=admin_headers(), json={**base, 'store_code': 'bogota'})
    assert bad.status_code == 400

    created = client.post('/api/users', headers=admin_headers(), json={**base, 'store_code': 'Primavera'})
    assert created.status_code == 201, created.get_json()
    user = created.get_json()['user']
    assert user['store_code'] == 'primavera'

    sin_tienda = client.post('/api/users', headers=admin_headers(), json={**base, 'email': 'otra@test.com'})
    assert sin_tienda.get_json()['user']['store_code'] == 'carreno'

    updated = client.put(f"/api/users/{user['id']}", headers=admin_headers(), json={'store_code': 'carreno'})
    assert updated.get_json()['user']['store_code'] == 'carreno'
    assert client.put(f"/api/users/{user['id']}", headers=admin_headers(), json={'store_code': 'x'}).status_code == 400

    listed = client.get('/api/users', headers=admin_headers()).get_json()['users']
    assert {u['email']: u['store_code'] for u in listed} == {'laura@test.com': 'carreno', 'otra@test.com': 'carreno'}


def test_login_devuelve_tienda_y_la_mete_en_el_token(app, client, admin_headers):
    client.post('/api/users', headers=admin_headers(), json={
        'email': 'vende@test.com', 'password': 'Clave123', 'name': 'Vende', 'role': 'sales', 'store_code': 'primavera'
    })
    resp = client.post('/auth/login', json={'email': 'vende@test.com', 'password': 'Clave123'})
    assert resp.status_code == 200, resp.get_json()
    body = resp.get_json()
    assert body['user']['store_code'] == 'primavera'
    assert [s['code'] for s in body['user']['stores']] == ['primavera']

    from app.services.jwt_service import JWTService
    with app.app_context():
        assert JWTService.verify_token(body['token'])['storeCode'] == 'primavera'


# ─── Fase 4: cron de las 9pm por tienda (GitHub Actions con X-Sync-Token) ────

def test_cron_sincroniza_y_reporta_fallos_por_tienda(client, admin_headers, monkeypatch):
    from app.config import Config
    monkeypatch.setattr(Config, 'DAILY_SYNC_TOKEN', 'token-cron')
    monkeypatch.setenv('ALEGRA_USER_PRIMAVERA', 'primavera@test.com')
    monkeypatch.setenv('ALEGRA_PASS_PRIMAVERA', 'tok-primavera')
    cron = lambda store: {'X-Sync-Token': 'token-cron', 'X-Store': store}

    client.post('/api/sum_payments', headers=admin_headers(), json=_closing_payload())
    client.post('/api/sum_payments', headers=admin_headers('primavera'), json=_closing_payload())

    # Fallo reportado solo para Primavera
    assert client.post('/api/accounts/sync-failure', headers=cron('primavera'),
                       json={'message': 'falló'}).status_code == 200
    status = lambda store: client.get('/api/accounts/sync-status', headers=admin_headers(store)).get_json()
    assert status('primavera')['last_failure']['message'] == 'falló'
    assert status('carreno')['last_failure'] is None

    # Corrida de Carreño: sincroniza solo Carreño y no limpia la alerta de Primavera
    r = client.post('/api/accounts/sync-daily', headers=cron('carreno'), json={})
    assert r.status_code == 200 and r.get_json()['synced_dates'] == ['2026-09-30']
    assert status('carreno')['pending_count'] == 0
    assert status('primavera')['pending_count'] == 1
    assert status('primavera')['last_failure'] is not None

    # Corrida de Primavera: sincroniza la suya y limpia su alerta
    r = client.post('/api/accounts/sync-daily', headers=cron('primavera'), json={})
    assert r.get_json()['synced_dates'] == ['2026-09-30']
    assert status('primavera')['pending_count'] == 0
    assert status('primavera')['last_failure'] is None

    # Token inválido: sigue protegido
    assert client.post('/api/accounts/sync-daily', headers={'X-Sync-Token': 'malo', 'X-Store': 'carreno'}).status_code == 401


# ─── Fase 5: comparativo entre tiendas ───────────────────────────────────────

def _fake_invoices(self, start, end):
    """Facturas simuladas según la cuenta de Alegra (= según la tienda)."""
    if self.username == 'carreno@test.com':
        return [
            {'date': '2026-09-01', 'total': 100000, 'status': 'open',
             'payments': [{'amount': 100000, 'paymentMethod': 'cash'}]},
            {'date': '2026-09-02', 'total': 50000, 'status': 'open',
             'payments': [{'amount': 50000, 'paymentMethod': 'transfer'}]},
            {'date': '2026-09-02', 'total': 999999, 'status': 'void', 'payments': []},
        ]
    return [{'date': '2026-09-02', 'total': 30000, 'status': 'open',
             'payments': [{'amount': 30000, 'paymentMethod': 'cash'}]}]


def test_comparativo_ventas_y_operacion_por_tienda(client, admin_headers, monkeypatch):
    monkeypatch.setattr(AlegraClient, 'get_all_invoices_in_range', _fake_invoices)
    client.post('/api/repurchase', headers=admin_headers('primavera'), json={'date': '2026-09-02', 'efectivo': 200000})

    resp = client.get('/api/stores/comparison?start_date=2026-09-01&end_date=2026-09-03', headers=admin_headers())
    assert resp.status_code == 200, resp.get_json()
    data = resp.get_json()
    assert data['date_range'] == {'start': '2026-09-01', 'end': '2026-09-03'}
    by_code = {s['code']: s for s in data['stores']}

    carreno = by_code['carreno']['sales']
    assert carreno['available'] is True
    assert carreno['total'] == 150000            # la anulada no cuenta
    assert carreno['invoices'] == 2
    assert carreno['average_ticket'] == 75000
    assert carreno['voided_invoices'] == 1
    assert [d['total'] for d in carreno['daily']] == [100000, 50000, 0]
    assert carreno['payment_methods']['cash']['total'] == 100000

    # Primavera sin cuenta de Alegra: ventas no disponibles, operación sí
    primavera = by_code['primavera']
    assert primavera['sales']['available'] is False
    assert 'Primavera' in primavera['sales']['error']
    assert primavera['operations']['repurchase_sent'] == 200000
    assert by_code['carreno']['operations']['repurchase_sent'] == 0
    assert primavera['operations']['period_days'] == 3


def test_comparativo_con_ambas_tiendas_configuradas(client, admin_headers, monkeypatch):
    monkeypatch.setattr(AlegraClient, 'get_all_invoices_in_range', _fake_invoices)
    monkeypatch.setenv('ALEGRA_USER_PRIMAVERA', 'primavera@test.com')
    monkeypatch.setenv('ALEGRA_PASS_PRIMAVERA', 'tok-primavera')
    data = client.get('/api/stores/comparison?start_date=2026-09-01&end_date=2026-09-02',
                      headers=admin_headers()).get_json()
    totals = {s['code']: s['sales']['total'] for s in data['stores']}
    assert totals == {'carreno': 150000, 'primavera': 30000}


def test_comparativo_solo_admin_y_rango_valido(client, admin_headers, sales_headers):
    assert client.get('/api/stores/comparison', headers=sales_headers()).status_code == 403
    assert client.get('/api/stores/comparison?start_date=2026-09-10&end_date=2026-09-01',
                      headers=admin_headers()).status_code == 400
    assert client.get('/api/stores/comparison?start_date=2026-01-01&end_date=2026-09-01',
                      headers=admin_headers()).status_code == 400
