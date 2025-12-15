# 🧪 Testing de Endpoints - Comandos rápidos

## 🔑 Obtener Token JWT

Primero necesitas autenticarte:

```bash
# Login
curl -X POST "http://localhost:5000/auth/login" \
  -H "Content-Type: application/json" \
  -d '{
    "email": "ventaspuertocarreno@gmail.com",
    "password": "tu_password"
  }'

# Respuesta:
# {
#   "success": true,
#   "token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
#   "user": {
#     "userId": 1,
#     "email": "ventaspuertocarreno@gmail.com",
#     "role": "admin"
#   }
# }
```

**Guarda el token para usarlo en las siguientes peticiones:**
```bash
export TOKEN="eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9..."
```

---

## 📊 ESTADÍSTICAS AVANZADAS (APIs Directas)

### 1. Inventario Completo

```bash
# Obtener 100 items del inventario de hoy
curl -X GET "http://localhost:5000/api/direct/inventory/value-report?toDate=2025-12-15&limit=100&page=1" \
  -H "Authorization: Bearer $TOKEN"

# Obtener 1000 items (máximo permitido)
curl -X GET "http://localhost:5000/api/direct/inventory/value-report?toDate=2025-12-15&limit=1000&page=1" \
  -H "Authorization: Bearer $TOKEN"

# Con filtro de búsqueda
curl -X GET "http://localhost:5000/api/direct/inventory/value-report?toDate=2025-12-15&limit=50&page=1&query=camisa" \
  -H "Authorization: Bearer $TOKEN"
```

### 2. Totales de Ventas

```bash
# Ventas del día de hoy
curl -X GET "http://localhost:5000/api/direct/sales/totals?from=2025-12-15&to=2025-12-15&groupBy=day" \
  -H "Authorization: Bearer $TOKEN"

# Ventas del último mes agrupadas por día
curl -X GET "http://localhost:5000/api/direct/sales/totals?from=2025-11-15&to=2025-12-15&groupBy=day&limit=31" \
  -H "Authorization: Bearer $TOKEN"

# Ventas del último año agrupadas por mes
curl -X GET "http://localhost:5000/api/direct/sales/totals?from=2024-12-15&to=2025-12-15&groupBy=month&limit=12" \
  -H "Authorization: Bearer $TOKEN"
```

### 3. Documentos de Ventas

```bash
# Facturas del día de hoy
curl -X GET "http://localhost:5000/api/direct/sales/documents?from=2025-12-15&to=2025-12-15&limit=50" \
  -H "Authorization: Bearer $TOKEN"

# Facturas de un rango de fechas
curl -X GET "http://localhost:5000/api/direct/sales/documents?from=2025-12-01&to=2025-12-15&limit=100" \
  -H "Authorization: Bearer $TOKEN"

# Con paginación (segunda página)
curl -X GET "http://localhost:5000/api/direct/sales/documents?from=2025-12-15&to=2025-12-15&limit=50&start=50" \
  -H "Authorization: Bearer $TOKEN"
```

---

## 📈 ESTADÍSTICAS ESTÁNDAR (APIs Documentadas)

### 1. Dashboard Completo

```bash
# Dashboard con todos los análisis del mes
curl -X GET "http://localhost:5000/api/analytics/dashboard?start_date=2025-12-01&end_date=2025-12-15" \
  -H "Authorization: Bearer $TOKEN"
```

### 2. Horas Pico

```bash
# Horas pico del día
curl -X GET "http://localhost:5000/api/analytics/peak-hours?date=2025-12-15" \
  -H "Authorization: Bearer $TOKEN"

# Horas pico de un rango
curl -X GET "http://localhost:5000/api/analytics/peak-hours?start_date=2025-12-01&end_date=2025-12-15" \
  -H "Authorization: Bearer $TOKEN"
```

### 3. Top Clientes

```bash
# Top 10 clientes del mes
curl -X GET "http://localhost:5000/api/analytics/top-customers?start_date=2025-12-01&end_date=2025-12-15&limit=10" \
  -H "Authorization: Bearer $TOKEN"
```

### 4. Top Vendedoras

```bash
# Top 5 vendedoras del mes
curl -X GET "http://localhost:5000/api/analytics/top-sellers?start_date=2025-12-01&end_date=2025-12-15&limit=5" \
  -H "Authorization: Bearer $TOKEN"
```

### 5. Retención de Clientes

```bash
# Análisis de retención del mes
curl -X GET "http://localhost:5000/api/analytics/customer-retention?start_date=2025-12-01&end_date=2025-12-15" \
  -H "Authorization: Bearer $TOKEN"
```

### 6. Tendencias de Ventas

```bash
# Tendencias del mes
curl -X GET "http://localhost:5000/api/analytics/sales-trends?start_date=2025-12-01&end_date=2025-12-15" \
  -H "Authorization: Bearer $TOKEN"
```

### 7. Cross-Selling

```bash
# Productos que se venden juntos
curl -X GET "http://localhost:5000/api/analytics/cross-selling?start_date=2025-12-01&end_date=2025-12-15&min_support=3" \
  -H "Authorization: Bearer $TOKEN"
```

---

## 🔹 ENDPOINTS COMUNES (Admin + Sales)

### Cierre de Caja

```bash
curl -X POST "http://localhost:5000/api/sum_payments" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "date": "2025-12-15",
    "timezone": "America/Bogota",
    "coins": {
      "50": 0,
      "100": 6,
      "200": 40,
      "500": 1,
      "1000": 0
    },
    "bills": {
      "2000": 16,
      "5000": 7,
      "10000": 7,
      "20000": 12,
      "50000": 12,
      "100000": 9
    },
    "excedentes": [
      {
        "tipo": "efectivo",
        "monto": 13500,
        "descripcion": "Excedente del día anterior"
      }
    ],
    "metodos_pago": {
      "efectivo": 1500000,
      "datafono": 800000,
      "transferencias": 300000
    },
    "gastos_operativos": 50000,
    "prestamos": 0
  }'
```

### Ventas Mensuales

```bash
# Ventas del mes actual (automático)
curl -X GET "http://localhost:5000/api/monthly_sales" \
  -H "Authorization: Bearer $TOKEN"

# Ventas de un rango específico
curl -X GET "http://localhost:5000/api/monthly_sales?start_date=2025-12-01&end_date=2025-12-15" \
  -H "Authorization: Bearer $TOKEN"
```

---

## 🔍 Pruebas de Roles

### Probar con usuario Sales (debe fallar en estadísticas)

```bash
# Login como sales
curl -X POST "http://localhost:5000/auth/login" \
  -H "Content-Type: application/json" \
  -d '{
    "email": "sales@example.com",
    "password": "sales_password"
  }'

export SALES_TOKEN="token_recibido"

# Esto debería funcionar (Sales tiene acceso)
curl -X GET "http://localhost:5000/api/monthly_sales" \
  -H "Authorization: Bearer $SALES_TOKEN"

# Esto debería fallar con 403 Forbidden (Sales NO tiene acceso)
curl -X GET "http://localhost:5000/api/direct/inventory/value-report" \
  -H "Authorization: Bearer $SALES_TOKEN"

# Debería retornar:
# {
#   "success": false,
#   "message": "No tiene permisos para acceder a este recurso"
# }
```

---

## ⚠️ Pruebas de Errores

### Token inválido (401)

```bash
curl -X GET "http://localhost:5000/api/direct/inventory/value-report" \
  -H "Authorization: Bearer token_invalido"

# Respuesta esperada:
# {
#   "success": false,
#   "message": "Token inválido"
# }
```

### Sin token (401)

```bash
curl -X GET "http://localhost:5000/api/direct/inventory/value-report"

# Respuesta esperada:
# {
#   "success": false,
#   "message": "Token no proporcionado"
# }
```

### Límite excedido (400)

```bash
curl -X GET "http://localhost:5000/api/direct/inventory/value-report?limit=2000" \
  -H "Authorization: Bearer $TOKEN"

# Respuesta esperada:
# {
#   "success": false,
#   "error": "El límite máximo es 1000 items por página"
# }
```

### Parámetros faltantes (400)

```bash
curl -X GET "http://localhost:5000/api/direct/sales/totals" \
  -H "Authorization: Bearer $TOKEN"

# Respuesta esperada:
# {
#   "success": false,
#   "error": "Los parámetros \"from\" y \"to\" son requeridos"
# }
```

---

## 📝 Notas

1. **Reemplaza `localhost:5000`** con la URL de tu servidor si está en producción
2. **Guarda el token** en una variable de entorno para facilitar las pruebas
3. **Ajusta las fechas** a fechas reales que tengas en tu base de datos
4. **Verifica los logs** del servidor para ver qué está pasando internamente

---

## 🎯 Testing Rápido Completo

```bash
#!/bin/bash
# Script de prueba completa

# 1. Login
echo "1. Obteniendo token..."
TOKEN=$(curl -s -X POST "http://localhost:5000/auth/login" \
  -H "Content-Type: application/json" \
  -d '{"email":"ventaspuertocarreno@gmail.com","password":"your_pass"}' \
  | jq -r '.token')

echo "Token: $TOKEN"

# 2. Inventario
echo "2. Probando inventario..."
curl -s -X GET "http://localhost:5000/api/direct/inventory/value-report?limit=10" \
  -H "Authorization: Bearer $TOKEN" | jq

# 3. Ventas totales
echo "3. Probando ventas totales..."
curl -s -X GET "http://localhost:5000/api/direct/sales/totals?from=2025-12-01&to=2025-12-15&groupBy=day" \
  -H "Authorization: Bearer $TOKEN" | jq

# 4. Dashboard
echo "4. Probando dashboard..."
curl -s -X GET "http://localhost:5000/api/analytics/dashboard?start_date=2025-12-01&end_date=2025-12-15" \
  -H "Authorization: Bearer $TOKEN" | jq

echo "✅ Pruebas completadas"
```

---

**Nota:** Instala `jq` para formatear el JSON:
```bash
# Ubuntu/Debian
sudo apt-get install jq

# macOS
brew install jq

# Windows
choco install jq
```
