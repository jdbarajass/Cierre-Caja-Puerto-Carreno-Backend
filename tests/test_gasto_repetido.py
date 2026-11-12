"""
Aviso de gasto repetido (pedido del usuario 2026-11-12, tras encontrar Alegra
pagada dos veces en octubre de Carreño): si un gasto que se paga una vez al
mes (o el mismo gasto fijo) ya está en ese mes, el backend responde 409 con
los parecidos y solo guarda si se confirma.
"""
from tests.test_expenses import app, h, _post, _balances  # noqa: F401  (fixtures)


def test_segundo_alegra_del_mes_pide_confirmar(client, h):
    assert _post(client, h(), concept='ALEGRA', subcategory='alegra', datafono=139900).status_code == 201
    r = _post(client, h(), date='2026-10-07', concept='Alegra', subcategory='alegra', datafono=139900)
    assert r.status_code == 409
    body = r.get_json()
    assert body['duplicate'] is True and len(body['existing']) == 1 and 'ALEGRA' in body['message']
    # No se guardó ni movió cuentas
    assert _balances(client, h())['addi_datafono'] == -(139900 + 560)
    # Confirmado: se guarda
    r = _post(client, h(), date='2026-10-07', concept='Alegra', subcategory='alegra', datafono=139900,
              confirm_duplicate=True)
    assert r.status_code == 201


def test_otro_mes_otra_tienda_y_sueldos_no_avisan(client, h):
    assert _post(client, h(), subcategory='internet', qr=266000).status_code == 201
    assert _post(client, h(), date='2026-11-05', subcategory='internet', qr=266000).status_code == 201
    assert _post(client, h('primavera'), subcategory='internet', qr=266000).status_code == 201
    assert _post(client, h(), subcategory='sueldos_empleadas_2', efectivo=550000).status_code == 201
    assert _post(client, h(), subcategory='sueldos_empleadas_2', efectivo=750000).status_code == 201


def test_editar_solo_avisa_si_la_edicion_lo_vuelve_repetido(client, h):
    a = _post(client, h(), subcategory='luz', efectivo=318000).get_json()['item']
    b = _post(client, h(), date='2026-10-31', period='2026-11', subcategory='luz', efectivo=350000).get_json()['item']
    # Pasar b a octubre lo vuelve repetido
    r = client.put(f"/api/expenses/{b['id']}", headers=h(), json={'period': '2026-10'})
    assert r.status_code == 409
    assert client.get('/api/expenses?year=2026&month=11', headers=h()).get_json()['items'][0]['period'] == '2026-11'
    # Pasar a a septiembre no
    assert client.put(f"/api/expenses/{a['id']}", headers=h(), json={'period': '2026-09'}).status_code == 200
    # Cambiar la nota de un repetido que ya se dejó así no vuelve a preguntar
    client.put(f"/api/expenses/{b['id']}", headers=h(), json={'period': '2026-09', 'confirm_duplicate': True})
    assert client.put(f"/api/expenses/{b['id']}", headers=h(), json={'notes': 'se deja así'}).status_code == 200
