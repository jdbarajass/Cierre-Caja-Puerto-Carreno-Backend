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
    assert set(real) == {'8421', 'KPC1500'}
    assert 'Se volvió a facturar 7 min después' in real['8421']['reason']
    assert real['KPC1500']['reason'] == 'Factura electrónica anulada'
    assert s['masiva_count'] == 3                              # 8420, 8423, 8430
    venta_8420 = 99900 + 7900 * 2 + 300
    assert s['real_sales_total'] == 109900 + venta_8420 + 109900 + (109900 + 15800)

    from app.services.history_2025 import real_sales_total
    with app.app_context():
        assert real_sales_total('carreno', date(2025, 1, 10), date(2025, 1, 10)) == 109900 + venta_8420 + 109900
        assert real_sales_total('carreno', date(2025, 2, 1), date(2025, 2, 28)) is None   # febrero no está cargado
        assert real_sales_total('carreno', date(2026, 1, 1), date(2026, 1, 31)) is None   # solo 2025


def test_marca_manual(app, client, h, loaded):
    resp = client.put('/api/history-2025/override', headers=h(), json={'number': '8421', 'counts_as_sale': True, 'note': 'era venta'})
    assert resp.status_code == 200
    s = client.get('/api/history-2025/status', headers=h()).get_json()['summary']
    assert s['masiva_count'] == 4 and [r['number'] for r in s['real_voids']] == ['KPC1500']
    client.put('/api/history-2025/override', headers=h(), json={'number': '8421', 'counts_as_sale': None})
    assert client.get('/api/history-2025/status', headers=h()).get_json()['summary']['masiva_count'] == 3
    assert client.put('/api/history-2025/override', headers=h(), json={'number': '1462', 'counts_as_sale': True}).status_code == 404


def test_informe_de_inventario_y_excel(app, client, h, loaded):
    data = client.get('/api/history-2025/inventory', headers=h()).get_json()
    rows = {r['item_id']: r for r in data['rows']}
    # masivas: 8420 (short, 2 medias, bolsa), 8423 (jean), 8430 (jean, 2 medias)
    assert rows['1183']['units_returned'] == 2 and rows['1183']['stock_before'] == 8 and rows['1183']['units_to_remove'] == 2
    assert rows['829']['units_returned'] == 4 and rows['829']['stock_before'] == 26
    assert rows['1928']['units_returned'] == 1 and rows['1928']['units_to_remove'] == 0
    assert rows['1928']['flag'].startswith('Da negativo')
    assert rows['2165']['is_bag'] is True
    assert '999' not in rows
    assert data['value_now'] == 10 * 50000 + 30 * 3000 + 500 * 100 + 5 * 20000
    assert data['value_to_remove'] == 2 * 50000 + 4 * 3000 + 1 * 100
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
    expected_day = 109900 + (99900 + 15800 + 300) + 109900
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
