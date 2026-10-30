"""
Gastos operativos del cierre (popup "¿En qué se gastaron?", 2026-10-30):
el detalle que manda el cierre queda en Cuentas → Gastos como "De la caja
del día" (no mueve EFECTIVO otra vez), se reemplaza si el cierre se reenvía
y debe sumar el total de gastos operativos. Reusa los fixtures de
test_excedentes_cierre (SQLite temporal y Alegra simulado).
"""
from tests.test_excedentes_cierre import app, alegra, h, DAY, _payload  # noqa: F401


def _gastos(app):
    from app.models.expense import Expense
    with app.app_context():
        return sorted((e.concept, e.efectivo, e.account_mode, e.subcategory, e.date.isoformat())
                      for e in Expense.query.all())


def _cierre(gastos, detalle):
    # Con gastos sacados de la caja, la venta en efectivo de Alegra es mayor
    p = _payload(excedentes=[])
    p['gastos_operativos'] = gastos
    if detalle is not None:
        p['gastos_detalle'] = detalle
    return p


def test_detalle_de_gastos_queda_en_gastos_sin_mover_efectivo(app, client, h, alegra):
    alegra['cash'] = 50600 + 4500
    r = client.post('/api/sum_payments', headers=h, json=_cierre(4500, [
        {'concepto': 'Escalera', 'valor': 2900},
        {'concepto': 'Moto carro', 'valor': 1600, 'subcategoria': 'moto_carro'},
    ]))
    assert r.status_code == 200, r.get_json()
    assert r.get_json()['validation']['validation_status'] == 'success'
    assert _gastos(app) == [('Escalera', 2900, 'caja', 'operativo', DAY),
                            ('Moto carro', 1600, 'caja', 'moto_carro', DAY)]

    # Reenviar el cierre reemplaza los gastos, no los duplica
    r = client.post('/api/sum_payments', headers=h, json=_cierre(4500, [{'concepto': 'Escalera', 'valor': 4500}]))
    assert r.status_code == 200
    assert _gastos(app) == [('Escalera', 4500, 'caja', 'operativo', DAY)]

    # Al sincronizar, EFECTIVO recibe solo lo consignado (los gastos no se descuentan otra vez)
    client.post('/api/accounts/sync-daily', headers=h)
    bal = {a['payment_key']: a['balance'] for a in client.get('/api/accounts', headers=h).get_json()['accounts']}
    assert bal['cash'] == 50600


def test_detalle_que_no_suma_el_total_se_rechaza(app, client, h):
    r = client.post('/api/sum_payments', headers=h, json=_cierre(4500, [{'concepto': 'Escalera', 'valor': 2900}]))
    assert r.status_code == 400
    r = client.post('/api/sum_payments', headers=h, json=_cierre(4500, [{'concepto': '', 'valor': 4500}]))
    assert r.status_code == 400
    assert _gastos(app) == []


def test_sin_detalle_igual_queda_el_gasto_con_la_nota_o_sin_descripcion(app, client, h, alegra):
    alegra['cash'] = 50600 + 4500
    r = client.post('/api/sum_payments', headers=h, json=_cierre(4500, None))
    assert r.status_code == 200
    assert _gastos(app) == [('Gasto del cierre sin descripción', 4500, 'caja', 'operativo', DAY)]

    p = _cierre(4500, None)
    p['gastos_operativos_nota'] = 'bolsas'
    assert client.post('/api/sum_payments', headers=h, json=p).status_code == 200
    assert _gastos(app) == [('bolsas', 4500, 'caja', 'operativo', DAY)]


def test_sin_gastos_ni_detalle_no_toca_gastos(app, client, h):
    assert client.post('/api/sum_payments', headers=h, json=_cierre(0, None)).status_code == 200
    assert _gastos(app) == []
