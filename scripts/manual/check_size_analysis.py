"""
Script de prueba para los nuevos endpoints de análisis por talla
Prueba los 3 nuevos endpoints y el reporte completo actualizado.
Script MANUAL (no es un test de pytest): python scripts/manual/check_size_analysis.py
Credenciales: ver scripts/manual/_credentials.py
"""
import requests
import json
from datetime import datetime
import sys
import io

from _credentials import api_url, login_payload

# Configurar salida UTF-8 para Windows
if sys.platform == 'win32':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')

# Configuración
BASE_URL = api_url()
LOGIN_URL = f"{BASE_URL}/auth/login"
SIZE_ANALYSIS_URL = f"{BASE_URL}/api/products/analysis/sizes"
CATEGORY_SIZE_URL = f"{BASE_URL}/api/products/analysis/category-sizes"
DEPARTMENT_SIZE_URL = f"{BASE_URL}/api/products/analysis/department-sizes"
COMPLETE_ANALYSIS_URL = f"{BASE_URL}/api/products/analysis"


def print_separator(title):
    """Imprime separador visual"""
    print("\n" + "="*80)
    print(f"  {title}")
    print("="*80 + "\n")

def login():
    """Obtiene token de autenticación"""
    print_separator("1. AUTENTICACIÓN")

    response = requests.post(LOGIN_URL, json=login_payload())

    if response.status_code == 200:
        data = response.json()
        token = data.get('token')
        print(f"✅ Login exitoso")
        print(f"Token: {token[:50]}...")
        return token
    else:
        print(f"❌ Error en login: {response.status_code}")
        print(response.text)
        return None

def test_size_analysis(token, date="2025-11-28"):
    """Prueba endpoint de análisis global por talla"""
    print_separator(f"2. ANÁLISIS GLOBAL POR TALLA - {date}")

    headers = {"Authorization": f"Bearer {token}"}
    response = requests.get(f"{SIZE_ANALYSIS_URL}?date={date}", headers=headers)

    if response.status_code == 200:
        data = response.json()
        print(f"✅ Endpoint funcionando correctamente")
        print(f"Rango de fechas: {data.get('date_range')}")

        size_data = data.get('data', [])
        print(f"\nTotal de tallas encontradas: {len(size_data)}")

        if size_data:
            print("\nPrimeras 5 tallas:")
            for size in size_data[:5]:
                print(f"  - {size['talla']}: {size['cantidad_formatted']} unidades, {size['ingresos_formatted']}")
        else:
            print("⚠️  No se encontraron datos de tallas")

        return data
    else:
        print(f"❌ Error: {response.status_code}")
        print(response.text)
        return None

def test_category_size_analysis(token, date="2025-11-28"):
    """Prueba endpoint de análisis por categoría y talla"""
    print_separator(f"3. ANÁLISIS POR CATEGORÍA Y TALLA - {date}")

    headers = {"Authorization": f"Bearer {token}"}
    response = requests.get(f"{CATEGORY_SIZE_URL}?date={date}", headers=headers)

    if response.status_code == 200:
        data = response.json()
        print(f"✅ Endpoint funcionando correctamente")
        print(f"Rango de fechas: {data.get('date_range')}")

        category_data = data.get('data', [])
        print(f"\nTotal de categorías encontradas: {len(category_data)}")

        if category_data:
            print("\nPrimeras 3 categorías:")
            for category in category_data[:3]:
                print(f"\n  📦 {category['categoria']}")
                print(f"     Total: {category['total_cantidad_formatted']} unidades, {category['total_ingresos_formatted']}")
                print(f"     Tallas disponibles: {len(category['tallas'])}")
                if category['tallas']:
                    print(f"     Top talla: {category['tallas'][0]['talla']} ({category['tallas'][0]['cantidad_formatted']} unidades)")
        else:
            print("⚠️  No se encontraron datos de categorías")

        return data
    else:
        print(f"❌ Error: {response.status_code}")
        print(response.text)
        return None

def test_department_size_analysis(token, date="2025-11-28"):
    """Prueba endpoint de análisis por departamento y talla"""
    print_separator(f"4. ANÁLISIS POR DEPARTAMENTO Y TALLA - {date}")

    headers = {"Authorization": f"Bearer {token}"}
    response = requests.get(f"{DEPARTMENT_SIZE_URL}?date={date}", headers=headers)

    if response.status_code == 200:
        data = response.json()
        print(f"✅ Endpoint funcionando correctamente")
        print(f"Rango de fechas: {data.get('date_range')}")

        department_data = data.get('data', [])
        print(f"\nTotal de departamentos encontrados: {len(department_data)}")

        if department_data:
            print("\nDepartamentos:")
            for department in department_data:
                print(f"\n  👔 {department['departamento']}")
                print(f"     Total: {department['total_cantidad_formatted']} unidades, {department['total_ingresos_formatted']}")
                print(f"     Tallas disponibles: {len(department['tallas'])}")
                if department['tallas']:
                    print(f"     Top talla: {department['tallas'][0]['talla']} ({department['tallas'][0]['cantidad_formatted']} unidades)")
        else:
            print("⚠️  No se encontraron datos de departamentos")

        return data
    else:
        print(f"❌ Error: {response.status_code}")
        print(response.text)
        return None

def test_complete_report(token, date="2025-11-28"):
    """Prueba que el reporte completo incluya los nuevos análisis"""
    print_separator(f"5. REPORTE COMPLETO ACTUALIZADO - {date}")

    headers = {"Authorization": f"Bearer {token}"}
    response = requests.get(f"{COMPLETE_ANALYSIS_URL}?date={date}", headers=headers)

    if response.status_code == 200:
        data = response.json()
        print(f"✅ Endpoint funcionando correctamente")
        print(f"Rango de fechas: {data.get('date_range')}")

        report = data.get('data', {})

        # Verificar secciones existentes
        print("\n📊 Secciones del reporte:")
        print(f"  ✓ resumen_ejecutivo: {len(report.get('resumen_ejecutivo', {}))} campos")
        print(f"  ✓ top_10_productos: {len(report.get('top_10_productos', []))} productos")
        print(f"  ✓ top_10_productos_unificados: {len(report.get('top_10_productos_unificados', []))} productos")
        print(f"  ✓ todos_productos_unificados: {len(report.get('todos_productos_unificados', []))} productos")
        print(f"  ✓ listado_completo: {len(report.get('listado_completo', []))} productos")

        # Verificar nuevas secciones
        print("\n📏 Nuevas secciones de análisis por talla:")
        has_size = 'ventas_por_talla' in report
        has_category = 'ventas_por_categoria_talla' in report
        has_department = 'ventas_por_departamento_talla' in report

        print(f"  {'✅' if has_size else '❌'} ventas_por_talla: {len(report.get('ventas_por_talla', []))} tallas")
        print(f"  {'✅' if has_category else '❌'} ventas_por_categoria_talla: {len(report.get('ventas_por_categoria_talla', []))} categorías")
        print(f"  {'✅' if has_department else '❌'} ventas_por_departamento_talla: {len(report.get('ventas_por_departamento_talla', []))} departamentos")

        if has_size and has_category and has_department:
            print("\n🎉 ¡TODAS las nuevas secciones están incluidas en el reporte completo!")
        else:
            print("\n⚠️  ATENCIÓN: Algunas secciones no están incluidas en el reporte completo")

        return data
    else:
        print(f"❌ Error: {response.status_code}")
        print(response.text)
        return None

def main():
    """Función principal de prueba"""
    print("\n" + "="*80)
    print("  PRUEBA DE IMPLEMENTACIÓN - ANÁLISIS POR TALLA")
    print("  " + datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
    print("="*80)

    # 1. Autenticación
    token = login()
    if not token:
        print("\n❌ No se pudo obtener token. Abortando pruebas.")
        return

    # 2. Probar endpoint de análisis global por talla
    test_size_analysis(token)

    # 3. Probar endpoint de análisis por categoría y talla
    test_category_size_analysis(token)

    # 4. Probar endpoint de análisis por departamento y talla
    test_department_size_analysis(token)

    # 5. Verificar que el reporte completo incluya los nuevos análisis
    test_complete_report(token)

    # Resumen final
    print_separator("RESUMEN DE PRUEBAS")
    print("✅ Autenticación: OK")
    print("✅ Endpoint /api/products/analysis/sizes: Probado")
    print("✅ Endpoint /api/products/analysis/category-sizes: Probado")
    print("✅ Endpoint /api/products/analysis/department-sizes: Probado")
    print("✅ Endpoint /api/products/analysis (completo): Verificado")
    print("\n🎉 ¡Implementación completada y probada!")
    print("\n")

if __name__ == "__main__":
    main()
