"""
Servicio de generación de PDFs para reportes de productos
Genera PDFs con el mismo estilo del reporte original
"""
from datetime import datetime
from io import BytesIO
from typing import Dict, List, Any
import logging

from reportlab.lib.pagesizes import letter
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, PageBreak
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch

logger = logging.getLogger(__name__)


class ProductReportPDFGenerator:
    """Genera PDFs de reportes de productos con estilo profesional"""

    def __init__(self):
        self.styles = getSampleStyleSheet()
        self._setup_custom_styles()

    def _setup_custom_styles(self):
        """Configura estilos personalizados para el PDF"""
        self.h1_style = self.styles['Heading1']
        self.h2_style = self.styles['Heading2']
        self.normal_style = ParagraphStyle(
            name='Justify',
            parent=self.styles['BodyText'],
            alignment=1  # Centrado
        )

    def generate_report(self, analytics_data: Dict[str, Any], date_range: str = None) -> BytesIO:
        """
        Genera PDF completo del reporte de productos

        Args:
            analytics_data: Datos del análisis completo de productos
            date_range: Rango de fechas del reporte (ej: "2025-11-20" o "2025-11-01 al 2025-11-30")

        Returns:
            BytesIO con el PDF generado
        """
        buffer = BytesIO()
        doc = SimpleDocTemplate(
            buffer,
            pagesize=letter,
            leftMargin=30,
            rightMargin=30,
            topMargin=40,
            bottomMargin=40
        )

        elementos = []

        # Título principal
        elementos.append(Paragraph('Reporte de Ventas - KOAJ Puerto Carreño', self.h1_style))
        elementos.append(Paragraph(
            f'Generado el: {datetime.now().strftime("%d/%m/%Y %H:%M")}',
            self.normal_style
        ))
        if date_range:
            elementos.append(Paragraph(f'Período: {date_range}', self.normal_style))
        elementos.append(Spacer(1, 20))

        # 1. Resumen Ejecutivo
        elementos.extend(self._create_executive_summary(analytics_data['resumen_ejecutivo']))

        # 2. Top 10 sin unificar
        elementos.extend(self._create_top_10_table(
            analytics_data['top_10_productos'],
            '🏆 Top 10 productos más vendidos Sin unificar (Sin tener en cuenta BOLSA PAPEL)',
            colors.lightblue
        ))

        # 3. Top 10 unificados
        elementos.extend(self._create_top_10_unified_table(
            analytics_data['top_10_productos_unificados'],
            '🏆 Top 10 productos unificados (Sin tener en cuenta BOLSA PAPEL)',
            colors.lightcoral
        ))

        # 4. Todos los productos unificados
        elementos.extend(self._create_all_products_unified_table(
            analytics_data['todos_productos_unificados'],
            'Productos unificados por nombre (Sin tener en cuenta BOLSA PAPEL)',
            colors.lightgreen
        ))

        # 5. Listado completo (puede ser muy largo, agregar PageBreak antes)
        elementos.append(PageBreak())
        elementos.extend(self._create_complete_listing_table(
            analytics_data['listado_completo'],
            'Listado completo de productos',
            colors.grey
        ))

        # 6. Análisis por tallas (si está disponible)
        if 'ventas_por_talla' in analytics_data and analytics_data['ventas_por_talla']:
            elementos.append(PageBreak())
            elementos.extend(self._create_size_analysis_table(
                analytics_data['ventas_por_talla'],
                '📏 Análisis de Ventas por Talla',
                colors.lightyellow
            ))

        # 7. Análisis por categoría y talla (si está disponible)
        if 'ventas_por_categoria_talla' in analytics_data and analytics_data['ventas_por_categoria_talla']:
            elementos.append(PageBreak())
            elementos.extend(self._create_category_size_analysis_table(
                analytics_data['ventas_por_categoria_talla'],
                '🏷️ Análisis de Ventas por Categoría y Talla',
                colors.lightcyan
            ))

        # 8. Análisis por departamento y talla (si está disponible)
        if 'ventas_por_departamento_talla' in analytics_data and analytics_data['ventas_por_departamento_talla']:
            elementos.append(PageBreak())
            elementos.extend(self._create_department_size_analysis_table(
                analytics_data['ventas_por_departamento_talla'],
                '👔 Análisis de Ventas por Departamento y Talla',
                colors.lightpink
            ))

        # Construir PDF
        doc.build(elementos)
        buffer.seek(0)
        return buffer

    def _create_executive_summary(self, summary: Dict[str, Any]) -> List:
        """Crea la tabla de resumen ejecutivo"""
        elementos = []
        elementos.append(Paragraph('Resumen Ejecutivo', self.h2_style))

        data = [
            ['Total de productos vendidos', summary['total_productos_vendidos_formatted']],
            ['Ingresos totales estimados', summary['ingresos_totales_formatted']],
            ['Producto más vendido (excluyendo BOLSA PAPEL)', summary['producto_mas_vendido']],
            ['Unidades del producto más vendido', summary['unidades_mas_vendido_formatted']]
        ]

        tabla = Table(data, hAlign='CENTER', colWidths=[3.5*inch, 3.5*inch])
        tabla.setStyle(TableStyle([
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('BACKGROUND', (0, 0), (0, -1), colors.lightgrey),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.black),
            ('FONTNAME', (0, 0), (-1, -1), 'Helvetica'),
            ('FONTSIZE', (0, 0), (-1, -1), 10),
        ]))

        elementos.append(tabla)
        elementos.append(Spacer(1, 20))

        return elementos

    def _create_top_10_table(self, products: List[Dict], title: str, header_color) -> List:
        """Crea tabla de top 10 productos sin unificar"""
        elementos = []
        elementos.append(Paragraph(title, self.h2_style))

        # Header
        data = [['#', 'Producto', 'Cantidad', 'Ingresos', '% de participación']]

        # Productos
        for product in products:
            data.append([
                product['ranking'],
                product['nombre'],
                product['cantidad_formatted'],
                product['ingresos_formatted'],
                product['porcentaje_participacion_formatted']
            ])

        # Totales
        total_cantidad = sum(p['cantidad'] for p in products)
        total_ingresos = sum(p['ingresos'] for p in products)
        total_pct = sum(p['porcentaje_participacion'] for p in products)

        data.append([
            'TOTAL',
            '',
            ProductReportPDFGenerator._format_number(total_cantidad),
            ProductReportPDFGenerator._format_pesos(total_ingresos),
            ProductReportPDFGenerator._format_percentage(total_pct)
        ])

        tabla = Table(data, hAlign='CENTER', colWidths=[0.5*inch, 3*inch, 1*inch, 1.3*inch, 1.2*inch])
        tabla.setStyle(TableStyle([
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('BACKGROUND', (0, 0), (-1, 0), header_color),
            ('BACKGROUND', (0, -1), (-1, -1), colors.lightgrey),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.black),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTNAME', (0, -1), (-1, -1), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, -1), 9),
        ]))

        elementos.append(tabla)
        elementos.append(Spacer(1, 20))

        return elementos

    def _create_top_10_unified_table(self, products: List[Dict], title: str, header_color) -> List:
        """Crea tabla de top 10 productos unificados"""
        elementos = []
        elementos.append(Paragraph(title, self.h2_style))

        # Header
        data = [['#', 'Producto', 'Cantidad', 'Ingresos', '% de participación']]

        # Productos
        for product in products:
            data.append([
                product['ranking'],
                product['nombre_base'],
                product['cantidad_formatted'],
                product['ingresos_formatted'],
                product['porcentaje_participacion_formatted']
            ])

        # Totales
        total_cantidad = sum(p['cantidad'] for p in products)
        total_ingresos = sum(p['ingresos'] for p in products)
        total_pct = sum(p['porcentaje_participacion'] for p in products)

        data.append([
            'TOTAL',
            '',
            ProductReportPDFGenerator._format_number(total_cantidad),
            ProductReportPDFGenerator._format_pesos(total_ingresos),
            ProductReportPDFGenerator._format_percentage(total_pct)
        ])

        tabla = Table(data, hAlign='CENTER', colWidths=[0.5*inch, 3*inch, 1*inch, 1.3*inch, 1.2*inch])
        tabla.setStyle(TableStyle([
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('BACKGROUND', (0, 0), (-1, 0), header_color),
            ('BACKGROUND', (0, -1), (-1, -1), colors.lightgrey),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.black),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTNAME', (0, -1), (-1, -1), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, -1), 9),
        ]))

        elementos.append(tabla)
        elementos.append(Spacer(1, 20))

        return elementos

    def _create_all_products_unified_table(self, products: List[Dict], title: str, header_color) -> List:
        """Crea tabla de todos los productos unificados"""
        elementos = []
        elementos.append(Paragraph(title, self.h2_style))

        # Header
        data = [['#', 'Producto', 'Cantidad', 'Ingresos', '% de participación']]

        # Productos (limitar a primeros 50 para que el PDF no sea muy largo)
        display_products = products[:50] if len(products) > 50 else products

        for product in display_products:
            data.append([
                product['ranking'],
                product['nombre_base'],
                product['cantidad_formatted'],
                product['ingresos_formatted'],
                product['porcentaje_participacion_formatted']
            ])

        # Agregar nota si hay más productos
        if len(products) > 50:
            elementos.append(Paragraph(
                f'<i>Mostrando los primeros 50 de {len(products)} productos. '
                'Consulte el JSON para ver la lista completa.</i>',
                self.normal_style
            ))
            elementos.append(Spacer(1, 10))

        # Totales (sobre todos los productos, no solo los mostrados)
        total_cantidad = sum(p['cantidad'] for p in products)
        total_ingresos = sum(p['ingresos'] for p in products)
        total_pct = sum(p['porcentaje_participacion'] for p in products)

        data.append([
            'TOTAL',
            '',
            ProductReportPDFGenerator._format_number(total_cantidad),
            ProductReportPDFGenerator._format_pesos(total_ingresos),
            ProductReportPDFGenerator._format_percentage(total_pct)
        ])

        tabla = Table(data, hAlign='CENTER', colWidths=[0.5*inch, 3*inch, 1*inch, 1.3*inch, 1.2*inch])
        tabla.setStyle(TableStyle([
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('BACKGROUND', (0, 0), (-1, 0), header_color),
            ('BACKGROUND', (0, -1), (-1, -1), colors.lightgrey),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.black),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTNAME', (0, -1), (-1, -1), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, -1), 8),
        ]))

        elementos.append(tabla)
        elementos.append(Spacer(1, 20))

        return elementos

    def _create_complete_listing_table(self, products: List[Dict], title: str, header_color) -> List:
        """Crea tabla de listado completo de productos"""
        elementos = []
        elementos.append(Paragraph(title, self.h2_style))

        # Header
        data = [['Producto', 'Cantidad', 'Ingresos', '% de participación']]

        # Productos (limitar para no hacer el PDF demasiado largo)
        display_products = products[:100] if len(products) > 100 else products

        for product in display_products:
            data.append([
                product['nombre'],
                product['cantidad_formatted'],
                product['ingresos_formatted'],
                product['porcentaje_participacion_formatted']
            ])

        # Agregar nota si hay más productos
        if len(products) > 100:
            elementos.append(Paragraph(
                f'<i>Mostrando los primeros 100 de {len(products)} productos. '
                'Consulte el JSON para ver la lista completa.</i>',
                self.normal_style
            ))
            elementos.append(Spacer(1, 10))

        # Totales
        total_cantidad = sum(p['cantidad'] for p in products)
        total_ingresos = sum(p['ingresos'] for p in products)
        total_pct = sum(p['porcentaje_participacion'] for p in products)

        data.append([
            'TOTAL',
            ProductReportPDFGenerator._format_number(total_cantidad),
            ProductReportPDFGenerator._format_pesos(total_ingresos),
            ProductReportPDFGenerator._format_percentage(total_pct)
        ])

        tabla = Table(data, hAlign='CENTER', colWidths=[3.5*inch, 1*inch, 1.3*inch, 1.2*inch])
        tabla.setStyle(TableStyle([
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('BACKGROUND', (0, 0), (-1, 0), header_color),
            ('BACKGROUND', (0, -1), (-1, -1), colors.lightgrey),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.black),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTNAME', (0, -1), (-1, -1), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, -1), 8),
        ]))

        elementos.append(tabla)
        elementos.append(Spacer(1, 20))

        return elementos

    def _create_size_analysis_table(self, size_data_dict: Dict, title: str, header_color) -> List:
        """Crea tabla de análisis global por tallas"""
        elementos = []
        elementos.append(Paragraph(title, self.h2_style))

        # Extraer la lista de tallas del diccionario
        size_data = size_data_dict.get('sizes', [])

        if not size_data:
            elementos.append(Paragraph(
                '<i>No hay datos de tallas disponibles para este período.</i>',
                self.normal_style
            ))
            elementos.append(Spacer(1, 20))
            return elementos

        # Header
        data = [['Talla', 'Cantidad', 'Ingresos', '% Participación']]

        # Datos de tallas
        for size in size_data:
            data.append([
                size['size'],
                size['units_formatted'],
                size['revenue_formatted'],
                size['percentage_formatted']
            ])

        # Totales
        total_cantidad = sum(s['units'] for s in size_data)
        total_ingresos = sum(s['revenue'] for s in size_data)
        total_pct = sum(s['percentage'] for s in size_data)

        data.append([
            'TOTAL',
            ProductReportPDFGenerator._format_number(total_cantidad),
            ProductReportPDFGenerator._format_pesos(total_ingresos),
            ProductReportPDFGenerator._format_percentage(total_pct)
        ])

        tabla = Table(data, hAlign='CENTER', colWidths=[1.5*inch, 1.5*inch, 2*inch, 2*inch])
        tabla.setStyle(TableStyle([
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('BACKGROUND', (0, 0), (-1, 0), header_color),
            ('BACKGROUND', (0, -1), (-1, -1), colors.lightgrey),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.black),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTNAME', (0, -1), (-1, -1), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, -1), 9),
        ]))

        elementos.append(tabla)
        elementos.append(Spacer(1, 20))

        return elementos

    def _create_category_size_analysis_table(self, category_data_dict: Dict, title: str, header_color) -> List:
        """Crea tabla de análisis por categoría y talla"""
        elementos = []
        elementos.append(Paragraph(title, self.h2_style))

        # Extraer la lista de categorías del diccionario
        category_data = category_data_dict.get('categories', [])

        if not category_data:
            elementos.append(Paragraph(
                '<i>No hay datos de categorías por talla disponibles para este período.</i>',
                self.normal_style
            ))
            elementos.append(Spacer(1, 20))
            return elementos

        for category in category_data:
            # Título de categoría
            elementos.append(Paragraph(
                f'<b>{category["category"]}</b>',
                self.h2_style
            ))

            # Header
            data = [['Talla', 'Cantidad', 'Ingresos', '% Participación']]

            # Datos de tallas para esta categoría
            for size in category['sizes']:
                data.append([
                    size['size'],
                    size['units_formatted'],
                    size['revenue_formatted'],
                    size['percentage_in_category_formatted']
                ])

            # Totales de la categoría
            total_cantidad = sum(s['units'] for s in category['sizes'])
            total_ingresos = sum(s['revenue'] for s in category['sizes'])
            total_pct = sum(s['percentage_in_category'] for s in category['sizes'])

            data.append([
                'TOTAL',
                ProductReportPDFGenerator._format_number(total_cantidad),
                ProductReportPDFGenerator._format_pesos(total_ingresos),
                ProductReportPDFGenerator._format_percentage(total_pct)
            ])

            tabla = Table(data, hAlign='CENTER', colWidths=[1.5*inch, 1.5*inch, 2*inch, 2*inch])
            tabla.setStyle(TableStyle([
                ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
                ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
                ('BACKGROUND', (0, 0), (-1, 0), header_color),
                ('BACKGROUND', (0, -1), (-1, -1), colors.lightgrey),
                ('GRID', (0, 0), (-1, -1), 0.5, colors.black),
                ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                ('FONTNAME', (0, -1), (-1, -1), 'Helvetica-Bold'),
                ('FONTSIZE', (0, 0), (-1, -1), 9),
            ]))

            elementos.append(tabla)
            elementos.append(Spacer(1, 15))

        elementos.append(Spacer(1, 10))
        return elementos

    def _create_department_size_analysis_table(self, department_data_dict: Dict, title: str, header_color) -> List:
        """Crea tabla de análisis por departamento y talla"""
        elementos = []
        elementos.append(Paragraph(title, self.h2_style))

        # Extraer la lista de departamentos del diccionario
        department_data = department_data_dict.get('departments', [])

        if not department_data:
            elementos.append(Paragraph(
                '<i>No hay datos de departamentos por talla disponibles para este período.</i>',
                self.normal_style
            ))
            elementos.append(Spacer(1, 20))
            return elementos

        for department in department_data:
            # Título de departamento
            elementos.append(Paragraph(
                f'<b>{department["department"]}</b>',
                self.h2_style
            ))

            # Header
            data = [['Talla', 'Cantidad', 'Ingresos', '% Participación']]

            # Datos de tallas para este departamento
            for size in department['sizes']:
                data.append([
                    size['size'],
                    size['units_formatted'],
                    size['revenue_formatted'],
                    size['percentage_in_department_formatted']
                ])

            # Totales del departamento
            total_cantidad = sum(s['units'] for s in department['sizes'])
            total_ingresos = sum(s['revenue'] for s in department['sizes'])
            total_pct = sum(s['percentage_in_department'] for s in department['sizes'])

            data.append([
                'TOTAL',
                ProductReportPDFGenerator._format_number(total_cantidad),
                ProductReportPDFGenerator._format_pesos(total_ingresos),
                ProductReportPDFGenerator._format_percentage(total_pct)
            ])

            tabla = Table(data, hAlign='CENTER', colWidths=[1.5*inch, 1.5*inch, 2*inch, 2*inch])
            tabla.setStyle(TableStyle([
                ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
                ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
                ('BACKGROUND', (0, 0), (-1, 0), header_color),
                ('BACKGROUND', (0, -1), (-1, -1), colors.lightgrey),
                ('GRID', (0, 0), (-1, -1), 0.5, colors.black),
                ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                ('FONTNAME', (0, -1), (-1, -1), 'Helvetica-Bold'),
                ('FONTSIZE', (0, 0), (-1, -1), 9),
            ]))

            elementos.append(tabla)
            elementos.append(Spacer(1, 15))

        elementos.append(Spacer(1, 10))
        return elementos

    @staticmethod
    def _format_pesos(value: float) -> str:
        """Formatea valor en pesos colombianos"""
        return f"$ {int(value):,}".replace(',', '.')

    @staticmethod
    def _format_number(value: int) -> str:
        """Formatea número con separador de miles"""
        return f"{int(value):,}".replace(',', '.')

    @staticmethod
    def _format_percentage(value: float) -> str:
        """Formatea porcentaje con 2 decimales"""
        return f"{value:.2f}%"
