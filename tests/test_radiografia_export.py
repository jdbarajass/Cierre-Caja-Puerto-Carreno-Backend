"""
Tests de la Radiografía, exportar (Fase 6 de docs/PLAN_RADIOGRAFIA.md): cada
vista (Mes, Año, Inventario, Flujo de caja, Comparativo) sale en Excel y PDF
con las MISMAS cifras de la pantalla, nombre con la tienda y el periodo, hoja
de Notas con ESTIMADO, y format inválido = 400.

Base SQLite temporal y Alegra simulado, sin red.
"""
from datetime import date, datetime
from io import BytesIO

import pytest
from openpyxl import load_workbook

from tests.test_radiografia_month import _exp, _seed, _today, app, h  # noqa: F401  (fixtures)
from tests.test_radiografia_inventory import fake_alegra  # noqa: F401  (fixture)

TODAY = date(2026, 11, 6)
XLSX = 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'


def _values(content):
    wb = load_workbook(BytesIO(content))
    cells = [c.value for ws in wb.worksheets for row in ws.iter_rows() for c in row if c.value is not None]
    return wb, cells


def _get(client, headers, url, fmt):
    resp = client.get(f'{url}{"&" if "?" in url else "?"}format={fmt}', headers=headers)
    assert resp.status_code == 200, resp.get_data(as_text=True)[:300]
    return resp


@pytest.fixture
def seeded(app, client, h, monkeypatch):
    import app.routes.radiografia as routes
    _today(monkeypatch, TODAY)
    monkeypatch.setattr(routes, 'get_colombia_now', lambda: datetime(2026, 11, 6, 12, 0))
    _seed(app)
    _seed(app, 'primavera')
    _exp(client, h(), subcategory='arriendo', efectivo=1052000)
    _exp(client, h(), subcategory='cuota_banco', efectivo=500000)
    client.post('/api/repurchase', headers=h(), json={'date': '2026-10-08', 'qr': 1000000})


VIEWS = [
    ('/api/radiografia/month?year=2026&month=10', 'month', 'radiografia_mes_carreno_2026-10'),
    ('/api/radiografia/year?year=2026', 'year', 'radiografia_anio_carreno_2026'),
    ('/api/radiografia/cash-flow?year=2026&month=10', 'cash_flow', 'radiografia_flujo_carreno_2026-10'),
    ('/api/radiografia/compare?year=2026&month=10', 'compare', 'radiografia_comparativo_2026-10'),
]


@pytest.mark.parametrize('url,key,name', VIEWS)
def test_excel_y_pdf_de_cada_vista(client, h, seeded, url, key, name):
    data = client.get(url, headers=h()).get_json()[key]
    x = _get(client, h(), url, 'xlsx')
    assert x.mimetype == XLSX and f'filename={name}.xlsx' in x.headers['Content-Disposition']
    wb, cells = _values(x.data)
    assert 'Notas' in wb.sheetnames
    notes = ' '.join(str(c) for c in (wb['Notas'].iter_rows(values_only=True)) for c in c if c)
    assert 'ESTIMADO' in notes
    # Las mismas cifras de la pantalla (números, no textos)
    if key == 'month':
        assert data['statement']['ventas'] in cells and data['statement']['utilidad_neta'] in cells
        assert data['statement']['lo_que_quedo'] in cells
    elif key == 'year':
        oct_ = data['months'][9]
        assert oct_['ventas'] in cells and data['totals']['ventas'] in cells
    elif key == 'cash_flow':
        assert data['flow']['final'] in cells and data['today']['plata'] in cells
        assert data['bridge']['utilidad_neta'] in cells
    else:
        assert data['consolidated']['statement']['ventas'] in cells
        assert all(s['statement']['ventas'] in cells for s in data['stores'])
    p = _get(client, h(), url, 'pdf')
    assert p.mimetype == 'application/pdf' and p.data[:4] == b'%PDF'
    assert f'filename={name}.pdf' in p.headers['Content-Disposition']


def test_inventario_y_formato_invalido(client, h, seeded, fake_alegra):
    inv = client.get('/api/radiografia/inventory?quiet=90', headers=h()).get_json()['inventory']
    x = _get(client, h(), '/api/radiografia/inventory?quiet=90', 'xlsx')
    assert 'radiografia_inventario_carreno_2026-11-06.xlsx' in x.headers['Content-Disposition']
    wb, cells = _values(x.data)
    assert inv['totals']['valor_venta'] in cells and inv['totals']['plata_parada'] in cells
    assert 'Por tipo de prenda' in wb.sheetnames                               # lista larga en su hoja
    assert _get(client, h(), '/api/radiografia/inventory?quiet=90', 'pdf').data[:4] == b'%PDF'
    assert client.get('/api/radiografia/month?year=2026&month=10&format=csv', headers=h()).status_code == 400
    # Por tienda y para el viewer (solo lee)
    assert 'primavera' in _get(client, h('primavera'), '/api/radiografia/month?year=2026&month=10', 'xlsx').headers['Content-Disposition']
    assert _get(client, h(role='viewer'), '/api/radiografia/year?year=2026', 'pdf').data[:4] == b'%PDF'


def test_mes_futuro_y_sin_gastos_tambien_se_exportan(client, h, seeded):
    _, cells = _values(_get(client, h(), '/api/radiografia/month?year=2026&month=12', 'xlsx').data)
    assert any('todavía no empieza' in str(c) for c in cells)
    _, cells = _values(_get(client, h('primavera'), '/api/radiografia/month?year=2026&month=10', 'xlsx').data)
    assert 'Sin gastos' in cells
    assert _get(client, h(), '/api/radiografia/cash-flow?year=2026&month=12', 'pdf').data[:4] == b'%PDF'
