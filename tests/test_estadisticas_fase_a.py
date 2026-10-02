"""
Fase A de Estadísticas (docs/PLAN_ESTADISTICAS.md): errores que cambiaban números.

Las facturas simuladas copian el formato REAL de /api/v1/invoices (leído con el
conector de Alegra el 2026-10-02): `seller` es objeto, las anuladas traen
status "void", `items[].discount` es PORCENTAJE y `items[].total` ya trae el
descuento. Las cifras de referencia son las de Alegra para el 30-sep-2026
(Ventas por vendedora: Rita $568.200 / 9 facturas, Mónica $323.745 / 5).
"""
from datetime import date, timedelta

import pytest
import requests

from app.config import TestingConfig
from app.services import alegra_client as alegra_client_module
from app.services import alegra_direct_client as direct_module
from app.services.alegra_client import AlegraClient
from app.services.alegra_direct_client import AlegraDirectClient
from app.services.inventory_analytics import InventoryAnalytics
from app.services.product_analytics import ProductAnalytics
from app.services.sales_analytics import SalesAnalytics

MONICA = {'id': '1', 'name': 'MONICA VARGAS', 'identification': '1192762720', 'observations': None}
RITA = {'id': '12', 'name': 'RITA INFANTE', 'identification': '17105692', 'observations': None}
CF = {'id': '1', 'name': 'Consumidor final', 'identification': '222222222222'}


def invoice(id_, seller, total, client=CF, status='closed', items=None, day='2026-09-30', hour='15:00:00'):
    items = items or [{'name': 'PRENDA', 'price': total, 'discount': 0, 'quantity': 1, 'id': '1', 'tax': [], 'total': total}]
    subtotal = sum(i['price'] * i['quantity'] for i in items)
    return {
        'id': str(id_), 'date': day, 'datetime': f'{day} {hour}', 'status': status,
        'subtotal': subtotal, 'discount': subtotal - total, 'tax': 0, 'total': total,
        'totalPaid': total if status != 'void' else 0, 'balance': 0,
        'paymentMethod': 'CASH', 'seller': seller, 'client': client,
        'numberTemplate': {'prefix': 'KPC', 'number': str(id_), 'fullNumber': f'KPC{id_}'},
        'items': items, 'payments': [{'amount': total, 'paymentMethod': 'cash', 'status': 'open'}],
    }


YESSICA = {'id': '5', 'name': 'yessica lopez', 'identification': '1121846391'}
# Las 14 facturas del 30-sep-2026 (montos, vendedora y la del descuento del 45 %)
SEP_30 = [
    invoice(12945, MONICA, 49900, client={'id': '735', 'name': 'INGRIT TATIANA BAQUERO CARRILLO', 'identification': '1121884855'}),
    invoice(12944, RITA, 10000), invoice(12943, RITA, 10000), invoice(12942, RITA, 39900),
    invoice(12941, MONICA, 80200, client={'id': '555', 'name': 'ALBA LUCIA MALDONADO SOLANO', 'identification': '21249017'}),
    invoice(12940, RITA, 110100), invoice(12939, MONICA, 70200), invoice(12938, RITA, 49900),
    invoice(12937, RITA, 74100), invoice(12936, RITA, 110200), invoice(12935, RITA, 73900),
    invoice(12934, RITA, 90100),
    invoice(12933, MONICA, 96000, client={'id': '1759', 'name': 'SEBASTIAN LOPEZ RODRIGUEZ', 'identification': '1007310399'}),
    invoice(12932, MONICA, 27445, client=YESSICA, items=[{
        'name': 'CAMISETA HOMBRE 49900 / 1051499002', 'price': 49900, 'discount': 45,
        'quantity': 1, 'id': '1044', 'tax': [], 'total': 27445}]),
]
ALEGRA_SEP_30_TOTAL = 568_200 + 323_745


# ─── 1. Inventario: lista completa de ítems ──────────────────────────────────

class FakeResponse:
    def __init__(self, payload, status_code=200):
        self._payload = payload
        self.status_code = status_code

    def json(self):
        return self._payload

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.exceptions.HTTPError(response=self)


def variant(i, qty=2, cost=10_000, price=49_900, name=None):
    return {'id': str(i), 'name': name or f'CAMISETA MUJER 49900 / 10524990{i:02d}', 'type': 'variant',
            'status': 'active', 'itemCategory': {'name': 'CAMISETA'},
            'inventory': {'availableQuantity': qty, 'unitCost': cost},
            'price': [{'idPriceList': '1', 'price': price}]}


@pytest.fixture
def alegra():
    alegra_client_module._items_cache.clear()
    yield AlegraClient('carreno@test.com', 'tok', 'https://api.alegra.com/api/v1')
    alegra_client_module._items_cache.clear()


def test_items_activos_pagina_hasta_el_final_y_cachea(alegra, monkeypatch):
    catalog = [variant(i) for i in range(65)]
    calls = []

    def fake_get(url, params=None, timeout=None):
        calls.append(dict(params))
        start, limit = params['start'], params['limit']
        return FakeResponse(catalog[start:start + limit])

    monkeypatch.setattr(alegra.session, 'get', fake_get)
    items = alegra.get_active_items()
    assert len(items) == 65  # antes: 30 (una sola petición)
    assert [c['start'] for c in calls] == [0, 30, 60]
    assert all(c['limit'] == 30 and c['status'] == 'active' for c in calls)

    # Las otras pestañas no vuelven a pedir ~55 páginas a Alegra
    assert len(alegra.get_active_items()) == 65 and len(calls) == 3


def test_items_cache_por_tienda(alegra, monkeypatch):
    monkeypatch.setattr(alegra.session, 'get', lambda url, params=None, timeout=None: FakeResponse([variant(1)]))
    alegra.get_active_items()
    otra = AlegraClient('primavera@test.com', 'tok', 'https://api.alegra.com/api/v1')
    monkeypatch.setattr(otra.session, 'get', lambda url, params=None, timeout=None: FakeResponse([variant(2), variant(3)]))
    assert len(otra.get_active_items()) == 2


def test_items_no_queda_en_ciclo_si_alegra_ignora_start(alegra, monkeypatch):
    page = [variant(i) for i in range(30)]
    calls = []
    monkeypatch.setattr(alegra.session, 'get',
                        lambda url, params=None, timeout=None: calls.append(params) or FakeResponse(page))
    assert len(alegra.get_active_items()) == 30 and len(calls) == 2


def test_items_si_alegra_falla_no_devuelve_lista_a_medias(alegra, monkeypatch):
    def fake_get(url, params=None, timeout=None):
        if params['start'] >= 30:
            return FakeResponse({}, status_code=503)
        return FakeResponse([variant(i) for i in range(30)])

    monkeypatch.setattr(alegra.session, 'get', fake_get)
    with pytest.raises(Exception):
        alegra.get_active_items()
    assert len(alegra_client_module._items_cache) == 0  # el error no queda en caché


def test_analisis_inventario_ignora_productos_con_asteriscos():
    items = [variant(1, qty=3), variant(2, qty=1), variant(3, qty=5, name='***** / 1047299001')]
    resumen = InventoryAnalytics(items).get_executive_summary()
    assert resumen['total_items'] == 2 and resumen['total_unidades'] == 4
    assert resumen['valor_total_inventario'] == 40_000


# ─── 3. Facturas por rango: no saltar días en silencio ───────────────────────

@pytest.fixture
def no_sleep(monkeypatch):
    monkeypatch.setattr(direct_module.time, 'sleep', lambda s: None)


def test_dia_fallido_se_reporta_y_no_se_salta_en_silencio(monkeypatch, no_sleep):
    calls = []

    def fake_request(self, endpoint, params=None):
        calls.append(params['date'])
        if params['date'] == '2026-09-29':
            raise requests.exceptions.ConnectionError('Alegra caído')
        return SEP_30 if params['date'] == '2026-09-30' else []

    monkeypatch.setattr(AlegraDirectClient, '_make_request', fake_request)
    result = AlegraDirectClient('u', 't').get_all_invoices_for_date_range('2026-09-28', '2026-09-30')
    assert result['success'] is True
    assert result['metadata']['failed_days'] == ['2026-09-29']
    assert result['metadata']['complete'] is False
    assert calls.count('2026-09-29') == direct_module.INVOICE_PAGE_ATTEMPTS  # reintentó
    assert len(result['data']) == 14


def test_fallo_pasajero_se_recupera_con_reintento(monkeypatch, no_sleep):
    attempts = {'n': 0}

    def flaky(self, endpoint, params=None):
        attempts['n'] += 1
        if attempts['n'] == 1:
            raise requests.exceptions.Timeout('lento')
        return SEP_30

    monkeypatch.setattr(AlegraDirectClient, '_make_request', flaky)
    result = AlegraDirectClient('u', 't').get_all_invoices_for_date_range('2026-09-30', '2026-09-30')
    assert result['metadata']['failed_days'] == [] and result['metadata']['complete'] is True
    assert sum(i['total'] for i in result['data']) == ALEGRA_SEP_30_TOTAL


def test_dia_a_medias_no_se_incluye(monkeypatch, no_sleep):
    first_page = [invoice(i, RITA, 10_000) for i in range(30)]

    def fake_request(self, endpoint, params=None):
        if params['start'] == 0:
            return first_page
        raise requests.exceptions.ConnectionError('se cayó en la página 2')

    monkeypatch.setattr(AlegraDirectClient, '_make_request', fake_request)
    result = AlegraDirectClient('u', 't').get_all_invoices_for_date_range('2026-09-30', '2026-09-30')
    assert result['data'] == [] and result['metadata']['failed_days'] == ['2026-09-30']


# ─── 4. Anuladas fuera de Totales / Documentos / Productos ────────────────────

@pytest.fixture
def app(tmp_path, monkeypatch):
    monkeypatch.setenv('ALEGRA_USER_CARRENO', 'carreno@test.com')
    monkeypatch.setenv('ALEGRA_PASS_CARRENO', 'tok-carreno')

    class FaseATestConfig(TestingConfig):
        SQLALCHEMY_DATABASE_URI = f"sqlite:///{(tmp_path / 'fase_a.db').as_posix()}"
        SQLALCHEMY_ENGINE_OPTIONS = {}

    from app import create_app
    return create_app(FaseATestConfig)


def _headers(app, role='admin'):
    from app.services.jwt_service import JWTService
    with app.app_context():
        token = JWTService.generate_token(1, f'{role}@test.com', role, None)
    return {'Authorization': f'Bearer {token}'}


VOID_FEB_24 = invoice(10374, MONICA, 379_900, status='void', day='2026-02-24')


def test_documentos_quita_anuladas_y_cuadra_con_alegra(client, app, monkeypatch):
    def fake_range(self, from_date, to_date):
        return {'success': True, 'data': SEP_30 + [VOID_FEB_24],
                'metadata': {'failed_days': ['2026-09-29'], 'complete': False}}

    monkeypatch.setattr(AlegraDirectClient, 'get_all_invoices_for_date_range', fake_range)
    res = client.get('/api/direct/sales/documents?from=2026-09-29&to=2026-09-30', headers=_headers(app))
    body = res.get_json()
    assert res.status_code == 200
    assert len(body['data']) == 14
    assert sum(d['total'] for d in body['data']) == ALEGRA_SEP_30_TOTAL
    assert body['voided']['count'] == 1 and body['voided']['total'] == 379_900
    assert body['metadata']['failed_days'] == ['2026-09-29']


def test_productos_no_cuentan_anuladas_y_usan_total_con_descuento():
    resumen = ProductAnalytics(SEP_30 + [VOID_FEB_24]).get_summary()
    assert resumen['numero_facturas'] == 14
    assert resumen['facturas_anuladas_excluidas'] == 1
    assert resumen['ingresos_totales'] == ALEGRA_SEP_30_TOTAL  # incluye el 45 % de descuento


# ─── 5 y 6. Analytics: retención y top clientes ──────────────────────────────

def _purchase(id_, client, day, total=100_000):
    return invoice(id_, RITA, total, client=client, day=day.isoformat())


def test_retencion_inactivo_en_riesgo_y_una_compra():
    hoy = date(2026, 9, 30)
    ana = {'id': '10', 'name': 'ANA', 'identification': '10'}
    bea = {'id': '11', 'name': 'BEA', 'identification': '11'}
    cami = {'id': '12', 'name': 'CAMI', 'identification': '12'}
    invoices = [
        _purchase(1, ana, hoy - timedelta(days=200)),
        _purchase(2, bea, hoy - timedelta(days=120)), _purchase(3, bea, hoy - timedelta(days=150)),
        _purchase(4, cami, hoy),
        _purchase(5, CF, hoy),
    ]
    data = SalesAnalytics(invoices).get_customer_retention_analysis()
    estado = {c['customer_name']: c['activity_status'] for c in data['rfm_data']}
    assert estado == {'ANA': 'Inactivo', 'BEA': 'En riesgo', 'CAMI': 'Activo'}  # antes ANA salía "En riesgo"
    tipo = {c['customer_name']: c['customer_type'] for c in data['rfm_data']}
    assert tipo == {'ANA': 'Una compra', 'BEA': 'Recurrente', 'CAMI': 'Una compra'}
    assert data['summary']['inactive_customers'] == 1
    assert data['summary']['new_customers'] == 2


def test_top_clientes_sin_consumidor_final():
    data = SalesAnalytics(SEP_30).get_top_customers_analysis(limit=10)
    names = [c['customer_name'] for c in data['top_customers']]
    assert 'Consumidor final' not in names
    assert names[0] == 'SEBASTIAN LOPEZ RODRIGUEZ'
    assert data['total_customers'] == 4
    cf_total = ALEGRA_SEP_30_TOTAL - (49_900 + 80_200 + 96_000 + 27_445)
    assert data['consumidor_final'] == {'total': cf_total, 'total_formatted': data['consumidor_final']['total_formatted'],
                                        'invoices': 10}


def test_consumidor_final_por_cedula_aunque_cambie_el_id():
    otro_cf = {'id': '999', 'name': 'CONSUMIDOR FINAL', 'identification': '222222222222'}
    data = SalesAnalytics([invoice(1, RITA, 50_000, client=otro_cf)]).get_top_customers_analysis()
    assert data['top_customers'] == [] and data['consumidor_final']['invoices'] == 1
