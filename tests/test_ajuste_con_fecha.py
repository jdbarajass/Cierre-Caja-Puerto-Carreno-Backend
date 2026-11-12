"""
Fecha de negocio de un ajuste manual hecho tarde (pedido del usuario
2026-11-12: el ajuste del 9-oct de Carreño compensaba un doble descuento del
5-oct y el QR se veía negativo del 6 al 8-oct). Solo mueve el día en el
detalle diario; el saldo de la cuenta no cambia.
"""
from datetime import date

from tests.test_month_sheet import app, h, _sheet, _row, _account_id  # noqa: F401  (fixtures)


def _balance(client, h, key):
    return {a['payment_key']: a['balance'] for a in client.get('/api/accounts', headers=h()).get_json()['accounts']}[key]


def _adjust(client, h, qr, amount, direction, **extra):
    r = client.post('/api/accounts/manual-adjustment', headers=h(),
                    json={'account_id': qr, 'amount': amount, 'direction': direction, 'description': 'Ajuste', **extra})
    assert r.status_code == 201, r.get_json()
    return r.get_json()['movement']


def test_poner_fecha_mueve_el_dia_sin_cambiar_el_saldo(app, client, h):
    qr = _account_id(client, h, 'qr')
    mov = _adjust(client, h, qr, 100000, 'in')  # hecho hoy, sin fecha
    saldo = _balance(client, h, 'qr')
    assert _row(_sheet(client, h), 'qr')['ajustes'] == 0  # octubre

    r = client.patch(f"/api/accounts/movements/{mov['id']}/business-date", headers=h(),
                     json={'business_date': '2026-10-05', 'note': 'compensa el doble descuento'})
    assert r.status_code == 200, r.get_json()
    assert r.get_json()['movement']['business_date'] == '2026-10-05'
    assert 'compensa el doble descuento' in r.get_json()['movement']['description']
    octubre = _row(_sheet(client, h), 'qr')
    assert octubre['ajustes'] == 100000
    assert [d['date'] for d in octubre['days']] == ['2026-10-05']
    assert _balance(client, h, 'qr') == saldo  # el saldo de hoy no cambia

    # Quitar la fecha: vuelve al día en que se registró
    assert client.patch(f"/api/accounts/movements/{mov['id']}/business-date", headers=h(),
                        json={'business_date': None}).status_code == 200
    assert _row(_sheet(client, h), 'qr')['ajustes'] == 0
    assert _balance(client, h, 'qr') == saldo


def test_ajuste_nuevo_con_fecha(app, client, h):
    qr = _account_id(client, h, 'qr')
    mov = _adjust(client, h, qr, 50000, 'out', business_date='2026-10-20')
    assert mov['business_date'] == '2026-10-20'
    assert _row(_sheet(client, h), 'qr')['ajustes'] == -50000


def test_validaciones(app, client, h):
    qr = _account_id(client, h, 'qr')
    mov = _adjust(client, h, qr, 10000, 'in')
    url = f"/api/accounts/movements/{mov['id']}/business-date"
    assert client.patch(url, headers=h(), json={'business_date': '2999-01-01'}).status_code == 400
    assert client.patch(url, headers=h(), json={'business_date': 'mañana'}).status_code == 400
    # Otros tipos de movimiento no (toman la fecha del gasto)
    client.post('/api/expenses', headers=h(), json={'date': '2026-10-03', 'concept': 'Internet', 'qr': 100000})
    gasto = [m for m in client.get('/api/accounts/movements?type=expense', headers=h()).get_json()['movements']][0]
    assert client.patch(f"/api/accounts/movements/{gasto['id']}/business-date", headers=h(),
                        json={'business_date': '2026-10-01'}).status_code == 400
    # Mes cerrado: no
    assert client.post('/api/month-sheet/close', headers=h(), json={'year': 2026, 'month': 10}).status_code == 200
    assert client.patch(url, headers=h(), json={'business_date': '2026-10-05'}).status_code == 400
    # Otra tienda no lo ve
    assert client.patch(url, headers=h('primavera'), json={'business_date': None}).status_code == 404
