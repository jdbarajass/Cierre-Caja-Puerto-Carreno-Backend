"""
Tests de Cuentas → Gastos (Fase 1 de docs/PLAN_CUENTAS_DIARIAS.md):
movimientos en las cuentas de Resumen (4x1000, editar/borrar revierte),
modos caja/sin_mover, entradas, enlace con Empleadas, gastos fijos del mes,
préstamos entre tiendas y separación por tienda.

Base SQLite temporal (nunca instance/cierre_caja.db), sin red.
"""
from datetime import datetime

import pytest

from app.config import TestingConfig


@pytest.fixture
def app(tmp_path):
    class ExpensesTestConfig(TestingConfig):
        SQLALCHEMY_DATABASE_URI = f"sqlite:///{(tmp_path / 'expenses.db').as_posix()}"
        SQLALCHEMY_ENGINE_OPTIONS = {}

    from app import create_app
    return create_app(ExpensesTestConfig)


@pytest.fixture
def h(app):
    from app.services.jwt_service import JWTService
    with app.app_context():
        token = JWTService.generate_token(1, 'admin1@test.com', 'admin', None)
    return lambda store=None: {
        'Authorization': f'Bearer {token}', **({'X-Store': store} if store else {})
    }


def _balances(client, headers):
    data = client.get('/api/accounts', headers=headers).get_json()
    return {a['payment_key']: a['balance'] for a in data['accounts']}


def _post(client, headers, **payload):
    base = {'date': '2026-10-05', 'concept': 'Gasto', 'category': 'operativo'}
    base.update(payload)
    return client.post('/api/expenses', headers=headers, json=base)


def _month(client, headers, year=2026, month=10):
    return client.get(f'/api/expenses?year={year}&month={month}', headers=headers).get_json()


# ─── Cuentas de Resumen ─────────────────────────────────────────────────────

def test_gasto_descuenta_cuenta_con_4x1000_y_borrar_revierte(client, h):
    resp = _post(client, h(), concept='Internet', qr=266000)
    assert resp.status_code == 201
    item = resp.get_json()['item']
    assert item['fee'] == 1064 and item['total_with_fee'] == 267064
    assert item['period'] == '2026-10'
    assert _balances(client, h())['qr'] == -267064

    mov = client.get('/api/accounts/movements?type=expense', headers=h()).get_json()
    assert len(mov['movements']) == 1

    assert client.delete(f"/api/expenses/{item['id']}", headers=h()).status_code == 200
    assert _balances(client, h())['qr'] == 0


def test_efectivo_no_paga_4x1000_y_mixto_reparte_solo_en_bancos(client, h):
    item = _post(client, h(), efectivo=100000, nequi=500000).get_json()['item']
    assert item['fee'] == 2000
    b = _balances(client, h())
    assert b['cash'] == -100000
    assert b['nequi'] == -502000


def test_editar_cambia_de_medio_y_comision_manual(client, h):
    item = _post(client, h(), qr=100000).get_json()['item']
    resp = client.put(f"/api/expenses/{item['id']}", headers=h(),
                      json={'qr': 0, 'datafono': 100000, 'fee_override': 0})
    assert resp.status_code == 200
    b = _balances(client, h())
    assert b['qr'] == 0
    assert b['addi_datafono'] == -100000


def test_modo_caja_no_mueve_cuentas_y_solo_efectivo(client, h):
    resp = _post(client, h(), concept='Aseo', efectivo=48700, account_mode='caja')
    assert resp.status_code == 201
    assert _balances(client, h())['cash'] == 0
    totals = _month(client, h())['totals']
    assert totals['out_total'] == 48700                       # sí salió plata en el mes
    assert totals['by_method']['efectivo']['out'] == 0        # pero no de la cuenta EFECTIVO
    assert totals['by_category']['operativo']['total'] == 48700
    assert _post(client, h(), qr=1000, account_mode='caja').status_code == 400


def test_entrada_suma_a_la_cuenta(client, h):
    resp = _post(client, h(), concept='Dinero extra', direction='in', category='ingreso_extra', nequi=50000)
    assert resp.status_code == 201
    assert resp.get_json()['item']['fee'] == 0
    assert _balances(client, h())['nequi'] == 50000
    # categoría de salida en una entrada: inválida
    assert _post(client, h(), direction='in', category='operativo', nequi=1).status_code == 400


def test_validaciones(client, h):
    assert _post(client, h(), qr=0).status_code == 400                       # sin valor
    assert _post(client, h(), concept='', qr=1).status_code == 400           # sin concepto
    assert _post(client, h(), qr=1, period='2026-13').status_code == 400     # mes inválido
    assert _post(client, h(), qr=-5).status_code == 400                      # negativo
    assert _post(client, h(), qr=1, category='prestamo_empleada').status_code == 400  # sin empleada


# ─── Mes de la fecha vs mes al que corresponde ──────────────────────────────

def test_mes_al_que_corresponde(client, h):
    # Internet de septiembre pagado el 5 de octubre
    _post(client, h(), concept='Internet sep', qr=100000, period='2026-09')
    sep = _month(client, h(), 2026, 9)
    assert len(sep['items']) == 1
    assert sep['totals']['by_category']['operativo']['total'] == 100000
    assert sep['totals']['out_total'] == 0          # la plata salió en octubre
    octubre = _month(client, h(), 2026, 10)
    assert octubre['totals']['out_total'] == 100400
    assert octubre['totals']['by_method']['qr']['out'] == 100400
    assert 'operativo' not in octubre['totals']['by_category']


# ─── Empleadas ──────────────────────────────────────────────────────────────

def test_prestamo_empleada_crea_actualiza_y_borra_en_empleadas(client, h):
    item = _post(client, h(), concept='Préstamo', category='prestamo_empleada',
                 employee_name='Mónica', efectivo=250000).get_json()['item']
    loans = client.get('/api/employee-records/loans', headers=h()).get_json()
    assert loans['total_acumulado'] == 250000

    client.put(f"/api/expenses/{item['id']}", headers=h(), json={'efectivo': 300000})
    assert client.get('/api/employee-records/loans', headers=h()).get_json()['total_acumulado'] == 300000

    # abono: devolución de la empleada
    _post(client, h(), concept='Abono Mónica', direction='in', category='devolucion_prestamo',
          employee_name='Mónica', efectivo=100000)
    assert client.get('/api/employee-records/loans', headers=h()).get_json()['total_acumulado'] == 200000

    client.delete(f"/api/expenses/{item['id']}", headers=h())
    assert client.get('/api/employee-records/loans', headers=h()).get_json()['total_acumulado'] == -100000


def test_sueldo_con_empleada_va_a_pagos(client, h):
    item = _post(client, h(), concept='Quincena', category='sueldo', employee_name='Rita',
                 efectivo=650000, account_mode='caja').get_json()['item']
    pagos = client.get('/api/employee-records/payments', headers=h()).get_json()
    assert pagos['total_pagado'] == 650000
    # cambiar de categoría quita el pago ligado
    client.put(f"/api/expenses/{item['id']}", headers=h(), json={'category': 'operativo'})
    assert client.get('/api/employee-records/payments', headers=h()).get_json()['total_pagado'] == 0


# ─── Gastos fijos ───────────────────────────────────────────────────────────

def test_gastos_fijos_plantilla_y_estado(client, h, monkeypatch):
    import app.routes.expenses as expenses_module
    monkeypatch.setattr(expenses_module, 'get_colombia_now', lambda: datetime(2026, 10, 10, 12, 0))

    first = client.get('/api/expenses/fixed?year=2026&month=10', headers=h()).get_json()
    assert first['template_available'] is True
    assert client.post('/api/expenses/fixed/load-template', headers=h()).status_code == 201
    assert client.post('/api/expenses/fixed/load-template', headers=h()).status_code == 409

    data = client.get('/api/expenses/fixed?year=2026&month=10', headers=h()).get_json()
    by_name = {i['name']: i for i in data['items']}
    assert by_name['Internet']['status'] == 'vencido'        # día 5, hoy 10
    assert by_name['Arriendo']['status'] == 'pendiente'      # día 30

    _post(client, h(), concept='Internet', qr=266000, fixed_expense_id=by_name['Internet']['id'])
    data = client.get('/api/expenses/fixed?year=2026&month=10', headers=h()).get_json()
    internet = next(i for i in data['items'] if i['name'] == 'Internet')
    assert internet['status'] == 'pagado' and internet['paid_amount'] == 266000
    # en noviembre vuelve a estar pendiente
    nov = client.get('/api/expenses/fixed?year=2026&month=11', headers=h()).get_json()
    assert next(i for i in nov['items'] if i['name'] == 'Internet')['status'] == 'pendiente'


def test_gasto_fijo_crud(client, h):
    resp = client.post('/api/expenses/fixed', headers=h(), json={'name': 'Agua', 'amount': 50000, 'due_day': 10})
    assert resp.status_code == 201
    fid = resp.get_json()['item']['id']
    assert client.post('/api/expenses/fixed', headers=h(), json={'name': 'X', 'due_day': 40}).status_code == 400
    exp = _post(client, h(), concept='Agua', efectivo=50000, fixed_expense_id=fid).get_json()['item']
    assert client.delete(f'/api/expenses/fixed/{fid}', headers=h()).status_code == 200
    # el gasto pagado se conserva sin enlace
    items = _month(client, h())['items']
    assert [i['fixed_expense_id'] for i in items if i['id'] == exp['id']] == [None]


# ─── Préstamos entre tiendas y separación por tienda ────────────────────────

def test_prestamo_entre_tiendas(client, h):
    assert _post(client, h(), concept='Herrajería Primavera', category='prestamo_tienda',
                 related_store_code='primavera', qr=500000).status_code == 201
    _post(client, h(), concept='Primavera devuelve', direction='in', category='devolucion_prestamo_tienda',
          related_store_code='primavera', qr=200000)
    # a sí misma: inválido
    assert _post(client, h(), category='prestamo_tienda', related_store_code='carreno', qr=1).status_code == 400

    carreno = client.get('/api/expenses/inter-store', headers=h()).get_json()
    assert carreno['lent'][0]['balance'] == 300000
    primavera = client.get('/api/expenses/inter-store', headers=h('primavera')).get_json()
    assert primavera['owed'][0]['balance'] == 300000
    assert primavera['owed'][0]['lender'] == 'carreno'


def test_gastos_separados_por_tienda(client, h):
    item = _post(client, h('primavera'), qr=10000).get_json()['item']
    assert _month(client, h())['items'] == []
    assert len(_month(client, h('primavera'))['items']) == 1
    assert client.delete(f"/api/expenses/{item['id']}", headers=h()).status_code == 404
    assert _balances(client, h())['qr'] == 0
    assert _balances(client, h('primavera'))['qr'] == -10040
