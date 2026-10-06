"""
Tests de Cuentas → Año (Fase 3 de docs/PLAN_CUENTAS_DIARIAS.md): resumen
mensual (ventas, recompras, gastos por mes al que corresponden, ganancias),
valores escritos a mano, inventario al cierre del mes desde Alegra
(simulado) y su variación, ventas por medio del año y separación por tienda.

Base SQLite temporal (nunca instance/cierre_caja.db), sin red.
"""
from datetime import date, datetime

import pytest

from app.config import TestingConfig


@pytest.fixture
def app(tmp_path):
    class SummaryTestConfig(TestingConfig):
        SQLALCHEMY_DATABASE_URI = f"sqlite:///{(tmp_path / 'summary.db').as_posix()}"
        SQLALCHEMY_ENGINE_OPTIONS = {}

    from app import create_app
    return create_app(SummaryTestConfig)


@pytest.fixture
def h(app):
    from app.services.jwt_service import JWTService
    with app.app_context():
        token = JWTService.generate_token(1, 'admin1@test.com', 'admin', None)
    return lambda store=None: {
        'Authorization': f'Bearer {token}', **({'X-Store': store} if store else {})
    }


@pytest.fixture(autouse=True)
def today_oct6(monkeypatch):
    import app.routes.monthly_summary as routes
    monkeypatch.setattr(routes, 'get_colombia_now', lambda: datetime(2026, 10, 6, 12, 0))


INVENTORY_BY_DATE = {'2026-08-31': 170000000, '2026-09-30': 175000000, '2026-10-06': 173000000,
                     '2026-07-31': 174013437}


class FakeDirect:
    def __init__(self):
        self.calls = []

    def get_inventory_value_totals(self, to_date, query='', force_inventory_parallel=False):
        self.calls.append(to_date)
        if to_date not in INVENTORY_BY_DATE:
            return {'success': False, 'error': 'sin dato'}
        return {'success': True, 'data': {'total': INVENTORY_BY_DATE[to_date]}}


def _seed_sales(app, store='carreno'):
    from app.models.user import db
    from app.models.invoice_fact import InvoiceFact
    from app.models.month_sheet import PaymentFact
    with app.app_context():
        rows = [('2026-08-15', 50000000, False), ('2026-09-10', 42239140, False), ('2026-09-11', 999, True),
                ('2026-10-01', 4382400, False), ('2026-10-05', 1344500, False)]
        for i, (d, total, voided) in enumerate(rows):
            db.session.add(InvoiceFact(store_code=store, alegra_id=f'{store}{i}', date=date.fromisoformat(d),
                                       total=total, voided=voided))
        for i, (d, medio, amount) in enumerate([('2026-10-01', 'qr', 1709700), ('2026-10-05', 'addi', 204700),
                                                ('2026-09-10', 'efectivo', 1000)]):
            db.session.add(PaymentFact(store_code=store, payment_id=str(i), invoice_id=str(i),
                                       invoice_date=date.fromisoformat(d), payment_date=date.fromisoformat(d),
                                       medio=medio, amount=amount))
        db.session.commit()


def _year(client, h, store=None):
    return client.get('/api/monthly-summary?year=2026', headers=h(store)).get_json()


def _month(data, n):
    return data['months'][n - 1]


def test_resumen_del_mes_y_ganancias(app, client, h):
    _seed_sales(app)
    client.post('/api/repurchase', headers=h(), json={'date': '2026-10-05', 'efectivo': 2710000})
    client.post('/api/repurchase/purchases', headers=h(), json={'date': '2026-10-06', 'store': 'X', 'amount': 1000000})
    exp = lambda **p: client.post('/api/expenses', headers=h(), json={'date': '2026-10-02', 'concept': 'x', **p})
    exp(category='operativo', efectivo=53200, account_mode='caja')
    exp(category='inversion', qr=308828, apply_fee=False, account_mode='sin_mover')
    exp(category='retiro_socio', efectivo=1000000)
    exp(category='prestamo_tienda', related_store_code='primavera', qr=500000, apply_fee=False)
    exp(category='operativo', qr=266000, period='2026-09', date='2026-10-05')   # internet de septiembre
    exp(category='flete', efectivo=607000)

    data = _year(client, h)
    sep, octubre, nov = _month(data, 9), _month(data, 10), _month(data, 11)

    assert sep['ventas'] == 42239140                    # sin la anulada
    assert sep['gastos_operativos'] == 266000 + 1064    # el internet cuenta en septiembre, con 4x1000
    assert octubre['ventas'] == 4382400 + 1344500
    assert octubre['recompras'] == 2710000
    fee_recompra = round(2710000 * 4 / 1000)
    assert octubre['gastos_operativos'] == 53200 + 607000 + fee_recompra
    assert octubre['inversiones'] == 308828
    assert octubre['retiros'] == 1000000
    assert octubre['prestamos'] == 500000
    assert octubre['fletes'] == 607000
    assert octubre['ganancia_bruta'] == octubre['ventas'] - 2710000
    assert octubre['ganancia_neta'] == octubre['ventas'] - octubre['gastos_operativos']
    assert octubre['ganancia_real'] == octubre['ventas'] - 2710000 - octubre['gastos_operativos']
    assert octubre['porcentaje'] == pytest.approx(octubre['ganancia_real'] / octubre['ventas'])
    assert octubre['jhonatan'] == 2710000 - 1000000
    assert octubre['in_progress'] is True
    assert nov['future'] is True and 'ventas' not in nov

    # Agosto se ve pero no suma en el total (el resumen arranca en septiembre)
    assert _month(data, 8)['ventas'] == 50000000 and _month(data, 8)['before_start'] is True
    assert data['totals']['ventas'] == sep['ventas'] + octubre['ventas']
    assert data['months_counted'] == 2

    # Ventas por medio del año
    assert data['ventas_por_medio_year']['qr'] == 1709700
    assert octubre['ventas_por_medio']['addi'] == 204700


def test_valor_escrito_a_mano_manda_y_se_puede_quitar(app, client, h):
    _seed_sales(app)
    resp = client.put('/api/monthly-summary/override', headers=h(),
                      json={'period': '2026-09', 'field': 'gastos_operativos', 'value': 4150293, 'note': 'Excel sep'})
    assert resp.status_code == 200
    sep = _month(_year(client, h), 9)
    assert sep['gastos_operativos'] == 4150293
    assert sep['edited']['gastos_operativos'] == {'computed': 0, 'note': 'Excel sep'}
    assert sep['has_expenses'] is True
    assert sep['ganancia_neta'] == 42239140 - 4150293

    client.put('/api/monthly-summary/override', headers=h(), json={'period': '2026-09', 'field': 'gastos_operativos', 'value': None})
    assert _month(_year(client, h), 9)['gastos_operativos'] == 0

    assert client.put('/api/monthly-summary/override', headers=h(),
                      json={'period': '2026-09', 'field': 'ganancia_real', 'value': 1}).status_code == 400


def test_inventario_desde_alegra_y_variacion(app, client, h, monkeypatch):
    import app.routes.monthly_summary as routes
    fake = FakeDirect()
    monkeypatch.setattr(routes, 'get_alegra_direct_client', lambda store=None: fake)
    _seed_sales(app)

    resp = client.post('/api/monthly-summary/inventory', headers=h(), json={})
    assert resp.status_code == 200
    assert fake.calls == ['2026-08-31', '2026-09-30', '2026-10-06']   # agosto (para la variación) a hoy
    # ya están todos: no vuelve a llamar
    client.post('/api/monthly-summary/inventory', headers=h(), json={})
    assert len(fake.calls) == 3

    data = _year(client, h)
    sep, octubre = _month(data, 9), _month(data, 10)
    assert sep['inventario'] == 175000000 and sep['inventario_cambio'] == 5000000
    assert sep['ganancia_con_inventario'] == sep['ganancia_real'] + 5000000
    assert octubre['inventario_cambio'] == -2000000
    assert octubre['inventory_as_of'] == '2026-10-06'

    # un mes puntual (julio, para comparar con el Excel)
    client.post('/api/monthly-summary/inventory', headers=h(), json={'year': 2026, 'month': 7})
    assert _month(_year(client, h), 7)['inventario'] == 174013437

    # inventario escrito a mano manda también en la variación
    client.put('/api/monthly-summary/override', headers=h(),
               json={'period': '2026-08', 'field': 'inventario', 'value': 160000000})
    assert _month(_year(client, h), 9)['inventario_cambio'] == 15000000


def test_falla_de_alegra_no_borra_nada(app, client, h, monkeypatch):
    import app.routes.monthly_summary as routes
    monkeypatch.setattr(routes, 'get_alegra_direct_client', lambda store=None: FakeDirect())
    resp = client.post('/api/monthly-summary/inventory', headers=h(), json={'year': 2026, 'month': 6})
    assert resp.status_code == 502
    assert resp.get_json()['errors'][0]['period'] == '2026-06'
    assert _month(_year(client, h), 6)['inventario'] is None


def test_separado_por_tienda_y_permisos(app, client, h):
    _seed_sales(app, store='primavera')
    assert _month(_year(client, h), 9)['ventas'] == 0
    assert _month(_year(client, h, 'primavera'), 9)['ventas'] == 42239140
    from app.services.jwt_service import JWTService
    with app.app_context():
        sales = JWTService.generate_token(2, 'v@test.com', 'sales', None)
    assert client.get('/api/monthly-summary?year=2026', headers={'Authorization': f'Bearer {sales}'}).status_code == 403
    assert client.get('/api/monthly-summary', headers=h()).status_code == 400
