"""
Tests de la carga de facturas en InvoiceFact (fase 4 del dashboard de
clientes, app/services/invoice_facts.py). Base SQLite temporal; Alegra
simulado con facturas en el formato de /api/v1/invoices.
"""
from datetime import date

import pytest

from app.config import TestingConfig
from app.exceptions import AlegraConnectionError
from app.models.invoice_fact import InvoiceFact, InvoiceSyncDay
from app.services import invoice_facts as svc


def invoice(id_, day, total, client=('353', 'Barrios Heidy', '20230261'), seller=('12', 'RITA INFANTE'),
            discount=0, status='closed', **extra):
    inv = {
        'id': id_, 'date': day, 'status': status, 'subtotal': total + discount, 'discount': discount,
        'tax': 0, 'total': total,
        'numberTemplate': {'prefix': 'KPC', 'number': id_, 'fullNumber': f'KPC{id_}'},
        'client': {'id': client[0], 'name': client[1], 'identification': client[2]} if client else None,
        'seller': {'id': seller[0], 'name': seller[1]} if seller else None,
    }
    inv.update(extra)
    return inv


class FakeAlegra:
    def __init__(self, by_day):
        self.by_day = by_day
        self.calls = []

    def get_invoices_by_date(self, day):
        self.calls.append(day)
        value = self.by_day.get(day, [])
        if isinstance(value, Exception):
            raise value
        return value


@pytest.fixture
def app(tmp_path):
    class FactsTestConfig(TestingConfig):
        SQLALCHEMY_DATABASE_URI = f"sqlite:///{(tmp_path / 'facts.db').as_posix()}"
        SQLALCHEMY_ENGINE_OPTIONS = {}

    from app import create_app
    application = create_app(FactsTestConfig)
    with application.app_context():
        yield application


D1, D2, D3 = date(2026, 1, 2), date(2026, 1, 3), date(2026, 1, 4)


def _facts(store='carreno'):
    return {f.alegra_id: f for f in InvoiceFact.query.filter_by(store_code=store).all()}


def test_factura_a_resumen():
    fact = svc.invoice_to_fact(invoice('12373', '2026-08-24', 166900, discount=10000))
    assert fact == {
        'alegra_id': '12373', 'number': 'KPC12373', 'client_id': '353', 'client_name': 'Barrios Heidy',
        'client_identification': '20230261', 'seller_id': '12', 'seller_name': 'RITA INFANTE',
        'subtotal': 176900, 'discount': 10000, 'total': 166900, 'voided': False,
    }
    # Sin vendedora ni cliente
    bare = svc.invoice_to_fact(invoice('1', '2026-08-24', 5000, client=None, seller=None))
    assert bare['seller_id'] is None and bare['client_id'] is None
    # Anulada
    assert svc.invoice_to_fact(invoice('2', '2026-08-24', 5000, status='void'))['voided'] is True


def test_descuento_por_item_si_no_viene_en_la_factura():
    inv = invoice('3', '2026-08-24', 90000)
    del inv['discount'], inv['subtotal']
    inv['items'] = [{'price': 50000, 'quantity': 2, 'discount': 10}]  # 10 % de 100.000
    fact = svc.invoice_to_fact(inv)
    assert fact['discount'] == 10000 and fact['subtotal'] == 100000


def test_cargar_un_dia_y_volver_a_cargarlo_lo_reemplaza(app):
    alegra = FakeAlegra({D1.isoformat(): [invoice('1', D1.isoformat(), 100000), invoice('2', D1.isoformat(), 50000)]})
    assert svc.sync_day(alegra, 'carreno', D1) == 2
    assert set(_facts()) == {'1', '2'}
    assert InvoiceSyncDay.query.filter_by(store_code='carreno', date=D1).one().invoice_count == 2

    # En Alegra: la 2 se anuló y la 1 desapareció (ej. se movió de día)
    alegra.by_day[D1.isoformat()] = [invoice('2', D1.isoformat(), 50000, status='void')]
    assert svc.sync_day(alegra, 'carreno', D1) == 1
    facts = _facts()
    assert set(facts) == {'2'} and facts['2'].voided is True
    assert InvoiceSyncDay.query.filter_by(store_code='carreno').count() == 1


def test_si_alegra_falla_no_se_borra_lo_que_habia(app):
    alegra = FakeAlegra({D1.isoformat(): [invoice('1', D1.isoformat(), 100000)]})
    svc.sync_day(alegra, 'carreno', D1)
    alegra.by_day[D1.isoformat()] = AlegraConnectionError('Alegra caído')
    with pytest.raises(AlegraConnectionError):
        svc.sync_day(alegra, 'carreno', D1)
    assert set(_facts()) == {'1'}


def test_factura_que_cambio_de_fecha_no_se_duplica(app):
    alegra = FakeAlegra({D1.isoformat(): [invoice('7', D1.isoformat(), 100000)]})
    svc.sync_day(alegra, 'carreno', D1)
    alegra.by_day = {D1.isoformat(): [], D2.isoformat(): [invoice('7', D2.isoformat(), 100000)]}
    svc.sync_day(alegra, 'carreno', D2)
    facts = _facts()
    assert len(facts) == 1 and facts['7'].date == D2


def test_tiendas_separadas(app):
    # Cada tienda tiene su propia cuenta de Alegra: el mismo id puede repetirse
    svc.sync_day(FakeAlegra({D1.isoformat(): [invoice('1', D1.isoformat(), 100000)]}), 'carreno', D1)
    svc.sync_day(FakeAlegra({D1.isoformat(): [invoice('1', D1.isoformat(), 7000)]}), 'primavera', D1)
    assert _facts('carreno')['1'].total == 100000
    assert _facts('primavera')['1'].total == 7000
    # Volver a cargar Carreño no toca Primavera
    svc.sync_day(FakeAlegra({}), 'carreno', D1)
    assert _facts('carreno') == {} and _facts('primavera')['1'].total == 7000


def test_rango_se_detiene_en_el_primer_error_y_se_puede_continuar(app):
    alegra = FakeAlegra({
        D1.isoformat(): [invoice('1', D1.isoformat(), 100000)],
        D2.isoformat(): AlegraConnectionError('Timeout'),
        D3.isoformat(): [invoice('3', D3.isoformat(), 30000)],
    })
    assert svc.missing_days('carreno', D1, D3) == [D1, D2, D3]

    result = svc.sync_range(alegra, 'carreno', svc.missing_days('carreno', D1, D3))
    assert result['synced_days'] == [D1.isoformat()] and result['failed_day'] == D2.isoformat()
    assert result['error'] == 'Timeout'
    assert D3.isoformat() not in alegra.calls  # no siguió después del error

    alegra.by_day[D2.isoformat()] = []  # día sin ventas
    result = svc.sync_range(alegra, 'carreno', svc.missing_days('carreno', D1, D3))
    assert result == {'synced_days': [D2.isoformat(), D3.isoformat()], 'invoices': 1,
                      'failed_day': None, 'error': None}
    assert svc.missing_days('carreno', D1, D3) == []
