#!/usr/bin/env python
"""
Script para inicializar los códigos KOAJ en la base de datos
Ejecutar: python scripts/init_koaj_codes.py
"""
import sys
import os

# Agregar el directorio raíz al path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import create_app
from app.config import get_config
from app.models.user import db
from app.models.koaj_code import KoajCode


# Catálogo de códigos KOAJ con sus categorías y género aplicable
KOAJ_CODES = [
    # Accesorios y varios
    {'code': '55', 'category': 'Maletas', 'applies_to': 'todos'},
    {'code': '50', 'category': 'Gorras', 'applies_to': 'todos'},
    {'code': '49', 'category': 'Cinturones', 'applies_to': 'todos'},
    {'code': '48', 'category': 'Medias', 'applies_to': 'todos'},
    {'code': '39', 'category': 'Gafas', 'applies_to': 'todos'},
    {'code': '33', 'category': 'Sombrero', 'applies_to': 'todos'},
    {'code': '30', 'category': 'Zapatos', 'applies_to': 'todos'},
    {'code': '21', 'category': 'Set Medias', 'applies_to': 'todos'},
    {'code': '15', 'category': 'Bono Regalo', 'applies_to': 'todos'},
    {'code': '11', 'category': 'Cosmetiquera / Camisa Niño', 'applies_to': 'todos'},
    {'code': '9', 'category': 'Termos KOAJ', 'applies_to': 'todos'},
    {'code': '4', 'category': 'Pines KOAJ', 'applies_to': 'todos'},
    {'code': '3', 'category': 'Bolsa Licencia', 'applies_to': 'todos'},
    {'code': '2', 'category': 'Vasos KOAJ', 'applies_to': 'todos'},
    {'code': '68', 'category': 'Sombrilla', 'applies_to': 'todos'},

    # Ropa Hombre
    {'code': '47', 'category': 'Boxer', 'applies_to': 'hombre'},
    {'code': '46', 'category': 'Chaquetas', 'applies_to': 'todos'},
    {'code': '45', 'category': 'Chalecos', 'applies_to': 'todos'},
    {'code': '44', 'category': 'Polo', 'applies_to': 'hombre'},
    {'code': '43', 'category': 'Camisa Manga Larga', 'applies_to': 'hombre'},
    {'code': '42', 'category': 'Bermudas', 'applies_to': 'hombre'},
    {'code': '27', 'category': 'Camisa Manga Corta', 'applies_to': 'hombre'},
    {'code': '16', 'category': 'Jogger Hombre', 'applies_to': 'hombre'},
    {'code': '61', 'category': 'Drill Hombre', 'applies_to': 'hombre'},
    {'code': '71', 'category': 'Camiseta Hombre Polo Club', 'applies_to': 'hombre'},
    {'code': '72', 'category': 'Polo Club', 'applies_to': 'hombre'},

    # Ropa Mujer
    {'code': '41', 'category': 'Short', 'applies_to': 'mujer'},
    {'code': '40', 'category': 'Blusas', 'applies_to': 'mujer'},
    {'code': '38', 'category': 'Jogger Mujer', 'applies_to': 'mujer'},
    {'code': '37', 'category': 'Pantalón Tela', 'applies_to': 'mujer'},
    {'code': '36', 'category': 'Vestido', 'applies_to': 'mujer'},
    {'code': '35', 'category': 'Bodys', 'applies_to': 'mujer'},
    {'code': '34', 'category': 'Crop Top', 'applies_to': 'mujer'},
    {'code': '32', 'category': 'Buzo Capota', 'applies_to': 'todos'},
    {'code': '31', 'category': 'Fleece (Suéter)', 'applies_to': 'todos'},
    {'code': '29', 'category': 'Falda', 'applies_to': 'mujer'},
    {'code': '28', 'category': 'Overol', 'applies_to': 'mujer'},
    {'code': '26', 'category': 'Boyfriend', 'applies_to': 'mujer'},
    {'code': '25', 'category': 'Momfit', 'applies_to': 'mujer'},
    {'code': '24', 'category': 'Bota Campana/Palazzo/Flare/Openleg', 'applies_to': 'mujer'},
    {'code': '23', 'category': 'Cargo', 'applies_to': 'todos'},
    {'code': '22', 'category': '90s', 'applies_to': 'mujer'},
    {'code': '20', 'category': 'Jegging', 'applies_to': 'mujer'},
    {'code': '1', 'category': 'Polo Mujer', 'applies_to': 'mujer'},
    {'code': '67', 'category': 'Pantaloneta Mujer', 'applies_to': 'mujer'},
    {'code': '69', 'category': 'Jean Mujer Moda KOAJ', 'applies_to': 'mujer'},
    {'code': '70', 'category': 'Jean Mujer Bota Campana', 'applies_to': 'mujer'},

    # Tallas únicas
    {'code': '62', 'category': 'Vestidos Talla Única', 'applies_to': 'mujer'},
    {'code': '63', 'category': 'Blusas Talla Única', 'applies_to': 'mujer'},
    {'code': '64', 'category': 'Suéter Tejido Talla Única', 'applies_to': 'mujer'},
    {'code': '65', 'category': 'Falda Talla Única', 'applies_to': 'mujer'},

    # Ropa Niño
    {'code': '53', 'category': 'Niño', 'applies_to': 'niño'},
    {'code': '18', 'category': 'Pantaloneta Niño', 'applies_to': 'niño'},
    {'code': '17', 'category': 'Polo Niño', 'applies_to': 'niño'},
    {'code': '10', 'category': 'Buzo Niño', 'applies_to': 'niño'},
    {'code': '6', 'category': 'Body Niño', 'applies_to': 'niño'},

    # Ropa Niña
    {'code': '54', 'category': 'Niña', 'applies_to': 'niña'},
    {'code': '19', 'category': 'Vestido Niña', 'applies_to': 'niña'},
    {'code': '14', 'category': 'Leggin Niña', 'applies_to': 'niña'},
    {'code': '13', 'category': 'Pantalón Tela Niña', 'applies_to': 'niña'},
    {'code': '12', 'category': 'Bicicletero Niña', 'applies_to': 'niña'},
    {'code': '8', 'category': 'Buzo Niña', 'applies_to': 'niña'},
    {'code': '7', 'category': 'Body Niña', 'applies_to': 'niña'},
    {'code': '5', 'category': 'Blusa Niña', 'applies_to': 'niña'},
    {'code': '60', 'category': 'Falda Niña', 'applies_to': 'niña'},
    {'code': '66', 'category': 'Short Niña', 'applies_to': 'niña'},
]


def init_koaj_codes():
    """
    Inicializa los códigos KOAJ en la base de datos
    """
    # Crear aplicación con contexto
    config = get_config(os.getenv('FLASK_ENV', 'production'))
    app = create_app(config)

    with app.app_context():
        print("Iniciando carga de códigos KOAJ...")
        print()

        created = 0
        updated = 0
        skipped = 0

        for code_data in KOAJ_CODES:
            existing = KoajCode.query.filter_by(code=code_data['code']).first()

            if existing:
                # Actualizar si la categoría o applies_to han cambiado
                if (existing.category != code_data['category'] or
                    existing.applies_to != code_data['applies_to']):
                    existing.category = code_data['category']
                    existing.applies_to = code_data['applies_to']
                    existing.is_active = True
                    updated += 1
                    print(f"  📝 Actualizado: {code_data['code']} - {code_data['category']}")
                else:
                    skipped += 1
            else:
                # Crear nuevo código
                new_code = KoajCode(
                    code=code_data['code'],
                    category=code_data['category'],
                    applies_to=code_data['applies_to'],
                    is_active=True
                )
                db.session.add(new_code)
                created += 1
                print(f"  ✅ Creado: {code_data['code']} - {code_data['category']}")

        db.session.commit()

        print()
        print("=" * 60)
        print("RESUMEN DE CARGA:")
        print(f"  ✅ Códigos creados: {created}")
        print(f"  📝 Códigos actualizados: {updated}")
        print(f"  ⏭️  Códigos sin cambios: {skipped}")
        print(f"  📊 Total de códigos: {len(KOAJ_CODES)}")
        print("=" * 60)


def main():
    """Función principal"""
    print("=" * 60)
    print("INICIALIZACIÓN DE CÓDIGOS KOAJ")
    print("Sistema de Cierre de Caja - KOAJ Puerto Carreño")
    print("=" * 60)
    print()

    proceed = input("¿Desea cargar/actualizar los códigos KOAJ? (s/n): ").strip().lower()

    if proceed == 's':
        init_koaj_codes()
        print()
        print("✅ Proceso completado exitosamente.")
        print("Los códigos KOAJ están ahora disponibles en la API.")
    else:
        print("❌ Operación cancelada.")


if __name__ == "__main__":
    main()
