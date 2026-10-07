"""
Tests de la carga de facturas en InvoiceFact (fase 4 del dashboard de
clientes, app/services/invoice_facts.py). Base SQLite temporal; Alegra
simulado con facturas en el formato de /api/v1/invoices.
"""
from datetime import date

import pytest

from app.config import TestingConfig
from app.exceptions import AlegraConnectionError
from app.models.invoice_fact import InvoiceFact, InvoiceSyncDay
from app.services import invoice_facts as svc


def invoice(id_, day, total, client=('353', 'Barrios Heidy', '20230261'), seller=('12', 'RITA INFANTE'),
            discount=0, status='closed', **extra):
    inv = {
        'id': id_, 'date': day, 'status': status, 'subtotal': total + discount, 'discount': discount,
        'tax': 0, 'total': total,
        'numberTemplate': {'prefix': 'KPC', 'number': id_, 'fullNumber': f'KPC{id_}'},
        'client': {'id': client[0], 'name': client[1], 'identification': client[2]} if client else None,
        'seller': {'id': seller[0], 'name': seller[1]} if seller else None,
    }
    inv.update(extra)
    return inv


class FakeAlegra:
    def __init__(self, by_day):
        self.by_day = by_day
        self.calls = []

    def get_invoices_by_date(self, day):
        self.calls.append(day)
        value = self.by_day.get(day, [])
        if isinstance(value, Exception):
            raise value
        return value


@pytest.fixture
def app(tmp_path):
    class FactsTestConfig(TestingConfig):
        SQLALCHEMY_DATABASE_URI = f"sqlite:///{(tmp_path / 'facts.db').as_posix()}"
        SQLALCHEMY_ENGINE_OPTIONS = {}

    from app import create_app
    application = create_app(FactsTestConfig)
    with application.app_context():
        yield application


D1, D2, D3 = date(2026, 1, 2), date(2026, 1, 3), date(2026, 1, 4)


def _facts(store='carreno'):
    return {f.alegra_id: f for f in InvoiceFact.query.filter_by(store_code=store).all()}


def test_factura_a_resumen():
    fact = svc.invoice_to_fact(invoice('12373', '2026-08-24', 166900, discount=10000))
    assert fact == {
        'alegra_id': '12373', 'number': 'KPC12373', 'client_id': '353', 'client_name': 'Barrios Heidy',
        'client_identification': '20230261', 'seller_id': '12', 'seller_name': 'RITA INFANTE',
        'subtotal': 176900, 'discount': 10000, 'total': 166900, 'voided': False,
        'hour': None,  # esta factura de prueba no trae datetime (Fase D2)
        # Reconstrucción 2025: no trae isElectronic, totalPaid ni datetime
        'is_electronic': None, 'total_paid': None, 'issued_at': None,
    }
    # Sin vendedora ni cliente
    bare = svc.invoice_to_fact(invoice('1', '2026-08-24', 5000, client=None, seller=None))
    assert bare['seller_id'] is None and bare['client_id'] is None
    # Anulada
    assert svc.invoice_to_fact(invoice('2', '2026-08-24', 5000, status='void'))['voided'] is True


def test_descuento_por_item_si_no_viene_en_la_factura():
    inv = invoice('3', '2026-08-24', 90000)
    del inv['discount'], inv['subtotal']
    inv['items'] = [{'price': 50000, 'quantity': 2, 'discount': 10}]  # 10 % de 100.000
    fact = svc.invoice_to_fact(inv)
    assert fact['discount'] == 10000 and fact['subtotal'] == 100000


def test_cargar_un_dia_y_volver_a_cargarlo_lo_reemplaza(app):
    alegra = FakeAlegra({D1.isoformat(): [invoice('1', D1.isoformat(), 100000), invoice('2', D1.isoformat(), 50000)]})
    assert svc.sync_day(alegra, 'carreno', D1) == 2
    assert set(_facts()) == {'1', '2'}
    assert InvoiceSyncDay.query.filter_by(store_code='carreno', date=D1).one().invoice_count == 2

    # En Alegra: la 2 se anuló y la 1 desapareció (ej. se movió de día)
    alegra.by_day[D1.isoformat()] = [invoice('2', D1.isoformat(), 50000, status='void')]
    assert svc.sync_day(alegra, 'carreno', D1) == 1
    facts = _facts()
    assert set(facts) == {'2'} and facts['2'].voided is True
    assert InvoiceSyncDay.query.filter_by(store_code='carreno').count() == 1


def test_si_alegra_falla_no_se_borra_lo_que_habia(app):
    alegra = FakeAlegra({D1.isoformat(): [invoice('1', D1.isoformat(), 100000)]})
    svc.sync_day(alegra, 'carreno', D1)
    alegra.by_day[D1.isoformat()] = AlegraConnectionError('Alegra caído')
    with pytest.raises(AlegraConnectionError):
        svc.sync_day(alegra, 'carreno', D1)
    assert set(_facts()) == {'1'}


def test_factura_que_cambio_de_fecha_no_se_duplica(app):
    alegra = FakeAlegra({D1.isoformat(): [invoice('7', D1.isoformat(), 100000)]})
    svc.sync_day(alegra, 'carreno', D1)
    alegra.by_day = {D1.isoformat(): [], D2.isoformat(): [invoice('7', D2.isoformat(), 100000)]}
    svc.sync_day(alegra, 'carreno', D2)
    facts = _facts()
    assert len(facts) == 1 and facts['7'].date == D2


def test_tiendas_separadas(app):
    # Cada tienda tiene su propia cuenta de Alegra: el mismo id puede repetirse
    svc.sync_day(FakeAlegra({D1.isoformat(): [invoice('1', D1.isoformat(), 100000)]}), 'carreno', D1)
    svc.sync_day(FakeAlegra({D1.isoformat(): [invoice('1', D1.isoformat(), 7000)]}), 'primavera', D1)
    assert _facts('carreno')['1'].total == 100000
    assert _facts('primavera')['1'].total == 7000
    # Volver a cargar Carreño no toca Primavera
    svc.sync_day(FakeAlegra({}), 'carreno', D1)
    assert _facts('carreno') == {} and _facts('primavera')['1'].total == 7000


def test_rango_se_detiene_en_el_primer_error_y_se_puede_continuar(app):
    alegra = FakeAlegra({
        D1.isoformat(): [invoice('1', D1.isoformat(), 100000)],
        D2.isoformat(): AlegraConnectionError('Timeout'),
        D3.isoformat(): [invoice('3', D3.isoformat(), 30000)],
    })
    assert svc.missing_days('carreno', D1, D3) == [D1, D2, D3]

    result = svc.sync_range(alegra, 'carreno', svc.missing_days('carreno', D1, D3))
    assert result['synced_days'] == [D1.isoformat()] and result['failed_day'] == D2.isoformat()
    assert result['error'] == 'Timeout'
    assert D3.isoformat() not in alegra.calls  # no siguió después del error

    alegra.by_day[D2.isoformat()] = []  # día sin ventas
    result = svc.sync_range(alegra, 'carreno', svc.missing_days('carreno', D1, D3))
    assert result == {'synced_days': [D2.isoformat(), D3.isoformat()], 'invoices': 1,
                      'failed_day': None, 'error': None, 'stopped_by_time': False}
    assert svc.missing_days('carreno', D1, D3) == []


def test_rango_se_detiene_al_llegar_al_limite_de_tiempo(app):
    alegra = FakeAlegra({})
    result = svc.sync_range(alegra, 'carreno', [D1, D2], deadline=0)  # ya vencido
    assert result['stopped_by_time'] is True and result['synced_days'] == [] and alegra.calls == []


def test_estado_de_la_carga_y_calidad_de_los_datos(app):
    alegra = FakeAlegra({D1.isoformat(): [
        invoice('1', D1.isoformat(), 90000, discount=10000),
        invoice('2', D1.isoformat(), 50000, client=('1', 'Consumidor final', None), seller=None),
        invoice('3', D1.isoformat(), 70000, status='void'),
    ]})
    svc.sync_day(alegra, 'carreno', D1)
    status = svc.coverage_status('carreno', D1, D3)
    assert status['total_days'] == 3 and status['loaded_days'] == 1 and status['missing_days'] == 2
    assert status['next_missing_day'] == D3.isoformat() and status['invoices'] == 3  # del más reciente al más antiguo
    assert status['quality'] == {
        'active_invoices': 2, 'voided_invoices': 1, 'with_seller': 1, 'with_identification': 1,
        'with_discount': 1, 'total': 140000, 'discount': 10000,
    }
    assert svc.coverage_status('primavera', D1, D3)['loaded_days'] == 0


# ─── Endpoints ───────────────────────────────────────────────────────────────

from app.config import Config  # noqa: E402
from app.routes import invoice_facts as routes  # noqa: E402
from app.services.alegra_client import AlegraClient  # noqa: E402


@pytest.fixture
def api(tmp_path, monkeypatch):
    monkeypatch.setenv('ALEGRA_USER_CARRENO', 'carreno@test.com')
    monkeypatch.setenv('ALEGRA_PASS_CARRENO', 'tok-carreno')
    monkeypatch.delenv('ALEGRA_USER_PRIMAVERA', raising=False)
    monkeypatch.delenv('ALEGRA_PASS_PRIMAVERA', raising=False)
    monkeypatch.setattr(Config, 'DAILY_SYNC_TOKEN', 'cron-secret')
    calls = []

    def fake_invoices(self, day):
        calls.append((self.username, day))
        return [invoice(f'{day}-1', day, 10000)]

    monkeypatch.setattr(AlegraClient, 'get_invoices_by_date', fake_invoices)

    class ApiTestConfig(TestingConfig):
        SQLALCHEMY_DATABASE_URI = f"sqlite:///{(tmp_path / 'facts_api.db').as_posix()}"
        SQLALCHEMY_ENGINE_OPTIONS = {}

    from app import create_app
    application = create_app(ApiTestConfig)
    return application, application.test_client(), calls


def _auth(app, role='admin', store=None):
    from app.services.jwt_service import JWTService
    with app.app_context():
        token = JWTService.generate_token(1, f'{role}@test.com', role, None)
    return {'Authorization': f'Bearer {token}', **({'X-Store': store} if store else {})}


def _days_back(n_from, count):
    """Fechas desde hace `n_from` días hacia atrás (la carga va del más reciente al más antiguo)."""
    from datetime import timedelta
    from app.utils.timezone import get_colombia_now
    today = get_colombia_now().date()
    return [(today - timedelta(days=n_from + i)).isoformat() for i in range(count)]


def test_sync_carga_la_siguiente_tanda_desde_lo_mas_reciente(api):
    app, client, calls = api
    res = client.post('/api/analytics/invoice-facts/sync', json={'max_days': 3}, headers=_auth(app))
    assert res.status_code == 200
    body = res.get_json()
    assert body['backfill']['synced_days'] == _days_back(1, 3)  # ayer, antier, ...
    assert body['status']['loaded_days'] == 3 and body['status']['next_missing_day'] == _days_back(4, 1)[0]

    # La siguiente llamada sigue donde quedó
    body = client.post('/api/analytics/invoice-facts/sync', json={'max_days': 2}, headers=_auth(app)).get_json()
    assert body['backfill']['synced_days'] == _days_back(4, 2)

    status = client.get('/api/analytics/invoice-facts/status', headers=_auth(app)).get_json()['data']
    assert status['loaded_days'] == 5 and status['invoices'] == 5 and status['quality']['with_seller'] == 5


def test_cron_con_token_recarga_los_dias_recientes_de_su_tienda(api, monkeypatch):
    app, client, calls = api
    monkeypatch.setenv('ALEGRA_USER_PRIMAVERA', 'primavera@test.com')
    monkeypatch.setenv('ALEGRA_PASS_PRIMAVERA', 'tok-primavera')
    headers = {'X-Sync-Token': 'cron-secret', 'X-Store': 'primavera'}
    res = client.post('/api/analytics/invoice-facts/sync', json={'recent_days': 3, 'max_days': 0}, headers=headers)
    assert res.status_code == 200
    body = res.get_json()
    assert body['store'] == 'primavera' and len(body['recent']['synced_days']) == 3
    assert body['backfill']['synced_days'] == []
    assert {u for u, _ in calls} == {'primavera@test.com'}
    with app.app_context():
        assert InvoiceFact.query.filter_by(store_code='carreno').count() == 0

    # Token equivocado: pide JWT admin
    bad = client.post('/api/analytics/invoice-facts/sync', json={}, headers={'X-Sync-Token': 'otro'})
    assert bad.status_code == 401


def test_sync_validaciones_permisos_y_tienda_sin_alegra(api):
    app, client, _ = api
    assert client.post('/api/analytics/invoice-facts/sync', json={}, headers=_auth(app, 'sales')).status_code == 403
    assert client.get('/api/analytics/invoice-facts/status', headers=_auth(app, 'sales')).status_code == 403
    assert client.post('/api/analytics/invoice-facts/sync', json={'max_days': 99},
                       headers=_auth(app)).status_code == 400
    res = client.post('/api/analytics/invoice-facts/sync', json={}, headers=_auth(app, store='primavera'))
    assert res.status_code == 503 and res.get_json()['code'] == 'alegra_not_configured'


def test_sync_reporta_error_de_alegra_sin_perder_lo_cargado(api, monkeypatch):
    app, client, _ = api
    client.post('/api/analytics/invoice-facts/sync', json={'max_days': 2}, headers=_auth(app))

    def broken(self, day):
        raise AlegraConnectionError('Alegra caído')

    monkeypatch.setattr(AlegraClient, 'get_invoices_by_date', broken)
    res = client.post('/api/analytics/invoice-facts/sync', json={'max_days': 5}, headers=_auth(app))
    assert res.status_code == 502
    body = res.get_json()
    assert body['message'] == 'Alegra caído' and body['backfill']['failed_day'] == _days_back(3, 1)[0]
    assert body['status']['loaded_days'] == 2


def test_sync_respeta_el_limite_de_tiempo(api, monkeypatch):
    app, client, _ = api
    monkeypatch.setattr(routes, 'TIME_BUDGET_SECONDS', 0)
    body = client.post('/api/analytics/invoice-facts/sync', json={'max_days': 5}, headers=_auth(app)).get_json()
    assert body['backfill']['stopped_by_time'] is True and body['backfill']['synced_days'] == []


# ─── Correcciones tras la prueba en producción (2026-10-02) ──────────────────

def test_segunda_carga_simultanea_recibe_409_sin_tocar_nada(api, monkeypatch):
    # En producción: clic en "Cargar siguiente tanda" mientras la primera
    # seguía corriendo en el servidor -> choque por unicidad (tienda, alegra_id).
    from contextlib import contextmanager
    app, client, calls = api

    @contextmanager
    def busy(store_code):
        yield False

    monkeypatch.setattr(svc, 'store_sync_lock', busy)
    res = client.post('/api/analytics/invoice-facts/sync', json={'max_days': 3}, headers=_auth(app))
    assert res.status_code == 409
    body = res.get_json()
    assert body['code'] == 'sync_in_progress' and body['status']['loaded_days'] == 0
    assert calls == []


def test_factura_repetida_en_la_respuesta_se_guarda_una_vez(app):
    repeated = [invoice('9', D1.isoformat(), 1000), invoice('9', D1.isoformat(), 1000)]
    assert svc.sync_day(FakeAlegra({D1.isoformat(): repeated}), 'carreno', D1) == 1


def test_error_interno_no_expone_detalle_tecnico(app, monkeypatch):
    def boom(alegra_client, store_code, day):
        raise RuntimeError('(psycopg.errors.UniqueViolation) duplicate key value ... SQL: INSERT ...')

    monkeypatch.setattr(svc, 'sync_day', boom)
    result = svc.sync_range(FakeAlegra({}), 'carreno', [D1])
    assert result['error'] == 'No se pudieron guardar las facturas de ese día'
    assert result['failed_day'] == D1.isoformat()
