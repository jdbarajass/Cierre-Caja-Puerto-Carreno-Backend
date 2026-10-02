"""
Lectura de talla desde el nombre del producto (SKUParser.extract_size_from_product_name),
usada por Prendas, Análisis de Productos e Inventario. Ejemplos REALES de Alegra
(Carreño, 2026-10-02) que antes se leían mal, y los que ya estaban bien (no deben cambiar).
"""
import pytest

from app.services.sku_parser import SKUParser


@pytest.mark.parametrize('name, size', [
    # Antes mal
    ('CAMISETA HOMBRE 62900 / 1051629001', 'XS'),        # antes ÚNICA (62 del precio)
    ('CAMISETA HOMBRE 64900 / 1051649003', 'M'),         # antes ÚNICA (64 del precio)
    ('JEAN MUJER 109900 / 10521099005', '5'),            # antes XL
    ('JEAN MUJER 99900 / 1052999004', '4'),              # antes L
    ('JEAN MUJER BOTA CAMPANA 119900 / 105224119904', '4'),   # antes L
    ('JEAN MUJER BOTA CAMPANA 129900 / 105270129906', '6'),   # antes sin talla
    ('JEAN HOMBRE 99900 / 10519990034', '34'),           # antes L
    ('ZAPATO MUJER 149900 / 1052301499043', '43'),       # antes M
    ('ZAPATO HOMBRE 129900 / 1051301299034', '34'),      # antes L
    ('ZAPATO HOMBRE 149900 / 1051301499039', '39'),      # antes sin talla
    ('BODY NIÑA 34900 / 1054734924', '2-4'),             # antes 24
    ('BODY NIÑA 34900 / 10547349810', '8-10'),           # antes 10
    ('BODY NIÑO 34900 / 1053734968', '6-8'),             # antes sin talla
    ('BICICLETERO NIÑA 36900 / 1054123690024', '2-4'),   # antes 24
    ('BLUSA NIÑA 59900 / 105455992', '2'),               # antes S
    ('BUZO NIÑA 39900 / 105483994', '4'),                # antes L
    ('MEDIAS 7900 / 10487900', 'ÚNICA'),
    ('GORRA 39900 / 105039900', 'ÚNICA'),
    # Ya estaban bien
    ('CAMISETA MUJER 49900 / 1052499002', 'S'),
    ('CAMISETA HOMBRE 79900 / 1051799002', 'S'),
    ('CAMISETA MUJER 36900 / 1052369005', 'XL'),
    ('JEAN MUJER 99900 / 10529990010', '10'),
    ('JEAN MUJER 90s 119900 / 1052221199018', '18'),
    ('JEAN MUJER BOTA CAMPANA 119900 / 1052241199010', '10'),
    ('BICICLETERO NIÑA 36900 / 105412369001214', '12-14'),
    ('BICICLETERO NIÑA 36900 / 10541236900810', '8-10'),
    ('BODY NIÑA 34900 / 105473491012', '10-12'),
    ('CAMISETA NIÑO 39900 / 1053399008', '8'),
    ('BLUSA 89900 / 1040899001', 'XS'),
    ('POLO HOMBRE 79900 / 105144799003', 'M'),
    ('FLEECE MUJER 69900 / 105231699002', 'S'),
])
def test_talla_desde_el_nombre(name, size):
    assert SKUParser.extract_size_from_product_name(name)['size'] == size


def test_departamento_y_nombre_base_no_cambian():
    r = SKUParser.extract_size_from_product_name('JEAN MUJER BOTA CAMPANA 119900 / 105224119904')
    assert (r['gender'], r['product_base'], r['price'], r['is_valid']) == ('MUJER', 'JEAN MUJER BOTA CAMPANA', 119900, True)


def test_sin_precio_en_el_codigo_usa_la_lectura_anterior():
    # El precio del nombre no aparece en el SKU: se cae a parse_sku sin romperse
    r = SKUParser.extract_size_from_product_name('CAMISETA MUJER 39900 / 1052388990010')
    assert r['is_valid'] is True and r['size'] != ''
