"""
Fase D1 de Estadísticas (docs/PLAN_ESTADISTICAS.md): llegadas de mercancía.

Las compras simuladas copian el formato REAL de /bills (factura 611 del
29-sep-2026, leída con el conector de Alegra el 2026-10-03): `purchases.items`
con id, name, price (precio de VENTA) y quantity; `provider` objeto.
"""
from datetime import date

import pytest

from app.models.purchase_fact import PurchaseItemFact
from app.services import invoice_facts as svc
from app.services import purchase_facts as pf
from app.services.alegra_direct_client import AlegraDirectClient
from tests.test_estadisticas_fase_a import MONICA
from tests.test_estadisticas_fase_c import FakeAlegra, _headers, app, inv, item  # noqa: F401

KOAJ = {'id': '2', 'name': 'KOAJ', 'identification': '1030652074'}


def bill(id_, day, items, status='closed', provider=KOAJ):
    return {'id': str(id_), 'date': day, 'dueDate': day, 'status': status, 'provider': provider,
            'numberTemplate': {'number': str(id_), 'fullNumber': str(id_)},
            'total': sum(i['price'] * i['quantity'] for i in items), 'warehouse': {'id': '1', 'name': 'Principal'},
            'type': 'bill', 'purchases': {'items': items}}


def bitem(item_id, name, price, qty):
    return {'id': item_id, 'name': name, 'price': price, 'discount': 0, 'observations': '', 'description': '',
            'tax': None, 'quantity': qty, 'subtotal': price * qty, 'total': price * qty}


GORRA = ('825', 'GORRA 39900 / 105039900', 39900)
MEDIAS = ('829', 'MEDIAS 7900 / 10487900', 7900)
BILL_611 = bill(611, '2026-09-29', [bitem(*GORRA, 23), bitem(*MEDIAS, 144), bitem('1749', 'MEDIAS 10000 / 104810000', 10000, 40)])


class FakeDirect:
    def __init__(self, bills):
        self.bills = bills

    def get_bills_since(self, since):
        return [b for b in self.bills if b['date'] >= since]


# ─── Formato y asignación ───────────────────────────────────────────────────

def test_compra_a_renglones():
    rows = pf.bill_to_rows(BILL_611)
    assert [(r['item_id'], r['quantity'], r['unit_price']) for r in rows] == [('825', 23, 39900), ('829', 144, 7900), ('1749', 40, 10000)]
    assert rows[0]['provider_name'] == 'KOAJ' and rows[0]['date'] == date(2026, 9, 29)
    assert pf.bill_to_rows({**BILL_611, 'status': 'void'}) == []


def test_ventas_van_a_la_llegada_mas_antigua():
    arrivals = [{'date': date(2026, 9, 20), 'quantity': 3}, {'date': date(2026, 9, 1), 'quantity': 5}]
    pf.allocate_sales(arrivals, {date(2026, 8, 30): 4,   # antes de llegar: no cuenta
                                 date(2026, 9, 10): 4,   # solo la del 1-sep había llegado
                                 date(2026, 9, 25): 3})  # 1 a la del 1-sep, 2 a la del 20-sep
    assert [(a['date'].day, a['sold']) for a in arrivals] == [(1, 5), (20, 2)]


# ─── Descarga de /bills ─────────────────────────────────────────────────────

def _bills_api(bills, respect_order=True):
    ordered = sorted(bills, key=lambda b: int(b['id']), reverse=respect_order)
    calls = []

    def fake(self, endpoint, params=None):
        assert endpoint == '/bills'
        calls.append(params['start'])
        return ordered[params['start']:params['start'] + params['limit']]
    return fake, calls


def test_compras_se_detienen_al_pasar_la_fecha(monkeypatch):
    bills = [bill(i, '2025-12-15' if i < 100 else '2026-02-01', []) for i in range(1, 160)]
    fake, calls = _bills_api(bills)
    monkeypatch.setattr(AlegraDirectClient, '_make_request', fake)
    result = AlegraDirectClient('u', 't').get_bills_since('2026-01-01')
    assert len(result) == 60 and calls == [0, 30, 60]  # para en la página que ya es toda de 2025


def test_compras_si_alegra_ignora_el_orden_las_recorre_todas(monkeypatch):
    bills = [bill(i, '2025-12-15' if i < 100 else '2026-02-01', []) for i in range(1, 160)]
    fake, calls = _bills_api(bills, respect_order=False)
    monkeypatch.setattr(AlegraDirectClient, '_make_request', fake)
    assert len(AlegraDirectClient('u', 't').get_bills_since('2026-01-01')) == 60
    assert len(calls) == 6


# ─── Carga e indicadores ────────────────────────────────────────────────────

def test_carga_reemplaza_y_separa_tiendas(app):
    with app.app_context():
        pf.sync_purchases(FakeDirect([BILL_611]), 'carreno', date(2026, 1, 1))
        pf.sync_purchases(FakeDirect([BILL_611]), 'carreno', date(2026, 1, 1))  # no duplica
        assert PurchaseItemFact.query.filter_by(store_code='carreno').count() == 3
        assert PurchaseItemFact.query.filter_by(store_code='primavera').count() == 0
        # Compra anulada en Alegra: desaparece en la siguiente carga
        pf.sync_purchases(FakeDirect([{**BILL_611, 'status': 'void'}]), 'carreno', date(2026, 1, 1))
        assert PurchaseItemFact.query.filter_by(store_code='carreno').count() == 0


def test_si_alegra_falla_no_se_borra_nada(app):
    class Broken:
        def get_bills_since(self, since):
            raise RuntimeError('caído')
    with app.app_context():
        pf.sync_purchases(FakeDirect([BILL_611]), 'carreno', date(2026, 1, 1))
        with pytest.raises(RuntimeError):
            pf.sync_purchases(Broken(), 'carreno', date(2026, 1, 1))
        assert PurchaseItemFact.query.filter_by(store_code='carreno').count() == 3


def test_llegada_con_lo_vendido(app):
    with app.app_context():
        pf.sync_purchases(FakeDirect([BILL_611]), 'carreno', date(2026, 1, 1))
        # 30-sep: 2 gorras y 10 medias de $7.900 (en dos facturas); hoy 2-oct no cuenta (día abierto)
        svc.sync_day(FakeAlegra({'2026-09-30': [
            inv(1, MONICA, [item(GORRA[1], GORRA[0], GORRA[2], qty=2), item(MEDIAS[1], MEDIAS[0], MEDIAS[2], qty=4)], day='2026-09-30'),
            inv(2, MONICA, [item(MEDIAS[1], MEDIAS[0], MEDIAS[2], qty=6)], day='2026-09-30'),
        ]}), 'carreno', date(2026, 9, 30))
        svc.sync_day(FakeAlegra({}), 'carreno', date(2026, 9, 29))
        svc.sync_day(FakeAlegra({}), 'carreno', date(2026, 10, 1))
        data = pf.ArrivalsService('carreno', date(2026, 10, 2)).summary(date(2026, 9, 29), date(2026, 10, 2))

        assert data['coverage']['complete'] is True
        assert data['totals'] == {'arrivals': 1, 'units': 207, 'sold_units': 12, 'sell_through_pct': 5.8,
                                  'value': 2455300}
        arrival = data['arrivals'][0]
        assert arrival['provider'] == 'KOAJ' and arrival['bills'] == ['611'] and arrival['days_since_arrival'] == 3
        medias = next(p for p in arrival['products'] if p['product'] == 'MEDIAS')
        assert medias['units'] == 184 and medias['sold_units'] == 10
        assert arrival['unsold_references'] == 1  # MEDIAS 10000
        assert data['stale'] == []  # llegó hace 3 días: todavía no cuenta como "no se mueve"


def test_endpoint_llegadas(client, app):
    with app.app_context():
        pf.sync_purchases(FakeDirect([BILL_611]), 'carreno', date(2026, 1, 1))
    res = client.get('/api/analytics/arrivals?start_date=2026-09-01&end_date=2026-09-30', headers=_headers(app))
    assert res.status_code == 200, res.get_json()
    assert res.get_json()['data']['totals']['units'] == 207
    assert client.get('/api/analytics/arrivals', headers=_headers(app, 'sales')).status_code == 403
    bad = client.get('/api/analytics/arrivals?start_date=2026-09-30&end_date=2026-09-01', headers=_headers(app))
    assert bad.status_code == 400


def test_carga_de_facturas_tambien_carga_compras(client, app, monkeypatch):
    from app.services.alegra_client import AlegraClient
    monkeypatch.setattr(AlegraClient, 'get_invoices_by_date', lambda self, d: [])
    monkeypatch.setattr(AlegraDirectClient, 'get_bills_since', lambda self, since: [BILL_611])
    res = client.post('/api/analytics/invoice-facts/sync', json={'max_days': 0, 'recent_days': 1}, headers=_headers(app))
    assert res.status_code == 200, res.get_json()
    assert res.get_json()['purchases'] == {'success': True, 'bills': 1, 'items': 3, 'units': 207}

    # Si las compras fallan, la carga de facturas igual sale bien
    def boom(self, since):
        raise RuntimeError('caído')
    monkeypatch.setattr(AlegraDirectClient, 'get_bills_since', boom)
    res = client.post('/api/analytics/invoice-facts/sync', json={'max_days': 0, 'recent_days': 1}, headers=_headers(app))
    assert res.status_code == 200 and res.get_json()['purchases']['success'] is False
