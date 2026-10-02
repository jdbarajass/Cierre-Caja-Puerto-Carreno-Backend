"""
Tests del dashboard de clientes (app/services/customer_insights.py y
/api/analytics/customers/*). Simulan Alegra con filas iguales en forma a
las reales de /reports/sales-by-client y sales-by-seller (no hay red).
"""


from datetime import date

import pytest
import requests

from app.config import TestingConfig
from app.services import customer_insights as ci
from app.services.alegra_direct_client import AlegraDirectClient


def client_row(id_, name, ident, docs, total, discount=0):
    return {'idLocal': id_, 'clientName': name, 'identification': ident, 'totalDocuments': docs,
            'totalSales': docs, 'subTotal': total + discount, 'discount': discount, 'creditNote': 0,
            'beforeTaxes': total, 'taxes': 0, 'afterTaxes': total, 'totalPayed': total}


def seller_row(id_, name, docs, total):
    return {'idLocal': id_, 'sellerName': name, 'identification': 'x', 'totalDocuments': docs,
            'subTotal': total, 'discount': 0, 'afterTaxes': total}


SELLERS = [
    {'id': '1', 'name': 'MONICA VARGAS', 'identification': '1192762720', 'status': 'active'},
    {'id': '12', 'name': 'RITA INFANTE', 'identification': '17105692', 'status': 'active'},
    {'id': '8', 'name': 'TATIANA', 'identification': None, 'status': 'inactive'},
]

PERIOD = [
    client_row('1', 'Consumidor final', '222222222222', 10, 1_000_000, 5_000),
    client_row('353', 'Barrios Heidy', '20230261', 4, 400_000),
    client_row('4', 'MONICA  ALEJANDRA VARGAS ', '1192772720', 5, 300_000, 50_000),  # cédula distinta, nombre sí
    client_row('821', 'INFANTE RITA', '17105692', 2, 200_000, 40_000),               # misma cédula
    client_row('900', 'TATIANA PEREZ', '555', 1, 100_000),                            # NO es la vendedora TATIANA
]
SELLER_SALES = [seller_row('1', 'MONICA VARGAS', 12, 1_200_000), seller_row('12', 'RITA INFANTE', 10, 800_000)]
BY_SELLER = {
    '1': [client_row('1', 'Consumidor final', '222222222222', 6, 600_000), client_row('353', 'Barrios Heidy', '20230261', 4, 400_000),
          client_row('4', 'MONICA  ALEJANDRA VARGAS ', '1192772720', 2, 200_000)],
    '12': [client_row('1', 'Consumidor final', '222222222222', 4, 400_000), client_row('821', 'INFANTE RITA', '17105692', 2, 200_000),
           client_row('4', 'MONICA  ALEJANDRA VARGAS ', '1192772720', 3, 100_000), client_row('900', 'TATIANA PEREZ', '555', 1, 100_000)],
}
HISTORY = [client_row('353', 'Barrios Heidy', '20230261', 9, 900_000)]


# ─── Cálculos puros ──────────────────────────────────────────────────────────

def test_resumen_identificado_ranking_y_equipo():
    data = ci.build_summary(PERIOD, SELLER_SALES, SELLERS, BY_SELLER, {'353'})
    k = data['kpis']
    assert k['total_sales'] == 2_000_000 and k['identified_sales'] == 1_000_000
    assert k['identified_pct'] == 50.0
    assert k['identified_documents_pct'] == round(12 * 100 / 22, 1)
    assert k['unique_clients'] == 4
    assert data['anonymous']['total'] == 1_000_000

    assert [c['id'] for c in data['top_by_amount']] == ['353', '4', '821', '900']
    assert [c['id'] for c in data['top_by_frequency']] == ['4', '353', '821', '900']
    assert [c['id'] for c in data['top_by_discount']] == ['4', '821']

    # Las vendedoras siguen en el ranking, marcadas, y se resumen aparte
    by_id = {c['id']: c for c in data['top_by_amount']}
    assert by_id['4']['employee']['seller_name'] == 'MONICA VARGAS'
    assert by_id['821']['employee']['seller_name'] == 'RITA INFANTE'
    assert by_id['900']['employee'] is None  # nombre de una sola palabra no cuenta
    assert data['employees']['total'] == 500_000
    assert data['employees']['share_of_discount_pct'] == round(90_000 * 100 / 95_000, 1)

    sellers = {s['id']: s for s in data['sellers']}
    assert sellers['1']['identified_pct'] == 50.0
    assert sellers['12']['identified_pct'] == 50.0

    nvr = data['new_vs_returning']
    assert nvr['returning_clients'] == 1 and nvr['returning_sales'] == 400_000
    assert nvr['new_clients'] == 3 and nvr['new_sales'] == 600_000


def test_resumen_sin_ventas_tienda_nueva():
    data = ci.build_summary([], [], [], {}, set())
    assert data['kpis']['total_sales'] == 0
    assert data['kpis']['identified_pct'] is None
    assert data['top_by_amount'] == [] and data['sellers'] == []
    assert data['new_vs_returning']['new_clients'] == 0


def test_vendedora_sin_filtro_confiable_queda_sin_porcentaje():
    data = ci.build_summary(PERIOD, SELLER_SALES, SELLERS, {'1': None, '12': BY_SELLER['12']}, None)
    sellers = {s['id']: s for s in data['sellers']}
    assert sellers['1']['identified_available'] is False
    assert sellers['12']['identified_available'] is True
    assert data['new_vs_returning'] is None


def test_inactivas_y_whatsapp():
    before = [client_row('353', 'Barrios Heidy', '20230261', 4, 400_000), client_row('77', 'ANA', '7', 1, 900_000),
              client_row('1', 'Consumidor final', '222222222222', 9, 9_000_000)]
    recent = [client_row('353', 'Barrios Heidy', '20230261', 1, 50_000)]
    inactive = ci.build_inactive(before, recent, SELLERS)
    assert [c['id'] for c in inactive] == ['77']

    assert ci.whatsapp_number('321 486 8471') == '573214868471'
    assert ci.whatsapp_number('+57 321-486-8471') == '573214868471'
    assert ci.whatsapp_number('6085654321') is None  # fijo
    assert ci.contact_phone({'phonePrimary': '6085654321', 'mobile': '3001112233'}) == '3001112233'
    assert ci.contact_phone({'phonePrimary': '6085654321'}) == '6085654321'


# ─── Endpoints ───────────────────────────────────────────────────────────────

@pytest.fixture
def app(tmp_path, monkeypatch):
    monkeypatch.setenv('ALEGRA_USER_CARRENO', 'carreno@test.com')
    monkeypatch.setenv('ALEGRA_PASS_CARRENO', 'tok-carreno')
    monkeypatch.delenv('ALEGRA_USER_PRIMAVERA', raising=False)
    monkeypatch.delenv('ALEGRA_PASS_PRIMAVERA', raising=False)
    ci.clear_cache()

    class InsightsTestConfig(TestingConfig):
        SQLALCHEMY_DATABASE_URI = f"sqlite:///{(tmp_path / 'insights.db').as_posix()}"
        SQLALCHEMY_ENGINE_OPTIONS = {}

    from app import create_app
    yield create_app(InsightsTestConfig)
    ci.clear_cache()


@pytest.fixture
def fake_alegra(monkeypatch):
    calls = []

    def sales_by_client(self, from_date, to_date, seller_id=None):
        calls.append(('clients', self.username, from_date, to_date, seller_id))
        if seller_id:
            return BY_SELLER.get(seller_id, [])
        if from_date == ci.HISTORY_START.isoformat():
            return HISTORY
        return PERIOD

    monkeypatch.setattr(AlegraDirectClient, 'get_sales_by_client', sales_by_client)
    monkeypatch.setattr(AlegraDirectClient, 'get_sales_by_seller', lambda self, f, t: SELLER_SALES)
    monkeypatch.setattr(AlegraDirectClient, 'get_sellers', lambda self: SELLERS)
    monkeypatch.setattr(AlegraDirectClient, 'get_contact', lambda self, cid: {'id': cid, 'mobile': '3214868471'})
    monkeypatch.setattr(AlegraDirectClient, 'get_last_invoice_date', lambda self, cid: '2026-05-10')
    return calls


def _headers(app, role='admin', store=None):
    from app.services.jwt_service import JWTService
    with app.app_context():
        token = JWTService.generate_token(1, f'{role}@test.com', role, None)
    return {'Authorization': f'Bearer {token}', **({'X-Store': store} if store else {})}


def test_summary_endpoint(client, app, fake_alegra):
    res = client.get('/api/analytics/customers/summary?start_date=2026-01-01&end_date=2026-09-30', headers=_headers(app))
    assert res.status_code == 200
    body = res.get_json()
    assert body['store'] == 'carreno'
    assert body['data']['kpis']['identified_pct'] == 50.0
    assert body['data']['new_vs_returning']['returning_clients'] == 1
    # Una consulta por periodo y una por historia (v1 no filtra por vendedora: no se pide)
    assert len(fake_alegra) == 2 and all(c[4] is None for c in fake_alegra)

    # Segunda vez: sale de caché
    client.get('/api/analytics/customers/summary?start_date=2026-01-01&end_date=2026-09-30', headers=_headers(app))
    assert len(fake_alegra) == 2


def test_summary_permisos_y_validacion(client, app, fake_alegra):
    assert client.get('/api/analytics/customers/summary', headers=_headers(app, 'sales')).status_code == 403
    bad = client.get('/api/analytics/customers/summary?start_date=2026-09-30&end_date=2026-01-01', headers=_headers(app))
    assert bad.status_code == 400
    long = client.get('/api/analytics/customers/summary?start_date=2020-01-01&end_date=2026-09-30', headers=_headers(app))
    assert long.status_code == 400


def test_primavera_sin_alegra_configurado(client, app, fake_alegra):
    res = client.get('/api/analytics/customers/summary', headers=_headers(app, store='primavera'))
    assert res.status_code == 503
    assert res.get_json()['code'] == 'alegra_not_configured'
    assert fake_alegra == []


def test_cache_separada_por_tienda(client, app, fake_alegra, monkeypatch):
    monkeypatch.setenv('ALEGRA_USER_PRIMAVERA', 'primavera@test.com')
    monkeypatch.setenv('ALEGRA_PASS_PRIMAVERA', 'tok-primavera')
    url = '/api/analytics/customers/summary?start_date=2026-01-01&end_date=2026-09-30'
    client.get(url, headers=_headers(app, store='carreno'))
    client.get(url, headers=_headers(app, store='primavera'))
    users = {c[1] for c in fake_alegra}
    assert users == {'carreno@test.com', 'primavera@test.com'}


def test_inactive_endpoint(client, app, fake_alegra, monkeypatch):
    before = [client_row('77', 'ANA LOPEZ', '7', 3, 900_000), client_row('353', 'Barrios Heidy', '20230261', 4, 400_000)]
    recent = [client_row('353', 'Barrios Heidy', '20230261', 1, 50_000)]

    # El periodo reciente termina hoy; el anterior, antes.
    monkeypatch.setattr(ci.CustomerInsightsService, '_clients',
                        lambda self, s, e, seller_id=None: recent if e == self.today else before)

    res = client.get('/api/analytics/customers/inactive?days=90', headers=_headers(app))
    assert res.status_code == 200
    data = res.get_json()['data']
    assert data['inactive_count'] == 1
    ana = data['clients'][0]
    assert ana['whatsapp'] == '573214868471' and ana['last_purchase'] == '2026-05-10'
    assert ana['days_since_last_purchase'] > 0

    assert client.get('/api/analytics/customers/inactive?days=7', headers=_headers(app)).status_code == 400


def test_errores_de_alegra(client, app, monkeypatch):
    def unauthorized(self, *a, **k):
        response = requests.Response()
        response.status_code = 401
        raise requests.exceptions.HTTPError(response=response)

    monkeypatch.setattr(AlegraDirectClient, 'get_sales_by_client', unauthorized)
    monkeypatch.setattr(AlegraDirectClient, 'get_sales_by_seller', lambda self, f, t: [])
    monkeypatch.setattr(AlegraDirectClient, 'get_sellers', lambda self: [])
    res = client.get('/api/analytics/customers/summary', headers=_headers(app))
    assert res.status_code == 502 and res.get_json()['code'] == 'alegra_auth'

    def slow(self, *a, **k):
        raise requests.exceptions.Timeout()

    monkeypatch.setattr(AlegraDirectClient, 'get_sales_by_client', slow)
    res = client.get('/api/analytics/customers/summary?start_date=2026-02-01', headers=_headers(app))
    assert res.status_code == 504


def test_paginacion_del_reporte(monkeypatch):
    pages = {0: {'data': [{'idLocal': '1'}, {'idLocal': '2'}], 'metadata': {'total': 3}},
             2: {'data': [{'idLocal': '3'}], 'metadata': {'total': 3}}}
    seen = []

    def fake_request(self, endpoint, params=None):
        seen.append(params)
        return pages[params['start']]

    monkeypatch.setattr(AlegraDirectClient, '_make_request', fake_request)
    rows = AlegraDirectClient('u', 't').get_sales_by_client('2026-01-01', '2026-09-30', seller_id='12')
    assert [r['idLocal'] for r in rows] == ['1', '2', '3']
    assert seen[0]['sellerId'] == '12' and seen[0]['limit'] == AlegraDirectClient.REPORT_PAGE_SIZE


def test_ultima_compra_ignora_factura_de_otro_cliente(monkeypatch):
    monkeypatch.setattr(AlegraDirectClient, '_make_request',
                        lambda self, e, p=None: [{'date': '2026-08-24', 'client': {'id': '999'}}])
    assert AlegraDirectClient('u', 't').get_last_invoice_date('353') is None
    monkeypatch.setattr(AlegraDirectClient, '_make_request',
                        lambda self, e, p=None: [{'date': '2026-08-24', 'client': {'id': '353'}}])
    assert AlegraDirectClient('u', 't').get_last_invoice_date('353') == '2026-08-24'


def test_paginacion_no_queda_en_ciclo_si_alegra_ignora_start(monkeypatch):
    # Reporte: Alegra devuelve siempre la misma página aunque diga que hay más.
    same = {'data': [{'idLocal': '1'}, {'idLocal': '2'}], 'metadata': {'total': 9999}}
    calls = []
    monkeypatch.setattr(AlegraDirectClient, '_make_request', lambda self, e, p=None: calls.append(p) or same)
    rows = AlegraDirectClient('u', 't').get_sales_by_client('2026-01-01', '2026-09-30')
    assert [r['idLocal'] for r in rows] == ['1', '2'] and len(calls) == 2

    # Vendedoras: 30 por página, siempre las mismas.
    thirty = [{'id': str(i), 'name': f'V{i}'} for i in range(30)]
    calls.clear()
    monkeypatch.setattr(AlegraDirectClient, '_make_request', lambda self, e, p=None: calls.append(p) or thirty)
    sellers = AlegraDirectClient('u', 't').get_sellers()
    assert len(sellers) == 30 and len(calls) == 2


def test_contacto_con_error_no_se_guarda_en_cache():
    ci.clear_cache()
    attempts = {'n': 0}

    class FlakyClient:
        def get_contact(self, cid):
            attempts['n'] += 1
            if attempts['n'] == 1:
                raise requests.exceptions.HTTPError('429 Too Many Requests')
            return {'mobile': '3214868471'}

        def get_last_invoice_date(self, cid):
            return '2026-05-10'

    service = ci.CustomerInsightsService(FlakyClient(), 'carreno', date(2026, 10, 1))
    assert service._contact_info('353')['whatsapp'] is None       # falló: no se guarda
    assert service._contact_info('353')['whatsapp'] == '573214868471'  # reintenta y ahora sí
    service._contact_info('353')
    assert attempts['n'] == 2                                       # la buena sí quedó en caché
    ci.clear_cache()


def v1_row(row):
    """Misma fila con los nombres de /api/v1 (Basic): el monto viene en `total`, no en `afterTaxes`."""
    out = {k: v for k, v in row.items() if k not in ('afterTaxes', 'beforeTaxes')}
    out['total'] = row['afterTaxes']
    return out


def test_formato_de_api_v1_con_total_en_vez_de_afterTaxes():
    # Bug visto en producción 2026-10-02: con filas de /api/v1 todo salía en $0.
    period = [v1_row(r) for r in PERIOD]
    sellers_sales = [v1_row(r) for r in SELLER_SALES]
    by_seller = {k: [v1_row(r) for r in rows] for k, rows in BY_SELLER.items()}
    data = ci.build_summary(period, sellers_sales, SELLERS, by_seller, {'353'})
    assert data['kpis']['total_sales'] == 2_000_000
    assert data['kpis']['identified_pct'] == 50.0
    assert data['top_by_amount'][0]['total'] == 400_000
    assert {s['id']: s['identified_pct'] for s in data['sellers']} == {'1': 50.0, '12': 50.0}


    # Un 0 real en `afterTaxes` no debe caer al otro campo
    assert ci.row_amount({'afterTaxes': 0, 'total': 999}) == 0


def test_respuesta_real_de_api_v1():
    """Filas copiadas de la respuesta real de /api/v1 (2026-10-02): sin cédula ni descuento."""
    period = [
        {'idLocal': '1', 'name': 'Consumidor final', 'totalDocuments': 1486, 'subTotal': 170175819, 'total': 170175819},
        {'idLocal': '353', 'name': 'Barrios Heidy', 'totalDocuments': 14, 'subTotal': 2459900, 'total': 2459900},
        {'idLocal': '4', 'name': 'MONICA  ALEJANDRA VARGAS ', 'totalDocuments': 13, 'subTotal': 1311470, 'total': 1311470},
    ]
    sellers_sales = [
        {'idLocal': '1', 'name': 'MONICA VARGAS', 'totalPayed': 201012695, 'subTotal': 201012695,
         'total': 201012695, 'totalDocuments': 1622, 'decimalPrecision': 0},
    ]
    data = ci.build_summary(period, sellers_sales, SELLERS, {}, set())
    assert data['kpis']['total_sales'] == 170175819 + 2459900 + 1311470
    assert data['anonymous']['documents'] == 1486
    assert data['discounts_available'] is False
    assert data['top_by_amount'][0]['identification'] == ''
    assert data['top_by_amount'][1]['employee']['seller_name'] == 'MONICA VARGAS'  # por nombre
    assert data['sellers'][0] == {
        'id': '1', 'name': 'MONICA VARGAS', 'total': 201012695, 'documents': 1622,
        'discount': 0, 'identified_available': False,
    }


# ─── Fase 4.3: resumen con las facturas guardadas ────────────────────────────

def _inv(id_, day, total, client, seller, discount=0, status='closed'):
    return {'id': id_, 'date': day, 'status': status, 'subtotal': total + discount, 'discount': discount,
            'total': total, 'numberTemplate': {'fullNumber': f'KPC{id_}'},
            'client': {'id': client[0], 'name': client[1], 'identification': client[2]} if client else None,
            'seller': {'id': seller[0], 'name': seller[1]} if seller else None}


CF = ('1', 'Consumidor final', '222222222222')
HEIDY = ('353', 'Barrios Heidy', '20230261')
RITA_CLIENT = ('821', 'INFANTE RITA', '17105692')
MONICA = ('1', 'MONICA VARGAS')
RITA = ('12', 'RITA INFANTE')


class FakeInvoices:
    def __init__(self, by_day):
        self.by_day, self.calls = by_day, []

    def get_invoices_by_date(self, day):
        self.calls.append(day)
        return self.by_day.get(day, [])


class FakeDirect:
    def __init__(self):
        self.report_calls = []

    def get_sellers(self):
        return SELLERS

    def get_sales_by_client(self, from_date, to_date, seller_id=None):
        self.report_calls.append((from_date, to_date))
        if from_date == ci.HISTORY_START.isoformat():
            return [client_row('353', 'Barrios Heidy', '20230261', 3, 300_000)]
        return PERIOD

    def get_sales_by_seller(self, from_date, to_date):
        return SELLER_SALES


def test_aggregate_facts_agrupa_por_cliente_y_vendedora():
    facts = [
        {'client_id': None, 'client_name': None, 'client_identification': None, 'seller_id': '1',
         'seller_name': 'MONICA', 'subtotal': 100, 'discount': 0, 'total': 100},
        {'client_id': '353', 'client_name': 'Heidy', 'client_identification': '2023', 'seller_id': '1',
         'seller_name': 'MONICA', 'subtotal': 60, 'discount': 10, 'total': 50},
        {'client_id': '353', 'client_name': 'Heidy', 'client_identification': '2023', 'seller_id': None,
         'seller_name': None, 'subtotal': 30, 'discount': 0, 'total': 30},
    ]
    clients, sellers, by_seller = ci.aggregate_facts(facts)
    by_id = {c['idLocal']: c for c in clients}
    assert by_id['1']['identification'] == ci.ANONYMOUS_IDENTIFICATION  # sin cliente = Consumidor final
    assert by_id['353']['totalDocuments'] == 2 and by_id['353']['discount'] == 10 and by_id['353']['total'] == 80
    assert sellers == [{'idLocal': '1', 'name': 'MONICA', 'identification': None, 'totalDocuments': 2,
                        'subTotal': 160, 'discount': 10, 'total': 150}]
    assert {c['idLocal'] for c in by_seller['1']} == {'1', '353'}


def test_resumen_con_facturas_guardadas_mas_las_de_hoy(app):
    from app.services import invoice_facts as facts_svc
    d1, d2, today = date(2026, 1, 2), date(2026, 1, 3), date(2026, 1, 4)
    with app.app_context():
        stored = FakeInvoices({
            d1.isoformat(): [_inv('1', '2026-01-02', 100_000, CF, MONICA),
                             _inv('2', '2026-01-02', 90_000, HEIDY, MONICA, discount=10_000),
                             _inv('3', '2026-01-02', 50_000, CF, RITA, status='void')],
            d2.isoformat(): [_inv('4', '2026-01-03', 80_000, RITA_CLIENT, RITA, discount=20_000),
                             _inv('5', '2026-01-03', 40_000, CF, None)],
        })
        facts_svc.sync_day(stored, 'carreno', d1)
        facts_svc.sync_day(stored, 'carreno', d2)
        live = FakeInvoices({today.isoformat(): [_inv('6', '2026-01-04', 60_000, CF, RITA)]})
        direct = FakeDirect()
        data = ci.CustomerInsightsService(direct, 'carreno', today, invoices_client=live).summary(d1, today)

    assert data['source'] == 'facts'
    assert live.calls == [today.isoformat()]                     # hoy en vivo
    assert all(c[0] == ci.HISTORY_START.isoformat() for c in direct.report_calls)  # solo la historia
    k = data['kpis']
    assert k['total_sales'] == 100_000 + 90_000 + 80_000 + 40_000 + 60_000  # sin la anulada
    assert k['total_documents'] == 5 and k['total_discount'] == 30_000
    assert data['discounts_available'] is True

    sellers = {s['id']: s for s in data['sellers']}
    assert sellers['1']['identified_pct'] == round(90_000 * 100 / 190_000, 1)   # Mónica: Heidy sí, CF no
    assert sellers['12']['identified_pct'] == round(80_000 * 100 / 140_000, 1)  # Rita: ella sí, CF de hoy no
    assert sellers['12']['discount'] == 20_000
    assert data['unassigned_sales'] == 40_000

    heidy = next(c for c in data['top_by_amount'] if c['id'] == '353')
    assert heidy['identification'] == '20230261' and heidy['discount'] == 10_000
    rita = next(c for c in data['employees']['clients'] if c['id'] == '821')
    assert rita['employee']['seller_name'] == 'RITA INFANTE' and rita['discount_pct'] == 20.0
    assert data['new_vs_returning']['returning_clients'] == 1  # Heidy ya había comprado

    assert [(r['number'], r['discount']) for r in data['discount_invoices']] == [('KPC4', 20_000), ('KPC2', 10_000)]
    assert data['discount_invoices'][0]['employee']['seller_name'] == 'RITA INFANTE'


def test_si_falta_un_dia_usa_el_reporte(app):
    from app.services import invoice_facts as facts_svc
    with app.app_context():
        facts_svc.sync_day(FakeInvoices({}), 'carreno', date(2026, 1, 2))  # falta el 3
        direct = FakeDirect()
        data = ci.CustomerInsightsService(direct, 'carreno', date(2026, 1, 10),
                                          invoices_client=FakeInvoices({})).summary(date(2026, 1, 2), date(2026, 1, 4))
    assert data['source'] == 'report' and data['discount_invoices'] == []
    assert ('2026-01-02', '2026-01-04') in direct.report_calls
