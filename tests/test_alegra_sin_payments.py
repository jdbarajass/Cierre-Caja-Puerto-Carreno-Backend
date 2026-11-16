"""
Desde el 2026-11-09 Alegra devuelve /invoices sin el detalle `payments`: el
cierre de caja y la preconsulta sumaban $0 por medio de pago ("Alegra hoy dice
$0"). Se arma el pago con `paymentForm` + `totalPaid` de cada factura.
Facturas reales de Carreño del 9-nov (KPC4886-KPC4890, reporte de Alegra:
transferencia 301.800, tarjeta débito 357.700, efectivo 159.800 = 819.300).
"""
from app.services.alegra_client import AlegraClient
from app.utils.formatters import ensure_invoice_payments, payment_form_method


def _inv(number, form, paid, status='closed', payments=None):
    return {'id': number, 'numberTemplate': {'fullNumber': number}, 'status': status, 'paymentMethod': 'CASH',
            'paymentForm': form, 'total': paid, 'totalPaid': paid, 'balance': 0, 'payments': payments}


NOV9 = [_inv('KPC4890', 'DEBIT_CARD', 207900), _inv('KPC4889', 'DEBIT_TRANSFER', 82000),
        _inv('KPC4888', 'CASH', 159800), _inv('KPC4887', 'DEBIT_CARD', 149800),
        _inv('KPC4886', 'DEBIT_TRANSFER', 219800)]


def test_cierre_del_9_de_noviembre_suma_por_medio():
    invoices = ensure_invoice_payments([dict(i) for i in NOV9])
    totals = AlegraClient('x', 'y', 'https://api.alegra.com/api/v1').process_invoices(invoices)['totals']
    assert totals == {'cash': 159800, 'transfer': 301800, 'debit-card': 357700, 'credit-card': 0}
    assert sum(totals.values()) == 819300
    assert all(i['payments'][0]['synthesized'] for i in invoices)


def test_transferencia_no_se_confunde_con_debito_y_respeta_lo_que_traiga_alegra():
    assert payment_form_method('DEBIT_TRANSFER') == 'transfer'    # contiene "debit"
    assert payment_form_method('CREDIT_CARD') == 'credit-card'
    assert payment_form_method(None) == 'other'
    real = [{'amount': 50000, 'paymentMethod': 'cash'}, {'amount': 10000, 'paymentMethod': 'transfer'}]
    inv = ensure_invoice_payments([_inv('A', 'CASH', 60000, payments=real)])[0]
    assert inv['payments'] == real                                # si Alegra manda el detalle, se usa
    # Anuladas y sin pagar no inventan pagos
    assert ensure_invoice_payments([_inv('B', 'CASH', 1000, status='void')])[0]['payments'] is None
    unpaid = _inv('C', 'CASH', 0)
    unpaid['balance'] = 5000
    assert ensure_invoice_payments([unpaid])[0]['payments'] is None


# --- Pagos mixtos: la division real sale de los recibos (/payments) ---
# Carreno 15-nov-2026 (KPC4929-KPC4935). KPC4934 ($170.100) se pago con
# $60.100 en efectivo + $110.000 por QR y su paymentForm es DEBIT_TRANSFER: sin
# los recibos el cierre decia efectivo 282.800 / transferencia 320.100; el
# Reporte diario de Alegra dice efectivo 342.900 / transferencia 260.000.
from app.services import invoice_receipts
from app.services.invoice_receipts import receipts_by_invoice_for_date, needs_receipts


def _inv15(inv_id, number, form, paid):
    inv = _inv(number, form, paid)
    inv['id'] = inv_id
    inv['date'] = '2026-11-15'
    return inv


NOV15 = [_inv15('13444', 'KPC4935', 'CREDIT_CARD', 40000),
         _inv15('13443', 'KPC4934', 'DEBIT_TRANSFER', 170100),
         _inv15('13442', 'KPC4933', 'CASH', 49900),
         _inv15('13441', 'KPC4932', 'CASH', 180100),
         _inv15('13440', 'KPC4931', 'DEBIT_TRANSFER', 150000),
         _inv15('13439', 'KPC4930', 'CASH', 44900),
         _inv15('13438', 'KPC4929', 'CASH', 7900)]


def _rc(rid, day, method, inv_id, amount, total=None):
    """Recibo con el formato de /api/v1/payments."""
    return {'id': rid, 'date': day, 'type': 'in', 'status': 'open', 'amount': amount,
            'paymentMethod': method, 'bankAccount': {'id': '9', 'name': 'Efectivo POS'},
            'invoices': [{'id': inv_id, 'date': day, 'amount': amount,
                          'total': total or amount, 'balance': 0}]}


RECEIPTS_NOV = [
    {'id': '17059', 'date': '2026-11-16', 'type': 'in', 'status': 'open', 'amount': 450000,
     'paymentMethod': '', 'anotation': 'Apertura de turno', 'categories': [{'id': '5274'}]},
    {'id': '17057', 'date': '2026-11-15', 'type': 'in', 'status': 'open', 'amount': 792900,
     'paymentMethod': '', 'anotation': 'Cierre de turno', 'categories': [{'id': '5274'}]},
    _rc('17055', '2026-11-15', 'credit-card', '13444', 40000),
    _rc('17054', '2026-11-15', 'transfer', '13443', 110000, total=170100),
    _rc('17053', '2026-11-15', 'cash', '13443', 60100, total=170100),
    _rc('17052', '2026-11-15', 'cash', '13442', 49900),
    _rc('17051', '2026-11-15', 'cash', '13441', 180100),
    _rc('17050', '2026-11-15', 'transfer', '13440', 150000),
    _rc('17049', '2026-11-15', 'cash', '13439', 44900),
    _rc('17048', '2026-11-15', 'cash', '13438', 7900),
    _rc('17043', '2026-11-14', 'transfer', '13437', 110200),
    _rc('17041', '2026-11-14', 'cash', '13435', 119900),
]


def _pager(receipts, calls=None):
    def fetch(start, limit):
        if calls is not None:
            calls.append(start)
        return receipts[start:start + limit]
    return fetch


def _client():
    return AlegraClient('x', 'y', 'https://api.alegra.com/api/v1')


def test_pago_mixto_del_15_de_noviembre_cuadra_con_el_reporte_de_alegra():
    invoice_receipts.clear_cache()
    receipts = receipts_by_invoice_for_date(_pager(RECEIPTS_NOV), 'carreno', '2026-11-15', '2026-11-16')
    invoices = ensure_invoice_payments([dict(i) for i in NOV15], receipts)
    totals = _client().process_invoices(invoices)['totals']
    assert totals == {'cash': 342900, 'transfer': 260000, 'debit-card': 0, 'credit-card': 40000}
    mixed = next(i for i in invoices if i['id'] == '13443')
    assert sorted((p['paymentMethod'], p['amount']) for p in mixed['payments']) == [
        ('cash', 60100), ('transfer', 110000)]


def test_sin_recibos_se_sigue_usando_payment_form():
    invoices = ensure_invoice_payments([dict(i) for i in NOV15], None)
    totals = _client().process_invoices(invoices)['totals']
    assert totals == {'cash': 282800, 'transfer': 320100, 'debit-card': 0, 'credit-card': 40000}


def test_recibos_parciales_y_recibos_que_no_cuadran():
    inv = _inv15('1', 'K1', 'DEBIT_TRANSFER', 100000)
    out = ensure_invoice_payments([dict(inv)], {'1': [{'amount': 30000, 'paymentMethod': 'cash'}]})[0]
    assert sorted((p['paymentMethod'], p['amount']) for p in out['payments']) == [
        ('cash', 30000), ('transfer', 70000)]                     # el resto va a paymentForm
    out = ensure_invoice_payments([dict(inv)], {'1': [{'amount': 150000, 'paymentMethod': 'cash'}]})[0]
    assert out['payments'] == [{'amount': 100000, 'paymentMethod': 'transfer',
                                'date': '2026-11-15', 'synthesized': True}]   # suman de mas: no se usan


def test_recorrido_de_recibos_para_y_guarda_cache():
    invoice_receipts.clear_cache()
    calls = []
    many = RECEIPTS_NOV + [_rc(str(9000 - i), '2026-11-13', 'cash', str(i), 1000) for i in range(60)]
    got = receipts_by_invoice_for_date(_pager(many, calls), 'carreno', '2026-11-14', '2026-11-16')
    assert got == {'13437': [{'amount': 110200, 'paymentMethod': 'transfer'}],
                   '13435': [{'amount': 119900, 'paymentMethod': 'cash'}]}
    assert calls == [0, 30]                     # la 2a pagina ya es toda del 13: para ahi
    # El 15 quedo completo en el mismo recorrido: no vuelve a pedir nada
    calls.clear()
    got15 = receipts_by_invoice_for_date(_pager(many, calls), 'carreno', '2026-11-15', '2026-11-16')
    assert calls == [] and sorted(got15) == ['13438', '13439', '13440', '13441', '13442', '13443', '13444']
    # Otra tienda (otro usuario de Alegra) no usa esa cache
    receipts_by_invoice_for_date(_pager(many, calls), 'primavera', '2026-11-15', '2026-11-16')
    assert calls == [0, 30]


def test_recibos_anulados_fallas_y_fechas_viejas():
    invoice_receipts.clear_cache()
    void = dict(_rc('1', '2026-11-15', 'cash', '13443', 60100), status='void')
    assert receipts_by_invoice_for_date(_pager([void]), 'c', '2026-11-15', '2026-11-16') == {}

    def boom(start, limit):
        raise RuntimeError('Alegra caida')
    invoice_receipts.clear_cache()
    assert receipts_by_invoice_for_date(boom, 'c', '2026-11-15', '2026-11-16') is None
    assert receipts_by_invoice_for_date(boom, 'c', '2026-08-01', '2026-11-16') is None   # muy atras
    # Hoy nunca se guarda en cache (siguen llegando recibos)
    calls = []
    receipts_by_invoice_for_date(_pager(RECEIPTS_NOV, calls), 'c', '2026-11-16', '2026-11-16')
    receipts_by_invoice_for_date(_pager(RECEIPTS_NOV, calls), 'c', '2026-11-16', '2026-11-16')
    assert calls == [0, 0]


def test_solo_se_piden_recibos_si_falta_el_detalle():
    assert needs_receipts([dict(i) for i in NOV15])
    real = _inv15('1', 'K1', 'CASH', 1000)
    real['payments'] = [{'amount': 1000, 'paymentMethod': 'cash'}]
    assert not needs_receipts([real, _inv('V', 'CASH', 5000, status='void')])
