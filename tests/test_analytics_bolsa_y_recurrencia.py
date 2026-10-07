"""
Correcciones de Analytics Avanzado y Análisis de Productos (2026-10-07):
la BOLSA PAPEL no cuenta como unidad ni en los % de participación,
"Consumidor final" no cuenta como clienta de la vendedora, y los productos
que se compran juntos se agrupan por prenda (sin talla ni código).

Sin red ni base de datos: facturas con el formato de /api/v1/invoices.
"""
from app.services.product_analytics import ProductAnalytics
from app.services.sales_analytics import SalesAnalytics

CF = {'id': '1', 'name': 'Consumidor final', 'identification': '222222222222'}
ANA = {'id': '50', 'name': 'ANA', 'identification': '1001'}
SELLER = {'id': '7', 'name': 'MONICA VARGAS'}
BOLSA = {'name': 'BOLSA PAPEL', 'quantity': 1, 'price': 300, 'total': 300}


def item(name, qty=1, price=50000):
    return {'name': name, 'quantity': qty, 'price': price, 'total': qty * price}


def invoice(id_, client, items, hour='10:00:00'):
    return {'id': str(id_), 'date': '2026-09-10', 'datetime': f'2026-09-10 {hour}', 'status': 'closed',
            'total': sum(i['total'] for i in items), 'client': client, 'seller': SELLER, 'items': items}


INVOICES = [
    invoice(1, CF, [item('JEAN HOMBRE 109900 / 105110990034'), item('CAMISETA MUJER 39900 / 1052399003'), BOLSA]),
    invoice(2, CF, [item('JEAN HOMBRE 109900 / 105110990036'), item('CAMISETA MUJER 39900 / 1052399004'), BOLSA]),
    invoice(3, ANA, [item('JEAN HOMBRE 109900 / 105110990034', qty=2), BOLSA]),
    invoice(4, ANA, [item('MEDIAS 7900 / 10487900'), BOLSA]),
]


def test_productos_sin_bolsa_en_unidades_ni_porcentajes():
    pa = ProductAnalytics(INVOICES)
    resumen = pa.get_summary()
    assert resumen['total_productos_vendidos'] == 7                # 2+2+2+1 prendas; sin 4 bolsas
    assert resumen['ingresos_totales'] == 7 * 50000 + 4 * 300       # el dinero sí incluye la bolsa
    top = pa.get_top_products_unified(limit=10)
    assert top[0]['nombre_base'] == 'JEAN HOMBRE' and top[0]['porcentaje_participacion'] == 4 / 7 * 100
    assert round(sum(p['porcentaje_participacion'] for p in top), 6) == 100
    cats = pa.get_category_analysis()['categorias']
    assert 'OTROS' not in {c['categoria'] for c in cats}
    assert round(sum(c['porcentaje_participacion'] for c in cats), 6) == 100


def test_vendedoras_sin_consumidor_final():
    seller = SalesAnalytics(INVOICES).get_top_sellers_analysis()['top_sellers'][0]
    assert seller['unique_customers'] == 1                         # solo ANA (antes 2: ANA + Consumidor final)
    assert seller['recurring_customer_rate'] == 50.0               # 2 facturas de ANA, 1 clienta
    assert seller['total_items'] == 7


def test_horas_y_tendencias_sin_bolsa():
    sa = SalesAnalytics(INVOICES)
    assert sum(h['total_items'] for h in sa.get_peak_hours_analysis()['hourly_breakdown']) == 7
    assert sa.get_sales_trends_analysis()['daily_sales'][0]['total_items'] == 7


def test_productos_juntos_por_prenda():
    data = SalesAnalytics(INVOICES).get_cross_selling_analysis(min_support=2)
    pair = data['top_product_pairs'][0]
    # dos facturas con jean + camiseta de tallas distintas: ahora es la misma pareja
    assert (pair['product1'], pair['product2'], pair['times_bought_together']) == ('CAMISETA MUJER', 'JEAN HOMBRE', 2)
    assert pair['confidence_2_to_1'] == round(2 / 3 * 100, 2)      # jean en 3 facturas, 2 con camiseta
    assert pair['confidence_1_to_2'] == 100.0
    assert all('BOLSA' not in p['product_name'] for p in data['top_individual_products'])
