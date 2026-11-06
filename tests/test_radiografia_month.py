"""
Tests de la Radiografía del mes (Fase 1 de docs/PLAN_RADIOGRAFIA.md): estado de
resultados con costo estimado, clasificación de salidas, "lo que quedó" igual a
la ganancia real de Cuentas → Año, punto de equilibrio, comparación por los
mismos días, mes en curso, mes sin gastos, por tienda y solo lectura.

Base SQLite temporal, sin red.
"""
from datetime import date, datetime

import pytest

from app.config import TestingConfig


@pytest.fixture
def app(tmp_path):
    class RadioTestConfig(TestingConfig):
        SQLALCHEMY_DATABASE_URI = f"sqlite:///{(tmp_path / 'radio.db').as_posix()}"
        SQLALCHEMY_ENGINE_OPTIONS = {}

    from app import create_app
    return create_app(RadioTestConfig)


@pytest.fixture
def h(app):
    from app.services.jwt_service import JWTService
    with app.app_context():
        token = JWTService.generate_token(1, 'admin1@test.com', 'admin', None)
        viewer = JWTService.generate_token(2, 'viewer@test.com', 'viewer', None)

    def headers(store=None, role='admin'):
        return {'Authorization': f'Bearer {token if role == "admin" else viewer}',
                **({'X-Store': store} if store else {})}
    return headers


def _today(monkeypatch, d):
    import app.routes.radiografia as routes
    import app.routes.monthly_summary as ms
    monkeypatch.setattr(routes, 'get_colombia_now', lambda: datetime(d.year, d.month, d.day, 12, 0))
    monkeypatch.setattr(ms, 'get_colombia_now', lambda: datetime(d.year, d.month, d.day, 12, 0))


def _seed(app, store='carreno'):
    """Octubre: 31 días cargados; 2 ventas el 5 y 1 el 20; noviembre: 1 venta el 3."""
    from app.models.user import db
    from app.models.invoice_fact import InvoiceFact, InvoiceItemFact, InvoiceSyncDay
    with app.app_context():
        for d in range(1, 32):
            db.session.add(InvoiceSyncDay(store_code=store, date=date(2026, 10, d), invoice_count=0, items_synced=True))
        for d in range(1, 31):
            db.session.add(InvoiceSyncDay(store_code=store, date=date(2026, 9, d), invoice_count=0, items_synced=True))
        for d in range(1, 6):
            db.session.add(InvoiceSyncDay(store_code=store, date=date(2026, 11, d), invoice_count=0, items_synced=True))
        rows = [('a', date(2026, 10, 5), 900000, False), ('b', date(2026, 10, 5), 100000, False),
                ('c', date(2026, 10, 20), 1000000, False), ('x', date(2026, 10, 21), 555, True),
                ('s', date(2026, 9, 3), 800000, False), ('n', date(2026, 11, 3), 500000, False)]
        for aid, d, total, voided in rows:
            db.session.add(InvoiceFact(store_code=store, alegra_id=f'{store}{aid}', date=d, total=total, voided=voided))
        items = [('a', date(2026, 10, 5), 'BUZO CAPOTA', 2, 500000), ('a', date(2026, 10, 5), 'BOLSA PAPEL', 1, 1000),
                 ('b', date(2026, 10, 5), 'SHORT', 1, 100000), ('c', date(2026, 10, 20), 'JEAN', 4, 300000),
                 ('s', date(2026, 9, 3), 'JEAN', 2, 400000), ('n', date(2026, 11, 3), 'BLUSA', 1, 500000)]
        for i, (aid, d, name, qty, price) in enumerate(items):
            db.session.add(InvoiceItemFact(store_code=store, invoice_alegra_id=f'{store}{aid}', line=i, date=d,
                                           name=name, quantity=qty, unit_price=price, total=qty * price))
        db.session.commit()


def _exp(client, headers, **p):
    base = {'date': '2026-10-10', 'concept': 'x'}
    base.update(p)
    resp = client.post('/api/expenses', headers=headers, json=base)
    assert resp.status_code == 201, resp.get_json()


def _month(client, headers, y=2026, m=10, **q):
    extra = ''.join(f'&{k}={v}' for k, v in q.items())
    return client.get(f'/api/radiografia/month?year={y}&month={m}{extra}', headers=headers).get_json()['month']


def test_estado_de_resultados_y_lo_que_quedo_igual_a_anio(app, client, h, monkeypatch):
    _today(monkeypatch, date(2026, 11, 6))
    _seed(app)
    _exp(client, h(), subcategory='arriendo', efectivo=1052000)          # operativo
    _exp(client, h(), subcategory='sueldos_empleadas_1', efectivo=1500000)  # sueldo
    _exp(client, h(), subcategory='flete', qr=100000)                    # flete con 4x1000 = 100.400
    _exp(client, h(), subcategory='cuota_banco', efectivo=500000)         # cuota: no baja la utilidad neta
    _exp(client, h(), subcategory='ganancia_jose', efectivo=1000000)      # retiro: no baja nada
    _exp(client, h(), subcategory='inversion', efectivo=300000)           # inversión: no baja nada
    client.post('/api/repurchase', headers=h(), json={'date': '2026-10-08', 'qr': 1000000})  # 4x1000 = 4.000

    m = _month(client, h())
    s = m['statement']
    assert s['ventas'] == 2000000                          # sin la anulada
    assert s['precio_lista'] == 2 * 500000 + 100000 + 4 * 300000   # sin la bolsa
    assert m['indicators']['unidades'] == 7
    assert s['descuentos'] == 2300000 - 2000000
    assert s['costo_estimado'] == pytest.approx(2300000 * 0.65)
    assert s['fletes'] == 100400
    assert s['gastos_operativos'] == 1052000 + 1500000
    assert s['gastos_financieros'] == 4000                 # 4x1000 de la recompra
    assert s['cuotas'] == 500000
    assert s['utilidad_neta'] == pytest.approx(2000000 - 2300000 * 0.65 - 100400 - 2552000 - 4000)
    assert m['has_expenses'] is True and m['in_progress'] is False

    # "Lo que quedó" = ganancia real de Cuentas → Año (misma regla)
    year = client.get('/api/monthly-summary?year=2026', headers=h()).get_json()['months'][9]
    assert s['lo_que_quedo'] == pytest.approx(year['ganancia_real'])
    assert s['recompras'] == year['recompras']

    classes = {o['class']: o for o in m['outflows']}
    assert classes['retiro_socio']['reduces_utility'] is False and classes['retiro_socio']['total'] == 1000000
    assert classes['inversion']['reduces_what_is_left'] is False
    assert classes['cuota_credito']['reduces_utility'] is False and classes['cuota_credito']['reduces_what_is_left'] is True

    ind = m['indicators']
    assert ind['transacciones'] == 3 and ind['ticket'] == pytest.approx(2000000 / 3)
    assert ind['nomina_ventas_pct'] == pytest.approx(1500000 / 2000000)
    # Septiembre completo contra octubre completo
    prev = m['comparisons']['previous_month']
    assert prev['range'] == ['2026-09-01', '2026-09-30']
    assert prev['ventas']['value'] == 800000 and prev['ventas']['change_pct'] == pytest.approx(1.5)
    # 2025 sin datos: no se compara
    assert m['comparisons']['last_year']['ventas']['value'] is None


def test_punto_de_equilibrio_con_gastos_fijos(app, client, h, monkeypatch):
    _today(monkeypatch, date(2026, 11, 6))
    _seed(app)
    client.post('/api/expenses/fixed', headers=h(), json={'name': 'Arriendo', 'amount': 1052000, 'subcategory': 'arriendo'})
    client.post('/api/expenses/fixed', headers=h(), json={'name': 'Ganancia José', 'amount': 1000000, 'subcategory': 'ganancia_jose'})
    client.post('/api/expenses/fixed', headers=h(), json={'name': 'Cuota', 'amount': 500000, 'subcategory': 'cuota_banco'})
    _exp(client, h(), subcategory='arriendo', efectivo=100)
    m = _month(client, h(), target=1000000)
    be = m['break_even']
    assert be['fixed_costs'] == 1052000                    # sin retiros de socios ni cuotas
    assert be['fixed_cuotas'] == 500000
    contrib = (2000000 - 2300000 * 0.65) / 2000000
    assert be['contribution_pct'] == pytest.approx(contrib)
    assert be['month'] == pytest.approx(1052000 / contrib)
    assert be['day'] == pytest.approx(1052000 / contrib / 31)
    assert be['month_with_cuotas'] == pytest.approx(1552000 / contrib)
    assert be['sales_for_target'] == pytest.approx(2052000 / contrib)
    assert be['progress_pct'] == pytest.approx(2000000 / (1052000 / contrib))


def test_mes_en_curso_mismos_dias_y_ritmo(app, client, h, monkeypatch):
    _today(monkeypatch, date(2026, 11, 6))
    _seed(app)
    m = _month(client, h(), m=11)
    assert m['in_progress'] is True and m['data_until'] == '2026-11-05'
    assert m['days_elapsed'] == 5
    prev = m['comparisons']['previous_month']
    assert prev['range'] == ['2026-10-01', '2026-10-05']   # mismos días de octubre
    assert prev['ventas']['value'] == 1000000
    assert m['break_even']['pace_month'] == pytest.approx(500000 / 5 * 30)
    assert m['has_expenses'] is False
    assert any('No hay gastos' in w for w in m['warnings'])
    assert m['indicators']['gastos_ventas_pct'] is None    # sin gastos no se inventa
    assert m['comparisons']['previous_month_closed'] is None


def test_division_por_cero_mes_vacio_y_tiendas_separadas(app, client, h, monkeypatch):
    _today(monkeypatch, date(2026, 11, 6))
    _seed(app)
    m = _month(client, h('primavera'))
    assert m['statement']['ventas'] == 0
    assert m['indicators']['ticket'] is None and m['statement']['margen_bruto_pct'] is None
    assert m['break_even']['month'] is None
    assert any('no hay facturas' in w.lower() for w in m['warnings'])
    assert _month(client, h(), m=12)['future'] is True
    assert client.get('/api/radiografia/month?year=2025&month=10', headers=h()).status_code == 400


def test_viewer_puede_ver(app, client, h, monkeypatch):
    _today(monkeypatch, date(2026, 11, 6))
    _seed(app)
    resp = client.get('/api/radiografia/month?year=2026&month=10', headers=h(role='viewer'))
    assert resp.status_code == 200
