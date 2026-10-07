"""
Tests de la Fase 4 de docs/PLAN_CUENTAS_DIARIAS.md: configuración financiera
por tienda (crecimiento de la meta, META 2, regla 70/30), incentivos por meta
con pago a Gastos (una vez por regla y mes), regla 70/30 en el resumen anual
y gastos en el comparativo de tiendas.

Base SQLite temporal, sin red (la meta del mes se simula).
"""
from datetime import date, datetime

import pytest

from app.config import TestingConfig


@pytest.fixture
def app(tmp_path):
    class FinanceTestConfig(TestingConfig):
        SQLALCHEMY_DATABASE_URI = f"sqlite:///{(tmp_path / 'finance.db').as_posix()}"
        SQLALCHEMY_ENGINE_OPTIONS = {}

    from app import create_app
    return create_app(FinanceTestConfig)


@pytest.fixture
def h(app):
    from app.services.jwt_service import JWTService
    with app.app_context():
        token = JWTService.generate_token(1, 'admin1@test.com', 'admin', None)
    return lambda store=None: {
        'Authorization': f'Bearer {token}', **({'X-Store': store} if store else {})
    }


@pytest.fixture(autouse=True)
def today(monkeypatch):
    import app.routes.finance as finance_routes
    import app.routes.monthly_summary as summary_routes
    now = lambda: datetime(2026, 10, 20, 12, 0)  # noqa: E731
    monkeypatch.setattr(finance_routes, 'get_colombia_now', now)
    monkeypatch.setattr(summary_routes, 'get_colombia_now', now)


def _goal(monkeypatch, meta1=55014000, sales=60000000):
    import app.routes.finance as finance_routes
    from app.services import finance_settings

    def fake(store, year, month):
        extra = finance_settings.get_settings(store)['meta2_extra']
        return {'meta1': meta1, 'meta2': meta1 + extra, 'sales': sales}
    monkeypatch.setattr(finance_routes, 'month_goal_status', fake)


def test_configuracion_por_tienda(client, h):
    data = client.get('/api/finance-settings', headers=h()).get_json()
    assert data['settings'] == {'goal_growth_pct': 15, 'meta2_extra': 300000, 'resurtido_pct': 70, 'margin_pct': 35}
    resp = client.put('/api/finance-settings', headers=h(), json={'goal_growth_pct': 25, 'resurtido_pct': 65})
    assert resp.status_code == 200 and resp.get_json()['settings']['goal_growth_pct'] == 25
    assert client.get('/api/finance-settings', headers=h('primavera')).get_json()['settings']['goal_growth_pct'] == 15
    assert client.put('/api/finance-settings', headers=h(), json={'resurtido_pct': 120}).status_code == 400


def test_crecimiento_configurable_en_metas(app):
    from app.services import finance_settings
    from app.services.seller_goals import SellerGoalsService, clear_cache

    class Direct:
        def get_all_sales_totals_by_day(self, start, end):
            return {'success': True, 'data': [{'total': 1000000}]}

        def get_sellers(self):
            return []

        def get_sales_by_seller(self, start, end):
            return []

    clear_cache()
    with app.test_request_context('/'):
        finance_settings.save_settings('carreno', {'goal_growth_pct': 25})
        svc = SellerGoalsService('carreno', date(2026, 10, 20), Direct(), None)
        svc._month_sales = lambda start, end: {'source': 'none', 'sellers': {}}
        summary = svc.summary(date(2026, 10, 1))
    clear_cache()
    assert summary['growth_pct'] == 25 and summary['store_auto_goal'] == 1250000


def test_incentivos_plantilla_estado_y_pago_una_vez(client, h, monkeypatch):
    _goal(monkeypatch, meta1=55014000, sales=55200000)   # pasa META 1 pero no META 2 (55.314.000)
    assert client.post('/api/incentives/rules/load-template', headers=h()).status_code == 201
    assert client.post('/api/incentives/rules/load-template', headers=h()).status_code == 409
    data = client.get('/api/incentives?year=2026&month=10', headers=h()).get_json()
    rules = {r['threshold']: r for r in data['rules']}
    assert rules['meta1']['amount'] == 300000 and rules['meta2']['amount'] == 150000

    def pay(rule):
        return client.post('/api/incentives/pay', headers=h(), json={
            'rule_id': rule['id'], 'year': 2026, 'month': 10, 'method': 'efectivo'})
    resp = pay(rules['meta1'])
    assert resp.status_code == 201, resp.get_json()
    exp = resp.get_json()['expense']
    assert exp['category'] == 'sueldo' and exp['efectivo'] == 300000 and exp['period'] == '2026-10'
    assert exp['date'] == '2026-10-20'
    assert pay(rules['meta1']).status_code == 400                                 # una sola vez
    assert 'no alcanza' in pay(rules['meta2']).get_json()['message']              # META 2 no se alcanzó
    paid = client.get('/api/incentives?year=2026&month=10', headers=h()).get_json()['rules']
    assert [r['paid'] is not None for r in paid] == [True, False]
    accounts = client.get('/api/accounts', headers=h()).get_json()['accounts']
    assert next(a['balance'] for a in accounts if a['payment_key'] == 'cash') == -300000


def test_regla_crud_y_validaciones(client, h):
    resp = client.post('/api/incentives/rules', headers=h(), json={'name': 'Bono Mónica', 'amount': 100000, 'threshold': 'meta2'})
    assert resp.status_code == 201
    rid = resp.get_json()['rule']['id']
    assert client.post('/api/incentives/rules', headers=h(), json={'name': 'X', 'amount': 0}).status_code == 400
    assert client.post('/api/incentives/rules', headers=h(), json={'name': 'X', 'amount': 1, 'threshold': 'meta3'}).status_code == 400
    assert client.put(f'/api/incentives/rules/{rid}', headers=h(), json={'amount': 120000}).get_json()['rule']['amount'] == 120000
    assert client.delete(f'/api/incentives/rules/{rid}', headers=h('primavera')).status_code == 404
    assert client.delete(f'/api/incentives/rules/{rid}', headers=h()).status_code == 200


def test_regla_70_30_en_el_resumen_anual(app, client, h):
    from app.models.user import db
    from app.models.invoice_fact import InvoiceFact
    with app.app_context():
        db.session.add(InvoiceFact(store_code='carreno', alegra_id='1', date=date(2026, 10, 5), total=10000000))
        db.session.commit()
    client.post('/api/repurchase', headers=h(), json={'date': '2026-10-05', 'efectivo': 6000000})
    octubre = client.get('/api/monthly-summary?year=2026', headers=h()).get_json()['months'][9]
    assert octubre['resurtido_esperado'] == pytest.approx(7000000)
    assert octubre['resurtido_diferencia'] == pytest.approx(-1000000)        # se recompró $1 M menos
    assert octubre['utilidad_esperada'] == pytest.approx(3000000)
    assert octubre['resurtido_en_ropa'] == pytest.approx(7000000 / 0.65)


def test_gastos_en_el_comparativo(app, client, h):
    from app.routes.stores import _operational_metrics
    client.post('/api/expenses', headers=h(), json={'date': '2026-10-05', 'concept': 'Arriendo', 'efectivo': 1000000})
    client.post('/api/expenses', headers=h(), json={'date': '2026-10-05', 'concept': 'Cámaras', 'category': 'inversion', 'efectivo': 500000})
    client.post('/api/repurchase', headers=h(), json={'date': '2026-10-05', 'efectivo': 1000000})
    with app.app_context():
        ops = _operational_metrics('carreno', date(2026, 10, 1), date(2026, 10, 31))
    assert ops['expenses_operating'] == 1000000 + 4000     # + 4x1000 de la recompra
    assert ops['expenses_other'] == 500000


def test_incentivo_por_empleada_queda_en_empleadas(client, h, monkeypatch):
    _goal(monkeypatch, meta1=55014000, sales=56000000)
    rules = [
        client.post('/api/incentives/rules', headers=h(), json={
            'name': 'Incentivo Mónica (META 1)', 'amount': 250000, 'threshold': 'meta1', 'employee_name': 'Mónica'}).get_json()['rule'],
        client.post('/api/incentives/rules', headers=h(), json={
            'name': 'Incentivo Rita (META 1)', 'amount': 150000, 'threshold': 'meta1', 'employee_name': 'Rita'}).get_json()['rule'],
    ]
    assert rules[0]['employee_name'] == 'Mónica'
    for r in rules:
        resp = client.post('/api/incentives/pay', headers=h(), json={'rule_id': r['id'], 'year': 2026, 'month': 10,
                                                                      'method': 'efectivo', 'account_mode': 'caja'})
        assert resp.status_code == 201
        assert resp.get_json()['expense']['employee_name'] == r['employee_name']
    pagos = client.get('/api/employee-records/payments', headers=h()).get_json()['items']
    assert sorted((p['nombre_empleada'], p['type'], p['amount']) for p in pagos) == [
        ('Mónica', 'comision', 250000), ('Rita', 'comision', 150000)]
    # sin empleada: no crea pago en Empleadas
    r = client.post('/api/incentives/rules', headers=h(), json={'name': 'Bono tienda', 'amount': 1000, 'threshold': 'meta1'}).get_json()['rule']
    client.post('/api/incentives/pay', headers=h(), json={'rule_id': r['id'], 'year': 2026, 'month': 10, 'method': 'efectivo'})
    assert len(client.get('/api/employee-records/payments', headers=h()).get_json()['items']) == 2
