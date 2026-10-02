"""
Fase C de Estadísticas: prendas de cada factura guardadas por tienda
(InvoiceItemFact) y pestaña Prendas (app/services/garment_insights.py).

Facturas con el formato real de /api/v1/invoices (30-sep-2026, conector de
Alegra): nombres "PRENDA PRECIO / SKU", BOLSA PAPEL de $300 en casi todas,
descuento del ítem en PORCENTAJE y items[].total con el descuento aplicado.
"""
from datetime import date

import pytest

from app.config import TestingConfig
from app.models.invoice_fact import InvoiceFact, InvoiceItemFact, InvoiceSyncDay
from app.models.user import db
from app.services import invoice_facts as svc
from app.services import garment_insights as gi
from app.services.alegra_client import AlegraClient
from tests.test_estadisticas_fase_a import MONICA, RITA, CF, invoice

BOLSA = {'name': 'BOLSA PAPEL', 'price': 300, 'discount': 0, 'quantity': 1, 'id': '2165', 'tax': [], 'total': 300}


def item(name, item_id, price, qty=1, discount=0):
    return {'name': name, 'price': price, 'discount': discount, 'quantity': qty, 'id': item_id, 'tax': [],
            'total': round(price * qty * (1 - discount / 100))}


def inv(id_, seller, items, status='closed', day='2026-09-30'):
    return invoice(id_, seller, sum(i['total'] for i in items), status=status, items=items, day=day)


# KPC4436, KPC4435, KPC4434, KPC4433 (45 % de descuento) y KPC4437 del 30-sep
JEAN_M_8 = item('JEAN MUJER 109900 / 10521099008', '1205', 109900)
SEP_30 = [
    inv(12936, RITA, [JEAN_M_8, BOLSA]),
    inv(12935, RITA, [item('MEDIAS 7900 / 10487900', '829', 7900, qty=3),
                      item('BODY U 49900 / 1035049900', '1581', 49900), BOLSA]),
    inv(12933, MONICA, [item('BLUSA 79900 / 1040799003', '1448', 79900), BOLSA,
                        item('MEDIAS 7900 / 10487900', '829', 7900, qty=2)]),
    inv(12932, MONICA, [item('CAMISETA HOMBRE 49900 / 1051499002', '1044', 49900, discount=45)]),
    inv(12937, RITA, [item('CAMISETA MUJER 36900 / 1052369001', '1085', 36900),
                      item('CAMISETA MUJER 36900 / 1052369005', '1089', 36900), BOLSA]),
]
VOID = inv(12950, RITA, [item('CAMISETA MUJER 36900 / 1052369001', '1085', 36900)], status='void')


# ─── Guardar prendas ────────────────────────────────────────────────────────

def test_renglones_de_una_factura():
    rows = svc.invoice_to_items(SEP_30[3])
    assert len(rows) == 1
    r = rows[0]
    assert (r['name'], r['quantity'], r['unit_price'], r['discount_pct'], r['total']) == \
        ('CAMISETA HOMBRE 49900 / 1051499002', 1, 49900, 45.0, 27445)
    assert (r['seller_id'], r['seller_name'], r['item_id']) == ('1', 'MONICA VARGAS', '1044')
    assert svc.invoice_to_items(VOID) == []  # anulada: no hay prendas vendidas


@pytest.fixture
def app(tmp_path, monkeypatch):
    monkeypatch.setenv('ALEGRA_USER_CARRENO', 'carreno@test.com')
    monkeypatch.setenv('ALEGRA_PASS_CARRENO', 'tok-carreno')
    monkeypatch.delenv('ALEGRA_USER_PRIMAVERA', raising=False)
    monkeypatch.delenv('ALEGRA_PASS_PRIMAVERA', raising=False)
    gi.parse_garment.cache_clear()

    class FaseCTestConfig(TestingConfig):
        SQLALCHEMY_DATABASE_URI = f"sqlite:///{(tmp_path / 'fase_c.db').as_posix()}"
        SQLALCHEMY_ENGINE_OPTIONS = {}

    from app import create_app
    return create_app(FaseCTestConfig)


class FakeAlegra:
    def __init__(self, by_day):
        self.by_day = by_day

    def get_invoices_by_date(self, day):
        return self.by_day.get(str(day), [])


def test_sync_day_guarda_prendas_y_reemplaza(app):
    with app.app_context():
        day = date(2026, 9, 30)
        svc.sync_day(FakeAlegra({'2026-09-30': SEP_30 + [VOID]}), 'carreno', day)
        items = InvoiceItemFact.query.filter_by(store_code='carreno', date=day).all()
        assert len(items) == 12  # renglones de las activas (2+3+3+1+3, bolsas incluidas); la anulada no
        assert InvoiceSyncDay.query.filter_by(store_code='carreno', date=day).one().items_synced is True

        # Volver a cargar el día no duplica
        svc.sync_day(FakeAlegra({'2026-09-30': SEP_30}), 'carreno', day)
        assert InvoiceItemFact.query.filter_by(store_code='carreno', date=day).count() == 12
        # Otra tienda queda aparte
        assert InvoiceItemFact.query.filter_by(store_code='primavera').count() == 0


def test_dias_viejos_sin_prendas_se_cargan_sin_afectar_a_clientes(app):
    with app.app_context():
        old = date(2026, 9, 29)
        # Día cargado antes de que existieran las prendas (items_synced NULL)
        db.session.add(InvoiceSyncDay(store_code='carreno', date=old, invoice_count=0))
        db.session.commit()
        start, end = date(2026, 9, 29), date(2026, 9, 30)
        assert svc.missing_days('carreno', start, end) == [date(2026, 9, 30)]  # Clientes: solo falta el 30
        assert svc.missing_item_days('carreno', start, end) == [old, date(2026, 9, 30)]
        assert svc.pending_days('carreno', start, end) == [old, date(2026, 9, 30)]
        status = svc.coverage_status('carreno', start, end)
        assert status['missing_days'] == 1 and status['items']['missing_days'] == 2


# ─── Indicadores (funciones puras) ──────────────────────────────────────────

def _rows(invoices):
    return gi.garment_rows([r for i in invoices for r in svc.invoice_to_items(i)])


def test_canasta_sin_bolsa_por_vendedora():
    rows = _rows(SEP_30)
    assert all('BOLSA' not in r['name'] for r in rows)
    sellers = {s['name']: s for s in gi.seller_baskets(rows)}
    rita = sellers['RITA INFANTE']  # 3 facturas: 1 + 4 + 2 prendas
    assert (rita['invoices'], rita['units'], rita['revenue']) == (3, 7, 109900 + 23700 + 49900 + 73800)
    assert rita['units_per_invoice'] == round(7 / 3, 2)
    assert rita['avg_price_per_unit'] == round(257300 / 7)
    monica = sellers['MONICA VARGAS']  # descuento del 45 % incluido
    assert (monica['invoices'], monica['units'], monica['revenue']) == (2, 4, 79900 + 15800 + 27445)


def test_mas_vendidos_agotados_y_por_agotarse():
    rows = _rows(SEP_30)
    stock = {'829': {'name': 'MEDIAS 7900 / 10487900', 'stock': 0},
             '1205': {'name': JEAN_M_8['name'], 'stock': 2},
             '1085': {'name': 'CAMISETA MUJER 36900 / 1052369001', 'stock': 9}}
    result = gi.best_sellers_stock(rows, stock)
    assert [(r['name'], r['units'], r['stock']) for r in result['out_of_stock']] == [('MEDIAS 7900 / 10487900', 5, 0)]
    assert [r['size'] for r in result['low_stock']] == ['8']  # jean talla 8, quedan 2


def test_curva_de_tallas_venta_vs_stock():
    rows = _rows(SEP_30)
    stock = {'a': {'name': 'CAMISETA MUJER 36900 / 1052369001', 'stock': 1},   # XS
             'b': {'name': 'CAMISETA MUJER 36900 / 1052369003', 'stock': 3}}   # M
    mujer_letras = next(g for g in gi.size_curve(rows, stock)
                        if g['department'] == 'MUJER' and g['family'] == 'Letras')
    by_size = {s['size']: s for s in mujer_letras['sizes']}
    assert [s['size'] for s in mujer_letras['sizes']] == ['XS', 'M', 'XL']  # orden de tallas
    assert by_size['XS']['sold_pct'] == 50.0 and by_size['XS']['stock_pct'] == 25.0
    assert by_size['XL']['sold_units'] == 1 and by_size['XL']['stock_units'] == 0


def test_rotacion_dias_de_inventario():
    rows = _rows(SEP_30)
    stock = {'1': {'name': 'JEAN MUJER 109900 / 10521099010', 'stock': 30},
             '2': {'name': 'CAMISETA MUJER 36900 / 1052369002', 'stock': 1},
             '3': {'name': 'GORRA 39900 / 105039900', 'stock': 4}}
    rot = {r['product']: r for r in gi.rotation(rows, stock, days=10)}
    assert rot['JEAN MUJER']['days_of_inventory'] == 300 and rot['JEAN MUJER']['status'] == 'lenta'
    assert rot['CAMISETA MUJER']['days_of_inventory'] == 5 and rot['CAMISETA MUJER']['status'] == 'se agota pronto'
    assert rot['GORRA']['status'] == 'sin ventas' and rot['GORRA']['days_of_inventory'] is None
    assert rot['MEDIAS']['status'] == 'agotado'


# ─── Endpoints ──────────────────────────────────────────────────────────────

def _headers(app, role='admin'):
    from app.services.jwt_service import JWTService
    with app.app_context():
        token = JWTService.generate_token(1, f'{role}@test.com', role, None)
    return {'Authorization': f'Bearer {token}'}


def test_endpoints_prendas(client, app, monkeypatch):
    with app.app_context():
        svc.sync_day(FakeAlegra({'2026-09-30': SEP_30}), 'carreno', date(2026, 9, 30))
    monkeypatch.setattr(AlegraClient, 'get_invoices_by_date', lambda self, d: [])
    monkeypatch.setattr(AlegraClient, 'get_active_items', lambda self: [
        {'id': '829', 'name': 'MEDIAS 7900 / 10487900', 'type': 'variant', 'inventory': {'availableQuantity': 0}},
        {'id': '2165', 'name': 'BOLSA PAPEL', 'type': 'variant', 'inventory': {'availableQuantity': 500}},
    ])
    url = '/api/analytics/garments/{}?start_date=2026-09-29&end_date=2026-09-30'

    res = client.get(url.format('summary'), headers=_headers(app))
    assert res.status_code == 200, res.get_json()
    data = res.get_json()['data']
    assert data['totals']['units'] == 11 and data['totals']['invoices'] == 5
    assert data['coverage'] == {'days': 2, 'missing_days': 1, 'first_missing_day': '2026-09-29', 'complete': False}
    assert data['top_products'][0]['product'] == 'MEDIAS'

    res = client.get(url.format('stock'), headers=_headers(app))
    data = res.get_json()['data']
    assert data['stock_variants'] == 1  # la bolsa no cuenta como stock
    assert data['best_sellers']['out_of_stock'][0]['product'] == 'MEDIAS'

    assert client.get(url.format('summary'), headers=_headers(app, 'sales')).status_code == 403
    bad = client.get('/api/analytics/garments/summary?start_date=2026-09-30&end_date=2026-09-01', headers=_headers(app))
    assert bad.status_code == 400


def test_prendas_de_hoy_en_vivo(app):
    with app.app_context():
        today = date(2026, 10, 2)
        service = gi.GarmentInsightsService('carreno', today, FakeAlegra({'2026-10-02': SEP_30[:1]}))
        data = service.summary(today, today)
        assert data['totals']['units'] == 1 and data['coverage']['complete'] is True
