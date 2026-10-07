"""
Servicio de análisis de productos
Procesa datos de facturas de Alegra para generar análisis de productos vendidos
"""
from typing import Dict, List, Any, Tuple
from datetime import datetime
import logging
from app.services.sku_parser import SKUParser
from app.utils.formatters import filter_voided_invoices

logger = logging.getLogger(__name__)


class ProductAnalytics:
    """Servicio para analizar productos de facturas de Alegra"""

    def __init__(self, invoices: List[Dict[str, Any]]):
        """
        Inicializa el servicio con facturas de Alegra

        Args:
            invoices: Lista de facturas de Alegra con estructura completa
        """
        # Las anuladas no son venta (antes se contaban sus prendas y su dinero)
        voided_info = filter_voided_invoices(invoices or [])
        self.invoices = voided_info['active_invoices']
        self.voided_count = voided_info['voided_count']
        self.products_data = []
        self._process_invoices()

    def _process_invoices(self):
        """Extrae items de todas las facturas y los estructura"""
        for invoice in self.invoices:
            items = invoice.get('items', [])
            for item in items:
                nombre = item.get('name', '')

                # Parsear SKU y talla del nombre del producto
                parsed_data = SKUParser.extract_size_from_product_name(nombre)

                # Extraer datos del item
                product = {
                    'nombre': nombre,
                    'cantidad': int(item.get('quantity', 0)),
                    'precio_unitario': float(item.get('price', 0)),
                    'total': float(item.get('total', 0)),
                    'factura_id': invoice.get('id', ''),
                    'fecha': invoice.get('date', ''),
                    'numero_factura': invoice.get('numberTemplate', {}).get('fullNumber', ''),
                    # Datos parseados del SKU
                    'talla': parsed_data.get('size', 'UNKNOWN'),
                    'talla_codigo': parsed_data.get('size_code', ''),
                    'genero': parsed_data.get('gender', 'UNKNOWN'),
                    'sku': parsed_data.get('sku_code', ''),
                    'producto_base': parsed_data.get('product_base', nombre)
                }
                self.products_data.append(product)

    def _units(self, exclude_bolsa: bool = True) -> int:
        """Unidades vendidas, sin la BOLSA PAPEL si exclude_bolsa."""
        return sum(p['cantidad'] for p in self.products_data
                   if not (exclude_bolsa and 'BOLSA PAPEL' in p['nombre'].upper()))

    @staticmethod
    def normalize_product_name(name: str) -> str:
        """
        Normaliza el nombre del producto eliminando códigos y números
        Ejemplo: "CAMISETA MUJER 39900 / 1052399003" -> "CAMISETA MUJER"

        Args:
            name: Nombre completo del producto

        Returns:
            Nombre base del producto sin códigos
        """
        if not name:
            return ""

        # Tomar la parte antes del "/" si existe
        base_name = name.split('/')[0].strip()

        # Eliminar tokens que son solo números o empiezan con números
        tokens = base_name.split()
        filtered_tokens = [
            token for token in tokens
            if not token.isdigit() and not token[0].isdigit()
        ]

        return ' '.join(filtered_tokens).strip()

    @staticmethod
    def format_pesos(value: float) -> str:
        """Formatea valor en pesos colombianos"""
        return f"$ {int(value):,}".replace(',', '.')

    @staticmethod
    def format_number(value: int) -> str:
        """Formatea número con separador de miles"""
        return f"{int(value):,}".replace(',', '.')

    @staticmethod
    def format_percentage(value: float) -> str:
        """Formatea porcentaje con 2 decimales"""
        return f"{value:.2f}%"

    def get_summary(self) -> Dict[str, Any]:
        """
        Obtiene resumen ejecutivo de ventas

        Returns:
            Dict con métricas principales
        """
        # Filtrar BOLSA PAPEL para estadísticas
        products_filtered = [
            p for p in self.products_data
            if 'BOLSA PAPEL' not in p['nombre'].upper()
        ]

        # Unidades: solo prendas (la bolsa se vende casi en cada factura e
        # inflaba el total). El dinero sí incluye todo lo facturado.
        total_productos = sum(p['cantidad'] for p in products_filtered)
        total_ingresos = sum(p['total'] for p in self.products_data)

        # Producto más vendido (excluyendo BOLSA PAPEL)
        if products_filtered:
            # Agrupar por nombre y sumar cantidades
            product_qty = {}
            for p in products_filtered:
                nombre = p['nombre']
                product_qty[nombre] = product_qty.get(nombre, 0) + p['cantidad']

            best_product = max(product_qty.items(), key=lambda x: x[1])
            best_prod_name = best_product[0]
            best_prod_qty = best_product[1]
        else:
            best_prod_name = "N/A"
            best_prod_qty = 0

        return {
            'total_productos_vendidos': total_productos,
            'total_productos_vendidos_formatted': self.format_number(total_productos),
            'ingresos_totales': total_ingresos,
            'ingresos_totales_formatted': self.format_pesos(total_ingresos),
            'producto_mas_vendido': best_prod_name,
            'unidades_mas_vendido': best_prod_qty,
            'unidades_mas_vendido_formatted': self.format_number(best_prod_qty),
            'numero_facturas': len(self.invoices),
            'facturas_anuladas_excluidas': self.voided_count,
            'numero_items_unicos': len(set(p['nombre'] for p in self.products_data))
        }

    def get_top_products(self, limit: int = 10, exclude_bolsa: bool = True) -> List[Dict[str, Any]]:
        """
        Obtiene top productos sin unificar (productos individuales con códigos)

        Args:
            limit: Número de productos a retornar
            exclude_bolsa: Si True, excluye BOLSA PAPEL

        Returns:
            Lista de productos ordenados por cantidad vendida
        """
        # Agrupar por nombre exacto
        products_grouped = {}
        for p in self.products_data:
            nombre = p['nombre']

            if exclude_bolsa and 'BOLSA PAPEL' in nombre.upper():
                continue

            if nombre not in products_grouped:
                products_grouped[nombre] = {
                    'nombre': nombre,
                    'cantidad': 0,
                    'ingresos': 0
                }

            products_grouped[nombre]['cantidad'] += p['cantidad']
            products_grouped[nombre]['ingresos'] += p['total']

        # Ordenar por cantidad
        products_list = list(products_grouped.values())
        products_list.sort(key=lambda x: x['cantidad'], reverse=True)

        # Participación sobre las mismas unidades que entran al ranking (antes
        # el total incluía la bolsa y todos los % salían más bajos)
        total_productos = self._units(exclude_bolsa)

        result = []
        for idx, product in enumerate(products_list[:limit], 1):
            pct = (product['cantidad'] / total_productos * 100) if total_productos > 0 else 0
            result.append({
                'ranking': idx,
                'nombre': product['nombre'],
                'cantidad': product['cantidad'],
                'cantidad_formatted': self.format_number(product['cantidad']),
                'ingresos': product['ingresos'],
                'ingresos_formatted': self.format_pesos(product['ingresos']),
                'porcentaje_participacion': pct,
                'porcentaje_participacion_formatted': self.format_percentage(pct)
            })

        return result

    def get_top_products_unified(self, limit: int = 10, exclude_bolsa: bool = True) -> List[Dict[str, Any]]:
        """
        Obtiene top productos unificados (agrupa variantes del mismo producto)
        Ejemplo: Agrupa todas las "CAMISETA MUJER" sin importar código/precio

        Args:
            limit: Número de productos a retornar
            exclude_bolsa: Si True, excluye BOLSA PAPEL

        Returns:
            Lista de productos unificados ordenados por cantidad vendida
        """
        # Agrupar por nombre base (unificado)
        products_grouped = {}
        for p in self.products_data:
            nombre_base = self.normalize_product_name(p['nombre'])

            if not nombre_base:
                continue

            if exclude_bolsa and 'BOLSA PAPEL' in nombre_base.upper():
                continue

            if nombre_base not in products_grouped:
                products_grouped[nombre_base] = {
                    'nombre_base': nombre_base,
                    'cantidad': 0,
                    'ingresos': 0,
                    'variantes': set()
                }

            products_grouped[nombre_base]['cantidad'] += p['cantidad']
            products_grouped[nombre_base]['ingresos'] += p['total']
            products_grouped[nombre_base]['variantes'].add(p['nombre'])

        # Ordenar por cantidad
        products_list = list(products_grouped.values())
        products_list.sort(key=lambda x: x['cantidad'], reverse=True)

        # Participación sobre las mismas unidades que entran al ranking (antes
        # el total incluía la bolsa y todos los % salían más bajos)
        total_productos = self._units(exclude_bolsa)

        result = []
        for idx, product in enumerate(products_list[:limit], 1):
            pct = (product['cantidad'] / total_productos * 100) if total_productos > 0 else 0
            result.append({
                'ranking': idx,
                'nombre_base': product['nombre_base'],
                'cantidad': product['cantidad'],
                'cantidad_formatted': self.format_number(product['cantidad']),
                'ingresos': product['ingresos'],
                'ingresos_formatted': self.format_pesos(product['ingresos']),
                'porcentaje_participacion': pct,
                'porcentaje_participacion_formatted': self.format_percentage(pct),
                'numero_variantes': len(product['variantes']),
                'variantes': list(product['variantes'])
            })

        return result

    def get_all_products_unified(self, exclude_bolsa: bool = True) -> List[Dict[str, Any]]:
        """
        Obtiene todos los productos unificados (sin límite)

        Args:
            exclude_bolsa: Si True, excluye BOLSA PAPEL

        Returns:
            Lista completa de productos unificados ordenados por cantidad
        """
        return self.get_top_products_unified(limit=9999, exclude_bolsa=exclude_bolsa)

    def get_all_products(self, exclude_bolsa: bool = False) -> List[Dict[str, Any]]:
        """
        Obtiene listado completo de todos los productos sin unificar

        Args:
            exclude_bolsa: Si True, excluye BOLSA PAPEL

        Returns:
            Lista completa de productos ordenados por cantidad
        """
        return self.get_top_products(limit=9999, exclude_bolsa=exclude_bolsa)

    def get_complete_report(self) -> Dict[str, Any]:
        """
        Genera reporte completo con todos los análisis

        Returns:
            Dict con resumen, top 10, unificados, listado completo y análisis por tallas
        """
        summary = self.get_summary()
        top_10 = self.get_top_products(limit=10, exclude_bolsa=True)
        top_10_unified = self.get_top_products_unified(limit=10, exclude_bolsa=True)
        all_unified = self.get_all_products_unified(exclude_bolsa=True)
        all_products = self.get_all_products(exclude_bolsa=False)

        # Agregar análisis por tallas
        sales_by_size = self.get_sales_by_size()
        sales_by_category_size = self.get_sales_by_category_and_size()
        sales_by_department_size = self.get_sales_by_department_and_size()

        # Análisis unificado departamento > categoría > tallas
        unified_analysis = self.get_unified_department_category_size_analysis()

        return {
            'resumen_ejecutivo': summary,
            'top_10_productos': top_10,
            'top_10_productos_unificados': top_10_unified,
            'todos_productos_unificados': all_unified,
            'listado_completo': all_products,
            'ventas_por_talla': sales_by_size,
            'ventas_por_categoria_talla': sales_by_category_size,
            'ventas_por_departamento_talla': sales_by_department_size,
            'analisis_unificado': unified_analysis,
            'metadata': {
                'fecha_generacion': datetime.now().isoformat(),
                'numero_facturas_procesadas': len(self.invoices),
                'numero_items_procesados': len(self.products_data)
            }
        }

    def get_category_analysis(self) -> Dict[str, Any]:
        """
        Analiza productos por categorías detectadas automáticamente

        Returns:
            Dict con análisis por categoría (CAMISETA, JEAN, BLUSA, etc.)
        """
        categories = {}

        # Palabras clave de categorías comunes
        category_keywords = ['CAMISETA', 'JEAN', 'BLUSA', 'POLO', 'MEDIAS',
                             'PANTALON', 'SHORT', 'VESTIDO', 'FALDA', 'SUDADERA']

        for p in self.products_data:
            nombre_upper = p['nombre'].upper()
            if 'BOLSA PAPEL' in nombre_upper:
                continue

            # Detectar categoría
            category = 'OTROS'
            for keyword in category_keywords:
                if keyword in nombre_upper:
                    category = keyword
                    break

            if category not in categories:
                categories[category] = {
                    'categoria': category,
                    'cantidad': 0,
                    'ingresos': 0,
                    'productos': []
                }

            categories[category]['cantidad'] += p['cantidad']
            categories[category]['ingresos'] += p['total']
            if p['nombre'] not in categories[category]['productos']:
                categories[category]['productos'].append(p['nombre'])

        # Ordenar por cantidad
        categories_list = list(categories.values())
        categories_list.sort(key=lambda x: x['cantidad'], reverse=True)

        # Calcular porcentajes (sin la bolsa)
        total_productos = self._units(exclude_bolsa=True)

        result = []
        for cat in categories_list:
            pct = (cat['cantidad'] / total_productos * 100) if total_productos > 0 else 0
            result.append({
                'categoria': cat['categoria'],
                'cantidad': cat['cantidad'],
                'cantidad_formatted': self.format_number(cat['cantidad']),
                'ingresos': cat['ingresos'],
                'ingresos_formatted': self.format_pesos(cat['ingresos']),
                'porcentaje_participacion': pct,
                'porcentaje_participacion_formatted': self.format_percentage(pct),
                'numero_productos_diferentes': len(cat['productos'])
            })

        return {
            'categorias': result,
            'total_categorias': len(result)
        }

    def get_sales_by_size(self, exclude_bolsa: bool = True, exclude_unknown: bool = True) -> Dict[str, Any]:
        """
        Análisis global de ventas por talla

        Args:
            exclude_bolsa: Si True, excluye BOLSA PAPEL
            exclude_unknown: Si True, excluye productos sin talla identificada

        Returns:
            {
                'total_units': int,
                'total_revenue': float,
                'sizes': [
                    {
                        'size': str,
                        'units': int,
                        'percentage': float,
                        'revenue': float,
                        'revenue_formatted': str
                    },
                    ...
                ]
            }
        """
        # Agrupar por talla
        sizes_data = {}
        total_units = 0
        total_revenue = 0

        for p in self.products_data:
            # Filtros
            if exclude_bolsa and 'BOLSA PAPEL' in p['nombre'].upper():
                continue

            talla = p.get('talla', 'UNKNOWN')

            if exclude_unknown and talla == 'UNKNOWN':
                continue

            if talla not in sizes_data:
                sizes_data[talla] = {
                    'size': talla,
                    'units': 0,
                    'revenue': 0
                }

            sizes_data[talla]['units'] += p['cantidad']
            sizes_data[talla]['revenue'] += p['total']
            total_units += p['cantidad']
            total_revenue += p['total']

        # Convertir a lista y ordenar por unidades
        sizes_list = list(sizes_data.values())
        sizes_list.sort(key=lambda x: x['units'], reverse=True)

        # Calcular porcentajes y formatear
        result = []
        for size_data in sizes_list:
            pct = (size_data['units'] / total_units * 100) if total_units > 0 else 0
            result.append({
                'size': size_data['size'],
                'units': size_data['units'],
                'units_formatted': self.format_number(size_data['units']),
                'percentage': pct,
                'percentage_formatted': self.format_percentage(pct),
                'revenue': size_data['revenue'],
                'revenue_formatted': self.format_pesos(size_data['revenue'])
            })

        return {
            'total_units': total_units,
            'total_units_formatted': self.format_number(total_units),
            'total_revenue': total_revenue,
            'total_revenue_formatted': self.format_pesos(total_revenue),
            'sizes': result,
            'total_sizes': len(result)
        }

    def get_sales_by_category_and_size(self, exclude_bolsa: bool = True, exclude_unknown: bool = True) -> Dict[str, Any]:
        """
        Análisis de ventas por categoría, desglosado por talla

        Args:
            exclude_bolsa: Si True, excluye BOLSA PAPEL
            exclude_unknown: Si True, excluye productos sin talla identificada

        Returns:
            {
                'categories': [
                    {
                        'category': str,
                        'total_units': int,
                        'percentage_of_total': float,
                        'total_revenue': float,
                        'sizes': [
                            {
                                'size': str,
                                'units': int,
                                'percentage_in_category': float,
                                'revenue': float
                            },
                            ...
                        ]
                    },
                    ...
                ]
            }
        """
        # Keywords de categorías
        category_keywords = ['CAMISETA', 'JEAN', 'BLUSA', 'POLO', 'MEDIAS',
                             'PANTALON', 'SHORT', 'VESTIDO', 'FALDA', 'SUDADERA',
                             'JOGGER', 'BUZO', 'CHAQUETA', 'BODY']

        # Estructura: {categoria: {talla: {units, revenue}}}
        categories_data = {}
        total_units = 0

        for p in self.products_data:
            # Filtros
            if exclude_bolsa and 'BOLSA PAPEL' in p['nombre'].upper():
                continue

            talla = p.get('talla', 'UNKNOWN')
            if exclude_unknown and talla == 'UNKNOWN':
                continue

            # Determinar categoría
            nombre_upper = p['nombre'].upper()
            category = 'OTROS'
            for keyword in category_keywords:
                if keyword in nombre_upper:
                    category = keyword
                    break

            # Inicializar estructuras
            if category not in categories_data:
                categories_data[category] = {
                    'category': category,
                    'total_units': 0,
                    'total_revenue': 0,
                    'sizes': {}
                }

            if talla not in categories_data[category]['sizes']:
                categories_data[category]['sizes'][talla] = {
                    'size': talla,
                    'units': 0,
                    'revenue': 0
                }

            # Acumular datos
            categories_data[category]['total_units'] += p['cantidad']
            categories_data[category]['total_revenue'] += p['total']
            categories_data[category]['sizes'][talla]['units'] += p['cantidad']
            categories_data[category]['sizes'][talla]['revenue'] += p['total']
            total_units += p['cantidad']

        # Convertir a lista y ordenar
        categories_list = list(categories_data.values())
        categories_list.sort(key=lambda x: x['total_units'], reverse=True)

        # Formatear resultado
        result = []
        for cat_data in categories_list:
            # Calcular porcentaje de la categoría sobre el total
            pct_total = (cat_data['total_units'] / total_units * 100) if total_units > 0 else 0

            # Convertir sizes dict a lista y ordenar
            sizes_list = list(cat_data['sizes'].values())
            sizes_list.sort(key=lambda x: x['units'], reverse=True)

            # Formatear tallas
            sizes_formatted = []
            for size_data in sizes_list:
                pct_in_cat = (size_data['units'] / cat_data['total_units'] * 100) if cat_data['total_units'] > 0 else 0
                sizes_formatted.append({
                    'size': size_data['size'],
                    'units': size_data['units'],
                    'units_formatted': self.format_number(size_data['units']),
                    'percentage_in_category': pct_in_cat,
                    'percentage_in_category_formatted': self.format_percentage(pct_in_cat),
                    'revenue': size_data['revenue'],
                    'revenue_formatted': self.format_pesos(size_data['revenue'])
                })

            result.append({
                'category': cat_data['category'],
                'total_units': cat_data['total_units'],
                'total_units_formatted': self.format_number(cat_data['total_units']),
                'percentage_of_total': pct_total,
                'percentage_of_total_formatted': self.format_percentage(pct_total),
                'total_revenue': cat_data['total_revenue'],
                'total_revenue_formatted': self.format_pesos(cat_data['total_revenue']),
                'sizes': sizes_formatted,
                'total_sizes_in_category': len(sizes_formatted)
            })

        return {
            'categories': result,
            'total_categories': len(result),
            'total_units': total_units,
            'total_units_formatted': self.format_number(total_units)
        }

    def get_sales_by_department_and_size(self, exclude_bolsa: bool = True, exclude_unknown: bool = True) -> Dict[str, Any]:
        """
        Análisis por departamento (género) y talla

        Args:
            exclude_bolsa: Si True, excluye BOLSA PAPEL
            exclude_unknown: Si True, excluye productos sin talla identificada

        Returns:
            {
                'departments': [
                    {
                        'department': str,  # MUJER, HOMBRE, NIÑO, NIÑA
                        'total_units': int,
                        'percentage_of_total': float,
                        'total_revenue': float,
                        'sizes': [
                            {
                                'size': str,
                                'units': int,
                                'percentage_in_department': float,
                                'revenue': float
                            },
                            ...
                        ]
                    },
                    ...
                ]
            }
        """
        # Estructura: {departamento: {talla: {units, revenue}}}
        departments_data = {}
        total_units = 0

        for p in self.products_data:
            # Filtros
            if exclude_bolsa and 'BOLSA PAPEL' in p['nombre'].upper():
                continue

            talla = p.get('talla', 'UNKNOWN')
            if exclude_unknown and talla == 'UNKNOWN':
                continue

            genero = p.get('genero', 'UNKNOWN')

            # Inicializar estructuras
            if genero not in departments_data:
                departments_data[genero] = {
                    'department': genero,
                    'total_units': 0,
                    'total_revenue': 0,
                    'sizes': {}
                }

            if talla not in departments_data[genero]['sizes']:
                departments_data[genero]['sizes'][talla] = {
                    'size': talla,
                    'units': 0,
                    'revenue': 0
                }

            # Acumular datos
            departments_data[genero]['total_units'] += p['cantidad']
            departments_data[genero]['total_revenue'] += p['total']
            departments_data[genero]['sizes'][talla]['units'] += p['cantidad']
            departments_data[genero]['sizes'][talla]['revenue'] += p['total']
            total_units += p['cantidad']

        # Convertir a lista y ordenar
        departments_list = list(departments_data.values())
        departments_list.sort(key=lambda x: x['total_units'], reverse=True)

        # Formatear resultado
        result = []
        for dept_data in departments_list:
            # Calcular porcentaje del departamento sobre el total
            pct_total = (dept_data['total_units'] / total_units * 100) if total_units > 0 else 0

            # Convertir sizes dict a lista y ordenar
            sizes_list = list(dept_data['sizes'].values())
            sizes_list.sort(key=lambda x: x['units'], reverse=True)

            # Formatear tallas
            sizes_formatted = []
            for size_data in sizes_list:
                pct_in_dept = (size_data['units'] / dept_data['total_units'] * 100) if dept_data['total_units'] > 0 else 0
                sizes_formatted.append({
                    'size': size_data['size'],
                    'units': size_data['units'],
                    'units_formatted': self.format_number(size_data['units']),
                    'percentage_in_department': pct_in_dept,
                    'percentage_in_department_formatted': self.format_percentage(pct_in_dept),
                    'revenue': size_data['revenue'],
                    'revenue_formatted': self.format_pesos(size_data['revenue'])
                })

            result.append({
                'department': dept_data['department'],
                'total_units': dept_data['total_units'],
                'total_units_formatted': self.format_number(dept_data['total_units']),
                'percentage_of_total': pct_total,
                'percentage_of_total_formatted': self.format_percentage(pct_total),
                'total_revenue': dept_data['total_revenue'],
                'total_revenue_formatted': self.format_pesos(dept_data['total_revenue']),
                'sizes': sizes_formatted,
                'total_sizes_in_department': len(sizes_formatted)
            })

        return {
            'departments': result,
            'total_departments': len(result),
            'total_units': total_units,
            'total_units_formatted': self.format_number(total_units)
        }

    def _classify_product_category(self, nombre: str) -> str:
        """
        Clasifica un producto en una categoría basándose en su nombre

        Args:
            nombre: Nombre del producto

        Returns:
            Categoría del producto
        """
        nombre_upper = nombre.upper()

        # Categorías de ROPA (prendas)
        clothing_keywords = {
            'CAMISETA': ['CAMISETA', 'CAMISA'],
            'JEAN': ['JEAN', 'JEANS'],
            'BLUSA': ['BLUSA'],
            'POLO': ['POLO'],
            'PANTALON': ['PANTALON'],
            'SHORT': ['SHORT'],
            'VESTIDO': ['VESTIDO'],
            'FALDA': ['FALDA'],
            'SUDADERA': ['SUDADERA'],
            'JOGGER': ['JOGGER'],
            'BUZO': ['BUZO'],
            'CHAQUETA': ['CHAQUETA'],
            'BODY': ['BODY'],
            'ENTERIZO': ['ENTERIZO'],
            'PIJAMA': ['PIJAMA'],
            'LICRA': ['LICRA'],
            'SUETER': ['SUETER', 'SWEATER'],
        }

        # Categorías de ACCESORIOS
        accessory_keywords = {
            'MEDIAS': ['MEDIAS', 'CALCETINES'],
            'ZAPATOS': ['ZAPATO', 'TENIS', 'SANDALIA', 'BOTA'],
            'CORREA': ['CORREA', 'CINTURON'],
            'GORRA': ['GORRA', 'SOMBRERO', 'CACHUCHA'],
            'BOLSO': ['BOLSO', 'CARTERA', 'MOCHILA'],
            'BUFANDA': ['BUFANDA'],
            'GUANTES': ['GUANTES'],
            'RELOJ': ['RELOJ'],
            'LENTES': ['LENTES', 'GAFAS'],
            'ACCESORIOS': ['ACCESORIO'],
        }

        # Buscar en categorías de ropa
        for category, keywords in clothing_keywords.items():
            for keyword in keywords:
                if keyword in nombre_upper:
                    return category

        # Buscar en categorías de accesorios
        for category, keywords in accessory_keywords.items():
            for keyword in keywords:
                if keyword in nombre_upper:
                    return category

        # Si no encuentra nada, devolver OTROS
        return 'OTROS'

    def _classify_department(self, genero: str, nombre: str) -> str:
        """
        Clasifica el departamento/género del producto

        Args:
            genero: Género parseado del SKU
            nombre: Nombre del producto para clasificación adicional

        Returns:
            Departamento clasificado
        """
        # Si ya viene clasificado del SKU
        if genero and genero != 'UNKNOWN':
            return genero

        # Intentar clasificar por nombre
        nombre_upper = nombre.upper()

        if 'MUJER' in nombre_upper or 'DAMA' in nombre_upper:
            return 'MUJER'
        elif 'HOMBRE' in nombre_upper or 'CABALLERO' in nombre_upper:
            return 'HOMBRE'
        elif 'NIÑO' in nombre_upper and 'NIÑA' not in nombre_upper:
            return 'NIÑO'
        elif 'NIÑA' in nombre_upper:
            return 'NIÑA'
        elif 'INFANTIL' in nombre_upper or 'BEBE' in nombre_upper or 'BABY' in nombre_upper:
            return 'NIÑO'

        # Si no se puede clasificar
        return 'UNKNOWN'

    def get_unified_department_category_size_analysis(self, exclude_bolsa: bool = True, exclude_unknown: bool = False) -> Dict[str, Any]:
        """
        Análisis unificado por departamento > categoría > tallas

        Organizado como:
        - MUJER
          - CAMISETA
            - Tallas
          - JEAN
            - Tallas
        - HOMBRE
        - NIÑOS (combina NIÑO + NIÑA)
        - ACCESORIOS

        Args:
            exclude_bolsa: Si True, excluye BOLSA PAPEL
            exclude_unknown: Si True, excluye productos sin departamento clasificado

        Returns:
            Estructura jerárquica departamento > categoría > tallas
        """
        # Estructura: {departamento: {categoria: {talla: {units, revenue}}}}
        hierarchy = {}
        total_units = 0

        # Definir accesorios
        accessory_categories = ['MEDIAS', 'ZAPATOS', 'CORREA', 'GORRA', 'BOLSO',
                                'BUFANDA', 'GUANTES', 'RELOJ', 'LENTES', 'ACCESORIOS']

        for p in self.products_data:
            # Filtros
            if exclude_bolsa and 'BOLSA PAPEL' in p['nombre'].upper():
                continue

            talla = p.get('talla', 'UNKNOWN')
            if exclude_unknown and talla == 'UNKNOWN':
                continue

            # Clasificar departamento y categoría
            department = self._classify_department(p.get('genero', 'UNKNOWN'), p['nombre'])
            category = self._classify_product_category(p['nombre'])

            # Filtrar UNKNOWN si es necesario
            if exclude_unknown and department == 'UNKNOWN':
                continue

            # Si es accesorio, reasignar departamento
            if category in accessory_categories:
                department = 'ACCESORIOS'
            # Combinar NIÑO y NIÑA en NIÑOS
            elif department in ['NIÑO', 'NIÑA']:
                department = 'NIÑOS'

            # Inicializar estructuras
            if department not in hierarchy:
                hierarchy[department] = {}

            if category not in hierarchy[department]:
                hierarchy[department][category] = {
                    'sizes': {},
                    'total_units': 0,
                    'total_revenue': 0
                }

            if talla not in hierarchy[department][category]['sizes']:
                hierarchy[department][category]['sizes'][talla] = {
                    'size': talla,
                    'units': 0,
                    'revenue': 0
                }

            # Acumular datos
            hierarchy[department][category]['sizes'][talla]['units'] += p['cantidad']
            hierarchy[department][category]['sizes'][talla]['revenue'] += p['total']
            hierarchy[department][category]['total_units'] += p['cantidad']
            hierarchy[department][category]['total_revenue'] += p['total']
            total_units += p['cantidad']

        # Formatear resultado
        result = []

        # Orden de departamentos
        department_order = ['MUJER', 'HOMBRE', 'NIÑOS', 'ACCESORIOS', 'UNKNOWN', 'OTROS']

        for dept_name in department_order:
            if dept_name not in hierarchy:
                continue

            dept_data = hierarchy[dept_name]
            dept_total_units = sum(cat['total_units'] for cat in dept_data.values())
            dept_total_revenue = sum(cat['total_revenue'] for cat in dept_data.values())

            # Formatear categorías
            categories = []
            for cat_name, cat_data in sorted(dept_data.items(), key=lambda x: x[1]['total_units'], reverse=True):
                # Formatear tallas
                sizes = []
                for size_data in sorted(cat_data['sizes'].values(), key=lambda x: x['units'], reverse=True):
                    pct_in_cat = (size_data['units'] / cat_data['total_units'] * 100) if cat_data['total_units'] > 0 else 0
                    sizes.append({
                        'size': size_data['size'],
                        'units': size_data['units'],
                        'units_formatted': self.format_number(size_data['units']),
                        'percentage_in_category': pct_in_cat,
                        'percentage_in_category_formatted': self.format_percentage(pct_in_cat),
                        'revenue': size_data['revenue'],
                        'revenue_formatted': self.format_pesos(size_data['revenue'])
                    })

                pct_of_dept = (cat_data['total_units'] / dept_total_units * 100) if dept_total_units > 0 else 0

                categories.append({
                    'category': cat_name,
                    'total_units': cat_data['total_units'],
                    'total_units_formatted': self.format_number(cat_data['total_units']),
                    'percentage_of_department': pct_of_dept,
                    'percentage_of_department_formatted': self.format_percentage(pct_of_dept),
                    'total_revenue': cat_data['total_revenue'],
                    'total_revenue_formatted': self.format_pesos(cat_data['total_revenue']),
                    'sizes': sizes,
                    'total_sizes': len(sizes)
                })

            pct_of_total = (dept_total_units / total_units * 100) if total_units > 0 else 0

            result.append({
                'department': dept_name,
                'total_units': dept_total_units,
                'total_units_formatted': self.format_number(dept_total_units),
                'percentage_of_total': pct_of_total,
                'percentage_of_total_formatted': self.format_percentage(pct_of_total),
                'total_revenue': dept_total_revenue,
                'total_revenue_formatted': self.format_pesos(dept_total_revenue),
                'categories': categories,
                'total_categories': len(categories)
            })

        return {
            'departments': result,
            'total_departments': len(result),
            'total_units': total_units,
            'total_units_formatted': self.format_number(total_units)
        }
