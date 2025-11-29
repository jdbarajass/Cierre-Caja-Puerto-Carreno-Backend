"""
Servicio de análisis avanzado de ventas
Incluye análisis de horas pico, top clientes, top vendedoras,
retención, tendencias y cross-selling
"""
from typing import Dict, List, Tuple
from datetime import datetime, timedelta
from collections import defaultdict, Counter
import logging

from app.utils.formatters import format_cop

logger = logging.getLogger(__name__)


class SalesAnalytics:
    """Servicio de análisis avanzado de ventas"""

    def __init__(self, invoices: List[Dict]):
        """
        Inicializa el servicio de analytics con facturas

        Args:
            invoices: Lista de facturas de Alegra
        """
        self.invoices = invoices
        self.total_invoices = len(invoices)
        logger.info(f"SalesAnalytics inicializado con {self.total_invoices} facturas")

    # ============================================================
    # 1. ANÁLISIS DE HORAS PICO DE VENTAS
    # ============================================================

    def get_peak_hours_analysis(self) -> Dict:
        """
        Analiza las horas pico de ventas

        Returns:
            Dict con análisis de ventas por hora del día
        """
        # Estructuras para almacenar datos
        sales_by_hour = defaultdict(lambda: {
            'total_revenue': 0,
            'invoice_count': 0,
            'total_items': 0
        })

        sales_by_day_hour = defaultdict(lambda: defaultdict(lambda: {
            'total_revenue': 0,
            'invoice_count': 0
        }))

        for invoice in self.invoices:
            # Obtener datetime de la factura
            datetime_str = invoice.get('datetime')
            if not datetime_str:
                continue

            try:
                # Parsear datetime (formato: "2025-11-28 19:55:48")
                dt = datetime.strptime(datetime_str, '%Y-%m-%d %H:%M:%S')
                hour = dt.hour
                day_name = dt.strftime('%A')  # Nombre del día en inglés

                # Traducir día a español
                days_translation = {
                    'Monday': 'Lunes',
                    'Tuesday': 'Martes',
                    'Wednesday': 'Miércoles',
                    'Thursday': 'Jueves',
                    'Friday': 'Viernes',
                    'Saturday': 'Sábado',
                    'Sunday': 'Domingo'
                }
                day_name_es = days_translation.get(day_name, day_name)

                # Obtener total de la factura
                total = float(invoice.get('total', 0))
                items_count = sum(item.get('quantity', 0) for item in invoice.get('items', []))

                # Agregar a estadísticas por hora
                sales_by_hour[hour]['total_revenue'] += total
                sales_by_hour[hour]['invoice_count'] += 1
                sales_by_hour[hour]['total_items'] += items_count

                # Agregar a estadísticas por día y hora
                sales_by_day_hour[day_name_es][hour]['total_revenue'] += total
                sales_by_day_hour[day_name_es][hour]['invoice_count'] += 1

            except (ValueError, TypeError) as e:
                logger.warning(f"Error parseando datetime de factura {invoice.get('id')}: {e}")
                continue

        # Construir resumen por hora
        hourly_summary = []
        for hour in range(24):
            data = sales_by_hour[hour]
            avg_ticket = data['total_revenue'] / data['invoice_count'] if data['invoice_count'] > 0 else 0

            # Formato de hora (ej: "14:00 - 15:00")
            hour_range = f"{hour:02d}:00 - {(hour+1):02d}:00"

            hourly_summary.append({
                'hour': hour,
                'hour_range': hour_range,
                'total_revenue': int(data['total_revenue']),
                'total_revenue_formatted': format_cop(data['total_revenue']),
                'invoice_count': data['invoice_count'],
                'total_items': data['total_items'],
                'average_ticket': int(avg_ticket),
                'average_ticket_formatted': format_cop(avg_ticket)
            })

        # Ordenar por ingresos (de mayor a menor)
        hourly_summary_sorted = sorted(
            hourly_summary,
            key=lambda x: x['total_revenue'],
            reverse=True
        )

        # Top 5 horas pico
        top_5_hours = hourly_summary_sorted[:5]

        # Análisis por día y hora
        daily_hourly_analysis = {}
        for day, hours_data in sales_by_day_hour.items():
            hourly_data = []
            for hour, data in hours_data.items():
                avg_ticket = data['total_revenue'] / data['invoice_count'] if data['invoice_count'] > 0 else 0
                hourly_data.append({
                    'hour': hour,
                    'hour_range': f"{hour:02d}:00 - {(hour+1):02d}:00",
                    'total_revenue': int(data['total_revenue']),
                    'total_revenue_formatted': format_cop(data['total_revenue']),
                    'invoice_count': data['invoice_count'],
                    'average_ticket': int(avg_ticket),
                    'average_ticket_formatted': format_cop(avg_ticket)
                })

            # Ordenar por hora
            hourly_data.sort(key=lambda x: x['hour'])
            daily_hourly_analysis[day] = hourly_data

        # Calcular totales
        total_revenue = sum(h['total_revenue'] for h in hourly_summary)
        total_invoices = sum(h['invoice_count'] for h in hourly_summary)

        return {
            'summary': {
                'total_revenue': total_revenue,
                'total_revenue_formatted': format_cop(total_revenue),
                'total_invoices': total_invoices,
                'hours_with_sales': len([h for h in hourly_summary if h['invoice_count'] > 0])
            },
            'top_5_peak_hours': top_5_hours,
            'hourly_breakdown': sorted(hourly_summary, key=lambda x: x['hour']),
            'daily_hourly_breakdown': daily_hourly_analysis
        }

    # ============================================================
    # 2. TOP CLIENTES QUE MÁS COMPRAN
    # ============================================================

    def get_top_customers_analysis(self, limit: int = 10) -> Dict:
        """
        Analiza los clientes que más compran

        Args:
            limit: Número de clientes a retornar en el top

        Returns:
            Dict con análisis de top clientes
        """
        customer_stats = defaultdict(lambda: {
            'customer_name': '',
            'customer_id': '',
            'identification': '',
            'email': '',
            'phone': '',
            'total_spent': 0,
            'purchase_count': 0,
            'total_items': 0,
            'last_purchase_date': None,
            'first_purchase_date': None,
            'favorite_payment_method': None,
            'payment_methods': defaultdict(int),
            'products_purchased': []
        })

        for invoice in self.invoices:
            client = invoice.get('client', {})
            if not client:
                continue

            client_id = str(client.get('id', ''))
            if not client_id:
                continue

            # Información del cliente
            customer_stats[client_id]['customer_name'] = client.get('name', 'Sin nombre')
            customer_stats[client_id]['customer_id'] = client_id
            customer_stats[client_id]['identification'] = client.get('identification', '')
            customer_stats[client_id]['email'] = client.get('email', '')
            customer_stats[client_id]['phone'] = client.get('phonePrimary') or client.get('mobile', '')

            # Totales
            total = float(invoice.get('total', 0))
            customer_stats[client_id]['total_spent'] += total
            customer_stats[client_id]['purchase_count'] += 1

            # Items comprados
            items = invoice.get('items', [])
            customer_stats[client_id]['total_items'] += sum(item.get('quantity', 0) for item in items)

            # Productos comprados (para análisis posterior)
            for item in items:
                customer_stats[client_id]['products_purchased'].append({
                    'name': item.get('name', ''),
                    'quantity': item.get('quantity', 0),
                    'price': item.get('price', 0)
                })

            # Fechas de compra
            date_str = invoice.get('date')
            if date_str:
                try:
                    purchase_date = datetime.strptime(date_str, '%Y-%m-%d')

                    if not customer_stats[client_id]['last_purchase_date'] or purchase_date > customer_stats[client_id]['last_purchase_date']:
                        customer_stats[client_id]['last_purchase_date'] = purchase_date

                    if not customer_stats[client_id]['first_purchase_date'] or purchase_date < customer_stats[client_id]['first_purchase_date']:
                        customer_stats[client_id]['first_purchase_date'] = purchase_date
                except ValueError:
                    pass

            # Métodos de pago
            payments = invoice.get('payments', [])
            for payment in payments:
                method = payment.get('paymentMethod', 'unknown')
                customer_stats[client_id]['payment_methods'][method] += 1

        # Calcular métricas adicionales y método de pago favorito
        customers_list = []
        for client_id, stats in customer_stats.items():
            # Ticket promedio
            avg_ticket = stats['total_spent'] / stats['purchase_count'] if stats['purchase_count'] > 0 else 0

            # Método de pago favorito
            if stats['payment_methods']:
                favorite_method = max(stats['payment_methods'].items(), key=lambda x: x[1])[0]
                stats['favorite_payment_method'] = favorite_method

            # Días entre primera y última compra
            days_as_customer = 0
            if stats['first_purchase_date'] and stats['last_purchase_date']:
                days_as_customer = (stats['last_purchase_date'] - stats['first_purchase_date']).days

            customers_list.append({
                'customer_id': stats['customer_id'],
                'customer_name': stats['customer_name'],
                'identification': stats['identification'],
                'email': stats['email'],
                'phone': stats['phone'],
                'total_spent': int(stats['total_spent']),
                'total_spent_formatted': format_cop(stats['total_spent']),
                'purchase_count': stats['purchase_count'],
                'total_items': stats['total_items'],
                'average_ticket': int(avg_ticket),
                'average_ticket_formatted': format_cop(avg_ticket),
                'last_purchase_date': stats['last_purchase_date'].strftime('%Y-%m-%d') if stats['last_purchase_date'] else None,
                'first_purchase_date': stats['first_purchase_date'].strftime('%Y-%m-%d') if stats['first_purchase_date'] else None,
                'days_as_customer': days_as_customer,
                'favorite_payment_method': stats['favorite_payment_method']
            })

        # Ordenar por total gastado (de mayor a menor)
        customers_sorted = sorted(customers_list, key=lambda x: x['total_spent'], reverse=True)

        # Top N clientes
        top_customers = customers_sorted[:limit]

        # Estadísticas generales
        total_unique_customers = len(customers_list)
        total_revenue = sum(c['total_spent'] for c in customers_list)
        avg_customer_value = total_revenue / total_unique_customers if total_unique_customers > 0 else 0

        # Clientes recurrentes (más de 1 compra)
        recurring_customers = len([c for c in customers_list if c['purchase_count'] > 1])

        return {
            'summary': {
                'total_unique_customers': total_unique_customers,
                'total_revenue': int(total_revenue),
                'total_revenue_formatted': format_cop(total_revenue),
                'average_customer_value': int(avg_customer_value),
                'average_customer_value_formatted': format_cop(avg_customer_value),
                'recurring_customers': recurring_customers,
                'recurring_rate': round((recurring_customers / total_unique_customers * 100), 2) if total_unique_customers > 0 else 0
            },
            'top_customers': top_customers,
            'total_customers': total_unique_customers
        }

    # ============================================================
    # 3. TOP VENDEDORAS QUE MÁS VENDEN
    # ============================================================

    def get_top_sellers_analysis(self, limit: int = 10) -> Dict:
        """
        Analiza las vendedoras que más venden

        Args:
            limit: Número de vendedoras a retornar en el top

        Returns:
            Dict con análisis de top vendedoras
        """
        seller_stats = defaultdict(lambda: {
            'seller_name': '',
            'seller_id': '',
            'identification': '',
            'total_sales': 0,
            'invoice_count': 0,
            'total_items': 0,
            'unique_customers': set(),
            'payment_methods': defaultdict(int),
            'hourly_sales': defaultdict(lambda: {'revenue': 0, 'invoices': 0}),
            'products_sold': []
        })

        for invoice in self.invoices:
            seller = invoice.get('seller', {})
            if not seller:
                continue

            seller_id = str(seller.get('id', ''))
            if not seller_id:
                continue

            # Información del vendedor
            seller_stats[seller_id]['seller_name'] = seller.get('name', 'Sin nombre')
            seller_stats[seller_id]['seller_id'] = seller_id
            seller_stats[seller_id]['identification'] = seller.get('identification', '')

            # Totales de venta
            total = float(invoice.get('total', 0))
            seller_stats[seller_id]['total_sales'] += total
            seller_stats[seller_id]['invoice_count'] += 1

            # Items vendidos
            items = invoice.get('items', [])
            seller_stats[seller_id]['total_items'] += sum(item.get('quantity', 0) for item in items)

            # Clientes únicos atendidos
            client = invoice.get('client', {})
            if client and client.get('id'):
                seller_stats[seller_id]['unique_customers'].add(str(client.get('id')))

            # Métodos de pago utilizados
            payments = invoice.get('payments', [])
            for payment in payments:
                method = payment.get('paymentMethod', 'unknown')
                seller_stats[seller_id]['payment_methods'][method] += 1

            # Análisis de horas de productividad
            datetime_str = invoice.get('datetime')
            if datetime_str:
                try:
                    dt = datetime.strptime(datetime_str, '%Y-%m-%d %H:%M:%S')
                    hour = dt.hour
                    seller_stats[seller_id]['hourly_sales'][hour]['revenue'] += total
                    seller_stats[seller_id]['hourly_sales'][hour]['invoices'] += 1
                except ValueError:
                    pass

            # Productos vendidos (para análisis posterior)
            for item in items:
                seller_stats[seller_id]['products_sold'].append({
                    'name': item.get('name', ''),
                    'quantity': item.get('quantity', 0),
                    'revenue': item.get('total', 0)
                })

        # Calcular métricas adicionales
        sellers_list = []
        for seller_id, stats in seller_stats.items():
            # Ticket promedio
            avg_ticket = stats['total_sales'] / stats['invoice_count'] if stats['invoice_count'] > 0 else 0

            # Método de pago más usado
            favorite_method = None
            if stats['payment_methods']:
                favorite_method = max(stats['payment_methods'].items(), key=lambda x: x[1])[0]

            # Hora más productiva
            most_productive_hour = None
            if stats['hourly_sales']:
                most_productive_hour = max(
                    stats['hourly_sales'].items(),
                    key=lambda x: x[1]['revenue']
                )[0]

            # Tasa de clientes recurrentes
            unique_customer_count = len(stats['unique_customers'])
            recurring_rate = 0
            if unique_customer_count > 0:
                recurring_rate = round(((stats['invoice_count'] - unique_customer_count) / stats['invoice_count']) * 100, 2)

            sellers_list.append({
                'seller_id': stats['seller_id'],
                'seller_name': stats['seller_name'],
                'identification': stats['identification'],
                'total_sales': int(stats['total_sales']),
                'total_sales_formatted': format_cop(stats['total_sales']),
                'invoice_count': stats['invoice_count'],
                'total_items': stats['total_items'],
                'average_ticket': int(avg_ticket),
                'average_ticket_formatted': format_cop(avg_ticket),
                'unique_customers': unique_customer_count,
                'recurring_customer_rate': recurring_rate,
                'favorite_payment_method': favorite_method,
                'most_productive_hour': f"{most_productive_hour:02d}:00" if most_productive_hour is not None else None
            })

        # Ordenar por ventas totales (de mayor a menor)
        sellers_sorted = sorted(sellers_list, key=lambda x: x['total_sales'], reverse=True)

        # Top N vendedoras
        top_sellers = sellers_sorted[:limit]

        # Estadísticas generales
        total_sellers = len(sellers_list)
        total_revenue = sum(s['total_sales'] for s in sellers_list)
        avg_sales_per_seller = total_revenue / total_sellers if total_sellers > 0 else 0

        return {
            'summary': {
                'total_sellers': total_sellers,
                'total_revenue': int(total_revenue),
                'total_revenue_formatted': format_cop(total_revenue),
                'average_sales_per_seller': int(avg_sales_per_seller),
                'average_sales_per_seller_formatted': format_cop(avg_sales_per_seller)
            },
            'top_sellers': top_sellers,
            'total_sellers': total_sellers
        }

    # ============================================================
    # 6. ANÁLISIS DE RETENCIÓN DE CLIENTES
    # ============================================================

    def get_customer_retention_analysis(self) -> Dict:
        """
        Analiza la retención de clientes (RFM: Recency, Frequency, Monetary)

        Returns:
            Dict con análisis de retención
        """
        customer_purchases = defaultdict(lambda: {
            'customer_name': '',
            'total_spent': 0,
            'purchase_count': 0,
            'purchase_dates': [],
            'last_purchase': None,
            'first_purchase': None
        })

        # Obtener fecha más reciente en el dataset
        max_date = None
        for invoice in self.invoices:
            date_str = invoice.get('date')
            if date_str:
                try:
                    invoice_date = datetime.strptime(date_str, '%Y-%m-%d')
                    if not max_date or invoice_date > max_date:
                        max_date = invoice_date
                except ValueError:
                    pass

        if not max_date:
            max_date = datetime.now()

        # Recopilar datos de clientes
        for invoice in self.invoices:
            client = invoice.get('client', {})
            if not client:
                continue

            client_id = str(client.get('id', ''))
            if not client_id or client_id == '1':  # Excluir "Consumidor final"
                continue

            customer_purchases[client_id]['customer_name'] = client.get('name', 'Sin nombre')

            total = float(invoice.get('total', 0))
            customer_purchases[client_id]['total_spent'] += total
            customer_purchases[client_id]['purchase_count'] += 1

            # Fechas
            date_str = invoice.get('date')
            if date_str:
                try:
                    purchase_date = datetime.strptime(date_str, '%Y-%m-%d')
                    customer_purchases[client_id]['purchase_dates'].append(purchase_date)

                    if not customer_purchases[client_id]['last_purchase'] or purchase_date > customer_purchases[client_id]['last_purchase']:
                        customer_purchases[client_id]['last_purchase'] = purchase_date

                    if not customer_purchases[client_id]['first_purchase'] or purchase_date < customer_purchases[client_id]['first_purchase']:
                        customer_purchases[client_id]['first_purchase'] = purchase_date
                except ValueError:
                    pass

        # Calcular RFM y métricas de retención
        rfm_analysis = []
        for client_id, data in customer_purchases.items():
            if not data['last_purchase']:
                continue

            # Recency: días desde la última compra
            recency = (max_date - data['last_purchase']).days

            # Frequency: número de compras
            frequency = data['purchase_count']

            # Monetary: total gastado
            monetary = data['total_spent']

            # Calcular promedio de días entre compras
            avg_days_between_purchases = 0
            if len(data['purchase_dates']) > 1:
                sorted_dates = sorted(data['purchase_dates'])
                days_between = [(sorted_dates[i+1] - sorted_dates[i]).days for i in range(len(sorted_dates)-1)]
                avg_days_between_purchases = sum(days_between) / len(days_between) if days_between else 0

            # Días como cliente
            days_as_customer = 0
            if data['first_purchase'] and data['last_purchase']:
                days_as_customer = (data['last_purchase'] - data['first_purchase']).days

            # Clasificación de cliente
            customer_type = 'Nuevo'
            if frequency >= 5:
                customer_type = 'Leal'
            elif frequency >= 2:
                customer_type = 'Recurrente'

            # Estado de actividad
            activity_status = 'Activo'
            if recency > 90:
                activity_status = 'En riesgo'
            elif recency > 180:
                activity_status = 'Inactivo'

            rfm_analysis.append({
                'customer_id': client_id,
                'customer_name': data['customer_name'],
                'recency_days': recency,
                'frequency': frequency,
                'monetary': int(monetary),
                'monetary_formatted': format_cop(monetary),
                'avg_days_between_purchases': round(avg_days_between_purchases, 1),
                'days_as_customer': days_as_customer,
                'customer_type': customer_type,
                'activity_status': activity_status,
                'last_purchase_date': data['last_purchase'].strftime('%Y-%m-%d'),
                'first_purchase_date': data['first_purchase'].strftime('%Y-%m-%d')
            })

        # Segmentación de clientes
        total_customers = len(rfm_analysis)
        new_customers = len([c for c in rfm_analysis if c['customer_type'] == 'Nuevo'])
        recurring_customers = len([c for c in rfm_analysis if c['customer_type'] == 'Recurrente'])
        loyal_customers = len([c for c in rfm_analysis if c['customer_type'] == 'Leal'])

        active_customers = len([c for c in rfm_analysis if c['activity_status'] == 'Activo'])
        at_risk_customers = len([c for c in rfm_analysis if c['activity_status'] == 'En riesgo'])
        inactive_customers = len([c for c in rfm_analysis if c['activity_status'] == 'Inactivo'])

        # Promedios
        avg_recency = sum(c['recency_days'] for c in rfm_analysis) / total_customers if total_customers > 0 else 0
        avg_frequency = sum(c['frequency'] for c in rfm_analysis) / total_customers if total_customers > 0 else 0
        avg_monetary = sum(c['monetary'] for c in rfm_analysis) / total_customers if total_customers > 0 else 0

        # Top clientes por lealtad (mayor frecuencia)
        top_loyal = sorted(rfm_analysis, key=lambda x: x['frequency'], reverse=True)[:10]

        # Clientes en riesgo (no han comprado recientemente pero tienen historial)
        at_risk = [c for c in rfm_analysis if c['activity_status'] == 'En riesgo' and c['frequency'] >= 2]
        at_risk_sorted = sorted(at_risk, key=lambda x: x['monetary'], reverse=True)[:10]

        return {
            'summary': {
                'total_customers': total_customers,
                'new_customers': new_customers,
                'recurring_customers': recurring_customers,
                'loyal_customers': loyal_customers,
                'active_customers': active_customers,
                'at_risk_customers': at_risk_customers,
                'inactive_customers': inactive_customers,
                'retention_rate': round((recurring_customers + loyal_customers) / total_customers * 100, 2) if total_customers > 0 else 0,
                'avg_recency_days': round(avg_recency, 1),
                'avg_frequency': round(avg_frequency, 2),
                'avg_monetary': int(avg_monetary),
                'avg_monetary_formatted': format_cop(avg_monetary)
            },
            'top_loyal_customers': top_loyal,
            'at_risk_customers': at_risk_sorted,
            'rfm_data': sorted(rfm_analysis, key=lambda x: x['monetary'], reverse=True)
        }

    # ============================================================
    # 7. ANÁLISIS DE TENDENCIAS DE VENTAS
    # ============================================================

    def get_sales_trends_analysis(self) -> Dict:
        """
        Analiza tendencias de ventas por día, día de la semana y comparaciones

        Returns:
            Dict con análisis de tendencias
        """
        daily_sales = defaultdict(lambda: {
            'total_revenue': 0,
            'invoice_count': 0,
            'total_items': 0,
            'day_of_week': None,
            'day_name': None
        })

        weekday_sales = defaultdict(lambda: {
            'total_revenue': 0,
            'invoice_count': 0,
            'total_items': 0,
            'days_count': set()
        })

        # Recopilar datos
        for invoice in self.invoices:
            date_str = invoice.get('date')
            if not date_str:
                continue

            try:
                invoice_date = datetime.strptime(date_str, '%Y-%m-%d')
                date_key = invoice_date.strftime('%Y-%m-%d')

                # Día de la semana (0=Lunes, 6=Domingo)
                weekday = invoice_date.weekday()
                weekday_names = ['Lunes', 'Martes', 'Miércoles', 'Jueves', 'Viernes', 'Sábado', 'Domingo']
                weekday_name = weekday_names[weekday]

                total = float(invoice.get('total', 0))
                items_count = sum(item.get('quantity', 0) for item in invoice.get('items', []))

                # Por día específico
                daily_sales[date_key]['total_revenue'] += total
                daily_sales[date_key]['invoice_count'] += 1
                daily_sales[date_key]['total_items'] += items_count
                daily_sales[date_key]['day_of_week'] = weekday
                daily_sales[date_key]['day_name'] = weekday_name

                # Por día de la semana
                weekday_sales[weekday_name]['total_revenue'] += total
                weekday_sales[weekday_name]['invoice_count'] += 1
                weekday_sales[weekday_name]['total_items'] += items_count
                weekday_sales[weekday_name]['days_count'].add(date_key)

            except ValueError as e:
                logger.warning(f"Error parseando fecha: {date_str} - {e}")
                continue

        # Construir resumen diario
        daily_breakdown = []
        for date_key, data in daily_sales.items():
            avg_ticket = data['total_revenue'] / data['invoice_count'] if data['invoice_count'] > 0 else 0

            daily_breakdown.append({
                'date': date_key,
                'day_name': data['day_name'],
                'total_revenue': int(data['total_revenue']),
                'total_revenue_formatted': format_cop(data['total_revenue']),
                'invoice_count': data['invoice_count'],
                'total_items': data['total_items'],
                'average_ticket': int(avg_ticket),
                'average_ticket_formatted': format_cop(avg_ticket)
            })

        # Ordenar por fecha
        daily_breakdown_sorted = sorted(daily_breakdown, key=lambda x: x['date'])

        # Construir resumen por día de la semana
        weekday_breakdown = []
        weekday_order = ['Lunes', 'Martes', 'Miércoles', 'Jueves', 'Viernes', 'Sábado', 'Domingo']

        for day_name in weekday_order:
            if day_name in weekday_sales:
                data = weekday_sales[day_name]
                days_count = len(data['days_count'])
                avg_revenue_per_day = data['total_revenue'] / days_count if days_count > 0 else 0
                avg_invoices_per_day = data['invoice_count'] / days_count if days_count > 0 else 0
                avg_ticket = data['total_revenue'] / data['invoice_count'] if data['invoice_count'] > 0 else 0

                weekday_breakdown.append({
                    'day_name': day_name,
                    'total_revenue': int(data['total_revenue']),
                    'total_revenue_formatted': format_cop(data['total_revenue']),
                    'invoice_count': data['invoice_count'],
                    'total_items': data['total_items'],
                    'days_count': days_count,
                    'avg_revenue_per_day': int(avg_revenue_per_day),
                    'avg_revenue_per_day_formatted': format_cop(avg_revenue_per_day),
                    'avg_invoices_per_day': round(avg_invoices_per_day, 1),
                    'average_ticket': int(avg_ticket),
                    'average_ticket_formatted': format_cop(avg_ticket)
                })

        # Mejores y peores días
        best_day = max(daily_breakdown, key=lambda x: x['total_revenue']) if daily_breakdown else None
        worst_day = min(daily_breakdown, key=lambda x: x['total_revenue']) if daily_breakdown else None

        # Mejor día de la semana
        best_weekday = max(weekday_breakdown, key=lambda x: x['avg_revenue_per_day']) if weekday_breakdown else None

        # Totales
        total_revenue = sum(d['total_revenue'] for d in daily_breakdown)
        total_invoices = sum(d['invoice_count'] for d in daily_breakdown)
        total_days = len(daily_breakdown)
        avg_revenue_per_day = total_revenue / total_days if total_days > 0 else 0

        return {
            'summary': {
                'total_revenue': int(total_revenue),
                'total_revenue_formatted': format_cop(total_revenue),
                'total_invoices': total_invoices,
                'total_days_with_sales': total_days,
                'avg_revenue_per_day': int(avg_revenue_per_day),
                'avg_revenue_per_day_formatted': format_cop(avg_revenue_per_day),
                'best_day': best_day,
                'worst_day': worst_day,
                'best_weekday': best_weekday
            },
            'daily_sales': daily_breakdown_sorted,
            'weekday_analysis': weekday_breakdown
        }

    # ============================================================
    # 8. ANÁLISIS DE CROSS-SELLING (PRODUCTOS QUE SE VENDEN JUNTOS)
    # ============================================================

    def get_cross_selling_analysis(self, min_support: int = 2) -> Dict:
        """
        Analiza qué productos se compran juntos (market basket analysis)

        Args:
            min_support: Mínimo número de veces que deben aparecer juntos

        Returns:
            Dict con análisis de productos que se venden juntos
        """
        # Pares de productos que se compran juntos
        product_pairs = defaultdict(lambda: {
            'count': 0,
            'total_revenue': 0,
            'invoices': []
        })

        # Productos individuales
        individual_products = defaultdict(lambda: {
            'count': 0,
            'total_revenue': 0
        })

        # Procesar facturas
        for invoice in self.invoices:
            items = invoice.get('items', [])
            invoice_id = invoice.get('id', '')

            # Filtrar productos válidos (excluir bolsas, etc.)
            valid_items = [
                item for item in items
                if 'BOLSA' not in item.get('name', '').upper()
            ]

            if len(valid_items) < 2:
                continue

            # Contar productos individuales
            for item in valid_items:
                product_name = item.get('name', '').strip()
                if not product_name:
                    continue

                individual_products[product_name]['count'] += item.get('quantity', 0)
                individual_products[product_name]['total_revenue'] += float(item.get('total', 0))

            # Generar pares de productos
            for i in range(len(valid_items)):
                for j in range(i + 1, len(valid_items)):
                    product1 = valid_items[i].get('name', '').strip()
                    product2 = valid_items[j].get('name', '').strip()

                    if not product1 or not product2:
                        continue

                    # Ordenar alfabéticamente para evitar duplicados (A,B) vs (B,A)
                    pair = tuple(sorted([product1, product2]))

                    revenue = float(valid_items[i].get('total', 0)) + float(valid_items[j].get('total', 0))

                    product_pairs[pair]['count'] += 1
                    product_pairs[pair]['total_revenue'] += revenue
                    product_pairs[pair]['invoices'].append(invoice_id)

        # Filtrar pares por soporte mínimo
        frequent_pairs = []
        for pair, data in product_pairs.items():
            if data['count'] >= min_support:
                product1, product2 = pair

                # Calcular confianza (qué tan probable es que si compran A, compren B)
                confidence_1_to_2 = 0
                confidence_2_to_1 = 0

                if individual_products[product1]['count'] > 0:
                    confidence_1_to_2 = (data['count'] / individual_products[product1]['count']) * 100

                if individual_products[product2]['count'] > 0:
                    confidence_2_to_1 = (data['count'] / individual_products[product2]['count']) * 100

                frequent_pairs.append({
                    'product1': product1,
                    'product2': product2,
                    'times_bought_together': data['count'],
                    'total_revenue': int(data['total_revenue']),
                    'total_revenue_formatted': format_cop(data['total_revenue']),
                    'confidence_1_to_2': round(confidence_1_to_2, 2),
                    'confidence_2_to_1': round(confidence_2_to_1, 2),
                    'avg_confidence': round((confidence_1_to_2 + confidence_2_to_1) / 2, 2)
                })

        # Ordenar por frecuencia
        frequent_pairs_sorted = sorted(frequent_pairs, key=lambda x: x['times_bought_together'], reverse=True)

        # Top 20 pares
        top_20_pairs = frequent_pairs_sorted[:20]

        # Productos más vendidos individualmente (para contexto)
        top_individual_products = []
        for product, data in individual_products.items():
            top_individual_products.append({
                'product_name': product,
                'times_sold': data['count'],
                'total_revenue': int(data['total_revenue']),
                'total_revenue_formatted': format_cop(data['total_revenue'])
            })

        top_individual_products_sorted = sorted(top_individual_products, key=lambda x: x['times_sold'], reverse=True)[:10]

        return {
            'summary': {
                'total_product_pairs': len(frequent_pairs),
                'min_support_used': min_support,
                'total_unique_products': len(individual_products)
            },
            'top_product_pairs': top_20_pairs,
            'top_individual_products': top_individual_products_sorted,
            'all_pairs': frequent_pairs_sorted
        }
