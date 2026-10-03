"""
Revisión de Estadísticas del 2026-10-03 (docs/PLAN_ESTADISTICAS.md, "Revisión 3-oct").

- Totales rápidos (/api/sales/quick-summary): se piden TODAS las páginas por
  día de /invoices/sales-totals (antes una sola con limit=100).
- Facturas de un día (AlegraClient.get_invoices_by_date): una factura repetida
  entre páginas cuenta una vez, y un día pasado incompleto no queda en caché.
"""
from datetime import date, timedelta

import pytest

from app.services import alegra_client as alegra_client_module
from app.services.alegra_client import AlegraClient
from app.services.alegra_direct_client import AlegraDirectClient
from tests.test_estadisticas_fase_a import FakeResponse
from tests.test_estadisticas_fase_c import app  # noqa: F401 (base de datos temporal propia)


# ─── Totales rápidos por día ────────────────────────────────────────────────

def _days(start: date, n: int):
    return [{'date': (start + timedelta(days=i)).isoformat(), 'total': 1_000 * (i + 1)} for i in range(n)]


def _sales_totals_api(rows, cap):
    """Simula /invoices/sales-totals: orden descendente y como máximo `cap` filas por página."""
    ordered = sorted(rows, key=lambda r: r['date'], reverse=True)
    calls = []

    def fake_request(self, endpoint, params=None):
        assert endpoint == '/invoices/sales-totals'
        calls.append(dict(params))
        start = params['start']
        return ordered[start:start + min(params['limit'], cap)]
    return fake_request, calls


@pytest.mark.parametrize('cap', [30, 100])
def test_totales_de_un_mes_de_31_dias_no_pierden_el_dia_1(monkeypatch, cap):
    rows = _days(date(2026, 8, 1), 31)
    fake, _ = _sales_totals_api(rows, cap)
    monkeypatch.setattr(AlegraDirectClient, '_make_request', fake)
    result = AlegraDirectClient('u', 't').get_all_sales_totals_by_day('2026-08-01', '2026-08-31')
    assert result['success']
    assert sum(r['total'] for r in result['data']) == sum(r['total'] for r in rows)
    assert '2026-08-01' in {r['date'] for r in result['data']}


def test_totales_de_mas_de_100_dias_suman_todo(monkeypatch):
    rows = _days(date(2026, 1, 1), 180)  # antes: limit=100 → faltaban 80 días
    fake, calls = _sales_totals_api(rows, 30)
    monkeypatch.setattr(AlegraDirectClient, '_make_request', fake)
    result = AlegraDirectClient('u', 't').get_all_sales_totals_by_day('2026-01-01', '2026-06-29')
    assert len(result['data']) == 180
    assert len(calls) == 6


def test_totales_no_duplican_si_alegra_ignora_start(monkeypatch):
    rows = _days(date(2026, 8, 1), 31)
    monkeypatch.setattr(AlegraDirectClient, '_make_request', lambda self, e, params=None: rows[:30])
    result = AlegraDirectClient('u', 't').get_all_sales_totals_by_day('2026-08-01', '2026-08-31')
    assert len(result['data']) == 30  # una vez cada día, sin quedarse en ciclo


def test_totales_si_alegra_falla_devuelve_error(monkeypatch):
    def boom(self, endpoint, params=None):
        raise RuntimeError('caído')
    monkeypatch.setattr(AlegraDirectClient, '_make_request', boom)
    result = AlegraDirectClient('u', 't').get_all_sales_totals_by_day('2026-08-01', '2026-08-31')
    assert result['success'] is False


# ─── Facturas de un día ─────────────────────────────────────────────────────

@pytest.fixture
def alegra():
    alegra_client_module._invoices_cache.clear()
    yield AlegraClient('carreno@test.com', 'tok', 'https://api.alegra.com/api/v1')
    alegra_client_module._invoices_cache.clear()


def _inv(i):
    return {'id': str(i), 'total': 10_000, 'status': 'closed'}


def test_factura_repetida_entre_paginas_cuenta_una_vez(alegra, monkeypatch):
    # Día en curso con 31 facturas; entra una venta entre la página 1 y la 2
    # (orden descendente): la factura 30 llega otra vez al inicio de la página 2.
    monkeypatch.setattr(alegra_client_module, 'get_colombia_today_string', lambda: '2026-10-03')
    page1 = {'metadata': {'total': 31}, 'data': [_inv(i) for i in range(31, 1, -1)]}
    page2 = [_inv(2), _inv(1)]
    responses = iter([FakeResponse(page1), FakeResponse(page2)])
    monkeypatch.setattr(alegra.session, 'get', lambda url, params=None, timeout=None: next(responses))
    invoices = alegra.get_invoices_by_date('2026-10-03')
    assert sorted(int(i['id']) for i in invoices) == list(range(1, 32))


def test_dia_pasado_incompleto_no_queda_en_cache(alegra, monkeypatch):
    monkeypatch.setattr(alegra_client_module, 'get_colombia_today_string', lambda: '2026-10-03')
    calls = []

    def fake_get(url, params=None, timeout=None):
        calls.append(params)
        return FakeResponse({'metadata': {'total': 5}, 'data': [_inv(1), _inv(2)]})
    monkeypatch.setattr(alegra.session, 'get', fake_get)
    alegra.get_invoices_by_date('2026-09-30')
    alegra.get_invoices_by_date('2026-09-30')
    assert len(calls) == 2  # la segunda vez vuelve a pedirlo


def test_dia_pasado_completo_si_queda_en_cache(alegra, monkeypatch):
    monkeypatch.setattr(alegra_client_module, 'get_colombia_today_string', lambda: '2026-10-03')
    calls = []

    def fake_get(url, params=None, timeout=None):
        calls.append(params)
        return FakeResponse({'metadata': {'total': 2}, 'data': [_inv(1), _inv(2)]})
    monkeypatch.setattr(alegra.session, 'get', fake_get)
    alegra.get_invoices_by_date('2026-09-30')
    alegra.get_invoices_by_date('2026-09-30')
    assert len(calls) == 1


# ─── Ajustes pedidos por el usuario (2026-10-03) ───────────────────────────

def test_stock_de_una_tienda_no_espera_a_la_otra():
    lock_a = alegra_client_module._items_lock_for('carreno@x|active_items')
    lock_b = alegra_client_module._items_lock_for('primavera@x|active_items')
    assert lock_a is not lock_b
    assert lock_a is alegra_client_module._items_lock_for('carreno@x|active_items')
    with lock_a:  # Carreño descargando: Primavera puede entrar
        assert lock_b.acquire(blocking=False)
        lock_b.release()


MEDIAS_STOCK = [{'id': '1', 'name': 'MEDIAS 7900 / 10487900', 'type': 'variant', 'inventory': {'availableQuantity': 50}}]


def test_rotacion_no_cuenta_hoy_como_dia_completo(app):
    from app.services import garment_insights as gi
    from app.services import invoice_facts as svc
    from tests.test_estadisticas_fase_c import SEP_30, FakeAlegra
    with app.app_context():
        svc.sync_day(FakeAlegra({'2026-09-30': SEP_30}), 'carreno', date(2026, 9, 30))  # 5 medias
        # Hoy (a medias) ya lleva 10 medias: antes la venta diaria salía (5 + 10) / 2 = 7,5
        service = gi.GarmentInsightsService('carreno', date(2026, 10, 1), FakeAlegra({'2026-10-01': SEP_30 + SEP_30}))
        service.client.get_active_items = lambda: MEDIAS_STOCK
        data = service.stock_analysis(date(2026, 9, 30), date(2026, 10, 1))
        medias = next(r for r in data['rotation'] if r['product'] == 'MEDIAS')
        assert medias['daily_units'] == 5 and medias['days_of_inventory'] == 10
        # Las ventas de hoy sí cuentan en agotados y curva de tallas
        assert data['size_curve'] is not None


def test_rotacion_de_solo_hoy_usa_hoy(app):
    from app.services import garment_insights as gi
    from tests.test_estadisticas_fase_c import SEP_30, FakeAlegra
    with app.app_context():
        service = gi.GarmentInsightsService('carreno', date(2026, 10, 1), FakeAlegra({'2026-10-01': SEP_30}))
        service.client.get_active_items = lambda: MEDIAS_STOCK
        data = service.stock_analysis(date(2026, 10, 1), date(2026, 10, 1))
        medias = next(r for r in data['rotation'] if r['product'] == 'MEDIAS')
        assert medias['daily_units'] == 5
