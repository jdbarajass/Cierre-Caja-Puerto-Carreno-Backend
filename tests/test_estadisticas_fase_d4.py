"""
Fase D4 de Estadísticas (docs/PLAN_ESTADISTICAS.md): alertas diarias en la
plataforma (día flojo, descuentos altos, más vendidos agotados, meta atrasada).
"""
from datetime import date, timedelta

from app.models.daily_alert import DailyAlert
from app.services import daily_alerts as da
from app.services import invoice_facts as svc
from app.services.alegra_client import AlegraClient
from app.services.alegra_direct_client import AlegraDirectClient
from tests.test_estadisticas_fase_a import MONICA, RITA, invoice
from tests.test_estadisticas_fase_c import FakeAlegra, _headers, app, inv, item  # noqa: F401

DAY = date(2026, 9, 26)  # sábado
CAMISETA = ('CAMISETA MUJER 49900 / 1052499002', '1087', 49900)
JEAN = ('JEAN MUJER 99900 / 10529990008', '2001', 99900)


def _load(day, invoices):
    svc.sync_day(FakeAlegra({day.isoformat(): invoices}), 'carreno', day)


def _saturdays(amount, weeks=8):
    for w in range(1, weeks + 1):
        d = DAY - timedelta(weeks=w)
        _load(d, [invoice(1000 + w, MONICA, amount, day=d.isoformat())])


def _no_goals():
    return {'store': {'goal': None}, 'pace': {'is_current': False}, 'sellers': []}


def test_dia_flojo(app):
    with app.app_context():
        _saturdays(1_000_000)
        _load(DAY, [invoice(1, MONICA, 400_000, day=DAY.isoformat())])
        alert = da.low_day('carreno', DAY)
        assert alert['severity'] == 'warning' and alert['data']['drop_pct'] == 60
        assert 'sábado' in alert['title']
        _load(DAY, [invoice(1, MONICA, 700_000, day=DAY.isoformat())])
        assert da.low_day('carreno', DAY) is None  # 70 % del promedio: normal


def test_dia_flojo_sin_historia_suficiente_no_avisa(app):
    with app.app_context():
        _saturdays(1_000_000, weeks=3)
        _load(DAY, [invoice(1, MONICA, 100_000, day=DAY.isoformat())])
        assert da.low_day('carreno', DAY) is None


def test_descuentos_altos(app):
    with app.app_context():
        half = inv(1, MONICA, [item(*JEAN, discount=50)], day=DAY.isoformat())
        small = inv(2, RITA, [item(*CAMISETA, discount=10)], day=DAY.isoformat())
        _load(DAY, [{**half, 'subtotal': 99900, 'discount': 49950, 'total': 49950},
                    {**small, 'subtotal': 49900, 'discount': 4990, 'total': 44910}])
        alert = da.high_discounts('carreno', DAY)
        assert alert['severity'] == 'info' and alert['data']['count'] == 1
        assert alert['data']['invoices'][0]['discount_pct'] == 50.0


def test_mas_vendidos_agotados_marca_los_nuevos(app):
    with app.app_context():
        _load(DAY, [inv(1, MONICA, [item(*CAMISETA, qty=3), item(*JEAN)], day=DAY.isoformat())])
        stock = [{'id': '1087', 'name': CAMISETA[0], 'type': 'variant', 'inventory': {'availableQuantity': 0}},
                 {'id': '2001', 'name': JEAN[0], 'type': 'variant', 'inventory': {'availableQuantity': 4}}]
        alert = da.best_sellers_out('carreno', DAY, lambda: stock)
        assert [i['item_id'] for i in alert['data']['items']] == ['1087'] and alert['data']['new'] == 1
        again = da.best_sellers_out('carreno', DAY, lambda: stock, previous=alert['data'])
        assert again['data']['new'] == 0


def test_meta_atrasada():
    goals = {'store': {'goal': 10_000_000, 'sales': 2_000_000, 'progress_pct': 20.0, 'needed_per_day': 400_000},
             'pace': {'is_current': True, 'expected_pct': 40.0},
             'sellers': [{'name': 'RITA', 'active': True, 'goal': 5_000_000, 'sales': 500_000, 'progress_pct': 10.0}]}
    alert = da.goal_pace(lambda: goals)
    assert alert['severity'] == 'warning' and alert['data']['sellers_behind'][0]['name'] == 'RITA'
    goals['store']['progress_pct'] = 35.0
    assert da.goal_pace(lambda: goals) is None  # 5 puntos: dentro de lo normal


def test_generar_guarda_respeta_descartadas_y_aguanta_fallos(app):
    with app.app_context():
        _saturdays(1_000_000)
        _load(DAY, [invoice(1, MONICA, 300_000, day=DAY.isoformat())])

        def broken_stock():
            raise RuntimeError('Alegra caído')
        result = da.generate('carreno', DAY, broken_stock, _no_goals)
        assert result['alerts'] == ['low_day'] and 'best_sellers_out' in result['errors']

        row = DailyAlert.query.filter_by(store_code='carreno', kind='low_day').one()
        row.dismissed_at = row.created_at
        da.generate('carreno', DAY, lambda: [], _no_goals)  # recalcular: sigue descartada
        assert DailyAlert.query.filter_by(store_code='carreno', kind='low_day').one().dismissed_at is not None
        assert da.active_alerts('carreno', DAY) == []

        # Si la condición desaparece al recalcular (ej. facturas que faltaban), la alerta se borra
        _load(DAY, [invoice(1, MONICA, 900_000, day=DAY.isoformat())])
        da.generate('carreno', DAY, lambda: [], _no_goals)
        assert DailyAlert.query.filter_by(store_code='carreno').count() == 0


def test_endpoints_alertas(client, app, monkeypatch):
    with app.app_context():
        _saturdays(1_000_000)
        _load(DAY, [invoice(1, MONICA, 300_000, day=DAY.isoformat())])
    monkeypatch.setattr(AlegraClient, 'get_active_items', lambda self: [])
    monkeypatch.setattr(AlegraClient, 'get_invoices_by_date', lambda self, d: [])
    monkeypatch.setattr(AlegraDirectClient, 'get_all_sales_totals_by_day',
                        lambda self, a, b: {'success': True, 'data': []})
    monkeypatch.setattr(AlegraDirectClient, 'get_sales_by_seller', lambda self, a, b: [])
    monkeypatch.setattr(AlegraDirectClient, 'get_sellers', lambda self: [])
    h = _headers(app)

    res = client.post('/api/analytics/alerts/generate', json={'date': DAY.isoformat()}, headers=h)
    assert res.status_code == 200, res.get_json()
    assert res.get_json()['result']['alerts'] == ['low_day']
    assert client.post('/api/analytics/alerts/generate', json={'date': '2099-01-01'}, headers=h).status_code == 400

    monkeypatch.setattr('app.routes.daily_alerts.get_colombia_now', lambda: __import__('datetime').datetime(2026, 9, 27, 9, 0))
    alerts = client.get('/api/analytics/alerts', headers=h).get_json()['data']
    assert [a['kind'] for a in alerts] == ['low_day']

    assert client.post(f"/api/analytics/alerts/{alerts[0]['id']}/dismiss", headers=_headers(app, 'sales')).status_code == 403
    assert client.post(f"/api/analytics/alerts/{alerts[0]['id']}/dismiss", headers=h).status_code == 200
    assert client.get('/api/analytics/alerts', headers=h).get_json()['data'] == []
    assert client.post('/api/analytics/alerts/99999/dismiss', headers=h).status_code == 404
