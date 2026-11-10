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
