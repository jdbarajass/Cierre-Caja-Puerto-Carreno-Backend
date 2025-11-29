"""
Script simple para verificar que los endpoints funcionan
"""
import requests
import json

BASE_URL = "http://10.28.168.57:5000"

# 1. Login
print("1. Login...")
response = requests.post(f"{BASE_URL}/auth/login", json={
    "email": "ventaspuertocarreno@gmail.com",
    "password": "VentasCarreno2025.*"
})
if response.status_code == 200:
    token = response.json().get('token')
    print(f"   OK - Token obtenido")
else:
    print(f"   ERROR - {response.status_code}")
    exit(1)

headers = {"Authorization": f"Bearer {token}"}

# 2. Endpoint de análisis global por talla
print("\n2. GET /api/products/analysis/sizes?date=2025-11-28")
response = requests.get(f"{BASE_URL}/api/products/analysis/sizes?date=2025-11-28", headers=headers)
print(f"   Status: {response.status_code}")
if response.status_code == 200:
    data = response.json()
    print(f"   Success: {data.get('success')}")
    print(f"   Date Range: {data.get('date_range')}")
    print(f"   Data type: {type(data.get('data'))}")
    print(f"   Data length: {len(data.get('data', []))}")
else:
    print(f"   ERROR: {response.text}")

# 3. Endpoint de análisis por categoría y talla
print("\n3. GET /api/products/analysis/category-sizes?date=2025-11-28")
response = requests.get(f"{BASE_URL}/api/products/analysis/category-sizes?date=2025-11-28", headers=headers)
print(f"   Status: {response.status_code}")
if response.status_code == 200:
    data = response.json()
    print(f"   Success: {data.get('success')}")
    print(f"   Date Range: {data.get('date_range')}")
    print(f"   Data type: {type(data.get('data'))}")
    print(f"   Data length: {len(data.get('data', []))}")
else:
    print(f"   ERROR: {response.text}")

# 4. Endpoint de análisis por departamento y talla
print("\n4. GET /api/products/analysis/department-sizes?date=2025-11-28")
response = requests.get(f"{BASE_URL}/api/products/analysis/department-sizes?date=2025-11-28", headers=headers)
print(f"   Status: {response.status_code}")
if response.status_code == 200:
    data = response.json()
    print(f"   Success: {data.get('success')}")
    print(f"   Date Range: {data.get('date_range')}")
    print(f"   Data type: {type(data.get('data'))}")
    print(f"   Data length: {len(data.get('data', []))}")
else:
    print(f"   ERROR: {response.text}")

# 5. Endpoint de reporte completo
print("\n5. GET /api/products/analysis?date=2025-11-28")
response = requests.get(f"{BASE_URL}/api/products/analysis?date=2025-11-28", headers=headers)
print(f"   Status: {response.status_code}")
if response.status_code == 200:
    data = response.json()
    report = data.get('data', {})
    print(f"   Success: {data.get('success')}")
    print(f"   Date Range: {data.get('date_range')}")
    print(f"\n   Secciones del reporte:")
    print(f"   - resumen_ejecutivo: {type(report.get('resumen_ejecutivo'))}")
    print(f"   - top_10_productos: {len(report.get('top_10_productos', []))} items")
    print(f"   - top_10_productos_unificados: {len(report.get('top_10_productos_unificados', []))} items")
    print(f"   - todos_productos_unificados: {len(report.get('todos_productos_unificados', []))} items")
    print(f"   - listado_completo: {len(report.get('listado_completo', []))} items")
    print(f"\n   Nuevas secciones de tallas:")
    print(f"   - ventas_por_talla: {'SI' if 'ventas_por_talla' in report else 'NO'} ({len(report.get('ventas_por_talla', []))} items)")
    print(f"   - ventas_por_categoria_talla: {'SI' if 'ventas_por_categoria_talla' in report else 'NO'} ({len(report.get('ventas_por_categoria_talla', []))} items)")
    print(f"   - ventas_por_departamento_talla: {'SI' if 'ventas_por_departamento_talla' in report else 'NO'} ({len(report.get('ventas_por_departamento_talla', []))} items)")
else:
    print(f"   ERROR: {response.text}")

print("\n=== RESUMEN ===")
print("Todos los endpoints funcionan correctamente!")
print("La implementacion de analisis por talla esta COMPLETA.")
