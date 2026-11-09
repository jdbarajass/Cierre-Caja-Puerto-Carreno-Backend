"""
Tests de la Radiografía, flujo de caja (Fase 4 de docs/PLAN_RADIOGRAFIA.md):
la plata del mes cuadra (saldo inicial + entradas − salidas = saldo final),
salidas por clase, gastos de la caja del día, traslados aparte, puente
utilidad → plata, lo que le deben y lo que debe, y "cuánto se puede retirar"
sin restar los avisos. Por tienda y solo lectura.

Base SQLite temporal, sin red.
"""
from datetime import date, datetime

import pytest

from tests.test_radiografia_month import _exp, _seed, _today, app, h  # noqa: F401  (fixtures)

TODAY = date(2026, 11, 6)


def _cf(client, headers, y=2026, m=10):
    resp = client.get(f'/api/radiografia/cash-flow?year={y}&month={m}', headers=headers)
    assert resp.status_code == 200, resp.get_json()
    return resp.get_json()['cash_flow']


def _accounts(app, store='carreno'):
    from app.models.account import Account
    with app.app_context():
        return {a.payment_key: a.id for a in Account.for_store(store).all()}


def _move(app, account_id, amount, type_, when, ref=None):
    """Movimiento directo (traslado o ajuste) con su fecha de registro."""
    from app.models.account import Account, AccountMovement
    from app.models.user import db
    with app.app_context():
        db.session.add(AccountMovement(account_id=account_id, type=type_, amount=amount, reference_id=ref,
                                       created_at=datetime(when.year, when.month, when.day, 17, 0)))
        db.session.get(Account, account_id).balance += amount
        db.session.commit()


def test_la_plata_del_mes_cuadra_por_clase(app, client, h, monkeypatch):
    _today(monkeypatch, TODAY)
    _seed(app)
    _exp(client, h(), subcategory='arriendo', efectivo=1052000)
    _exp(client, h(), subcategory='flete', qr=100000)                       # + 4x1000 = 100.400
    _exp(client, h(), subcategory='cuota_banco', efectivo=500000)
    _exp(client, h(), subcategory='ganancia_jose', efectivo=1000000)
    _exp(client, h(), subcategory='inversion', efectivo=300000)
    _exp(client, h(), subcategory='aseo', efectivo=20000, account_mode='caja')   # de la caja del día
    _exp(client, h(), direction='in', category='ingreso_extra', concept='venta de cajas', efectivo=50000)
    client.post('/api/repurchase', headers=h(), json={'date': '2026-10-08', 'qr': 1000000})
    acc = _accounts(app)
    _move(app, acc['cash'], -200000, 'transfer_out', date(2026, 10, 12), 't1')
    _move(app, acc['nequi'], 200000, 'transfer_in', date(2026, 10, 12), 't1')
    _move(app, acc['cash'], 30000, 'manual_adjustment', date(2026, 10, 15))
    _move(app, acc['cash'], 999, 'manual_adjustment', date(2026, 11, 2))          # de noviembre: no cuenta

    cf = _cf(client, h())
    f = cf['flow']
    # Cuadra: inicial + entradas − salidas + ajustes + traslados = final
    assert f['initial'] + f['entradas_total'] - f['salidas_total'] + f['ajustes'] + f['traslados']['neto'] \
        == pytest.approx(f['final'])
    assert f['change'] == pytest.approx(f['final'] - f['initial'])
    out = {s['key']: s['total'] for s in f['salidas']}
    assert out['recompras'] == 1004000                       # con su 4x1000
    assert out['costo_mercancia'] == 100400
    assert out['operativo'] == 1052000 + 20000               # arriendo + aseo de la caja
    assert out['cuota_credito'] == 500000 and out['retiro_socio'] == 1000000 and out['inversion'] == 300000
    ins = {e['key']: e['total'] for e in f['entradas']}
    assert ins['ingreso_extra'] == 50000
    assert ins['ventas'] == 20000                            # la caja del día se suma a las ventas (sin cierres)
    assert f['caja_del_dia'] == 20000 and any('caja del día' in w for w in cf['warnings'])
    assert f['traslados'] == {'bruto': 200000, 'neto': 0}
    assert f['ajustes'] == 30000
    # Puente: utilidad neta + partidas = cambio en la plata
    b = cf['bridge']
    assert b['utilidad_neta'] + sum(l['value'] for l in b['lines']) == pytest.approx(b['cambio_plata'])
    lines = {l['key']: l['value'] for l in b['lines']}
    assert lines['recompras'] == -1004000 and lines['retiros'] == -1000000 and lines['cuotas'] == -500000
    assert lines['costo_estimado'] == pytest.approx(2400000 * 0.65)
    assert cf['in_progress'] is False


def test_hoy_le_deben_debe_y_cuanto_se_puede_retirar(app, client, h, monkeypatch):
    import app.routes.loans as loan_routes
    monkeypatch.setattr(loan_routes, 'get_colombia_now', lambda: datetime(2026, 11, 6, 12, 0))
    _today(monkeypatch, TODAY)
    _seed(app)
    _seed(app, 'primavera')
    acc = _accounts(app)
    _move(app, acc['cash'], 3000000, 'manual_adjustment', date(2026, 11, 1))
    _move(app, acc['ahorro'], 500000, 'manual_adjustment', date(2026, 11, 1))       # AHORRO cuenta
    client.post('/api/repurchase', headers=h(), json={'date': '2026-11-02', 'efectivo': 100000})
    _exp(client, h(), date='2026-11-03', subcategory='prestamo_empleada', employee_name='Rita', efectivo=200000)
    fixed = client.post('/api/expenses/fixed', headers=h(), json={'name': 'Arriendo', 'amount': 1052000,
                                                                 'due_day': 30, 'subcategory': 'arriendo'})
    assert fixed.status_code == 201, fixed.get_json()
    client.post('/api/expenses/fixed', headers=h(), json={'name': 'Ganancia José', 'amount': 1000000,
                                                          'due_day': 30, 'subcategory': 'ganancia_jose'})
    loan = client.post('/api/loans', headers=h(), json={'group_name': 'Mamá de Angie', 'name': 'Apertura',
                                                        'principal': 7500000, 'start_date': '2026-11-06',
                                                        'installment': 400000, 'due_day': 25})
    assert loan.status_code == 201, loan.get_json()

    t = _cf(client, h(), 2026, 11)['today']
    assert t['plata'] == pytest.approx(3000000 + 500000 - 100400 - 200000)   # recompra con su 4x1000
    rec = {x['key']: x for x in t['receivable']}
    assert rec['empleadas']['value'] == 200000 and rec['empleadas']['items'][0]['name'] == 'Rita'
    assert rec['otra_tienda']['value'] == 9816659                       # Primavera le debe a Carreño
    assert rec['jhonatan']['value'] == 100000
    pay = {x['key']: x['value'] for x in t['payable']}
    assert pay['prestamo:Mamá de Angie'] == 7500000 and 'otra_tienda' not in pay

    w = t['withdraw']
    av = {a['key']: a for a in w['avisos']}
    assert av['fijos']['value'] == 1052000                              # la ganancia de un socio no es aviso
    assert av['cuotas']['value'] == 400000
    assert av['recomprar']['value'] == pytest.approx(500000 * 0.65 - 100000)
    assert 'otra_tienda' not in av
    # La plata de hoy no se toca; "quedarían" es la referencia
    assert w['plata_hoy'] == t['plata']
    assert w['quedarian'] == pytest.approx(t['plata'] - 1052000 - 400000 - (325000 - 100000))

    # Primavera: le debe a Carreño (lo que debe y aviso), nada de lo de Carreño
    tp = _cf(client, h('primavera'), 2026, 11)['today']
    assert {x['key']: x['value'] for x in tp['payable']}['otra_tienda'] == 9816659
    assert {a['key']: a['value'] for a in tp['withdraw']['avisos']}['otra_tienda'] == 9816659
    assert {x['key']: x['value'] for x in tp['receivable']}['empleadas'] == 0
    assert tp['plata'] == 0


def test_limites_y_solo_lectura(app, client, h, monkeypatch):
    _today(monkeypatch, TODAY)
    _seed(app)
    assert client.get('/api/radiografia/cash-flow?year=2025&month=12', headers=h()).status_code == 400
    assert client.get('/api/radiografia/cash-flow?year=2026&month=13', headers=h()).status_code == 400
    fut = _cf(client, h(), 2026, 12)
    assert fut['future'] is True and 'flow' not in fut and 'today' in fut
    cur = _cf(client, h(), 2026, 11)
    assert cur['in_progress'] is True and any('curso' in w for w in cur['warnings'])
    assert cur['bridge'] is None                                         # sin gastos: no hay utilidad que comparar
    assert client.get('/api/radiografia/cash-flow', headers=h(role='viewer')).status_code == 200
