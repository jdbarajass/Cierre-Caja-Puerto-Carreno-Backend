"""
Fase D2 de Estadísticas (docs/PLAN_ESTADISTICAS.md): ventas por día de la
semana y hora. La hora sale de `datetime` de /api/v1/invoices
("2026-09-30 15:00:00", ver tests/test_estadisticas_fase_a.py).
"""
from datetime import date

from app.models.invoice_fact import InvoiceFact, InvoiceSyncDay
from app.models.user import db
from app.services import invoice_facts as svc
from app.services import sales_patterns as sp
from tests.test_estadisticas_fase_a import MONICA, RITA, invoice
from tests.test_estadisticas_fase_c import FakeAlegra, _headers, app  # noqa: F401

# 26-sep-2026 = sábado, 28-sep = lunes, 3-oct = sábado
SAT_1, MON, SAT_2 = date(2026, 9, 26), date(2026, 9, 28), date(2026, 10, 3)


def test_hora_de_la_factura():
    assert svc.invoice_hour({'datetime': '2026-09-30 15:42:10'}) == 15
    assert svc.invoice_hour({'datetime': '2026-09-30T09:05:00'}) == 9
    assert svc.invoice_hour({'datetime': None}) is None
    assert svc.invoice_hour({}) is None


def test_carga_guarda_la_hora_y_la_version(app):
    with app.app_context():
        svc.sync_day(FakeAlegra({'2026-09-30': [invoice(1, MONICA, 50000, hour='18:20:00')]}), 'carreno', date(2026, 9, 30))
        assert InvoiceFact.query.filter_by(store_code='carreno').one().hour == 18
        assert InvoiceSyncDay.query.filter_by(store_code='carreno').one().fact_version == svc.FACT_VERSION


def test_dias_viejos_sin_hora_se_vuelven_a_cargar_sin_afectar_a_clientes(app):
    with app.app_context():
        old = date(2026, 9, 29)
        # Día cargado antes de la Fase D2: con prendas, sin versión
        db.session.add(InvoiceSyncDay(store_code='carreno', date=old, invoice_count=0, items_synced=True))
        db.session.commit()
        assert svc.missing_days('carreno', old, old) == []        # Clientes: completo
        assert svc.missing_item_days('carreno', old, old) == []   # Prendas: completo
        assert svc.pending_days('carreno', old, old) == [old]     # pero se recarga para la hora
        status = svc.coverage_status('carreno', old, old)
        assert status['hours'] == {'loaded_days': 0, 'missing_days': 1, 'next_missing_day': '2026-09-29'}


def test_promedio_por_dia_de_la_semana():
    facts = [
        {'date': SAT_1, 'hour': 10, 'total': 100_000}, {'date': SAT_1, 'hour': 17, 'total': 300_000},
        {'date': SAT_2, 'hour': 17, 'total': 200_000},
        {'date': MON, 'hour': 10, 'total': 50_000},
    ]
    data = sp.build_patterns(facts, [SAT_1, MON, SAT_2])
    sat = data['weekdays'][5]
    assert sat['days'] == 2 and sat['sales'] == 600_000 and sat['avg_sales_per_day'] == 300_000
    assert data['weekdays'][0]['avg_sales_per_day'] == 50_000
    assert [h['hour'] for h in data['hours']] == list(range(10, 18))  # horas seguidas, aunque no haya ventas
    sat_17 = next(c for c in data['heatmap'][5]['cells'] if c['hour'] == 17)
    assert sat_17 == {'hour': 17, 'avg_sales': 250_000, 'avg_invoices': 1.0}
    assert data['hours'][-1]['share_pct'] == round(500_000 * 100 / 650_000, 1)


def test_servicio_sin_hoy_y_sin_dias_viejos(app):
    with app.app_context():
        svc.sync_day(FakeAlegra({'2026-09-28': [invoice(1, MONICA, 50_000, day='2026-09-28', hour='10:00:00'),
                                                invoice(2, RITA, 70_000, day='2026-09-28', hour='16:00:00')]}),
                     'carreno', MON)
        # Día viejo (sin hora): no entra en los promedios
        db.session.add(InvoiceSyncDay(store_code='carreno', date=date(2026, 9, 29), invoice_count=1, items_synced=True))
        db.session.add(InvoiceFact(store_code='carreno', alegra_id='99', date=date(2026, 9, 29), total=999_999))
        db.session.commit()
        today = date(2026, 9, 30)
        live = FakeAlegra({'2026-09-30': [invoice(3, MONICA, 1_000_000, day='2026-09-30', hour='11:00:00')]})
        data = sp.SalesPatternsService('carreno', today, live).summary(MON, today)
        assert data['total_sales'] == 120_000  # ni el día viejo ni hoy (va a medias)
        assert data['coverage']['missing_days'] == 1 and data['coverage']['loaded_days'] == 1
        assert [s['name'] for s in data['sellers']] == ['RITA INFANTE', 'MONICA VARGAS']

        solo_monica = sp.SalesPatternsService('carreno', today, live).summary(MON, today, seller_id='1')
        assert solo_monica['total_sales'] == 50_000

        # Periodo de solo hoy: se usa hoy en vivo
        assert sp.SalesPatternsService('carreno', today, live).summary(today, today)['total_sales'] == 1_000_000


def test_endpoint_dia_y_hora(client, app):
    with app.app_context():
        svc.sync_day(FakeAlegra({'2026-09-28': [invoice(1, MONICA, 50_000, day='2026-09-28', hour='10:00:00')]}),
                     'carreno', MON)
    res = client.get('/api/analytics/sales-patterns?start_date=2026-09-28&end_date=2026-09-28', headers=_headers(app))
    assert res.status_code == 200, res.get_json()
    assert res.get_json()['data']['weekdays'][0]['sales'] == 50_000
    assert client.get('/api/analytics/sales-patterns', headers=_headers(app, 'sales')).status_code == 403
