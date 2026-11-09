"""
Tests de la Radiografía del año (Fase 2 de docs/PLAN_RADIOGRAFIA.md): cada mes
cuadra con Cuentas → Año (también con cifras escritas a mano), meses sin gastos
no inventan utilidad, inventario a costo, totales y promedios, por tienda.

Base SQLite temporal, sin red. Reusa la siembra de test_radiografia_month.
"""
from datetime import date, datetime

import pytest

from tests.test_radiografia_month import _exp, _seed, app, h  # noqa: F401  (fixtures)


def _today(monkeypatch, d):
    import app.routes.radiografia as routes
    import app.routes.monthly_summary as ms
    monkeypatch.setattr(routes, 'get_colombia_now', lambda: datetime(d.year, d.month, d.day, 12, 0))
    monkeypatch.setattr(ms, 'get_colombia_now', lambda: datetime(d.year, d.month, d.day, 12, 0))


def _year(client, headers, y=2026):
    resp = client.get(f'/api/radiografia/year?year={y}', headers=headers)
    assert resp.status_code == 200, resp.get_json()
    return resp.get_json()['year']


def _anio(client, headers):
    return client.get('/api/monthly-summary?year=2026', headers=headers).get_json()


def _override(client, headers, period, field, value):
    resp = client.put('/api/monthly-summary/override', headers=headers,
                      json={'period': period, 'field': field, 'value': value, 'note': 'prueba'})
    assert resp.status_code == 200


def test_cada_mes_cuadra_con_anio(app, client, h, monkeypatch):
    _today(monkeypatch, date(2026, 11, 6))
    _seed(app)
    _exp(client, h(), subcategory='arriendo', efectivo=1052000)
    _exp(client, h(), subcategory='flete', qr=100000)
    _exp(client, h(), subcategory='cuota_banco', efectivo=500000)
    client.post('/api/repurchase', headers=h(), json={'date': '2026-10-08', 'qr': 1000000})

    y = _year(client, h())
    anio = _anio(client, h())
    assert len(y['months']) == 12 and y['months'][11]['future'] is True
    for rm, am in zip(y['months'], anio['months']):
        if rm['future']:
            continue
        assert rm['ventas'] == am['ventas']
        assert rm['recompras'] == am['recompras']
        if am['period'] >= '2026-09':
            assert rm['lo_que_quedo'] == pytest.approx(am['ganancia_real'])
    assert y['totals']['lo_que_quedo'] == pytest.approx(anio['totals']['ganancia_real'])

    oct_ = y['months'][9]
    assert oct_['precio_lista'] == 2400000 and oct_['costo_estimado'] == pytest.approx(2400000 * 0.65)
    assert oct_['utilidad_neta'] == pytest.approx(2000000 - 2400000 * 0.65 - 100400 - 1052000 - 4000)
    assert oct_['cuotas'] == 500000 and oct_['has_expenses'] is True
    assert oct_['transacciones'] == 3


def test_mes_sin_gastos_no_inventa_utilidad_y_promedios(app, client, h, monkeypatch):
    _today(monkeypatch, date(2026, 11, 6))
    _seed(app)
    _exp(client, h(), subcategory='arriendo', efectivo=1000000)          # solo octubre tiene gastos
    y = _year(client, h())
    sep, oct_, nov = y['months'][8], y['months'][9], y['months'][10]
    assert sep['has_data'] and not sep['has_expenses']
    assert sep['utilidad_neta'] is None and sep['utilidad_bruta'] == pytest.approx(800000 - 800000 * 0.65)
    assert sep['lo_que_quedo'] == 800000                                 # igual que Año (sin gastos)
    assert y['months'][0]['has_data'] is False                           # enero sin facturas
    # Utilidad neta total: solo meses con gastos
    assert y['totals']['utilidad_neta'] == pytest.approx(oct_['utilidad_neta'])
    assert y['totals']['ventas'] == 800000 + 2000000 + 500000
    # Promedios: meses cerrados (nov en curso no entra)
    assert nov['in_progress'] is True
    assert y['averages']['months'] == 2
    assert y['averages']['ventas'] == pytest.approx((800000 + 2000000) / 2)
    assert y['averages']['utilidad_neta'] == pytest.approx(oct_['utilidad_neta'])
    assert any('Sin gastos' in w and 'Septiembre' in w for w in y['warnings'])
    assert y['best_month']['label'] == 'Octubre' and y['worst_month']['label'] == 'Septiembre'


def test_cifras_a_mano_de_anio_mandan(app, client, h, monkeypatch):
    _today(monkeypatch, date(2026, 11, 6))
    _seed(app)
    _exp(client, h(), date='2026-09-10', subcategory='cuota_banco', efectivo=300000)
    _override(client, h(), '2026-09', 'gastos_operativos', 400000)       # el total de todo, como el Excel
    _override(client, h(), '2026-09', 'ventas', 900000)
    _override(client, h(), '2026-08', 'inventario', 10000000)
    _override(client, h(), '2026-09', 'inventario', 12000000)
    y = _year(client, h())
    sep = y['months'][8]
    assert sep['gastos_a_mano'] is True and sep['cuotas'] == 0           # ya vienen en el total
    assert sep['ventas'] == 900000 and 'ventas' in sep['edited']
    assert sep['utilidad_neta'] == pytest.approx(900000 - 800000 * 0.65 - 400000)
    assert sep['lo_que_quedo'] == pytest.approx(_anio(client, h())['months'][8]['ganancia_real'])
    assert sep['inventario_costo'] == pytest.approx(12000000 * 0.65)
    assert sep['inventario_cambio'] == 2000000
    assert any('escritos a mano' in w for w in y['warnings'])


def test_tiendas_separadas_y_limites(app, client, h, monkeypatch):
    _today(monkeypatch, date(2026, 11, 6))
    _seed(app)
    y = _year(client, h('primavera'))
    assert y['months_with_data'] == 0 and y['totals']['ventas'] is None
    assert y['best_month'] is None
    assert client.get('/api/radiografia/year?year=2025', headers=h()).status_code == 400
    assert client.get('/api/radiografia/year?year=2027', headers=h()).status_code == 400
    assert client.get('/api/radiografia/year?year=2026', headers=h(role='viewer')).status_code == 200


def test_nota_del_ajuste_de_2025_en_el_inventario(app, client, h, monkeypatch):
    _today(monkeypatch, date(2026, 11, 6))
    _seed(app)
    from app.services import history_2025 as hist
    with app.app_context():
        hist._save_state('carreno', {'date': '2026-10-07', 'value': 395721300, 'completed': True,
                                     'done': [{'part': 1, 'number': '1716'}, {'part': 2, 'number': '1717'}]})
    _override(client, h(), '2026-09', 'inventario', 605000000)
    _override(client, h(), '2026-10', 'inventario', 194000000)
    y = _year(client, h())
    oct_ = y['months'][9]
    assert oct_['inventario_cambio'] == -411000000                     # la cifra no cambia
    assert oct_['inventario_ajuste_2025'] == 395721300
    assert oct_['inventario_cambio_sin_ajuste'] == -411000000 + 395721300
    assert '1716, 1717' in oct_['inventario_nota'] and '$395.721.300' in oct_['inventario_nota']
    assert any('Inventario de octubre' in w for w in y['warnings'])
    assert 'inventario_nota' not in y['months'][8]
    # La otra tienda no tiene ajuste
    assert all('inventario_nota' not in m for m in _year(client, h('primavera'))['months'])
