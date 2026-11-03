"""
Tests de las solicitudes de ajuste de inventario (docs/PLAN_AJUSTES_INVENTARIO.md):
las vendedoras piden, nada toca Alegra hasta que el admin acepta, el ajuste
se crea una sola vez y cada tienda ve solo lo suyo.

Ítems con el formato REAL de /items de Alegra (Carreño, 2026-11-03: el código
va al final del nombre, la referencia está vacía). Base SQLite temporal, sin red.
"""
import copy
from datetime import datetime, timedelta

import pytest

from app.config import TestingConfig
from app.exceptions import AlegraConnectionError


@pytest.fixture
def app(tmp_path):
    class InventoryRequestsTestConfig(TestingConfig):
        SQLALCHEMY_DATABASE_URI = f"sqlite:///{(tmp_path / 'inventory_requests.db').as_posix()}"
        SQLALCHEMY_ENGINE_OPTIONS = {}

    from app import create_app
    return create_app(InventoryRequestsTestConfig)


def _headers(app, user_id, role, store=None):
    from app.services.jwt_service import JWTService
    with app.app_context():
        token = JWTService.generate_token(user_id, f'{role}{user_id}@test.com', role, None)
    return {'Authorization': f'Bearer {token}', **({'X-Store': store} if store else {})}


def item(id_, name, qty, cost, price=None, warehouse='1'):
    return {
        'id': id_, 'name': name, 'reference': None, 'status': 'active', 'type': 'variant',
        'price': [{'idPriceList': '1', 'name': 'General', 'price': price or cost, 'main': True}],
        'inventory': {'unit': 'unit', 'unitCost': cost, 'availableQuantity': qty,
                      'warehouses': [{'id': warehouse, 'name': 'Principal', 'isDefault': True,
                                      'availableQuantity': qty}]},
    }


ITEMS = [
    item('1643', 'CAMISETA NIÑA 39900 / 1054399004', 5, 39900),
    item('1645', 'CAMISETA NIÑA 39900 / 1054399008', 1, 39900),
    item('2189', 'BUZO NIÑA 59900 / 105485992', 2, 59900),
    item('2119', 'TARJETA REGALO 100000 / 1510000015', 0, 100000),
    item('1820', 'JEAN MUJER BOTA CAMPANA 119900 / 105224119908', 3, 118500.5, price=119900),
]


class FakeAlegra:
    def __init__(self, items=None):
        self.items = copy.deepcopy(items or ITEMS)
        self.created = []
        self.fail = None          # 'timeout' | 'rejected'
        self.listed_days = []

    def get_active_items(self):
        return self.items

    def get_item(self, item_id):
        return next(i for i in self.items if i['id'] == item_id)

    def create_inventory_adjustment(self, payload):
        if self.fail == 'timeout':
            self.fail = None
            self.created.append(payload)      # Alegra sí lo creó, pero no respondió
            raise AlegraConnectionError('No se pudo conectar con Alegra: timeout')
        if self.fail == 'rejected':
            self.fail = None
            raise AlegraConnectionError('Alegra no aceptó el ajuste de inventario (HTTP 400)',
                                        details={'status_code': 400, 'response': {'message': 'cantidad inválida'}})
        self.created.append(payload)
        for line in payload['items']:
            it = self.get_item(line['id'])
            delta = line['quantity'] if line['type'] == 'in' else -line['quantity']
            it['inventory']['availableQuantity'] += delta
            it['inventory']['warehouses'][0]['availableQuantity'] += delta
        return {'id': f'adj-{len(self.created)}', 'number': 1787 + len(self.created),
                'observations': payload['observations']}

    def get_inventory_adjustments(self, day):
        self.listed_days.append(day)
        return [{'id': f'adj-{n}', 'number': 1787 + n, 'observations': p['observations']}
                for n, p in enumerate(self.created, start=1) if p['date'] == day]

    def invalidate_items_cache(self):
        pass


@pytest.fixture
def fake(monkeypatch):
    from app.routes import inventory_requests as routes
    alegra = FakeAlegra()
    monkeypatch.setattr(routes, 'get_alegra_client', lambda code=None: alegra)
    return alegra


CONTEO = {'kind': 'conteo', 'requested_by': 'Yesica', 'lines': [
    {'code': '1054399004', 'physical_qty': 6},     # sistema 5 -> aumentar 1
    {'code': '1054399008', 'physical_qty': 0},     # sistema 1 -> disminuir 1
    {'code': ' 105485992 ', 'physical_qty': 1},    # sistema 2 -> disminuir 1
]}

TARJETA = {'kind': 'tarjeta_regalo', 'requested_by': 'Daniela', 'gift_card_code': '1510000015',
           'lines': [{'code': '105224119908', 'quantity': 1}], 'excedente_valor': 9900, 'excedente_medio': 'efectivo'}


def test_buscar_codigo_en_el_nombre_de_la_variante(app, client, fake):
    resp = client.get('/api/inventory-requests/lookup?code=1054399004', headers=_headers(app, 2, 'sales'))
    assert resp.status_code == 200
    it = resp.get_json()['item']
    assert (it['item_id'], it['name'], it['available'], it['is_gift_card']) == ('1643', 'CAMISETA NIÑA 39900 / 1054399004', 5, False)
    assert client.get('/api/inventory-requests/lookup?code=999', headers=_headers(app, 2, 'sales')).status_code == 404
    assert client.get('/api/inventory-requests/lookup?code=1510000015', headers=_headers(app, 2, 'sales')).get_json()['item']['is_gift_card']


def test_conteo_calcula_la_diferencia_y_no_toca_alegra(app, client, fake):
    resp = client.post('/api/inventory-requests', headers=_headers(app, 2, 'sales'), json=CONTEO)
    assert resp.status_code == 201, resp.get_json()
    req = resp.get_json()['request']
    assert req['status'] == 'pendiente' and req['requested_by'] == 'Yesica'
    assert [(l['code'], l['type'], l['quantity'], l['system_qty']) for l in req['lines']] == [
        ('1054399004', 'in', 1, 5), ('1054399008', 'out', 1, 1), ('105485992', 'out', 1, 2)]
    assert fake.created == []


def test_validaciones_al_pedir(app, client, fake):
    h = _headers(app, 2, 'sales')
    assert client.post('/api/inventory-requests', headers=h, json={**CONTEO, 'requested_by': ''}).status_code == 400
    same = {**CONTEO, 'lines': [{'code': '1054399004', 'physical_qty': 5}]}
    assert 'igual al sistema' in client.post('/api/inventory-requests', headers=h, json=same).get_json()['message']
    dup = {**CONTEO, 'lines': [{'code': '1054399004', 'physical_qty': 6}, {'code': '1054399004', 'physical_qty': 7}]}
    assert 'repetido' in client.post('/api/inventory-requests', headers=h, json=dup).get_json()['message']
    not_card = {**TARJETA, 'gift_card_code': '1054399004'}
    assert 'no una tarjeta regalo' in client.post('/api/inventory-requests', headers=h, json=not_card).get_json()['message']
    too_many = {**TARJETA, 'lines': [{'code': '105224119908', 'quantity': 4}]}
    assert 'hay 3' in client.post('/api/inventory-requests', headers=h, json=too_many).get_json()['message']
    no_medio = {**TARJETA, 'excedente_medio': ''}
    assert client.post('/api/inventory-requests', headers=h, json=no_medio).status_code == 400


def test_admin_acepta_y_se_crea_el_ajuste_con_el_formato_de_alegra(app, client, fake):
    rid = client.post('/api/inventory-requests', headers=_headers(app, 2, 'sales'), json=TARJETA).get_json()['request']['id']
    admin = _headers(app, 1, 'admin')
    assert client.post(f'/api/inventory-requests/{rid}/approve', headers=_headers(app, 2, 'sales')).status_code == 403
    assert fake.created == []

    resp = client.post(f'/api/inventory-requests/{rid}/approve', headers=admin)
    assert resp.status_code == 200, resp.get_json()
    req = resp.get_json()['request']
    assert req['status'] == 'aplicada' and req['alegra_number'] == '1788'
    payload = fake.created[0]
    assert payload['warehouse'] == {'id': '1'}
    assert payload['date'] == req['request_date']
    assert payload['items'] == [
        {'id': '2119', 'type': 'in', 'quantity': 1, 'unitCost': 100000},
        {'id': '1820', 'type': 'out', 'quantity': 1, 'unitCost': 118500.5},   # costo promedio, no el precio
    ]
    assert 'Redimir tarjeta regalo - pedido por Daniela' in payload['observations']
    assert 'Excedente $9.900 (efectivo)' in payload['observations']
    assert payload['observations'].endswith(f'[KOAJ-AJ-{rid}]')

    # Una sola vez
    again = client.post(f'/api/inventory-requests/{rid}/approve', headers=admin)
    assert again.status_code == 409 and len(fake.created) == 1
    assert client.post(f'/api/inventory-requests/{rid}/reject', headers=admin, json={'reason': 'x'}).status_code == 409


def test_no_deja_inventario_en_negativo(app, client, fake):
    rid = client.post('/api/inventory-requests', headers=_headers(app, 2, 'sales'), json=CONTEO).get_json()['request']['id']
    fake.get_item('1645')['inventory']['warehouses'][0]['availableQuantity'] = 0   # se vendió mientras tanto
    admin = _headers(app, 1, 'admin')
    check = client.get(f'/api/inventory-requests/{rid}/check', headers=admin).get_json()
    assert check['warnings'] == ['1054399008: cuando lo pidieron había 1 y ahora hay 0.']
    assert 'negativo' in check['problem']
    resp = client.post(f'/api/inventory-requests/{rid}/approve', headers=admin)
    assert resp.status_code == 409 and fake.created == []
    assert resp.get_json()['request']['status'] == 'pendiente'
    assert 'negativo' in resp.get_json()['request']['last_error']


def test_alegra_no_responde_y_al_reintentar_no_duplica(app, client, fake):
    rid = client.post('/api/inventory-requests', headers=_headers(app, 2, 'sales'), json=CONTEO).get_json()['request']['id']
    admin = _headers(app, 1, 'admin')
    fake.fail = 'timeout'
    resp = client.post(f'/api/inventory-requests/{rid}/approve', headers=admin)
    assert resp.status_code == 409 and resp.get_json()['request']['status'] == 'revisar'
    assert client.post(f'/api/inventory-requests/{rid}/reject', headers=admin, json={'reason': 'x'}).status_code == 409

    resp = client.post(f'/api/inventory-requests/{rid}/approve', headers=admin)
    assert resp.status_code == 200
    assert resp.get_json()['request']['status'] == 'aplicada'
    assert resp.get_json()['request']['alegra_number'] == '1788'
    assert len(fake.created) == 1 and fake.listed_days


def test_alegra_rechaza_y_queda_pendiente(app, client, fake):
    rid = client.post('/api/inventory-requests', headers=_headers(app, 2, 'sales'), json=CONTEO).get_json()['request']['id']
    fake.fail = 'rejected'
    resp = client.post(f'/api/inventory-requests/{rid}/approve', headers=_headers(app, 1, 'admin'))
    assert resp.status_code == 409
    req = resp.get_json()['request']
    assert req['status'] == 'pendiente' and 'cantidad inválida' in req['last_error']


def test_aplicando_viejo_se_puede_retomar(app, client, fake):
    rid = client.post('/api/inventory-requests', headers=_headers(app, 2, 'sales'), json=CONTEO).get_json()['request']['id']
    from app.models.inventory_request import InventoryRequest
    from app.models.user import db
    with app.app_context():
        r = db.session.get(InventoryRequest, rid)
        r.status, r.reviewed_at = 'aplicando', datetime.utcnow() - timedelta(minutes=1)
        db.session.commit()
    admin = _headers(app, 1, 'admin')
    assert client.post(f'/api/inventory-requests/{rid}/approve', headers=admin).status_code == 409   # reciente: en curso
    with app.app_context():
        r = db.session.get(InventoryRequest, rid)
        r.reviewed_at = datetime.utcnow() - timedelta(minutes=10)
        db.session.commit()
    resp = client.post(f'/api/inventory-requests/{rid}/approve', headers=admin)
    assert resp.status_code == 200 and fake.listed_days and len(fake.created) == 1


def test_aceptar_todas_rechazar_y_cancelar(app, client, fake):
    sales = _headers(app, 2, 'sales')
    admin = _headers(app, 1, 'admin')
    a = client.post('/api/inventory-requests', headers=sales, json=CONTEO).get_json()['request']['id']
    b = client.post('/api/inventory-requests', headers=sales, json=TARJETA).get_json()['request']['id']
    c = client.post('/api/inventory-requests', headers=sales,
                    json={'kind': 'conteo', 'requested_by': 'Yesica', 'lines': [{'code': '2189', 'physical_qty': 3}]})
    assert c.status_code == 400   # 2189 es el id, no el código
    c = client.post('/api/inventory-requests', headers=sales,
                    json={'kind': 'conteo', 'requested_by': 'Yesica', 'lines': [{'code': '105485992', 'physical_qty': 4}]}).get_json()['request']['id']
    d = client.post('/api/inventory-requests', headers=sales,
                    json={'kind': 'conteo', 'requested_by': 'Yesica', 'lines': [{'code': '1054399008', 'physical_qty': 3}]}).get_json()['request']['id']

    assert client.post(f'/api/inventory-requests/{c}/reject', headers=admin, json={}).status_code == 400
    assert client.post(f'/api/inventory-requests/{c}/reject', headers=admin, json={'reason': 'contar otra vez'}).get_json()['request']['status'] == 'rechazada'
    assert client.post(f'/api/inventory-requests/{d}/cancel', headers=sales).get_json()['request']['status'] == 'cancelada'

    listing = client.get('/api/inventory-requests', headers=admin).get_json()
    assert listing['open_count'] == 2 and {r['id'] for r in listing['items']} == {a, b}

    reminders = client.get('/api/reminders', headers=admin).get_json()['reminders']
    assert reminders[0]['kind'] == 'inventory_requests' and reminders[0]['title'].startswith('2 ajustes')

    result = client.post('/api/inventory-requests/approve-all', headers=admin).get_json()
    assert (result['applied'], result['failed']) == (2, 0) and len(fake.created) == 2
    assert client.get('/api/inventory-requests', headers=admin).get_json()['open_count'] == 0
    assert all(r['kind'] != 'inventory_requests' for r in client.get('/api/reminders', headers=admin).get_json()['reminders'])
    assert client.post(f'/api/inventory-requests/{a}/cancel', headers=sales).status_code == 409
    assert len(client.get('/api/inventory-requests?status=all', headers=admin).get_json()['items']) == 4


def test_cada_tienda_ve_solo_lo_suyo_y_solo_lectura_no_acepta(app, client, fake):
    rid = client.post('/api/inventory-requests', headers=_headers(app, 1, 'admin', 'primavera'), json=CONTEO).get_json()['request']['id']
    assert client.get('/api/inventory-requests', headers=_headers(app, 1, 'admin', 'carreno')).get_json()['open_count'] == 0
    assert client.post(f'/api/inventory-requests/{rid}/approve', headers=_headers(app, 1, 'admin', 'carreno')).status_code == 404
    assert client.get('/api/inventory-requests', headers=_headers(app, 1, 'admin', 'primavera')).get_json()['items'][0]['store_code'] == 'primavera'

    viewer = _headers(app, 9, 'viewer', 'primavera')
    assert client.get('/api/inventory-requests', headers=viewer).status_code == 200
    assert client.post(f'/api/inventory-requests/{rid}/approve', headers=viewer).status_code == 403
    assert fake.created == []


CAMBIO = {'kind': 'cambio_prenda', 'requested_by': 'Yesica',
          'in_lines': [{'code': '1054399008', 'quantity': 1}],          # devuelve camiseta 39.900
          'lines': [{'code': '105485992', 'quantity': 1}],             # se lleva buzo 59.900
          'excedente_valor': 20000, 'excedente_medio': 'qr'}


def test_cambio_de_prenda_entra_la_devuelta_y_sale_la_nueva(app, client, fake):
    resp = client.post('/api/inventory-requests', headers=_headers(app, 2, 'sales'), json=CAMBIO)
    assert resp.status_code == 201, resp.get_json()
    req = resp.get_json()['request']
    assert req['kind_label'] == 'Cambio de prenda' and req['price_difference'] == 20000
    assert [(l['code'], l['type'], l['quantity']) for l in req['lines']] == [('1054399008', 'in', 1), ('105485992', 'out', 1)]
    done = client.post(f'/api/inventory-requests/{req["id"]}/approve', headers=_headers(app, 1, 'admin')).get_json()['request']
    assert done['status'] == 'aplicada'
    payload = fake.created[0]
    assert [(i['id'], i['type']) for i in payload['items']] == [('1645', 'in'), ('2189', 'out')]
    assert 'Cambio de prenda - pedido por Yesica' in payload['observations'] and 'Excedente $20.000 (qr)' in payload['observations']


def test_cambio_nunca_devuelve_plata(app, client, fake):
    h = _headers(app, 2, 'sales')
    menor = {**CAMBIO, 'in_lines': [{'code': '105485992'}], 'lines': [{'code': '1054399008'}], 'excedente_valor': 0}
    msg = client.post('/api/inventory-requests', headers=h, json=menor).get_json()['message']
    assert 'Nunca se devuelve plata' in msg and '$39.900' in msg and '$59.900' in msg
    # Llevando dos prendas iguala o pasa el valor: vale
    dos = {**menor, 'lines': [{'code': '1054399008'}, {'code': '1054399004'}], 'excedente_valor': 19900, 'excedente_medio': 'efectivo'}
    assert client.post('/api/inventory-requests', headers=h, json=dos).status_code == 201
    # Más caro sin excedente: lo pide
    sin = {**CAMBIO, 'excedente_valor': 0}
    assert 'escribe el excedente' in client.post('/api/inventory-requests', headers=h, json=sin).get_json()['message']
    # Mismo valor: sin excedente está bien
    igual = {**CAMBIO, 'lines': [{'code': '1054399004'}], 'excedente_valor': 0}
    assert client.post('/api/inventory-requests', headers=h, json=igual).status_code == 201
    tarjeta = {**CAMBIO, 'in_lines': [{'code': '1510000015'}]}
    assert 'Redimir tarjeta regalo' in client.post('/api/inventory-requests', headers=h, json=tarjeta).get_json()['message']


def test_tarjeta_regalo_tampoco_devuelve_plata(app, client, fake):
    h = _headers(app, 2, 'sales')
    # Tarjeta de 100.000 por una camiseta de 39.900: debe llevar más
    menor = {**TARJETA, 'lines': [{'code': '1054399004'}], 'excedente_valor': 0}
    msg = client.post('/api/inventory-requests', headers=h, json=menor).get_json()['message']
    assert 'Nunca se devuelve plata' in msg and 'que la tarjeta' in msg
    # Jean de 119.900 sin excedente: lo pide
    sin = {**TARJETA, 'excedente_valor': 0}
    assert 'escribe el excedente' in client.post('/api/inventory-requests', headers=h, json=sin).get_json()['message']
    # Dos camisetas y un buzo (139.700): vale con excedente
    mas = {**TARJETA, 'lines': [{'code': '1054399004', 'quantity': 2}, {'code': '105485992'}], 'excedente_valor': 39700}
    resp = client.post('/api/inventory-requests', headers=h, json=mas)
    assert resp.status_code == 201 and resp.get_json()['request']['price_difference'] == 39700
