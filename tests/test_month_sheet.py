"""
Tests de Cuentas → Mes (Fase 2 de docs/PLAN_CUENTAS_DIARIAS.md): festivos y
llegada de la plata del datáfono/Addi, clasificación de los recibos de
Alegra, carga de pagos (formato real de /api/v1/payments), hoja del mes
(ventas por medio, calificación, estado por cuenta, tránsito, comisiones,
conciliación) y cerrar / reabrir el mes.

Base SQLite temporal (nunca instance/cierre_caja.db), Alegra simulado.
"""
from datetime import date, datetime

import pytest

from app.config import TestingConfig
from app.services.payment_facts import (
    arrival_date, classify_payment, colombia_holidays, net_amount, payment_rows,
)


@pytest.fixture
def app(tmp_path):
    class MonthSheetTestConfig(TestingConfig):
        SQLALCHEMY_DATABASE_URI = f"sqlite:///{(tmp_path / 'month_sheet.db').as_posix()}"
        SQLALCHEMY_ENGINE_OPTIONS = {}

    from app import create_app
    return create_app(MonthSheetTestConfig)


@pytest.fixture
def h(app):
    from app.services.jwt_service import JWTService
    with app.app_context():
        token = JWTService.generate_token(1, 'admin1@test.com', 'admin', None)
    return lambda store=None: {
        'Authorization': f'Bearer {token}', **({'X-Store': store} if store else {})
    }


# Recibos con el formato REAL de Alegra /api/v1/payments (copiados de Carreño, 5/6-oct-2026)
def _pay(pid, pdate, amount, method, bank, inv_date=None, inv_id=None, status='open'):
    return {
        'id': str(pid), 'date': pdate, 'amount': amount, 'type': 'in', 'paymentMethod': method,
        'status': status, 'bankAccount': {'id': '7', 'name': bank, 'type': 'bank'},
        'invoices': [{'id': str(inv_id or pid + 10000), 'number': f'KPC{pid}', 'date': inv_date or pdate,
                      'amount': amount, 'total': amount, 'balance': 0}],
    }


OCT5 = [
    _pay(16525, '2026-10-06', 89900, 'cash', 'Caja general', inv_date='2026-10-05'),
    {'id': '16508', 'date': '2026-10-05', 'amount': 450000, 'type': 'in', 'paymentMethod': '',
     'anotation': 'Apertura de turno', 'status': 'open',
     'bankAccount': {'id': '9', 'name': 'Efectivo POS - Terminal Terminal 1', 'type': 'cash'},
     'categories': [{'id': '5274', 'name': 'Transferencias bancarias', 'total': 450000}]},
    _pay(16524, '2026-10-05', 34900, 'transfer', 'Caja general'),
    _pay(16523, '2026-10-05', 41600, 'transfer', 'QR'),
    _pay(16522, '2026-10-05', 69900, 'credit-card', 'DATAFONO'),
    _pay(16521, '2026-10-05', 34900, 'cash', 'Efectivo POS - Terminal Terminal 1'),
    _pay(16520, '2026-10-05', 49900, 'cash', 'Efectivo POS - Terminal Terminal 1'),
    _pay(16519, '2026-10-05', 45200, 'transfer', 'QR'),
    _pay(16518, '2026-10-05', 89900, 'cash', 'Efectivo POS - Terminal Terminal 1'),
    _pay(16517, '2026-10-05', 10000, 'cash', 'Efectivo POS - Terminal Terminal 1'),
    _pay(16516, '2026-10-05', 170000, 'debit-card', 'DATAFONO'),
    _pay(16515, '2026-10-05', 109900, 'cash', 'Efectivo POS - Terminal Terminal 1'),
    _pay(16514, '2026-10-05', 19950, 'transfer', 'QR'),
    _pay(16513, '2026-10-05', 36900, 'credit-card', 'DATAFONO'),
    _pay(16512, '2026-10-05', 87150, 'credit-card', 'DATAFONO'),
    _pay(16511, '2026-10-05', 204700, 'transfer', 'ADDI'),
    _pay(16510, '2026-10-05', 109900, 'transfer', 'QR'),
    _pay(16509, '2026-10-05', 139800, 'transfer', 'QR'),
    _pay(16400, '2026-10-04', 5000, 'cash', 'Efectivo POS', status='void'),   # anulado
    _pay(16300, '2026-09-28', 77000, 'cash', 'Efectivo POS'),                 # antes de since
]


class FakeAlegra:
    def __init__(self, payments, page_size=30):
        self.payments = payments
        self.calls = []

    def get_payments_page(self, start, limit=30):
        self.calls.append(start)
        return self.payments[start:start + limit]


# ─── Festivos, llegada y clasificación ──────────────────────────────────────

def test_festivos_2026():
    hol = {d.isoformat() for d in colombia_holidays(2026)}
    for d in ('2026-01-12', '2026-03-23', '2026-04-02', '2026-04-03', '2026-05-18', '2026-06-08',
              '2026-06-15', '2026-08-17', '2026-10-12', '2026-11-02', '2026-11-16', '2026-12-08'):
        assert d in hol


def test_llegada_addi_igual_al_reporte_de_addi():
    # Reporte de pagos de Addi del usuario: venta -> pago
    for sale, pay in (('2026-10-05', '2026-11-04'), ('2026-10-03', '2026-11-03'), ('2026-10-01', '2026-11-03'),
                      ('2026-09-29', '2026-10-29'), ('2026-09-25', '2026-10-26'), ('2026-09-20', '2026-10-20')):
        assert arrival_date('addi', date.fromisoformat(sale)).isoformat() == pay
    assert round(net_amount('addi', 204700), 2) == 188866.45      # mismo neto del reporte
    assert arrival_date('ahorro', date(2026, 10, 3)) == date(2026, 10, 5)    # sábado -> lunes
    assert arrival_date('credito', date(2026, 10, 30)) == date(2026, 11, 3)  # viernes, lunes festivo
    assert arrival_date('efectivo', date(2026, 10, 3)) is None


def test_clasificacion():
    assert classify_payment('cash', 'Efectivo POS - Terminal Terminal 1') == ('efectivo', False)
    assert classify_payment('transfer', 'QR') == ('qr', False)
    assert classify_payment('debit-card', 'DATAFONO') == ('ahorro', False)
    assert classify_payment('credit-card', 'DATAFONO') == ('credito', False)
    assert classify_payment('credit-card', 'ADDI') == ('addi', False)
    assert classify_payment('transfer', 'NEQUI') == ('nequi', False)
    assert classify_payment('transfer', 'Caja general') == ('qr', True)
    assert classify_payment('', 'Caja chica') == ('otro', True)


def test_recibo_sin_factura_o_anulado_no_cuenta():
    assert payment_rows(OCT5[1], date(2026, 10, 1)) == []     # apertura de turno
    assert payment_rows(OCT5[-2], date(2026, 10, 1)) == []    # anulado


# ─── Carga y hoja del mes ───────────────────────────────────────────────────

def _load(app, payments=OCT5, store='carreno', since=date(2026, 10, 1)):
    from app.services.payment_facts import sync_payments
    with app.app_context():
        return sync_payments(FakeAlegra(payments), store, since)


def _sheet(client, h, year=2026, month=10, store=None):
    return client.get(f'/api/month-sheet?year={year}&month={month}', headers=h(store)).get_json()


def test_carga_paginada_y_hoja_cuadra_con_el_excel(app, client, h, monkeypatch):
    import app.routes.month_sheet as ms_routes
    monkeypatch.setattr(ms_routes, 'get_colombia_now', lambda: datetime(2026, 10, 6, 12, 0))

    fake = FakeAlegra(OCT5)
    from app.services.payment_facts import sync_payments
    with app.app_context():
        result = sync_payments(fake, 'carreno', date(2026, 10, 1))
    assert result['payments'] == 17
    assert fake.calls == [0]        # una página de menos de 30 -> se detiene

    sheet = _sheet(client, h)
    day5 = next(d for d in sheet['sales']['days'] if d['date'] == '2026-10-05')
    m = day5['medios']
    # Fila del 5-oct del Excel del usuario
    assert m['efectivo'] == 384500
    assert m['qr'] == 391350
    assert m['ahorro'] == 170000
    assert m['credito'] == 193950
    assert m['addi'] == 204700
    assert day5['total'] == 1344500
    assert day5['rating'] == 'buena'
    assert day5['needs_review'] == 1             # la transferencia en "Caja general"
    assert sheet['sales']['ratings']['buena']['count'] == 1
    assert len(sheet['sales']['days']) == 6      # 1 al 6 de octubre (hoy)

    # Tránsito al 6-oct: datáfono del 5 llegó el 6; Addi del 5 llega el 4-nov
    tr = sheet['transit']
    assert [(i['medio'], i['arrival_date'], i['gross']) for i in tr['items']] == [('addi', '2026-11-04', 204700)]
    assert tr['net'] == 188866
    # Comisiones: 3,8 % de 363.950 + 7,735 % de 204.700
    assert sheet['commissions']['total'] == round(363950 * 0.038 + 204700 * 0.07735)


def test_recarga_reemplaza_sin_duplicar(app, client, h):
    _load(app)
    _load(app, OCT5[:5])          # recarga con menos recibos: se reemplaza
    from app.models.month_sheet import PaymentFact
    with app.app_context():
        assert PaymentFact.query.count() == 4


def test_pagos_separados_por_tienda(app, client, h):
    _load(app, store='primavera')
    assert _sheet(client, h)['sales']['total'] == 0
    assert _sheet(client, h, store='primavera')['sales']['total'] == 1344500


def test_ruta_de_carga_con_alegra_simulado(app, client, h, monkeypatch):
    import app.routes.month_sheet as ms_routes
    monkeypatch.setattr(ms_routes, 'get_alegra_client', lambda store=None: FakeAlegra(OCT5))
    resp = client.post('/api/month-sheet/sync-payments', headers=h(), json={'since': '2026-09-01'})
    assert resp.status_code == 200
    assert resp.get_json()['since'] == '2026-10-01'      # nunca antes del arranque
    assert resp.get_json()['payments'] == 17


# ─── Estado por cuenta, conciliación, comisiones, cierre ────────────────────

def _account_id(client, h, key):
    accounts = client.get('/api/accounts', headers=h()).get_json()['accounts']
    return next(a['id'] for a in accounts if a['payment_key'] == key)


def _row(sheet, key):
    return next(r for r in sheet['statement'] if r['payment_key'] == key)


def test_estado_por_cuenta_y_conciliacion(app, client, h):
    qr = _account_id(client, h, 'qr')
    client.post('/api/expenses', headers=h(), json={'date': '2026-10-01', 'concept': 'Plata extra', 'direction': 'in',
                                                     'category': 'ingreso_extra', 'qr': 1000000})
    client.post('/api/expenses', headers=h(), json={'date': '2026-10-03', 'concept': 'Internet', 'qr': 100000})
    client.post('/api/expenses', headers=h(), json={'date': '2026-11-02', 'concept': 'Luz nov', 'qr': 50000})

    octubre = _row(_sheet(client, h), 'qr')
    assert octubre['entradas'] == 1000000
    assert octubre['gastos'] == -100400
    assert octubre['final'] == octubre['initial'] + 1000000 - 100400
    assert octubre['days'][-1]['balance'] == octubre['final']
    noviembre = _row(_sheet(client, h, 2026, 11), 'qr')
    assert noviembre['initial'] == octubre['final']
    assert noviembre['gastos'] == -50200

    resp = client.put('/api/month-sheet/reconciliation', headers=h(),
                      json={'period': '2026-10', 'account_id': qr, 'real_balance': octubre['final'] + 5000, 'note': 'banco'})
    assert resp.status_code == 200
    row = _row(_sheet(client, h), 'qr')
    assert row['real_balance'] == octubre['final'] + 5000 and row['difference'] == 5000
    client.put('/api/month-sheet/reconciliation', headers=h(),
               json={'period': '2026-10', 'account_id': qr, 'real_balance': None})
    assert _row(_sheet(client, h), 'qr')['difference'] is None


def test_registrar_comisiones_una_sola_vez(app, client, h, monkeypatch):
    import app.routes.month_sheet as ms_routes
    monkeypatch.setattr(ms_routes, 'get_colombia_now', lambda: datetime(2026, 10, 6, 12, 0))
    _load(app)
    expected = round(363950 * 0.038 + 204700 * 0.07735)
    for _ in range(2):
        resp = client.post('/api/month-sheet/commissions', headers=h(), json={'year': 2026, 'month': 10})
        assert resp.status_code == 200 and resp.get_json()['total'] == expected
    items = client.get('/api/expenses?year=2026&month=10', headers=h()).get_json()['items']
    assert [(i['category'], i['datafono'], i['fee']) for i in items] == [('financiero', expected, 0)]
    sheet = _sheet(client, h)
    row = _row(sheet, 'addi_datafono')
    assert row['gastos'] == -expected
    assert row['pending_commission'] == 0
    assert sheet['commissions']['registered_amount'] == expected


def test_cerrar_y_reabrir_mes(app, client, h):
    _load(app)
    assert client.post('/api/month-sheet/close', headers=h(),
                       json={'year': 2026, 'month': 10, 'notes': 'Revisado'}).status_code == 200
    sheet = _sheet(client, h)
    assert sheet['closed']['notes'] == 'Revisado'
    assert sheet['closed']['snapshot']['sales_total'] == 1344500
    assert sheet['closed']['changed_accounts'] == []

    # algo cambia después de cerrar: se avisa, no se bloquea
    client.post('/api/expenses', headers=h(), json={'date': '2026-10-04', 'concept': 'Bolsas', 'nequi': 10000})
    assert _sheet(client, h)['closed']['changed_accounts'] == ['NEQUI']

    assert client.delete('/api/month-sheet/close?year=2026&month=10', headers=h()).status_code == 200
    assert _sheet(client, h)['closed'] is None


def test_validaciones_y_permisos(app, client, h):
    assert client.get('/api/month-sheet?year=2026&month=13', headers=h()).status_code == 400
    assert client.put('/api/month-sheet/reconciliation', headers=h(),
                      json={'period': 'x', 'account_id': 1, 'real_balance': 1}).status_code == 400
    from app.services.jwt_service import JWTService
    with app.app_context():
        sales = JWTService.generate_token(2, 'v@test.com', 'sales', None)
    assert client.get('/api/month-sheet?year=2026&month=10',
                      headers={'Authorization': f'Bearer {sales}'}).status_code == 403
