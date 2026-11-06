"""
Tests de la deuda entre tiendas (Radiografía Fase 0b, docs/PLAN_RADIOGRAFIA.md):
saldo de partida $9.816.659 al 6-nov-2026, préstamos que suben la deuda, abonos
que la bajan sin bajar la ganancia, registros espejo (recompra sin mover cuentas
y entrada en la cuenta donde llegó) que se editan y borran solos, historial,
rastro del saldo de partida y solo lectura.

Base SQLite temporal, sin red.
"""
import pytest

from app.config import TestingConfig

OPENING = 9816659


@pytest.fixture
def app(tmp_path):
    class DebtTestConfig(TestingConfig):
        SQLALCHEMY_DATABASE_URI = f"sqlite:///{(tmp_path / 'debt.db').as_posix()}"
        SQLALCHEMY_ENGINE_OPTIONS = {}

    from app import create_app
    return create_app(DebtTestConfig)


@pytest.fixture
def h(app):
    from app.services.jwt_service import JWTService
    with app.app_context():
        token = JWTService.generate_token(1, 'admin1@test.com', 'admin', None)
        viewer = JWTService.generate_token(2, 'viewer@test.com', 'viewer', None)

    def headers(store=None, role='admin'):
        return {'Authorization': f'Bearer {token if role == "admin" else viewer}',
                **({'X-Store': store} if store else {})}
    return headers


def _post(client, headers, **payload):
    base = {'date': '2026-11-07', 'concept': 'Movimiento'}
    base.update(payload)
    return client.post('/api/expenses', headers=headers, json=base)


def _debt(client, headers):
    return client.get('/api/inter-store-debt', headers=headers).get_json()['debt']


def _balances(client, headers):
    data = client.get('/api/accounts', headers=headers).get_json()
    return {a['payment_key']: a['balance'] for a in data['accounts']}


def test_saldo_de_partida_igual_en_las_dos_tiendas(client, h):
    carreno, primavera = _debt(client, h()), _debt(client, h('primavera'))
    assert carreno['balance'] == primavera['balance'] == OPENING
    assert carreno['opening_date'] == '2026-11-06'
    assert carreno['perspective'] == 'lender' and primavera['perspective'] == 'borrower'
    assert carreno['lender_name'] and carreno['borrower'] == 'primavera'


def test_abono_baja_deuda_y_cuenta_de_primavera_sin_tocar_carreno_ni_ganancia(client, h):
    resp = _post(client, h('primavera'), concept='Abono en ganancias de los dueños', category='pago_prestamo_tienda',
                 related_store_code='carreno', purpose='ganancias', nequi=1000000)
    assert resp.status_code == 201, resp.get_json()
    assert _debt(client, h())['balance'] == OPENING - 1000000
    assert _balances(client, h('primavera'))['nequi'] == -(1000000 + 4000)   # sale con su 4x1000
    assert _balances(client, h())['nequi'] == 0                                 # no suma a Carreño
    assert client.get('/api/expenses?year=2026&month=11', headers=h()).get_json()['items'] == []
    # No es gasto: la ganancia de Primavera no baja
    nov = client.get('/api/monthly-summary?year=2026', headers=h('primavera')).get_json()['months'][10]
    assert nov['gastos_operativos'] == 0 and nov['cuotas'] == 0
    assert nov['prestamos'] == 1000000 + 4000                                 # aparte, con su 4x1000


def test_abono_que_llega_a_cuenta_de_carreno_crea_espejo_y_se_sincroniza(client, h):
    resp = _post(client, h('primavera'), concept='Transferencia', category='pago_prestamo_tienda',
                 related_store_code='carreno', purpose='cuenta', arrived_method='qr', qr=500000)
    assert resp.status_code == 201, resp.get_json()
    pid = resp.get_json()['item']['id']
    assert _balances(client, h())['qr'] == 500000                     # llegó a Carreño
    mirror = client.get('/api/expenses?year=2026&month=11', headers=h()).get_json()['items'][0]
    assert mirror['direction'] == 'in' and mirror['linked_from_id'] == pid
    # el espejo no baja la deuda otra vez
    assert _debt(client, h())['balance'] == OPENING - 500000
    # el espejo no se edita ni se borra por su lado
    assert client.delete(f"/api/expenses/{mirror['id']}", headers=h()).status_code == 400
    # editar el abono cambia el espejo; borrarlo lo quita y revierte las cuentas
    assert client.put(f'/api/expenses/{pid}', headers=h('primavera'), json={'qr': 300000}).status_code == 200
    assert _balances(client, h())['qr'] == 300000
    assert _debt(client, h())['balance'] == OPENING - 300000
    assert client.delete(f'/api/expenses/{pid}', headers=h('primavera')).status_code == 200
    assert _balances(client, h())['qr'] == 0
    assert client.get('/api/expenses?year=2026&month=11', headers=h()).get_json()['items'] == []
    assert _debt(client, h())['balance'] == OPENING


def test_abono_con_recompra_de_carreno_crea_recompra_sin_mover_cuentas(client, h):
    resp = _post(client, h('primavera'), concept='Recompra de Carreño', category='pago_prestamo_tienda',
                 related_store_code='carreno', purpose='recompra', efectivo=2000000, account_mode='cuentas')
    assert resp.status_code == 201, resp.get_json()
    pid = resp.get_json()['item']['id']
    entries = client.get('/api/repurchase?year=2026&month=11', headers=h()).get_json()
    rows = entries.get('entries') or entries.get('items') or []
    assert len(rows) == 1
    rec = rows[0]
    assert rec['paid_by_store'] == 'primavera' and rec['linked_expense_id'] == pid
    assert rec['total_enviado'] == 2000000 and rec['fee_4mil'] == 0
    assert 'No se movió en cuentas' in rec['notes']
    assert _balances(client, h())['cash'] == 0                          # Carreño no mueve cuentas
    assert _balances(client, h('primavera'))['cash'] == -2000000         # sale de Primavera
    assert client.delete(f"/api/repurchase/{rec['id']}", headers=h()).status_code == 400
    # La recompra cuenta en Año de Carreño (repone su mercancía)
    nov = client.get('/api/monthly-summary?year=2026', headers=h()).get_json()['months'][10]
    assert nov['recompras'] == 2000000
    # cambiar "para qué fue" quita la recompra espejo
    client.put(f'/api/expenses/{pid}', headers=h('primavera'), json={'purpose': 'otro'})
    entries = client.get('/api/repurchase?year=2026&month=11', headers=h()).get_json()
    assert (entries.get('entries') or entries.get('items') or []) == []


def test_prestamo_nuevo_de_carreno_suma_a_la_deuda(client, h):
    _post(client, h(), concept='Pago de vestieres de Primavera', category='prestamo_tienda',
          related_store_code='primavera', purpose='otro', qr=400000)
    debt = _debt(client, h('primavera'))
    assert debt['balance'] == OPENING + 400000
    assert debt['movements'][0]['kind'] == 'prestamo'
    assert debt['movements'][0]['balance_after'] == OPENING + 400000


def test_lo_anterior_a_la_partida_es_solo_historial(client, h):
    _post(client, h(), date='2026-10-20', concept='Viejo', category='prestamo_tienda',
          related_store_code='primavera', purpose='otro', qr=3000000)
    _post(client, h(), date='2026-10-25', concept='Devolución vieja', direction='in',
          category='devolucion_prestamo_tienda', related_store_code='primavera', qr=1000000)
    debt = _debt(client, h())
    assert debt['balance'] == OPENING and debt['history_before']['count'] == 2
    # Una devolución anotada a mano en Carreño después de la partida sí baja
    _post(client, h(), concept='Primavera consignó', direction='in',
          category='devolucion_prestamo_tienda', related_store_code='primavera', qr=100000)
    assert _debt(client, h())['balance'] == OPENING - 100000


def test_validaciones_de_para_que_fue(client, h):
    p = h('primavera')
    assert _post(client, p, category='pago_prestamo_tienda', related_store_code='carreno', qr=1).status_code == 400
    assert _post(client, p, category='pago_prestamo_tienda', related_store_code='carreno',
                 purpose='cuenta', qr=1).status_code == 400                # falta a qué cuenta llegó
    assert _post(client, h(), category='prestamo_tienda', related_store_code='primavera',
                 purpose='ganancias', qr=1).status_code == 400             # ganancias solo en abonos
    assert _post(client, p, category='pago_prestamo_tienda', related_store_code='primavera',
                 purpose='otro', qr=1).status_code == 400                  # a sí misma


def test_cambiar_saldo_de_partida_deja_rastro_y_viewer_solo_ve(client, h):
    assert client.put('/api/inter-store-debt/opening', headers=h(),
                      json={'opening_balance': 9000000, 'opening_date': '2026-11-06'}).status_code == 400  # sin nota
    resp = client.put('/api/inter-store-debt/opening', headers=h(),
                      json={'opening_balance': 9000000, 'opening_date': '2026-11-06', 'note': 'Cuadre con Cristhian'})
    assert resp.status_code == 200
    debt = resp.get_json()['debt']
    assert debt['balance'] == 9000000
    assert debt['opening_history'][-1]['old_balance'] == OPENING
    assert debt['opening_history'][-1]['note'] == 'Cuadre con Cristhian'
    viewer = h('primavera', role='viewer')
    assert client.get('/api/inter-store-debt', headers=viewer).status_code == 200
    assert client.put('/api/inter-store-debt/opening', headers=viewer,
                      json={'opening_balance': 1, 'opening_date': '2026-11-06', 'note': 'x'}).status_code == 403
    assert _post(client, viewer, category='pago_prestamo_tienda', related_store_code='carreno',
                 purpose='otro', qr=1).status_code == 403
