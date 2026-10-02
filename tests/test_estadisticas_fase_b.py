"""
Fase B de Estadísticas (docs/PLAN_ESTADISTICAS.md): AlegraClient.get_all_invoices_in_range
(Productos, Analytics, Ventas Mensuales, Comparativo de tiendas) ya no salta días
en silencio: los informa en `last_failed_days`, en el header X-Alegra-Failed-Days
y, en el comparativo, por tienda.
"""
import pytest

from app.config import TestingConfig
from app.exceptions import AlegraConnectionError
from app.services.alegra_client import AlegraClient
from tests.test_estadisticas_fase_a import SEP_30, invoice, RITA

FAIL_DAY = '2026-09-29'


def _fake_by_date(self, date):
    date = str(date)
    if date == FAIL_DAY:
        raise AlegraConnectionError('Error del servidor de Alegra (HTTP 503)')
    if date == '2026-09-30':
        return SEP_30
    if date == '2026-09-28':
        return [invoice(12900, RITA, 150_000, day='2026-09-28')]
    return []


@pytest.fixture
def app(tmp_path, monkeypatch):
    monkeypatch.setenv('ALEGRA_USER_CARRENO', 'carreno@test.com')
    monkeypatch.setenv('ALEGRA_PASS_CARRENO', 'tok-carreno')
    monkeypatch.delenv('ALEGRA_USER_PRIMAVERA', raising=False)
    monkeypatch.delenv('ALEGRA_PASS_PRIMAVERA', raising=False)
    monkeypatch.setattr(AlegraClient, 'get_invoices_by_date', _fake_by_date)

    class FaseBTestConfig(TestingConfig):
        SQLALCHEMY_DATABASE_URI = f"sqlite:///{(tmp_path / 'fase_b.db').as_posix()}"
        SQLALCHEMY_ENGINE_OPTIONS = {}

    from app import create_app
    return create_app(FaseBTestConfig)


def _headers(app, origin=None):
    from app.services.jwt_service import JWTService
    with app.app_context():
        token = JWTService.generate_token(1, 'admin@test.com', 'admin', None)
    return {'Authorization': f'Bearer {token}', **({'Origin': origin} if origin else {})}


def test_rango_reporta_dia_fallido_sin_perder_los_demas(monkeypatch):
    monkeypatch.setattr(AlegraClient, 'get_invoices_by_date', _fake_by_date)
    client = AlegraClient('carreno@test.com', 'tok', 'https://api.alegra.com/api/v1')
    invoices = client.get_all_invoices_in_range('2026-09-28', '2026-09-30')
    assert len(invoices) == 15
    assert client.last_failed_days == [FAIL_DAY]


def test_analytics_avisa_dias_faltantes_en_header(client, app):
    origin = app.config['ALLOWED_ORIGINS'][0]
    res = client.get('/api/analytics/top-customers?start_date=2026-09-28&end_date=2026-09-30',
                     headers=_headers(app, origin))
    assert res.status_code == 200
    assert res.headers['X-Alegra-Failed-Days'] == FAIL_DAY
    # El navegador solo deja leer el header si está expuesto por CORS
    assert 'X-Alegra-Failed-Days' in res.headers['Access-Control-Expose-Headers']


def test_sin_fallos_no_hay_header(client, app):
    res = client.get('/api/analytics/top-customers?start_date=2026-09-30&end_date=2026-09-30',
                     headers=_headers(app))
    assert res.status_code == 200
    assert 'X-Alegra-Failed-Days' not in res.headers


def test_productos_avisa_dias_faltantes(client, app):
    res = client.get('/api/products/summary?start_date=2026-09-28&end_date=2026-09-30', headers=_headers(app))
    assert res.status_code == 200
    assert res.headers['X-Alegra-Failed-Days'] == FAIL_DAY


def test_comparativo_marca_tienda_incompleta(client, app):
    res = client.get('/api/stores/comparison?start_date=2026-09-28&end_date=2026-09-30', headers=_headers(app))
    assert res.status_code == 200, res.get_json()
    carreno = {s['code']: s for s in res.get_json()['stores']}['carreno']['sales']
    assert carreno['failed_days'] == [FAIL_DAY]
    assert carreno['total'] == 150_000 + 568_200 + 323_745
