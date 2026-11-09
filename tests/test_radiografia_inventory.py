"""
Tests de la Radiografía del inventario (Fase 3 de docs/PLAN_RADIOGRAFIA.md):
valor a precio de venta y a costo, días de inventario, rotación, prendas
quietas (sin venta y sin llegada), tienda recién abierta, por tipo y
departamento, por tienda y solo lectura.

Base SQLite temporal y Alegra simulado (lista de ítems), sin red.
"""
from datetime import date, datetime, timedelta

import pytest

from tests.test_radiografia_month import app, h  # noqa: F401  (fixtures)

TODAY = date(2026, 11, 6)


def _item(id_, name, stock, price, type_='variant'):
    return {'id': id_, 'name': name, 'type': type_, 'inventory': {'availableQuantity': stock},
            'price': [{'idPriceList': 1, 'price': price, 'main': True}]}


ITEMS = [
    _item(1, 'JEAN MUJER 129900 / 8', 4, 129900),
    _item(2, 'BUZO HOMBRE 99900 / M', 5, 99900),
    _item(3, 'SHORT HOMBRE 59900 / L', 2, 59900),
    _item(4, '*****BUZO VIEJO', 9, 50000),
    _item(5, 'BOLSA PAPEL', 100, 1000),
    _item(6, 'CAMISETA MUJER 39900 / S', -1, 39900),
    _item(7, 'SERVICIO', 0, 0, type_='simple'),
]


class FakeClient:
    def get_active_items(self):
        return ITEMS


@pytest.fixture
def fake_alegra(monkeypatch):
    import app.stores as stores
    monkeypatch.setattr(stores, 'get_alegra_client', lambda code=None: FakeClient())


def _today(monkeypatch):
    import app.routes.radiografia as routes
    monkeypatch.setattr(routes, 'get_colombia_now', lambda: datetime(TODAY.year, TODAY.month, TODAY.day, 12, 0))


def _seed(app, store='carreno', first_day=date(2026, 1, 2)):
    from app.models.user import db
    from app.models.invoice_fact import InvoiceFact, InvoiceItemFact, InvoiceSyncDay
    from app.models.purchase_fact import PurchaseItemFact
    with app.app_context():
        d = date(2026, 1, 1)
        while d < TODAY:
            db.session.add(InvoiceSyncDay(store_code=store, date=d, invoice_count=0, items_synced=True))
            d += timedelta(days=1)
        db.session.add(InvoiceFact(store_code=store, alegra_id=f'{store}first', date=first_day, total=10, voided=False))
        lines = [('1', 'JEAN MUJER 129900 / 8', date(2026, 10, 20), 2, 129900, 220000),   # 15 % de descuento
                 ('2', 'BUZO HOMBRE 99900 / M', date(2026, 3, 1), 1, 99900, 99900),     # hace más de 180 días
                 (None, 'BOLSA PAPEL', date(2026, 10, 20), 1, 1000, 1000)]
        for i, (item_id, name, d, qty, price, total) in enumerate(lines):
            db.session.add(InvoiceItemFact(store_code=store, invoice_alegra_id=f'{store}x{i}', line=i, date=d,
                                           item_id=item_id, name=name, quantity=qty, unit_price=price, total=total))
        db.session.add(PurchaseItemFact(store_code=store, bill_alegra_id='b1', line=0, date=date(2026, 10, 1),
                                        item_id='3', name='SHORT HOMBRE 59900 / L', quantity=2, unit_price=59900))
        db.session.commit()


def _get(client, headers, quiet=90):
    resp = client.get(f'/api/radiografia/inventory?quiet={quiet}', headers=headers)
    assert resp.status_code == 200, resp.get_json()
    return resp.get_json()['inventory']


def test_valor_dias_rotacion_y_quietas(app, client, h, monkeypatch, fake_alegra):
    _today(monkeypatch)
    _seed(app)
    inv = _get(client, h())
    t = inv['totals']
    valor = 4 * 129900 + 5 * 99900 + 2 * 59900                 # sin obsoletos, bolsa, negativos ni servicios
    assert t['valor_venta'] == valor and t['unidades'] == 11 and t['referencias'] == 3
    assert t['valor_costo'] == pytest.approx(valor * 0.65)
    # Ritmo: precio de lista vendido en los últimos 90 días ÷ días cargados (sin bolsa)
    w = inv['sales_window']
    assert w['start'] == (TODAY - timedelta(days=90)).isoformat() and w['loaded_days'] == 90
    assert t['vendido_lista_dia'] == pytest.approx(2 * 129900 / 90)
    assert t['dias_inventario'] == pytest.approx(valor / (2 * 129900 / 90))
    # Rotación: lista vendido del año llevado a 12 meses ÷ inventario de hoy
    days = (TODAY - date(2026, 1, 1)).days
    assert t['rotation_days_used'] == days
    assert t['rotacion_anual'] == pytest.approx((2 * 129900 + 99900) / days * 365 / valor)
    # Quieta: el buzo (sin venta en 90 días y sin llegada); el short llegó hace poco; el jean se vendió
    names = [q['name'] for q in inv['quiet']]
    assert names == ['BUZO HOMBRE 99900 / M']
    assert t['plata_parada'] == pytest.approx(5 * 99900 * 0.65)
    assert inv['quiet'][0]['last_sale'] == '2026-03-01' and inv['quiet'][0]['last_arrival'] is None
    assert t['negative_count'] == 1 and any('negativo' in x for x in inv['warnings'])
    assert inv['opened'] is None                                # Carreño vende desde enero


def test_quieta_segun_dias_elegidos(app, client, h, monkeypatch, fake_alegra):
    _today(monkeypatch)
    _seed(app)
    # A 60 días el short (llegó el 1-oct, hace 36 días) sigue sin ser quieto
    assert [q['name'] for q in _get(client, h(), 60)['quiet']] == ['BUZO HOMBRE 99900 / M']
    # Con 180 días el buzo (última venta 1-mar, hace 250 días) sigue quieto
    assert [q['name'] for q in _get(client, h(), 180)['quiet']] == ['BUZO HOMBRE 99900 / M']
    assert client.get('/api/radiografia/inventory?quiet=30', headers=h()).status_code == 400


def test_por_tipo_y_departamento(app, client, h, monkeypatch, fake_alegra):
    _today(monkeypatch)
    _seed(app)
    inv = _get(client, h())
    jean = next(x for x in inv['by_type'] if x['name'].startswith('JEAN'))
    assert jean['units'] == 2 and jean['ventas'] == 220000 and jean['precio_lista'] == 2 * 129900
    assert jean['descuento_pct'] == pytest.approx((259800 - 220000) / 259800)
    assert jean['utilidad_estimada'] == pytest.approx(220000 - 259800 * 0.65)
    assert jean['stock'] == 4 and jean['dias_inventario'] == pytest.approx(4 * 129900 / (259800 / 90))
    buzo = next(x for x in inv['by_type'] if x['name'].startswith('BUZO'))
    assert buzo['dias_inventario'] is None and buzo['plata_parada'] == pytest.approx(5 * 99900 * 0.65)
    depts = {d['name']: d for d in inv['by_department']}
    assert depts['MUJER']['valor_venta'] == 4 * 129900
    assert depts['HOMBRE']['stock'] == 7
    assert inv['fastest'][0]['name'].startswith('JEAN')
    assert inv['slowest'][0]['name'].startswith('BUZO')       # con stock y sin ventas primero


def test_tienda_recien_abierta_nada_quieto(app, client, h, monkeypatch, fake_alegra):
    _today(monkeypatch)
    _seed(app, 'primavera', first_day=date(2026, 10, 25))
    inv = _get(client, h('primavera'))
    assert inv['opened'] == '2026-10-25'
    assert inv['quiet'] == []                                   # abrió hace 12 días
    assert inv['sales_window']['start'] == '2026-10-25'
    assert any('abrió' in w for w in inv['warnings'])
    # Carreño no se mezcla con Primavera
    assert _get(client, h())['totals']['vendido_lista_dia'] is None
    assert client.get('/api/radiografia/inventory', headers=h(role='viewer')).status_code == 200
