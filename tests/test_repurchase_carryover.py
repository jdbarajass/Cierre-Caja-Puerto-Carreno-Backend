"""
Tests del arrastre automático del balance de Cuentas Recompras: lo que le
queda disponible a Jhonatan al cerrar un mes (enviado + sobrante manual -
compras) se suma solo al mes siguiente, desde CARRYOVER_START (sep-2026).
Ver _carryover_before en app/routes/repurchase.py.

Base SQLite temporal (nunca instance/cierre_caja.db), sin red.
"""
import pytest

from app.config import TestingConfig


@pytest.fixture
def app(tmp_path):
    class CarryoverTestConfig(TestingConfig):
        SQLALCHEMY_DATABASE_URI = f"sqlite:///{(tmp_path / 'carryover.db').as_posix()}"
        SQLALCHEMY_ENGINE_OPTIONS = {}

    from app import create_app
    return create_app(CarryoverTestConfig)


@pytest.fixture
def headers(app):
    from app.services.jwt_service import JWTService
    with app.app_context():
        token = JWTService.generate_token(1, 'admin1@test.com', 'admin', None)
    return lambda store=None: {
        'Authorization': f'Bearer {token}', **({'X-Store': store} if store else {})
    }


def _envio(client, h, date, efectivo=0, sobrante=0):
    resp = client.post('/api/repurchase', headers=h, json={
        'date': date, 'efectivo': efectivo, 'sobrante_mes_anterior': sobrante,
    })
    assert resp.status_code == 201


def _compra(client, h, date, amount):
    resp = client.post('/api/repurchase/purchases', headers=h, json={
        'date': date, 'store': 'Proveedor', 'amount': amount,
    })
    assert resp.status_code == 201


def _mes(client, h, year, month):
    return client.get(f'/api/repurchase?year={year}&month={month}', headers=h).get_json()


def test_septiembre_no_arrastra_y_octubre_trae_su_sobrante(client, headers):
    h = headers()
    _envio(client, h, '2026-08-10', efectivo=999000)   # antes del arranque: no cuenta
    _envio(client, h, '2026-09-05', efectivo=3000000, sobrante=500000)
    _compra(client, h, '2026-09-20', 2800000)
    _envio(client, h, '2026-10-05', efectivo=2710000)

    sep = _mes(client, h, 2026, 9)
    assert sep['carryover_active'] is False
    assert sep['saldo_mes_anterior'] == 0

    octubre = _mes(client, h, 2026, 10)
    assert octubre['carryover_active'] is True
    assert octubre['saldo_mes_anterior'] == 3000000 + 500000 - 2800000  # 700.000
    # Los totales del mes no cambian: el arrastre va aparte.
    assert octubre['totals']['total_enviado'] == 2710000


def test_arrastre_encadena_meses_y_suma_el_manual(client, headers):
    h = headers()
    _envio(client, h, '2026-09-05', efectivo=1000000)
    _compra(client, h, '2026-09-25', 400000)          # sep deja 600.000
    _envio(client, h, '2026-10-05', efectivo=2000000, sobrante=100000)
    _compra(client, h, '2026-10-20', 2500000)         # oct: 600 + 2.100 - 2.500 = 200.000

    assert _mes(client, h, 2026, 11)['saldo_mes_anterior'] == 200000
    # Un mes sin movimientos sigue arrastrando el mismo saldo.
    assert _mes(client, h, 2026, 12)['saldo_mes_anterior'] == 200000


def test_saldo_negativo_si_gasto_de_mas(client, headers):
    h = headers()
    _envio(client, h, '2026-09-05', efectivo=500000)
    _compra(client, h, '2026-09-25', 800000)
    assert _mes(client, h, 2026, 10)['saldo_mes_anterior'] == -300000


def test_arrastre_por_tienda(client, headers):
    _envio(client, headers('primavera'), '2026-09-05', efectivo=1000000)
    assert _mes(client, headers('primavera'), 2026, 10)['saldo_mes_anterior'] == 1000000
    assert _mes(client, headers(), 2026, 10)['saldo_mes_anterior'] == 0
