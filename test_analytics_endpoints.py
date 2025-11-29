"""
Script de prueba para los endpoints de analytics
Ejecutar después de iniciar el servidor: python run.py
"""
import requests
import json
from datetime import datetime, timedelta

# Configuración
BASE_URL = "http://localhost:5000"
# Reemplazar con tu token JWT real después de login
TOKEN = "YOUR_JWT_TOKEN_HERE"

headers = {
    "Authorization": f"Bearer {TOKEN}",
    "Content-Type": "application/json"
}


def print_section(title):
    """Imprime un separador visual"""
    print("\n" + "=" * 80)
    print(f"  {title}")
    print("=" * 80 + "\n")


def test_login():
    """Obtener token de autenticación"""
    print_section("1. OBTENIENDO TOKEN DE AUTENTICACIÓN")

    url = f"{BASE_URL}/auth/login"
    payload = {
        "username": "admin",  # Reemplazar con usuario real
        "password": "password"  # Reemplazar con contraseña real
    }

    try:
        response = requests.post(url, json=payload)
        print(f"Status: {response.status_code}")

        if response.status_code == 200:
            data = response.json()
            token = data.get('token')
            print(f"✓ Token obtenido exitosamente")
            print(f"Token: {token[:50]}...")
            return token
        else:
            print(f"✗ Error: {response.json()}")
            return None
    except Exception as e:
        print(f"✗ Error de conexión: {e}")
        return None


def test_peak_hours(token):
    """Probar endpoint de horas pico"""
    print_section("2. HORAS PICO DE VENTAS")

    # Fecha de ejemplo (ajustar según tus datos)
    end_date = datetime.now().date()
    start_date = end_date - timedelta(days=7)

    url = f"{BASE_URL}/api/analytics/peak-hours"
    params = {
        "start_date": start_date.strftime('%Y-%m-%d'),
        "end_date": end_date.strftime('%Y-%m-%d')
    }

    headers_auth = {"Authorization": f"Bearer {token}"}

    try:
        response = requests.get(url, params=params, headers=headers_auth)
        print(f"URL: {response.url}")
        print(f"Status: {response.status_code}")

        if response.status_code == 200:
            data = response.json()
            print(f"✓ Datos obtenidos exitosamente")
            print(f"\nResumen:")
            summary = data.get('data', {}).get('summary', {})
            print(f"  - Total ingresos: {summary.get('total_revenue_formatted')}")
            print(f"  - Total facturas: {summary.get('total_invoices')}")
            print(f"  - Horas con ventas: {summary.get('hours_with_sales')}")

            print(f"\nTop 3 horas pico:")
            top_hours = data.get('data', {}).get('top_5_peak_hours', [])[:3]
            for i, hour in enumerate(top_hours, 1):
                print(f"  {i}. {hour['hour_range']}: {hour['total_revenue_formatted']} ({hour['invoice_count']} facturas)")
        else:
            print(f"✗ Error: {response.json()}")
    except Exception as e:
        print(f"✗ Error: {e}")


def test_top_customers(token):
    """Probar endpoint de top clientes"""
    print_section("3. TOP CLIENTES")

    end_date = datetime.now().date()
    start_date = end_date - timedelta(days=30)

    url = f"{BASE_URL}/api/analytics/top-customers"
    params = {
        "start_date": start_date.strftime('%Y-%m-%d'),
        "end_date": end_date.strftime('%Y-%m-%d'),
        "limit": 5
    }

    headers_auth = {"Authorization": f"Bearer {token}"}

    try:
        response = requests.get(url, params=params, headers=headers_auth)
        print(f"URL: {response.url}")
        print(f"Status: {response.status_code}")

        if response.status_code == 200:
            data = response.json()
            print(f"✓ Datos obtenidos exitosamente")

            summary = data.get('data', {}).get('summary', {})
            print(f"\nResumen:")
            print(f"  - Total clientes únicos: {summary.get('total_unique_customers')}")
            print(f"  - Total ingresos: {summary.get('total_revenue_formatted')}")
            print(f"  - Valor promedio por cliente: {summary.get('average_customer_value_formatted')}")
            print(f"  - Tasa de recurrencia: {summary.get('recurring_rate')}%")

            print(f"\nTop 5 Clientes:")
            customers = data.get('data', {}).get('top_customers', [])
            for i, customer in enumerate(customers, 1):
                print(f"  {i}. {customer['customer_name']}")
                print(f"     Total gastado: {customer['total_spent_formatted']}")
                print(f"     Compras: {customer['purchase_count']}")
                print(f"     Ticket promedio: {customer['average_ticket_formatted']}")
        else:
            print(f"✗ Error: {response.json()}")
    except Exception as e:
        print(f"✗ Error: {e}")


def test_top_sellers(token):
    """Probar endpoint de top vendedoras"""
    print_section("4. TOP VENDEDORAS")

    end_date = datetime.now().date()
    start_date = end_date - timedelta(days=30)

    url = f"{BASE_URL}/api/analytics/top-sellers"
    params = {
        "start_date": start_date.strftime('%Y-%m-%d'),
        "end_date": end_date.strftime('%Y-%m-%d'),
        "limit": 5
    }

    headers_auth = {"Authorization": f"Bearer {token}"}

    try:
        response = requests.get(url, params=params, headers=headers_auth)
        print(f"URL: {response.url}")
        print(f"Status: {response.status_code}")

        if response.status_code == 200:
            data = response.json()
            print(f"✓ Datos obtenidos exitosamente")

            summary = data.get('data', {}).get('summary', {})
            print(f"\nResumen:")
            print(f"  - Total vendedoras: {summary.get('total_sellers')}")
            print(f"  - Total ingresos: {summary.get('total_revenue_formatted')}")
            print(f"  - Promedio por vendedora: {summary.get('average_sales_per_seller_formatted')}")

            print(f"\nTop Vendedoras:")
            sellers = data.get('data', {}).get('top_sellers', [])
            for i, seller in enumerate(sellers, 1):
                print(f"  {i}. {seller['seller_name']}")
                print(f"     Total ventas: {seller['total_sales_formatted']}")
                print(f"     Facturas: {seller['invoice_count']}")
                print(f"     Ticket promedio: {seller['average_ticket_formatted']}")
                print(f"     Clientes únicos: {seller['unique_customers']}")
                print(f"     Hora más productiva: {seller.get('most_productive_hour', 'N/A')}")
        else:
            print(f"✗ Error: {response.json()}")
    except Exception as e:
        print(f"✗ Error: {e}")


def test_customer_retention(token):
    """Probar endpoint de retención de clientes"""
    print_section("5. RETENCIÓN DE CLIENTES (RFM)")

    end_date = datetime.now().date()
    start_date = end_date - timedelta(days=60)

    url = f"{BASE_URL}/api/analytics/customer-retention"
    params = {
        "start_date": start_date.strftime('%Y-%m-%d'),
        "end_date": end_date.strftime('%Y-%m-%d')
    }

    headers_auth = {"Authorization": f"Bearer {token}"}

    try:
        response = requests.get(url, params=params, headers=headers_auth)
        print(f"URL: {response.url}")
        print(f"Status: {response.status_code}")

        if response.status_code == 200:
            data = response.json()
            print(f"✓ Datos obtenidos exitosamente")

            summary = data.get('data', {}).get('summary', {})
            print(f"\nResumen:")
            print(f"  - Total clientes: {summary.get('total_customers')}")
            print(f"  - Clientes nuevos: {summary.get('new_customers')}")
            print(f"  - Clientes recurrentes: {summary.get('recurring_customers')}")
            print(f"  - Clientes leales: {summary.get('loyal_customers')}")
            print(f"  - Tasa de retención: {summary.get('retention_rate')}%")
            print(f"  - Clientes activos: {summary.get('active_customers')}")
            print(f"  - Clientes en riesgo: {summary.get('at_risk_customers')}")
            print(f"  - Clientes inactivos: {summary.get('inactive_customers')}")
        else:
            print(f"✗ Error: {response.json()}")
    except Exception as e:
        print(f"✗ Error: {e}")


def test_sales_trends(token):
    """Probar endpoint de tendencias"""
    print_section("6. TENDENCIAS DE VENTAS")

    end_date = datetime.now().date()
    start_date = end_date - timedelta(days=14)

    url = f"{BASE_URL}/api/analytics/sales-trends"
    params = {
        "start_date": start_date.strftime('%Y-%m-%d'),
        "end_date": end_date.strftime('%Y-%m-%d')
    }

    headers_auth = {"Authorization": f"Bearer {token}"}

    try:
        response = requests.get(url, params=params, headers=headers_auth)
        print(f"URL: {response.url}")
        print(f"Status: {response.status_code}")

        if response.status_code == 200:
            data = response.json()
            print(f"✓ Datos obtenidos exitosamente")

            summary = data.get('data', {}).get('summary', {})
            print(f"\nResumen:")
            print(f"  - Total ingresos: {summary.get('total_revenue_formatted')}")
            print(f"  - Total facturas: {summary.get('total_invoices')}")
            print(f"  - Días con ventas: {summary.get('total_days_with_sales')}")
            print(f"  - Promedio por día: {summary.get('avg_revenue_per_day_formatted')}")

            best_day = summary.get('best_day', {})
            print(f"\nMejor día:")
            print(f"  - Fecha: {best_day.get('date')} ({best_day.get('day_name')})")
            print(f"  - Ingresos: {best_day.get('total_revenue_formatted')}")

            best_weekday = summary.get('best_weekday', {})
            if best_weekday:
                print(f"\nMejor día de la semana:")
                print(f"  - {best_weekday.get('day_name')}")
                print(f"  - Promedio: {best_weekday.get('avg_revenue_per_day_formatted')}")
        else:
            print(f"✗ Error: {response.json()}")
    except Exception as e:
        print(f"✗ Error: {e}")


def test_cross_selling(token):
    """Probar endpoint de cross-selling"""
    print_section("7. CROSS-SELLING (PRODUCTOS QUE SE VENDEN JUNTOS)")

    end_date = datetime.now().date()
    start_date = end_date - timedelta(days=30)

    url = f"{BASE_URL}/api/analytics/cross-selling"
    params = {
        "start_date": start_date.strftime('%Y-%m-%d'),
        "end_date": end_date.strftime('%Y-%m-%d'),
        "min_support": 2
    }

    headers_auth = {"Authorization": f"Bearer {token}"}

    try:
        response = requests.get(url, params=params, headers=headers_auth)
        print(f"URL: {response.url}")
        print(f"Status: {response.status_code}")

        if response.status_code == 200:
            data = response.json()
            print(f"✓ Datos obtenidos exitosamente")

            summary = data.get('data', {}).get('summary', {})
            print(f"\nResumen:")
            print(f"  - Total pares de productos: {summary.get('total_product_pairs')}")
            print(f"  - Productos únicos: {summary.get('total_unique_products')}")

            print(f"\nTop 5 Combinaciones:")
            pairs = data.get('data', {}).get('top_product_pairs', [])[:5]
            for i, pair in enumerate(pairs, 1):
                print(f"  {i}. {pair['product1'][:30]}... + {pair['product2'][:30]}...")
                print(f"     Veces comprados juntos: {pair['times_bought_together']}")
                print(f"     Ingresos: {pair['total_revenue_formatted']}")
                print(f"     Confianza promedio: {pair['avg_confidence']}%")
        else:
            print(f"✗ Error: {response.json()}")
    except Exception as e:
        print(f"✗ Error: {e}")


def test_dashboard(token):
    """Probar endpoint de dashboard completo"""
    print_section("8. DASHBOARD COMPLETO")

    end_date = datetime.now().date()
    start_date = end_date - timedelta(days=7)

    url = f"{BASE_URL}/api/analytics/dashboard"
    params = {
        "start_date": start_date.strftime('%Y-%m-%d'),
        "end_date": end_date.strftime('%Y-%m-%d')
    }

    headers_auth = {"Authorization": f"Bearer {token}"}

    try:
        response = requests.get(url, params=params, headers=headers_auth)
        print(f"URL: {response.url}")
        print(f"Status: {response.status_code}")

        if response.status_code == 200:
            data = response.json()
            print(f"✓ Dashboard completo obtenido exitosamente")

            analytics_data = data.get('data', {})
            print(f"\nAnálisis disponibles:")
            print(f"  - Horas pico: {'✓' if 'peak_hours' in analytics_data else '✗'}")
            print(f"  - Top clientes: {'✓' if 'top_customers' in analytics_data else '✗'}")
            print(f"  - Top vendedoras: {'✓' if 'top_sellers' in analytics_data else '✗'}")
            print(f"  - Retención: {'✓' if 'customer_retention' in analytics_data else '✗'}")
            print(f"  - Tendencias: {'✓' if 'sales_trends' in analytics_data else '✗'}")
            print(f"  - Cross-selling: {'✓' if 'cross_selling' in analytics_data else '✗'}")
        else:
            print(f"✗ Error: {response.json()}")
    except Exception as e:
        print(f"✗ Error: {e}")


def main():
    """Función principal"""
    print("\n" + "=" * 80)
    print("  PRUEBA DE ENDPOINTS DE ANALYTICS")
    print("  Sistema de Cierre de Caja KOAJ")
    print("=" * 80)

    # Paso 1: Obtener token
    token = test_login()

    if not token:
        print("\n⚠️  No se pudo obtener el token. Actualiza las credenciales en el script.")
        print("    O usa un token existente modificando la variable TOKEN al inicio del script.")
        return

    # Paso 2: Probar todos los endpoints
    test_peak_hours(token)
    test_top_customers(token)
    test_top_sellers(token)
    test_customer_retention(token)
    test_sales_trends(token)
    test_cross_selling(token)
    test_dashboard(token)

    print("\n" + "=" * 80)
    print("  PRUEBAS COMPLETADAS")
    print("=" * 80 + "\n")


if __name__ == "__main__":
    main()
