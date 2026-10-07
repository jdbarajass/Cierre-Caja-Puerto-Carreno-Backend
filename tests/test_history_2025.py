"""
Tests de la reconstrucción de 2025 (docs/PLAN_RECONSTRUCCION_2025.md): carga
de 2025 con las prendas de las anuladas, clasificación anulación masiva vs.
anulación real, marca manual, venta real (Metas y comparación con el año
anterior) e informe de inventario (pantalla y Excel).

Facturas con el formato REAL de /api/v1/invoices (copiado de Carreño: POS
8420 anulada, KPC1462 electrónica). Base SQLite temporal, sin red.
"""
import io
from datetime import date

import pytest

from app.config import TestingConfig


@pytest.fixture
def app(tmp_path):
    class HistoryTestConfig(TestingConfig):
        SQLALCHEMY_DATABASE_URI = f"sqlite:///{(tmp_path / 'history.db').as_posix()}"
        SQLALCHEMY_ENGINE_OPTIONS = {}

    from app import create_app
    return create_app(HistoryTestConfig)


@pytest.fixture
def h(app):
    from app.services.jwt_service import JWTService
    with app.app_context():
        token = JWTService.generate_token(1, 'admin1@test.com', 'admin', None)
    return lambda store=None: {
        'Authorization': f'Bearer {token}', **({'X-Store': store} if store else {})
    }


def inv(id_, day, time, items, status='void', electronic=False, total_paid=0, number=None):
    total = sum(p * q for _, _, p, q in items)
    return {
        'id': str(id_), 'date': day, 'datetime': f'{day} {time}', 'status': status,
        'subtotal': total, 'discount': 0, 'tax': 0, 'total': total, 'totalPaid': total_paid, 'balance': 0,
        'numberTemplate': {'id': '16' if electronic else '1', 'prefix': 'KPC' if electronic else None,
                           'number': str(number or id_), 'fullNumber': f"{'KPC' if electronic else ''}{number or id_}",
                           'isElectronic': electronic},
        'client': {'id': '1', 'name': 'Consumidor final', 'identification': '222222222222'},
        'seller': {'id': '1', 'name': 'MONICA VARGAS'},
        'items': [{'id': iid, 'name': name, 'price': p, 'discount': 0, 'quantity': q, 'total': p * q}
                  for iid, name, p, q in items],
    }


JEAN = ('1183', 'JEAN HOMBRE 109900 / 105110990034', 109900, 1)
SHORT = ('1928', 'SHORT 99900 / 10419990016', 99900, 1)
MEDIAS = ('829', 'MEDIAS 7900 / 10487900', 7900, 2)
BOLSA = ('2165', 'BOLSA PAPEL', 300, 1)

BY_DAY = {
    '2025-01-10': [
        inv(8420, '2025-01-10', '20:10:45', [SHORT, MEDIAS, BOLSA]),                     # anulación masiva
        inv(8421, '2025-01-10', '20:12:46', [JEAN]),                                     # anulada en el momento...
        inv(8423, '2025-01-10', '20:20:00', [JEAN]),                                     # ...re-facturada 8 min después (también masiva)
        inv(1462, '2025-01-10', '20:11:10', [JEAN], status='closed', electronic=True, total_paid=109900),
    ],
    '2025-01-11': [
        inv(1500, '2025-01-11', '10:00:00', [SHORT], electronic=True),                   # electrónica anulada: real
        inv(8430, '2025-01-11', '11:00:00', [JEAN, MEDIAS]),                             # masiva
    ],
}


class FakeAlegra:
    def __init__(self, by_day=BY_DAY, items=None):
        self.by_day = by_day
        self.items = items or []

    def get_invoices_by_date(self, day):
        return self.by_day.get(day, [])

    def get_active_items(self):
        return self.items


ITEMS = [
    {'id': '1183', 'name': 'JEAN HOMBRE 109900', 'inventory': {'availableQuantity': 10, 'unitCost': 50000}},
    {'id': '1928', 'name': 'SHORT 99900', 'inventory': {'availableQuantity': 0, 'unitCost': 40000}},
    {'id': '829', 'name': 'MEDIAS 7900', 'inventory': {'availableQuantity': 30, 'unitCost': 3000}},
    {'id': '2165', 'name': 'BOLSA PAPEL', 'inventory': {'availableQuantity': 500, 'unitCost': 100}},
    {'id': '999', 'name': 'OTRA PRENDA', 'inventory': {'availableQuantity': 5, 'unitCost': 20000}},
]


@pytest.fixture
def loaded(app, client, h, monkeypatch):
    import app.routes.history_2025 as routes
    fake = FakeAlegra(items=ITEMS)
    monkeypatch.setattr(routes, 'get_alegra_client', lambda store=None: fake)
    resp = client.post('/api/history-2025/sync', headers=h(), json={'max_days': 31})
    assert resp.status_code == 200, resp.get_json()
    assert resp.get_json()['coverage']['loaded_days'] == 31
    return fake


def test_carga_guarda_prendas_de_anuladas_sin_tocar_prendas_vendidas(app, loaded):
    from app.models.invoice_fact import InvoiceFact, InvoiceItemFact, InvoiceVoidItem
    with app.app_context():
        f = InvoiceFact.query.filter_by(alegra_id='8420').one()
        assert f.voided and f.is_electronic is False and f.total_paid == 0 and f.issued_at == '2025-01-10 20:10:45'
        assert InvoiceVoidItem.query.filter_by(invoice_alegra_id='8420').count() == 3
        # las prendas vendidas (Prendas, Llegadas) siguen solo con las vigentes
        assert {r.invoice_alegra_id for r in InvoiceItemFact.query.all()} == {'1462'}


def test_clasificacion_y_venta_real(app, client, h, loaded):
    s = client.get('/api/history-2025/status', headers=h()).get_json()['summary']
    real = {r['number']: r for r in s['real_voids']}
    assert set(real) == {'KPC1500'}
    assert real['KPC1500']['reason'] == 'Factura electrónica anulada'
    # 8421 tiene otra factura igual 7 min después: cuenta como venta, pero queda para revisar
    assert [r['number'] for r in s['review']] == ['8421']
    assert 'lo mismo 7 min después' in s['review'][0]['reason']
    assert s['masiva_count'] == 4                              # 8420, 8421, 8423, 8430
    venta_8420 = 99900 + 7900 * 2 + 300
    assert s['real_sales_total'] == 109900 + venta_8420 + 109900 + 109900 + (109900 + 15800)

    from app.services.history_2025 import real_sales_total
    with app.app_context():
        assert real_sales_total('carreno', date(2025, 1, 10), date(2025, 1, 10)) == 109900 + venta_8420 + 109900 + 109900
        assert real_sales_total('carreno', date(2025, 2, 1), date(2025, 2, 28)) is None   # febrero no está cargado
        assert real_sales_total('carreno', date(2026, 1, 1), date(2026, 1, 31)) is None   # solo 2025


def test_marca_manual(app, client, h, loaded):
    resp = client.put('/api/history-2025/override', headers=h(), json={'number': '8421', 'counts_as_sale': False, 'note': 'devolución'})
    assert resp.status_code == 200
    s = client.get('/api/history-2025/status', headers=h()).get_json()['summary']
    assert s['masiva_count'] == 3 and [r['number'] for r in s['real_voids']] == ['8421', 'KPC1500']
    assert s['review'] == [] and s['real_voids'][0]['manual'] is True
    client.put('/api/history-2025/override', headers=h(), json={'number': '8421', 'counts_as_sale': None})
    assert client.get('/api/history-2025/status', headers=h()).get_json()['summary']['masiva_count'] == 4
    assert client.put('/api/history-2025/override', headers=h(), json={'number': '1462', 'counts_as_sale': True}).status_code == 404


def test_informe_de_inventario_y_excel(app, client, h, loaded):
    data = client.get('/api/history-2025/inventory', headers=h()).get_json()
    rows = {r['item_id']: r for r in data['rows']}
    # masivas: 8420 (short, 2 medias, bolsa), 8421 y 8423 (jean), 8430 (jean, 2 medias)
    assert rows['1183']['units_returned'] == 3 and rows['1183']['stock_before'] == 7 and rows['1183']['units_to_remove'] == 3
    assert rows['829']['units_returned'] == 4 and rows['829']['stock_before'] == 26
    assert rows['1928']['units_returned'] == 1 and rows['1928']['units_to_remove'] == 0
    assert rows['1928']['flag'].startswith('Da negativo')
    assert rows['2165']['is_bag'] is True
    assert '999' not in rows
    assert data['value_now'] == 10 * 50000 + 30 * 3000 + 500 * 100 + 5 * 20000
    assert data['value_to_remove'] == 3 * 50000 + 4 * 3000 + 1 * 100
    assert data['value_before'] == data['value_now'] - data['value_to_remove']

    resp = client.get('/api/history-2025/inventory.xlsx', headers=h())
    assert resp.status_code == 200
    from openpyxl import load_workbook
    ws = load_workbook(io.BytesIO(resp.data)).active
    assert ws['A1'].value.startswith('KOAJ Puerto Carreño')
    assert any(row[0] == '1183' for row in ws.iter_rows(values_only=True))


def test_metas_y_comparacion_usan_la_venta_real(app, loaded):
    from app.routes.cash_closing import _real_previous_year
    with app.test_request_context('/'):
        month, daily = _real_previous_year(
            1000, {'current': {'total': 500000}, 'previous_year': {'total': 1}, 'comparison': {}},
            date(2025, 1, 1), date(2025, 1, 10))
    expected_day = 109900 + (99900 + 15800 + 300) + 109900 + 109900
    assert month == expected_day                       # 1 al 10 de enero: solo el 10 tiene ventas
    assert daily['previous_year']['total'] == expected_day
    assert daily['comparison']['difference'] == 500000 - expected_day

    # mes no cargado: se queda con lo de Alegra
    with app.test_request_context('/'):
        month, daily = _real_previous_year(1000, {'previous_year': {'total': 1}}, date(2025, 3, 1), date(2025, 3, 5))
    assert month == 1000 and daily['previous_year']['total'] == 1


def test_permisos(app, client):
    from app.services.jwt_service import JWTService
    with app.app_context():
        sales = JWTService.generate_token(2, 'v@test.com', 'sales', None)
    assert client.get('/api/history-2025/status', headers={'Authorization': f'Bearer {sales}'}).status_code == 403


# ─── R3: ajuste de inventario en Alegra ─────────────────────────────────────

class FakeAlegraWrite(FakeAlegra):
    def __init__(self, *a, fail_on=None, **kw):
        super().__init__(*a, **kw)
        self.created = []
        self.fail_on = fail_on or set()

    def create_inventory_adjustment(self, payload):
        n = len(self.created) + 1
        if n in self.fail_on:
            self.fail_on.discard(n)
            raise RuntimeError('Alegra caído')
        self.created.append(payload)
        return {'id': f'adj-{n}', 'number': 1715 + n}


def _complete_2025(app):
    """Marca todos los días de 2025 como cargados (sin facturas extra)."""
    from datetime import timedelta
    from app.models.user import db
    from app.models.invoice_fact import InvoiceSyncDay
    with app.app_context():
        loaded = {r.date for r in InvoiceSyncDay.query.all()}
        d = date(2025, 1, 1)
        while d <= date(2025, 12, 31):
            if d not in loaded:
                db.session.add(InvoiceSyncDay(store_code='carreno', date=d, invoice_count=0, items_synced=True))
            d += timedelta(days=1)
        db.session.commit()


OK = {'confirm': 'AJUSTAR', 'accountant_ok': True}


def test_ajuste_pide_confirmacion_y_2025_completo(app, client, h, loaded, monkeypatch):
    import app.routes.history_2025 as routes
    fake = FakeAlegraWrite(items=ITEMS)
    monkeypatch.setattr(routes, 'get_alegra_client', lambda store=None: fake)
    url = '/api/history-2025/inventory-adjustment'
    assert client.post(url, headers=h(), json={'confirm': 'ajustar'}).status_code == 400          # sin aprobación del contador
    resp = client.post(url, headers=h(), json={**OK, 'expected_units': 7})
    assert resp.status_code == 409 and 'todo 2025' in resp.get_json()['message']
    assert fake.created == []


def test_ajuste_se_crea_una_sola_vez_con_el_formato_de_alegra(app, client, h, loaded, monkeypatch):
    import app.routes.history_2025 as routes
    fake = FakeAlegraWrite(items=ITEMS)
    monkeypatch.setattr(routes, 'get_alegra_client', lambda store=None: fake)
    _complete_2025(app)
    url = '/api/history-2025/inventory-adjustment'

    # jean 3 + medias 4 + bolsa 1 = 8 (el short no tiene existencia)
    resp = client.post(url, headers=h(), json={**OK, 'expected_units': 7})
    assert resp.status_code == 409 and 'cambió' in resp.get_json()['message']

    resp = client.post(url, headers=h(), json={**OK, 'expected_units': 8})
    assert resp.status_code == 200, resp.get_json()
    assert len(fake.created) == 1
    payload = fake.created[0]
    assert payload['warehouse'] == {'id': '1'} and payload['date']
    assert 'anulación masiva' in payload['observations']
    assert sorted((i['id'], i['type'], i['quantity'], i['unitCost']) for i in payload['items']) == [
        ('1183', 'out', 3, 50000), ('2165', 'out', 1, 100), ('829', 'out', 4, 3000)]
    adj = resp.get_json()['adjustment']
    assert adj['completed'] is True and adj['units'] == 8 and adj['done'][0]['number'] == 1716

    # no se repite
    again = client.post(url, headers=h(), json={**OK, 'expected_units': 8})
    assert again.status_code == 409 and 'ya se creó' in again.get_json()['message']
    assert len(fake.created) == 1
    status = client.get('/api/history-2025/status', headers=h()).get_json()
    assert status['adjustment']['completed'] is True and 'chunks' not in status['adjustment']


def test_ajuste_por_partes_retoma_sin_duplicar(app, client, h, loaded, monkeypatch):
    import app.routes.history_2025 as routes
    import app.services.history_2025 as svc
    monkeypatch.setattr(svc, 'ADJUSTMENT_CHUNK', 1)
    fake = FakeAlegraWrite(items=ITEMS, fail_on={2})
    monkeypatch.setattr(routes, 'get_alegra_client', lambda store=None: fake)
    _complete_2025(app)
    url = '/api/history-2025/inventory-adjustment'

    resp = client.post(url, headers=h(), json={**OK, 'expected_units': 8})
    assert resp.status_code == 409 and 'parte 2 de 3' in resp.get_json()['message']
    assert len(fake.created) == 1 and resp.get_json()['adjustment']['completed'] is False

    # La existencia en Alegra ya bajó por la parte 1; el reintento usa el plan guardado
    fake.items = [dict(i, inventory={**i['inventory'], 'availableQuantity': 0}) for i in ITEMS]
    resp = client.post(url, headers=h(), json={**OK})
    assert resp.status_code == 200
    assert len(fake.created) == 3
    assert sum(i['quantity'] for p in fake.created for i in p['items']) == 8
    assert [d['part'] for d in resp.get_json()['adjustment']['done']] == [1, 2, 3]


def test_resumen_rapido_del_dashboard_usa_la_venta_real(app, client, h, loaded, monkeypatch):
    """La comparación con el año anterior y la meta del Dashboard (quick-summary) usan la venta real de 2025."""
    import app.routes.direct_api as direct_routes

    class Direct:
        def get_all_sales_totals_by_day(self, start, end):
            return {'success': True, 'data': [{'date': start, 'total': 109900}]}   # lo que Alegra muestra hoy
    monkeypatch.setattr(direct_routes, 'get_alegra_direct_client', lambda *a, **k: Direct())
    real_day = 109900 + (99900 + 15800 + 300) + 109900 + 109900
    data = client.get('/api/sales/quick-summary?from=2025-01-10&to=2025-01-10', headers=h()).get_json()
    assert data['total_sales'] == real_day
    # fuera de 2025 o sin cargar: queda lo de Alegra
    assert client.get('/api/sales/quick-summary?from=2025-03-01&to=2025-03-05', headers=h()).get_json()['total_sales'] == 109900
