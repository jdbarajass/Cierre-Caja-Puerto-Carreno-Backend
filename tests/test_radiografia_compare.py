"""
Tests de la Radiografía, comparativo y consolidado (Fase 5 de docs/PLAN_RADIOGRAFIA.md):
cada tienda trae lo mismo que su Mes y su Flujo de caja; "Las dos" es la suma
con los porcentajes sacados de las sumas; el préstamo entre tiendas no
aparece (la deuda se cancela y lo que llegó a la otra tienda se cancela con su
salida); solo quien ve las dos tiendas.

Base SQLite temporal, sin red.
"""
from datetime import date

import pytest

from tests.test_radiografia_month import _exp, _seed, _today, app, h  # noqa: F401  (fixtures)

TODAY = date(2026, 11, 6)


def _cmp(client, headers, y=2026, m=10):
    resp = client.get(f'/api/radiografia/compare?year={y}&month={m}', headers=headers)
    assert resp.status_code == 200, resp.get_json()
    return resp.get_json()['compare']


def _seed_inventory(app):
    from app.models.monthly_summary import InventorySnapshot
    from app.models.user import db
    with app.app_context():
        db.session.add(InventorySnapshot(store_code='carreno', period='2026-10', value=1000000, as_of=date(2026, 10, 31)))
        db.session.add(InventorySnapshot(store_code='primavera', period='2026-10', value=400000, as_of=date(2026, 10, 31)))
        db.session.commit()


def test_cada_tienda_igual_a_su_mes_y_las_dos_suman(app, client, h, monkeypatch):
    _today(monkeypatch, TODAY)
    _seed(app)
    _seed(app, 'primavera')
    _seed_inventory(app)
    _exp(client, h(), subcategory='arriendo', efectivo=1052000)
    _exp(client, h('primavera'), subcategory='arriendo', efectivo=800000)
    _exp(client, h('primavera'), subcategory='luz', qr=100000)

    c = _cmp(client, h())
    by = {s['store']: s for s in c['stores']}
    for store in ('carreno', 'primavera'):
        mes = client.get('/api/radiografia/month?year=2026&month=10', headers=h(store)).get_json()['month']['statement']
        for k in ('ventas', 'costo_estimado', 'utilidad_neta', 'lo_que_quedo'):
            assert by[store]['statement'][k] == pytest.approx(mes[k])
    both = c['consolidated']
    for k in ('ventas', 'costo_estimado', 'gastos_operativos', 'utilidad_neta', 'lo_que_quedo'):
        assert both['statement'][k] == pytest.approx(by['carreno']['statement'][k] + by['primavera']['statement'][k])
    # Porcentajes de las sumas, no sumados
    assert both['pct']['utilidad_neta'] == pytest.approx(both['statement']['utilidad_neta'] / both['statement']['ventas'])
    assert both['indicators']['ticket'] == pytest.approx(4000000 / 6)
    assert both['inventory']['valor_venta'] == 1400000
    assert both['inventory']['valor_costo'] == pytest.approx(1400000 * 0.65)


def test_el_prestamo_entre_tiendas_no_aparece_en_las_dos(app, client, h, monkeypatch):
    _today(monkeypatch, TODAY)
    _seed(app)
    _seed(app, 'primavera')
    # Primavera abona 500.000 por QR y llegan a la cuenta QR de Carreño (espejo)
    resp = client.post('/api/expenses', headers=h('primavera'), json={
        'date': '2026-11-06', 'concept': 'Abono', 'category': 'pago_prestamo_tienda', 'related_store_code': 'carreno',
        'purpose': 'cuenta', 'arrived_method': 'qr', 'qr': 500000})
    assert resp.status_code == 201, resp.get_json()

    c = _cmp(client, h(), 2026, 11)
    by = {s['store']: s for s in c['stores']}
    assert by['primavera']['flow']['inter_store_out'] == 502000         # con su 4x1000
    assert by['carreno']['flow']['inter_store_in'] == 500000
    both = c['consolidated']
    # Lo que llegó a Carreño se cancela; solo queda el 4x1000 que sí salió de las dos
    assert both['flow']['inter_store_net'] == 2000
    assert both['flow']['entradas_total'] == pytest.approx(
        by['carreno']['flow']['entradas_total'] + by['primavera']['flow']['entradas_total'] - 500000)
    assert both['flow']['change'] == pytest.approx(-2000)
    # La deuda entre tiendas se cancela: no está en lo que le deben, lo que debe ni en los avisos
    assert both['today']['inter_store_debt'] == 9816659 - 500000
    assert both['today']['receivable_total'] == pytest.approx(sum(
        x['value'] for s in c['stores'] for x in s['today']['receivable'] if x['key'] != 'otra_tienda'))
    assert both['today']['payable_total'] == 0
    assert both['today']['plata'] == pytest.approx(-2000)


def test_solo_quien_ve_las_dos_tiendas(app, client, h, monkeypatch):
    _today(monkeypatch, TODAY)
    _seed(app)
    assert client.get('/api/radiografia/compare?year=2025&month=10', headers=h()).status_code == 400
    assert client.get('/api/radiografia/compare', headers=h(role='viewer')).status_code == 200
    fut = _cmp(client, h(), 2026, 12)
    assert fut['consolidated']['future'] is True and all(s['future'] for s in fut['stores'])
    # Sin gastos en una tienda, la utilidad de las dos no se suma
    _exp(client, h(), subcategory='arriendo', efectivo=1052000)
    both = _cmp(client, h())['consolidated']
    assert both['has_expenses'] is False and both['statement']['utilidad_neta'] is None
