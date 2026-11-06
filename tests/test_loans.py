"""
Tests de los préstamos de cada tienda (Radiografía Fase 0c, docs/PLAN_RADIOGRAFIA.md):
cuota y tasa (recálculo al editar), pago desde Gastos (un solo registro que
mueve cuentas y baja la deuda), cuota descontada del préstamo, ajuste de saldo,
interés como gasto financiero en Año, avisos del 25 y de fin de mes, por tienda
y solo lectura.

Base SQLite temporal, sin red.
"""
from datetime import date, datetime

import pytest

from app.config import TestingConfig
from app.services import loans as svc


@pytest.fixture
def app(tmp_path):
    class LoansTestConfig(TestingConfig):
        SQLALCHEMY_DATABASE_URI = f"sqlite:///{(tmp_path / 'loans.db').as_posix()}"
        SQLALCHEMY_ENGINE_OPTIONS = {}

    from app import create_app
    return create_app(LoansTestConfig)


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


@pytest.fixture(autouse=True)
def nov6(monkeypatch):
    import app.routes.loans as routes
    monkeypatch.setattr(routes, 'get_colombia_now', lambda: datetime(2026, 11, 6, 12, 0))


DON_MIGUEL = [('Préstamo de $20.000.000', 20000000, 60, 554633),
              ('Préstamo de $10.000.000', 10000000, 24, 527600),
              ('Préstamo de $37.000.000', 37000000, 72, 951000)]


def _create(client, headers, **p):
    base = {'group_name': 'Don Miguel (BBVA)', 'start_date': '2026-11-06', 'due_day': 25}
    base.update(p)
    resp = client.post('/api/loans', headers=headers, json=base)
    assert resp.status_code == 201, resp.get_json()
    return resp.get_json()['id']


def _groups(client, headers):
    return client.get('/api/loans', headers=headers).get_json()['groups']


def _loan(client, headers, loan_id):
    return next(l for g in _groups(client, headers) for l in g['loans'] if l['id'] == loan_id)


def test_formulas():
    assert svc.annuity_payment(20000000, None, 60) == pytest.approx(333333.33, abs=1)
    assert svc.rate_from_payment(20000000, 60, 554633) == pytest.approx(1.85, abs=0.01)
    assert svc.rate_from_payment(10000000, 24, 527600) == pytest.approx(1.98, abs=0.01)
    assert svc.rate_from_payment(37000000, 72, 951000) == pytest.approx(1.91, abs=0.01)
    assert svc.rate_from_payment(37000000, 12, 421000) is None          # no alcanza ni sin intereses
    assert svc.annuity_payment(20000000, 1.8498, 60) == pytest.approx(554633, abs=50)
    assert svc.installments_left(20000000, 1.8498, 554633) == 60
    assert svc.installments_left(1000, None, 300) == 4
    assert svc.installments_left(1000000, 5, 40000) is None              # no alcanza para el interés


def test_don_miguel_tres_prestamos_en_una_tarjeta_con_tasa_estimada(client, h):
    p = h('primavera')
    for name, principal, term, cuota in DON_MIGUEL:
        _create(client, p, name=name, principal=principal, term_months=term, installment=cuota)
    groups = _groups(client, p)
    assert len(groups) == 1
    g = groups[0]
    assert g['group_name'] == 'Don Miguel (BBVA)' and g['principal'] == 67000000
    assert g['installment'] == 554633 + 527600 + 951000
    l20 = g['loans'][0]
    assert l20['rate_estimated'] is True and l20['monthly_rate_pct'] == pytest.approx(1.85, abs=0.01)
    assert l20['installments_left'] == 60
    assert _groups(client, h()) == []                                     # Carreño no lo ve


def test_mama_de_angie_cuota_libre(client, h):
    lid = _create(client, h(), group_name='Mamá de Angie', name='Deuda de la apertura de Carreño', principal=7500000)
    loan = _loan(client, h(), lid)
    assert loan['installment'] is None and loan['monthly_rate_pct'] is None
    assert loan['balance'] == 7500000 and loan['installments_left'] is None


def test_pago_desde_gastos_baja_cuenta_y_deuda_con_interes_aparte(client, h, monkeypatch):
    p = h('primavera')
    lid = _create(client, p, name='Préstamo de $10.000.000', principal=10000000, term_months=24, installment=527600)
    rate = _loan(client, p, lid)['monthly_rate_pct']
    resp = client.post('/api/expenses', headers=p, json={
        'date': '2026-11-07', 'concept': 'Cuota 1 de 24, préstamo 10M don Miguel BBVA',
        'subcategory': 'cuota_banco', 'efectivo': 527600, 'loan_id': lid})
    assert resp.status_code == 201, resp.get_json()
    eid = resp.get_json()['item']['id']
    accounts = client.get('/api/accounts', headers=p).get_json()['accounts']
    assert next(a for a in accounts if a['payment_key'] == 'cash')['balance'] == -527600
    loan = _loan(client, p, lid)
    interest = round(10000000 * rate / 100)
    assert loan['payments'][0]['interest'] == interest
    assert loan['balance'] == pytest.approx(10000000 - (527600 - interest))
    assert loan['installments_left'] == 23
    assert loan['pending_this_month'] is False
    # Año: el interés es gasto financiero, el capital es cuota; la ganancia real resta todo
    import app.routes.monthly_summary as ms
    monkeypatch.setattr(ms, 'get_colombia_now', lambda: datetime(2026, 11, 7, 12, 0))
    nov = client.get('/api/monthly-summary?year=2026', headers=p).get_json()['months'][10]
    assert nov['gastos_operativos'] == pytest.approx(interest)
    assert nov['cuotas'] == pytest.approx(527600 - interest)
    assert nov['ganancia_real'] == pytest.approx(nov['ventas'] - nov['recompras'] - 527600)
    # Editar el gasto cambia el pago; borrarlo lo quita
    client.put(f'/api/expenses/{eid}', headers=p, json={'efectivo': 500000})
    assert _loan(client, p, lid)['payments'][0]['amount'] == 500000
    client.delete(f'/api/expenses/{eid}', headers=p)
    assert _loan(client, p, lid)['payments'] == []
    assert _loan(client, p, lid)['balance'] == 10000000


def test_cuota_descontada_del_prestamo_y_ajuste_de_saldo(client, h):
    p = h('primavera')
    lid = _create(client, p, name='Préstamo de $20.000.000', principal=20000000, term_months=60, installment=554633)
    resp = client.post(f'/api/loans/{lid}/payments', headers=p,
                       json={'kind': 'descontado', 'amount': 554633, 'date': '2026-11-06',
                             'note': 'Cuota 1: se descontó del mismo préstamo'})
    assert resp.status_code == 201
    loan = _loan(client, p, lid)
    assert loan['payments'][0]['kind'] == 'descontado' and loan['installments_left'] == 59
    # No movió cuentas ni es gasto del mes
    accounts = client.get('/api/accounts', headers=p).get_json()['accounts']
    assert all(a['balance'] == 0 for a in accounts)
    # Ajustar saldo: exige nota y lleva al saldo pedido
    assert client.post(f'/api/loans/{lid}/payments', headers=p, json={'kind': 'ajuste', 'new_balance': 19000000}).status_code == 400
    client.post(f'/api/loans/{lid}/payments', headers=p,
                json={'kind': 'ajuste', 'new_balance': 19500000, 'note': 'Según extracto BBVA'})
    assert _loan(client, p, lid)['balance'] == pytest.approx(19500000)
    # Un pago "con plata" no se registra aquí sino en Gastos
    assert client.post(f'/api/loans/{lid}/payments', headers=p, json={'kind': 'pago', 'amount': 1}).status_code == 400
    pid = _loan(client, p, lid)['payments'][-1]['id']
    assert client.delete(f'/api/loans/payments/{pid}', headers=p).status_code == 200


def test_cuota_pagada_en_dos_partes_reparte_el_interes_del_mes(client, h):
    """Caso real (37M, cuota 1 de $951.000 = $530.000 descontados + $421.000 en efectivo)."""
    p = h('primavera')
    lid = _create(client, p, name='Préstamo de $37.000.000', principal=37000000, term_months=72, installment=951000)
    rate = _loan(client, p, lid)['monthly_rate_pct']
    client.post(f'/api/loans/{lid}/payments', headers=p, json={'kind': 'descontado', 'amount': 530000, 'date': '2026-11-06'})
    client.post('/api/expenses', headers=p, json={'date': '2026-11-06', 'concept': 'Cuota 1', 'subcategory': 'cuota_banco',
                                                  'efectivo': 421000, 'loan_id': lid})
    loan = _loan(client, p, lid)
    interest = round(37000000 * rate / 100)
    first, second = loan['payments']
    assert first['interest'] == 530000 and first['capital'] == 0
    assert second['interest'] == interest - 530000          # lo que faltaba del interés del mes
    assert loan['interest_total'] == interest
    assert loan['balance'] == pytest.approx(37000000 - (951000 - interest))


def test_editar_recalcula_y_deja_rastro(client, h):
    p = h('primavera')
    lid = _create(client, p, name='Préstamo de $37.000.000', principal=37000000, term_months=72, installment=951000)
    # Cambiar el plazo con la tasa de hoy recalcula la cuota
    client.put(f'/api/loans/{lid}', headers=p, json={'term_months': 60, 'change_note': 'Era a 5 años'})
    loan = _loan(client, p, lid)
    assert loan['term_months'] == 60
    assert loan['installment'] == round(svc.annuity_payment(37000000, loan['monthly_rate_pct'], 60))
    # Escribir la tasa real recalcula la cuota y deja de ser estimada
    client.put(f'/api/loans/{lid}', headers=p, json={'monthly_rate_pct': 1.5})
    loan = _loan(client, p, lid)
    assert loan['rate_estimated'] is False
    assert loan['installment'] == round(svc.annuity_payment(37000000, 1.5, 60))
    # Escribir la cuota recalcula la tasa (estimada)
    client.put(f'/api/loans/{lid}', headers=p, json={'installment': 951000})
    loan = _loan(client, p, lid)
    assert loan['rate_estimated'] is True
    assert loan['monthly_rate_pct'] == pytest.approx(svc.rate_from_payment(37000000, 60, 951000))
    assert len(loan['history']) == 3 and loan['history'][0]['note'] == 'Era a 5 años'
    assert 'term_months' in loan['history'][0]['changes']


def test_avisos_del_25_y_de_fin_de_mes(app, client, h, monkeypatch):
    from app.services.reminders import active
    p = h('primavera')
    lid = _create(client, p, name='Préstamo de $10.000.000', principal=10000000, term_months=24, installment=527600)
    client.post('/api/expenses/fixed', headers=p, json={'name': 'Arriendo', 'amount': 1052000, 'due_day': 30,
                                                        'subcategory': 'arriendo'})
    with app.app_context():
        keys = lambda d: [r['key'] for r in active('primavera', d)]
        assert keys(date(2026, 11, 24)) == []
        assert 'loans-2026-11' in keys(date(2026, 11, 25))
        assert 'fixed-2026-11' not in keys(date(2026, 11, 27))
        assert 'fixed-2026-11' in keys(date(2026, 11, 28))           # noviembre tiene 30 días
        assert 'fixed-2027-02' in keys(date(2027, 2, 26))            # febrero de 28
        assert keys(date(2026, 11, 25)) and active('carreno', date(2026, 11, 28)) == []
    client.post('/api/expenses', headers=p, json={'date': '2026-11-25', 'concept': 'Cuota',
                                                  'subcategory': 'cuota_banco', 'efectivo': 527600, 'loan_id': lid})
    with app.app_context():
        assert 'loans-2026-11' not in [r['key'] for r in active('primavera', date(2026, 11, 26))]


def test_validaciones_y_solo_lectura(client, h):
    p = h('primavera')
    assert client.post('/api/loans', headers=p, json={'group_name': 'X', 'name': 'Y', 'start_date': '2026-11-06'}).status_code == 400
    lid = _create(client, p, name='Préstamo', principal=1000000)
    # Préstamo de otra tienda en un gasto: 400
    assert client.post('/api/expenses', headers=h(), json={'date': '2026-11-07', 'concept': 'x',
                                                            'subcategory': 'cuota_banco', 'efectivo': 1,
                                                            'loan_id': lid}).status_code == 400
    # loan_id en una categoría que no es cuota: se ignora
    resp = client.post('/api/expenses', headers=p, json={'date': '2026-11-07', 'concept': 'x',
                                                          'subcategory': 'arriendo', 'efectivo': 1, 'loan_id': lid})
    assert resp.status_code == 201 and resp.get_json()['item']['loan_id'] is None
    viewer = h('primavera', role='viewer')
    assert client.get('/api/loans', headers=viewer).status_code == 200
    assert client.put(f'/api/loans/{lid}', headers=viewer, json={'principal': 1}).status_code == 403
    assert client.post(f'/api/loans/{lid}/payments', headers=viewer,
                       json={'kind': 'descontado', 'amount': 1}).status_code == 403
