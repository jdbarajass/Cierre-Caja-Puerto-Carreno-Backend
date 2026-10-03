"""
Fase D3 de Estadísticas (docs/PLAN_ESTADISTICAS.md): metas por vendedora.
Reparto automático (mismo mes del año anterior +15 %, según la venta de los 3
meses anteriores) que el admin puede ajustar. Los reportes simulados copian
el formato de /api/v1 (sales-by-seller: idLocal, name, totalDocuments, total).
"""
from datetime import date

import pytest

from app.services import invoice_facts as svc
from app.services import seller_goals as sg
from app.services.alegra_client import AlegraClient
from app.services.alegra_direct_client import AlegraDirectClient
from tests.test_estadisticas_fase_a import MONICA, RITA, invoice
from tests.test_estadisticas_fase_c import BOLSA, FakeAlegra, _headers, app, inv, item  # noqa: F401

CLIENTA = {'id': '735', 'name': 'INGRIT BAQUERO', 'identification': '1121884855'}
SELLERS = [
    {'id': '1', 'name': 'MONICA VARGAS', 'identification': '1192762720', 'status': 'active'},
    {'id': '12', 'name': 'RITA INFANTE', 'identification': '17105692', 'status': 'active'},
    {'id': '7', 'name': 'ASTRID PEREZ', 'identification': '1', 'status': 'inactive'},
]
HISTORY = [  # jul-sep 2026
    {'idLocal': '1', 'name': 'MONICA VARGAS', 'totalDocuments': 600, 'total': 60_000_000},
    {'idLocal': '12', 'name': 'RITA INFANTE', 'totalDocuments': 400, 'total': 40_000_000},
    {'idLocal': '7', 'name': 'ASTRID PEREZ', 'totalDocuments': 10, 'total': 5_000_000},  # ya no está
]


class FakeDirect:
    def __init__(self, last_year_total=40_000_000, month_report=None):
        self.last_year_total = last_year_total
        self.month_report = month_report or []
        self.calls = []

    def get_all_sales_totals_by_day(self, start, end):
        self.calls.append(('totals', start, end))
        return {'success': True, 'data': [{'date': start, 'total': self.last_year_total}]}

    def get_sales_by_seller(self, start, end):
        self.calls.append(('sellers-report', start, end))
        return HISTORY if start == '2026-07-01' else self.month_report

    def get_sellers(self):
        return SELLERS


@pytest.fixture(autouse=True)
def _clear():
    sg.clear_cache()
    yield
    sg.clear_cache()


# ─── Cálculos ───────────────────────────────────────────────────────────────

def test_reparto_por_venta_de_los_meses_anteriores():
    assert sg.split_goal(46_000_000, {'1': 60, '12': 40}, ['1', '12']) == {'1': 27_600_000, '12': 18_400_000}
    assert sg.split_goal(46_000_000, {}, ['1', '12']) == {'1': 23_000_000, '12': 23_000_000}  # sin historia
    assert sg.split_goal(None, {'1': 60}, ['1']) == {'1': None}  # tienda sin año anterior (Primavera)


def test_ritmo_del_mes():
    p = sg.pace(date(2026, 10, 1), date(2026, 10, 3))
    assert p == {'days_in_month': 31, 'elapsed_days': 3, 'remaining_days': 28, 'expected_pct': 9.7, 'is_current': True}
    prog = sg.seller_progress(31_000_000, 2_000_000, p)
    assert prog['projection'] == 20_666_667 and prog['on_track'] is False
    assert prog['needed_per_day'] == round(29_000_000 / 29)  # hoy aún cuenta
    assert sg.pace(date(2026, 9, 1), date(2026, 10, 3))['elapsed_days'] == 30


def test_rango_de_historia():
    assert sg.history_range(date(2026, 1, 1)) == (date(2025, 10, 1), date(2025, 12, 31))


# ─── Servicio ───────────────────────────────────────────────────────────────

def _load_october(today_invoices=()):
    # 1-oct: Mónica $100.000 a una clienta (2 prendas + bolsa); 2-oct: Rita $50.000 sin cliente
    svc.sync_day(FakeAlegra({'2026-10-01': [
        {**inv(1, MONICA, [item('CAMISETA MUJER 49900 / 1052499002', '1087', 50000, qty=2), BOLSA], day='2026-10-01'),
         'client': CLIENTA, 'total': 100_000},
    ]}), 'carreno', date(2026, 10, 1))
    svc.sync_day(FakeAlegra({'2026-10-02': [invoice(2, RITA, 50_000, day='2026-10-02')]}), 'carreno', date(2026, 10, 2))
    return FakeAlegra({'2026-10-03': list(today_invoices)})


def test_metas_y_avance_del_mes(app):
    with app.app_context():
        live = _load_october([invoice(3, RITA, 30_000, day='2026-10-03')])
        direct = FakeDirect()
        data = sg.SellerGoalsService('carreno', date(2026, 10, 3), direct, live).summary(date(2026, 10, 1))

        assert data['last_year'] == {'start': '2025-10-01', 'end': '2025-10-31', 'total': 40_000_000}
        assert data['store_auto_goal'] == 46_000_000
        assert data['source'] == 'facts'
        by_id = {r['id']: r for r in data['sellers']}
        assert set(by_id) == {'1', '12'}  # Astrid inactiva: sin meta (su parte se reparte)
        monica, rita = by_id['1'], by_id['12']
        assert monica['goal'] == 27_600_000 and monica['adjusted'] is False
        assert monica['sales'] == 100_000 and monica['units'] == 2 and monica['units_per_invoice'] == 2
        assert monica['identified_pct'] == 100.0
        assert rita['sales'] == 80_000 and rita['invoices'] == 2 and rita['identified_pct'] == 0.0  # hoy en vivo incluido
        assert data['store']['goal'] == 46_000_000 and data['store']['sales'] == 180_000


def test_meta_ajustada_por_el_admin(app):
    with app.app_context():
        live = _load_october()
        sg.set_goal('carreno', date(2026, 10, 1), '12', 'RITA INFANTE', 20_000_000, 'admin@test.com')
        data = sg.SellerGoalsService('carreno', date(2026, 10, 3), FakeDirect(), live).summary(date(2026, 10, 1))
        rita = next(r for r in data['sellers'] if r['id'] == '12')
        assert rita['goal'] == 20_000_000 and rita['auto_goal'] == 18_400_000 and rita['adjusted'] is True
        assert data['store']['goal'] == 27_600_000 + 20_000_000
        # Otra tienda no ve el ajuste
        other = sg.SellerGoalsService('primavera', date(2026, 10, 3), FakeDirect(), FakeAlegra({})).summary(date(2026, 10, 1))
        assert next(r for r in other['sellers'] if r['id'] == '12')['adjusted'] is False
        # Volver a la automática
        sg.set_goal('carreno', date(2026, 10, 1), '12', None, None, 'admin@test.com')
        data = sg.SellerGoalsService('carreno', date(2026, 10, 3), FakeDirect(), live).summary(date(2026, 10, 1))
        assert next(r for r in data['sellers'] if r['id'] == '12')['goal'] == 18_400_000


def test_si_faltan_dias_usa_el_reporte(app):
    with app.app_context():
        # Solo el 2-oct cargado: falta el 1-oct
        svc.sync_day(FakeAlegra({'2026-10-02': [invoice(2, RITA, 50_000, day='2026-10-02')]}), 'carreno', date(2026, 10, 2))
        report = [{'idLocal': '1', 'name': 'MONICA VARGAS', 'totalDocuments': 3, 'total': 300_000}]
        data = sg.SellerGoalsService('carreno', date(2026, 10, 3), FakeDirect(month_report=report), FakeAlegra({})) \
            .summary(date(2026, 10, 1))
        assert data['source'] == 'report'
        monica = next(r for r in data['sellers'] if r['id'] == '1')
        assert monica['sales'] == 300_000 and monica['units'] is None and monica['identified_pct'] is None


def test_mes_siguiente_sin_ventas(app):
    with app.app_context():
        data = sg.SellerGoalsService('carreno', date(2026, 10, 3), FakeDirect(), FakeAlegra({})).summary(date(2026, 11, 1))
        assert data['pace']['elapsed_days'] == 0 and data['store']['sales'] == 0
        assert data['store_auto_goal'] == 46_000_000


# ─── Endpoints ──────────────────────────────────────────────────────────────

def test_endpoints_metas(client, app, monkeypatch):
    direct = FakeDirect()
    for name in ('get_all_sales_totals_by_day', 'get_sales_by_seller', 'get_sellers'):
        monkeypatch.setattr(AlegraDirectClient, name, lambda self, *a, _n=name: getattr(direct, _n)(*a))
    monkeypatch.setattr(AlegraClient, 'get_invoices_by_date', lambda self, d: [])
    h = _headers(app)

    res = client.get('/api/analytics/seller-goals?month=2026-01', headers=h)
    assert res.status_code == 200, res.get_json()
    assert client.get('/api/analytics/seller-goals?month=2025-12', headers=h).status_code == 400
    assert client.get('/api/analytics/seller-goals?month=enero', headers=h).status_code == 400
    assert client.get('/api/analytics/seller-goals', headers=_headers(app, 'sales')).status_code == 403

    ok = client.put('/api/analytics/seller-goals', json={'month': '2026-01', 'seller_id': '12', 'amount': 5_000_000}, headers=h)
    assert ok.status_code == 200
    data = client.get('/api/analytics/seller-goals?month=2026-01', headers=h).get_json()['data']
    assert next(r for r in data['sellers'] if r['id'] == '12')['goal'] == 5_000_000
    assert client.put('/api/analytics/seller-goals', json={'month': '2026-01', 'seller_id': '12', 'amount': 0}, headers=h).status_code == 400
    assert client.put('/api/analytics/seller-goals', json={'seller_id': '12', 'amount': 1}, headers=h).status_code == 400
    assert client.put('/api/analytics/seller-goals', json={'month': '2026-01', 'seller_id': '12', 'amount': 1},
                      headers=_headers(app, 'sales')).status_code == 403
