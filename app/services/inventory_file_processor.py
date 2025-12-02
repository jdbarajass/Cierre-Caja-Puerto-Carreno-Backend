"""
Servicio para procesar archivos de inventario de Alegra
"""
import csv
import io
from typing import Dict, List, Any, BinaryIO
from decimal import Decimal
import openpyxl


class InventoryFileProcessor:
    """Procesador de archivos de inventario"""

    # Departamentos y sus palabras clave
    DEPARTMENT_KEYWORDS = {
        'hombre': ['HOMBRE', 'MASCULINO'],
        'mujer': ['MUJER', 'FEMENINO', 'FALDA', 'BLUSA', 'VESTIDO'],
        'nino': ['NIÑO', 'NINO'],
        'nina': ['NIÑA', 'NINA'],
        'accesorios': [
            'TARJETA', 'GORRA', 'SOMBRERO', 'BUFANDA', 'CINTURON',
            'BOLSO', 'MOCHILA', 'CARTERA', 'BILLETERA', 'GUANTE',
            'MEDIAS', 'CALCETINES', 'RELOJ', 'JOYA', 'ACCESORIO'
        ]
    }

    @staticmethod
    def detect_separator(content: str) -> str:
        """
        Detecta el separador del archivo CSV

        Args:
            content: Contenido del archivo como string

        Returns:
            str: Separador detectado (, o ;)
        """
        first_lines = content.split('\n')[:5]

        # Revisar si hay indicador de separador
        if first_lines and '?sep=' in first_lines[0]:
            return first_lines[0].split('=')[1].strip()

        # Contar ocurrencias de separadores comunes
        semicolon_count = sum(line.count(';') for line in first_lines)
        comma_count = sum(line.count(',') for line in first_lines)

        return ';' if semicolon_count > comma_count else ','

    @staticmethod
    def parse_decimal(value: str) -> Decimal:
        """
        Convierte un string a Decimal manejando formatos con coma y punto

        Args:
            value: String a convertir

        Returns:
            Decimal: Valor convertido
        """
        if not value or not value.strip():
            return Decimal('0')

        # Remover comillas y espacios
        value = value.strip().replace('"', '').replace('=', '')

        # Manejar formato europeo (coma decimal)
        if ',' in value and '.' not in value:
            value = value.replace(',', '.')
        elif ',' in value and '.' in value:
            # Si tiene ambos, asumir que el punto es separador de miles
            value = value.replace('.', '').replace(',', '.')

        try:
            return Decimal(value)
        except:
            return Decimal('0')

    @staticmethod
    def classify_department(category: str, name: str) -> str:
        """
        Clasifica un producto en un departamento basándose en su categoría y nombre

        Args:
            category: Categoría del producto
            name: Nombre del producto

        Returns:
            str: Departamento asignado
        """
        text = f"{category} {name}".upper()

        # Revisar cada departamento
        for dept, keywords in InventoryFileProcessor.DEPARTMENT_KEYWORDS.items():
            if any(keyword in text for keyword in keywords):
                return dept

        return 'otros'

    @staticmethod
    def process_csv_file(file_content: bytes, encoding: str = 'latin-1') -> Dict[str, Any]:
        """
        Procesa un archivo CSV de inventario

        Args:
            file_content: Contenido del archivo en bytes
            encoding: Encoding del archivo

        Returns:
            Dict con el análisis del inventario
        """
        try:
            # Decodificar el contenido
            content = file_content.decode(encoding)

            # Detectar separador
            separator = InventoryFileProcessor.detect_separator(content)

            # Parsear CSV
            lines = content.split('\n')

            # Saltar la primera línea si es indicador de separador
            start_line = 1 if lines and '?sep=' in lines[0] else 0

            # Crear lector CSV
            csv_reader = csv.DictReader(
                lines[start_line:],
                delimiter=separator
            )

            # Procesar filas
            return InventoryFileProcessor._process_rows(list(csv_reader))

        except Exception as e:
            raise ValueError(f"Error procesando archivo CSV: {str(e)}")

    @staticmethod
    def process_excel_file(file_content: bytes) -> Dict[str, Any]:
        """
        Procesa un archivo Excel de inventario

        Args:
            file_content: Contenido del archivo en bytes

        Returns:
            Dict con el análisis del inventario
        """
        try:
            # Cargar workbook
            wb = openpyxl.load_workbook(io.BytesIO(file_content))
            sheet = wb.active

            # Obtener headers (primera fila)
            headers = [cell.value for cell in sheet[1]]

            # Convertir a lista de diccionarios
            rows = []
            for row in sheet.iter_rows(min_row=2, values_only=True):
                row_dict = dict(zip(headers, row))
                rows.append(row_dict)

            # Procesar filas
            return InventoryFileProcessor._process_rows(rows)

        except Exception as e:
            raise ValueError(f"Error procesando archivo Excel: {str(e)}")

    @staticmethod
    def _detect_file_structure(rows: List[Dict[str, Any]]) -> str:
        """
        Detecta qué estructura tiene el archivo de inventario

        Args:
            rows: Lista de diccionarios con los datos

        Returns:
            str: 'alegra_export' para exportación de Alegra o 'alegra_inventory' para inventario de Alegra
        """
        if not rows:
            return 'alegra_export'

        # Verificar columnas de la primera fila
        first_row_keys = set(rows[0].keys())

        # Columnas características de inventario de Alegra
        inventory_columns = {'Ítem', 'Item', 'Cantidad', 'Estado', 'Costo promedio', 'Total'}

        # Columnas características de exportación de productos
        export_columns = {'Tipo', 'tipo', 'Nombre', 'nombre', 'Precio base', 'precio_base'}

        # Contar coincidencias
        inventory_matches = len(inventory_columns & first_row_keys)
        export_matches = len(export_columns & first_row_keys)

        # Si hay más coincidencias con inventario, es inventario
        if inventory_matches > export_matches:
            return 'alegra_inventory'
        else:
            return 'alegra_export'

    @staticmethod
    def _process_rows(rows: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Procesa las filas del inventario y genera el análisis

        Args:
            rows: Lista de diccionarios con los datos de cada producto

        Returns:
            Dict con el análisis completo del inventario
        """
        # Detectar estructura del archivo
        file_structure = InventoryFileProcessor._detect_file_structure(rows)

        # Procesar según la estructura
        if file_structure == 'alegra_inventory':
            return InventoryFileProcessor._process_inventory_rows(rows)
        else:
            return InventoryFileProcessor._process_export_rows(rows)

    @staticmethod
    def _process_export_rows(rows: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Procesa filas de exportación de productos de Alegra (estructura antigua)

        Args:
            rows: Lista de diccionarios con los datos de cada producto

        Returns:
            Dict con el análisis completo del inventario
        """
        # Inicializar contadores por departamento
        departments = {
            'hombre': {'items': [], 'total_cost': Decimal('0'), 'total_price': Decimal('0'), 'quantity': 0},
            'mujer': {'items': [], 'total_cost': Decimal('0'), 'total_price': Decimal('0'), 'quantity': 0},
            'nino': {'items': [], 'total_cost': Decimal('0'), 'total_price': Decimal('0'), 'quantity': 0},
            'nina': {'items': [], 'total_cost': Decimal('0'), 'total_price': Decimal('0'), 'quantity': 0},
            'accesorios': {'items': [], 'total_cost': Decimal('0'), 'total_price': Decimal('0'), 'quantity': 0},
            'otros': {'items': [], 'total_cost': Decimal('0'), 'total_price': Decimal('0'), 'quantity': 0}
        }

        # Contadores generales
        total_items = 0
        total_cost_value = Decimal('0')
        total_price_value = Decimal('0')
        categories_count = {}

        # Procesar cada fila
        for row in rows:
            # Obtener valores (manejar diferentes nombres de columnas)
            tipo = row.get('Tipo', row.get('tipo', ''))
            nombre = row.get('Nombre', row.get('nombre', ''))
            categoria = row.get('Categoría', row.get('Categoria', row.get('categoria', '')))

            # Solo procesar productos y variantes inventariables
            if tipo not in ['Producto', 'Variante', 'producto', 'variante']:
                continue

            # Obtener valores numéricos
            costo_str = row.get('Costo inicial', row.get('costo_inicial', row.get('costo', '0')))
            precio_str = row.get('Precio base', row.get('precio_base', row.get('precio', '0')))

            costo = InventoryFileProcessor.parse_decimal(str(costo_str))
            precio = InventoryFileProcessor.parse_decimal(str(precio_str))

            # Clasificar departamento
            department = InventoryFileProcessor.classify_department(categoria or '', nombre or '')

            # Crear item
            item = {
                'nombre': nombre,
                'categoria': categoria,
                'tipo': tipo,
                'costo': float(costo),
                'precio': float(precio),
                'margen': float(precio - costo) if precio > 0 else 0,
                'margen_porcentaje': float((precio - costo) / precio * 100) if precio > 0 else 0
            }

            # Agregar a departamento
            departments[department]['items'].append(item)
            departments[department]['total_cost'] += costo
            departments[department]['total_price'] += precio
            departments[department]['quantity'] += 1

            # Actualizar contadores generales
            total_items += 1
            total_cost_value += costo
            total_price_value += precio

            # Contar categorías
            if categoria:
                categories_count[categoria] = categories_count.get(categoria, 0) + 1

        # Calcular métricas por departamento
        departments_summary = {}
        for dept_name, dept_data in departments.items():
            if dept_data['quantity'] > 0:
                departments_summary[dept_name] = {
                    'cantidad': dept_data['quantity'],
                    'valor_costo': float(dept_data['total_cost']),
                    'valor_precio': float(dept_data['total_price']),
                    'margen_total': float(dept_data['total_price'] - dept_data['total_cost']),
                    'margen_porcentaje': float(
                        (dept_data['total_price'] - dept_data['total_cost']) / dept_data['total_price'] * 100
                    ) if dept_data['total_price'] > 0 else 0,
                    'precio_promedio': float(dept_data['total_price'] / dept_data['quantity']),
                    'costo_promedio': float(dept_data['total_cost'] / dept_data['quantity']),
                    'porcentaje_inventario': float(dept_data['quantity'] / total_items * 100) if total_items > 0 else 0,
                    'items': dept_data['items'][:10]  # Solo primeros 10 items como muestra
                }

        # Top categorías
        top_categories = sorted(
            [{'categoria': cat, 'cantidad': count} for cat, count in categories_count.items()],
            key=lambda x: x['cantidad'],
            reverse=True
        )[:20]

        # Construir respuesta
        return {
            'success': True,
            'resumen_general': {
                'total_items': total_items,
                'valor_total_costo': float(total_cost_value),
                'valor_total_precio': float(total_price_value),
                'margen_total': float(total_price_value - total_cost_value),
                'margen_porcentaje': float(
                    (total_price_value - total_cost_value) / total_price_value * 100
                ) if total_price_value > 0 else 0,
                'total_categorias': len(categories_count)
            },
            'por_departamento': departments_summary,
            'top_categorias': top_categories,
            'departamentos_ordenados': sorted(
                [
                    {
                        'nombre': dept_name,
                        'cantidad': data['cantidad'],
                        'valor': data['valor_precio']
                    }
                    for dept_name, data in departments_summary.items()
                ],
                key=lambda x: x['valor'],
                reverse=True
            )
        }

    @staticmethod
    def _process_inventory_rows(rows: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Procesa filas de inventario de Alegra (estructura nueva)

        Estructura esperada:
        - Categoría
        - Ítem (nombre del producto)
        - Cantidad (inventario actual)
        - Estado (Activo/Inactivo)
        - Costo promedio
        - Total (Cantidad × Costo promedio)

        Args:
            rows: Lista de diccionarios con los datos de inventario

        Returns:
            Dict con el análisis completo del inventario
        """
        # Inicializar contadores por departamento
        departments = {
            'hombre': {'items': [], 'total_cost': Decimal('0'), 'total_value': Decimal('0'), 'quantity': 0},
            'mujer': {'items': [], 'total_cost': Decimal('0'), 'total_value': Decimal('0'), 'quantity': 0},
            'nino': {'items': [], 'total_cost': Decimal('0'), 'total_value': Decimal('0'), 'quantity': 0},
            'nina': {'items': [], 'total_cost': Decimal('0'), 'total_value': Decimal('0'), 'quantity': 0},
            'accesorios': {'items': [], 'total_cost': Decimal('0'), 'total_value': Decimal('0'), 'quantity': 0},
            'otros': {'items': [], 'total_cost': Decimal('0'), 'total_value': Decimal('0'), 'quantity': 0}
        }

        # Contadores generales
        total_items = 0
        total_quantity = 0
        total_cost_value = Decimal('0')
        total_inventory_value = Decimal('0')
        categories_count = {}
        active_items = 0
        inactive_items = 0

        # Procesar cada fila
        for row in rows:
            # Obtener valores (maneja diferentes nombres de columnas)
            categoria = row.get('Categoría', row.get('Categoria', row.get('categoria', '')))
            nombre = row.get('Ítem', row.get('Item', row.get('item', row.get('nombre', ''))))
            estado = row.get('Estado', row.get('estado', ''))

            # Obtener valores numéricos
            cantidad = int(row.get('Cantidad', row.get('cantidad', 0)) or 0)
            costo_str = row.get('Costo promedio', row.get('costo_promedio', row.get('costo', '0')))
            total_str = row.get('Total', row.get('total', '0'))

            costo = InventoryFileProcessor.parse_decimal(str(costo_str))
            total = InventoryFileProcessor.parse_decimal(str(total_str))

            # Clasificar departamento
            department = InventoryFileProcessor.classify_department(categoria or '', nombre or '')

            # Crear item
            item = {
                'nombre': nombre,
                'categoria': categoria,
                'cantidad': cantidad,
                'estado': estado,
                'costo_unitario': float(costo),
                'valor_total': float(total)
            }

            # Solo contar productos activos con cantidad > 0 para algunos totales
            is_active = estado and estado.lower() == 'activo'
            has_stock = cantidad > 0

            # Agregar a departamento
            departments[department]['items'].append(item)
            departments[department]['total_cost'] += costo * cantidad  # Costo total del inventario
            departments[department]['total_value'] += total
            departments[department]['quantity'] += cantidad

            # Actualizar contadores generales
            total_items += 1
            total_quantity += cantidad
            total_cost_value += costo * cantidad
            total_inventory_value += total

            # Contar categorías
            if categoria:
                categories_count[categoria] = categories_count.get(categoria, 0) + 1

            # Contar activos/inactivos
            if is_active:
                active_items += 1
            else:
                inactive_items += 1

        # Calcular métricas por departamento
        departments_summary = {}
        for dept_name, dept_data in departments.items():
            if dept_data['quantity'] > 0:
                item_count = len(dept_data['items'])
                departments_summary[dept_name] = {
                    'cantidad_items': item_count,
                    'cantidad_unidades': dept_data['quantity'],
                    'valor_inventario': float(dept_data['total_value']),
                    'costo_total': float(dept_data['total_cost']),
                    'costo_promedio': float(dept_data['total_cost'] / dept_data['quantity']),
                    'valor_promedio': float(dept_data['total_value'] / dept_data['quantity']) if dept_data['quantity'] > 0 else 0,
                    'porcentaje_unidades': float(dept_data['quantity'] / total_quantity * 100) if total_quantity > 0 else 0,
                    'porcentaje_valor': float(dept_data['total_value'] / total_inventory_value * 100) if total_inventory_value > 0 else 0,
                    'items': dept_data['items'][:10]  # Solo primeros 10 items como muestra
                }

        # Top categorías
        top_categories = sorted(
            [{'categoria': cat, 'cantidad': count} for cat, count in categories_count.items()],
            key=lambda x: x['cantidad'],
            reverse=True
        )[:20]

        # Construir respuesta
        return {
            'success': True,
            'tipo_archivo': 'inventario_alegra',
            'resumen_general': {
                'total_items': total_items,
                'total_unidades': total_quantity,
                'items_activos': active_items,
                'items_inactivos': inactive_items,
                'valor_total_inventario': float(total_inventory_value),
                'costo_total_inventario': float(total_cost_value),
                'total_categorias': len(categories_count)
            },
            'por_departamento': departments_summary,
            'top_categorias': top_categories,
            'departamentos_ordenados': sorted(
                [
                    {
                        'nombre': dept_name,
                        'cantidad_unidades': data['cantidad_unidades'],
                        'valor': data['valor_inventario']
                    }
                    for dept_name, data in departments_summary.items()
                ],
                key=lambda x: x['valor'],
                reverse=True
            )
        }

    @staticmethod
    def process_file(file_stream: BinaryIO, filename: str) -> Dict[str, Any]:
        """
        Procesa un archivo de inventario (CSV o Excel)

        Args:
            file_stream: Stream del archivo
            filename: Nombre del archivo

        Returns:
            Dict con el análisis del inventario
        """
        # Leer contenido
        file_content = file_stream.read()

        # Determinar tipo de archivo
        if filename.lower().endswith('.csv'):
            return InventoryFileProcessor.process_csv_file(file_content)
        elif filename.lower().endswith(('.xlsx', '.xls')):
            return InventoryFileProcessor.process_excel_file(file_content)
        else:
            raise ValueError("Formato de archivo no soportado. Use CSV o Excel (.xlsx, .xls)")
