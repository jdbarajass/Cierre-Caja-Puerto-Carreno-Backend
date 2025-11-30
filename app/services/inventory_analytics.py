"""
Servicio de análisis de inventario
Procesa items de Alegra y genera métricas completas de inventario
"""
import logging
from typing import Dict, List
from collections import defaultdict

from app.services.sku_parser import SKUParser

logger = logging.getLogger(__name__)


class InventoryAnalytics:
    """Analiza inventario desde items de Alegra"""

    def __init__(self, items: List[Dict]):
        """
        Inicializa el analizador de inventario

        Args:
            items: Lista de items de Alegra con inventario
        """
        self.items = items
        self.sku_parser = SKUParser()

    def get_complete_analysis(self) -> Dict:
        """
        Obtiene análisis completo del inventario

        Returns:
            Dict con análisis completo:
            {
                'resumen_ejecutivo': {...},
                'por_departamento': {...},
                'por_categoria': {...},
                'por_talla': {...},
                'productos_sin_stock': [...],
                'productos_bajo_stock': [...],
                'top_productos_por_valor': [...],
                'abc_analysis': {...}
            }
        """
        logger.info(f"Iniciando análisis completo de {len(self.items)} items")

        return {
            'resumen_ejecutivo': self.get_executive_summary(),
            'por_departamento': self.get_by_department(),
            'por_categoria': self.get_by_category(),
            'por_talla': self.get_by_size(),
            'productos_sin_stock': self.get_out_of_stock(),
            'productos_bajo_stock': self.get_low_stock(threshold=5),
            'top_productos_por_valor': self.get_top_by_value(limit=20),
            'abc_analysis': self.get_abc_analysis()
        }

    def get_executive_summary(self) -> Dict:
        """
        Genera resumen ejecutivo del inventario

        Returns:
            {
                'total_items': int,
                'total_items_con_stock': int,
                'total_unidades': int,
                'valor_total_inventario': int,
                'valor_potencial_venta': int,
                'margen_esperado': int,
                'porcentaje_margen': float,
                'costo_promedio_por_unidad': float,
                'precio_promedio_venta': float
            }
        """
        total_items = 0
        total_items_con_stock = 0
        total_unidades = 0
        valor_total_inventario = 0
        valor_potencial_venta = 0

        for item in self.items:
            # Solo procesar variantes (productos con inventario)
            if item.get('type') != 'variant':
                continue

            inventory = item.get('inventory', {})
            if not inventory:
                continue

            quantity = inventory.get('availableQuantity', 0)
            unit_cost = inventory.get('unitCost', 0)

            # Precio de venta
            prices = item.get('price', [])
            sale_price = prices[0].get('price', 0) if prices else 0

            total_items += 1
            if quantity > 0:
                total_items_con_stock += 1
                total_unidades += quantity
                valor_total_inventario += quantity * unit_cost
                valor_potencial_venta += quantity * sale_price

        margen_esperado = valor_potencial_venta - valor_total_inventario
        porcentaje_margen = (margen_esperado / valor_potencial_venta * 100) if valor_potencial_venta > 0 else 0
        costo_promedio = valor_total_inventario / total_unidades if total_unidades > 0 else 0
        precio_promedio = valor_potencial_venta / total_unidades if total_unidades > 0 else 0

        return {
            'total_items': total_items,
            'total_items_con_stock': total_items_con_stock,
            'total_unidades': total_unidades,
            'valor_total_inventario': int(valor_total_inventario),
            'valor_potencial_venta': int(valor_potencial_venta),
            'margen_esperado': int(margen_esperado),
            'porcentaje_margen': round(porcentaje_margen, 2),
            'costo_promedio_por_unidad': round(costo_promedio, 2),
            'precio_promedio_venta': round(precio_promedio, 2)
        }

    def get_by_department(self) -> Dict:
        """
        Analiza inventario por departamento (HOMBRE, MUJER, NIÑO, NIÑA)

        Returns:
            {
                'HOMBRE': {
                    'total_items': int,
                    'total_unidades': int,
                    'valor_inventario': int,
                    'valor_potencial_venta': int,
                    'margen': int,
                    'por_categoria': {...}
                },
                ...
            }
        """
        departments = defaultdict(lambda: {
            'total_items': 0,
            'total_unidades': 0,
            'valor_inventario': 0,
            'valor_potencial_venta': 0,
            'margen': 0,
            'por_categoria': defaultdict(lambda: {
                'total_items': 0,
                'total_unidades': 0,
                'valor_inventario': 0
            })
        })

        for item in self.items:
            if item.get('type') != 'variant':
                continue

            # Parsear nombre para obtener género
            name = item.get('name', '')
            parsed = self.sku_parser.extract_size_from_product_name(name)
            gender = parsed.get('gender', 'UNKNOWN')

            # Obtener categoría desde item de Alegra
            item_category = item.get('itemCategory', {})
            category_name = item_category.get('name', 'SIN CATEGORÍA') if item_category else 'SIN CATEGORÍA'

            inventory = item.get('inventory', {})
            if not inventory:
                continue

            quantity = inventory.get('availableQuantity', 0)
            unit_cost = inventory.get('unitCost', 0)

            prices = item.get('price', [])
            sale_price = prices[0].get('price', 0) if prices else 0

            valor_inv = quantity * unit_cost
            valor_venta = quantity * sale_price
            margen = valor_venta - valor_inv

            # Actualizar departamento
            dept = departments[gender]
            dept['total_items'] += 1
            if quantity > 0:
                dept['total_unidades'] += quantity
                dept['valor_inventario'] += valor_inv
                dept['valor_potencial_venta'] += valor_venta
                dept['margen'] += margen

                # Por categoría dentro del departamento
                cat = dept['por_categoria'][category_name]
                cat['total_items'] += 1
                cat['total_unidades'] += quantity
                cat['valor_inventario'] += valor_inv

        # Convertir a dict normal y formatear
        result = {}
        for dept_name, dept_data in departments.items():
            result[dept_name] = {
                'total_items': dept_data['total_items'],
                'total_unidades': dept_data['total_unidades'],
                'valor_inventario': int(dept_data['valor_inventario']),
                'valor_potencial_venta': int(dept_data['valor_potencial_venta']),
                'margen': int(dept_data['margen']),
                'por_categoria': {
                    cat: {
                        'total_items': data['total_items'],
                        'total_unidades': data['total_unidades'],
                        'valor_inventario': int(data['valor_inventario'])
                    }
                    for cat, data in dept_data['por_categoria'].items()
                }
            }

        return result

    def get_by_category(self) -> List[Dict]:
        """
        Analiza inventario por categoría de producto

        Returns:
            Lista de categorías ordenadas por valor:
            [
                {
                    'categoria': str,
                    'total_items': int,
                    'total_unidades': int,
                    'valor_inventario': int,
                    'porcentaje_valor': float
                },
                ...
            ]
        """
        categories = defaultdict(lambda: {
            'total_items': 0,
            'total_unidades': 0,
            'valor_inventario': 0
        })

        total_valor = 0

        for item in self.items:
            if item.get('type') != 'variant':
                continue

            item_category = item.get('itemCategory', {})
            category_name = item_category.get('name', 'SIN CATEGORÍA') if item_category else 'SIN CATEGORÍA'

            inventory = item.get('inventory', {})
            if not inventory:
                continue

            quantity = inventory.get('availableQuantity', 0)
            unit_cost = inventory.get('unitCost', 0)

            valor = quantity * unit_cost
            total_valor += valor

            cat = categories[category_name]
            cat['total_items'] += 1
            cat['total_unidades'] += quantity
            cat['valor_inventario'] += valor

        # Convertir a lista y calcular porcentajes
        result = []
        for cat_name, cat_data in categories.items():
            porcentaje = (cat_data['valor_inventario'] / total_valor * 100) if total_valor > 0 else 0
            result.append({
                'categoria': cat_name,
                'total_items': cat_data['total_items'],
                'total_unidades': cat_data['total_unidades'],
                'valor_inventario': int(cat_data['valor_inventario']),
                'porcentaje_valor': round(porcentaje, 2)
            })

        # Ordenar por valor descendente
        result.sort(key=lambda x: x['valor_inventario'], reverse=True)
        return result

    def get_by_size(self) -> List[Dict]:
        """
        Analiza inventario por talla

        Returns:
            Lista de tallas ordenadas por unidades:
            [
                {
                    'talla': str,
                    'total_unidades': int,
                    'valor_inventario': int,
                    'cantidad_items': int
                },
                ...
            ]
        """
        sizes = defaultdict(lambda: {
            'total_unidades': 0,
            'valor_inventario': 0,
            'cantidad_items': 0
        })

        for item in self.items:
            if item.get('type') != 'variant':
                continue

            name = item.get('name', '')
            parsed = self.sku_parser.extract_size_from_product_name(name)
            size = parsed.get('size', 'UNKNOWN')

            inventory = item.get('inventory', {})
            if not inventory:
                continue

            quantity = inventory.get('availableQuantity', 0)
            unit_cost = inventory.get('unitCost', 0)

            valor = quantity * unit_cost

            sz = sizes[size]
            sz['total_unidades'] += quantity
            sz['valor_inventario'] += valor
            sz['cantidad_items'] += 1

        # Convertir a lista
        result = []
        for size_name, size_data in sizes.items():
            result.append({
                'talla': size_name,
                'total_unidades': size_data['total_unidades'],
                'valor_inventario': int(size_data['valor_inventario']),
                'cantidad_items': size_data['cantidad_items']
            })

        # Ordenar por unidades descendente
        result.sort(key=lambda x: x['total_unidades'], reverse=True)
        return result

    def get_out_of_stock(self) -> List[Dict]:
        """
        Obtiene productos sin stock

        Returns:
            Lista de productos sin stock:
            [
                {
                    'id': str,
                    'nombre': str,
                    'categoria': str,
                    'departamento': str,
                    'precio_venta': int
                },
                ...
            ]
        """
        out_of_stock = []

        for item in self.items:
            if item.get('type') != 'variant':
                continue

            inventory = item.get('inventory', {})
            if not inventory:
                continue

            quantity = inventory.get('availableQuantity', 0)

            if quantity == 0:
                name = item.get('name', '')
                parsed = self.sku_parser.extract_size_from_product_name(name)

                item_category = item.get('itemCategory', {})
                category_name = item_category.get('name', 'SIN CATEGORÍA') if item_category else 'SIN CATEGORÍA'

                prices = item.get('price', [])
                sale_price = prices[0].get('price', 0) if prices else 0

                out_of_stock.append({
                    'id': item.get('id', ''),
                    'nombre': name,
                    'categoria': category_name,
                    'departamento': parsed.get('gender', 'UNKNOWN'),
                    'precio_venta': sale_price
                })

        return out_of_stock

    def get_low_stock(self, threshold: int = 5) -> List[Dict]:
        """
        Obtiene productos con bajo stock

        Args:
            threshold: Cantidad mínima para considerar bajo stock

        Returns:
            Lista de productos con bajo stock
        """
        low_stock = []

        for item in self.items:
            if item.get('type') != 'variant':
                continue

            inventory = item.get('inventory', {})
            if not inventory:
                continue

            quantity = inventory.get('availableQuantity', 0)

            if 0 < quantity <= threshold:
                name = item.get('name', '')
                parsed = self.sku_parser.extract_size_from_product_name(name)

                item_category = item.get('itemCategory', {})
                category_name = item_category.get('name', 'SIN CATEGORÍA') if item_category else 'SIN CATEGORÍA'

                prices = item.get('price', [])
                sale_price = prices[0].get('price', 0) if prices else 0

                low_stock.append({
                    'id': item.get('id', ''),
                    'nombre': name,
                    'categoria': category_name,
                    'departamento': parsed.get('gender', 'UNKNOWN'),
                    'cantidad_disponible': quantity,
                    'precio_venta': sale_price
                })

        # Ordenar por cantidad disponible
        low_stock.sort(key=lambda x: x['cantidad_disponible'])
        return low_stock

    def get_top_by_value(self, limit: int = 20) -> List[Dict]:
        """
        Obtiene top productos por valor en inventario

        Args:
            limit: Cantidad de productos a retornar

        Returns:
            Lista de top productos ordenados por valor
        """
        products = []

        for item in self.items:
            if item.get('type') != 'variant':
                continue

            inventory = item.get('inventory', {})
            if not inventory:
                continue

            quantity = inventory.get('availableQuantity', 0)
            unit_cost = inventory.get('unitCost', 0)

            if quantity == 0:
                continue

            name = item.get('name', '')
            parsed = self.sku_parser.extract_size_from_product_name(name)

            item_category = item.get('itemCategory', {})
            category_name = item_category.get('name', 'SIN CATEGORÍA') if item_category else 'SIN CATEGORÍA'

            prices = item.get('price', [])
            sale_price = prices[0].get('price', 0) if prices else 0

            valor = quantity * unit_cost

            products.append({
                'id': item.get('id', ''),
                'nombre': name,
                'categoria': category_name,
                'departamento': parsed.get('gender', 'UNKNOWN'),
                'cantidad': quantity,
                'costo_unitario': unit_cost,
                'precio_venta': sale_price,
                'valor_inventario': int(valor),
                'valor_potencial_venta': int(quantity * sale_price)
            })

        # Ordenar por valor descendente
        products.sort(key=lambda x: x['valor_inventario'], reverse=True)
        return products[:limit]

    def get_abc_analysis(self) -> Dict:
        """
        Análisis ABC del inventario
        Clasifica productos por su contribución al valor total

        A: Top 20% de productos que representan ~80% del valor
        B: Siguiente 30% que representan ~15% del valor
        C: Restante 50% que representan ~5% del valor

        Returns:
            {
                'clase_A': {
                    'cantidad_items': int,
                    'porcentaje_items': float,
                    'valor_inventario': int,
                    'porcentaje_valor': float
                },
                'clase_B': {...},
                'clase_C': {...}
            }
        """
        # Obtener todos los productos con valor
        products = []
        total_valor = 0

        for item in self.items:
            if item.get('type') != 'variant':
                continue

            inventory = item.get('inventory', {})
            if not inventory:
                continue

            quantity = inventory.get('availableQuantity', 0)
            unit_cost = inventory.get('unitCost', 0)

            valor = quantity * unit_cost
            if valor == 0:
                continue

            total_valor += valor
            products.append({
                'id': item.get('id', ''),
                'nombre': item.get('name', ''),
                'valor': valor
            })

        # Ordenar por valor descendente
        products.sort(key=lambda x: x['valor'], reverse=True)

        # Clasificar en A, B, C
        total_items = len(products)
        valor_acumulado = 0
        clase_a_items = 0
        clase_b_items = 0
        clase_c_items = 0
        clase_a_valor = 0
        clase_b_valor = 0
        clase_c_valor = 0

        for i, prod in enumerate(products):
            valor_acumulado += prod['valor']
            porcentaje_valor = valor_acumulado / total_valor * 100 if total_valor > 0 else 0

            if porcentaje_valor <= 80:
                clase_a_items += 1
                clase_a_valor += prod['valor']
            elif porcentaje_valor <= 95:
                clase_b_items += 1
                clase_b_valor += prod['valor']
            else:
                clase_c_items += 1
                clase_c_valor += prod['valor']

        return {
            'clase_A': {
                'cantidad_items': clase_a_items,
                'porcentaje_items': round(clase_a_items / total_items * 100, 2) if total_items > 0 else 0,
                'valor_inventario': int(clase_a_valor),
                'porcentaje_valor': round(clase_a_valor / total_valor * 100, 2) if total_valor > 0 else 0
            },
            'clase_B': {
                'cantidad_items': clase_b_items,
                'porcentaje_items': round(clase_b_items / total_items * 100, 2) if total_items > 0 else 0,
                'valor_inventario': int(clase_b_valor),
                'porcentaje_valor': round(clase_b_valor / total_valor * 100, 2) if total_valor > 0 else 0
            },
            'clase_C': {
                'cantidad_items': clase_c_items,
                'porcentaje_items': round(clase_c_items / total_items * 100, 2) if total_items > 0 else 0,
                'valor_inventario': int(clase_c_valor),
                'porcentaje_valor': round(clase_c_valor / total_valor * 100, 2) if total_valor > 0 else 0
            }
        }
