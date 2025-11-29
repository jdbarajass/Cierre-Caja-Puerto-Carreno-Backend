# API de Analytics - Documentación Completa

## Descripción General

Esta API proporciona análisis avanzados de ventas basados en los datos de facturas obtenidas desde Alegra. Incluye análisis de horas pico, top clientes, top vendedoras, retención de clientes, tendencias de ventas y productos que se venden juntos (cross-selling).

**Versión:** 1.0.0
**Base URL:** `/api/analytics`
**Autenticación:** Requiere token JWT en header `Authorization: Bearer <token>`

---

## Endpoints Disponibles

### 1. Horas Pico de Ventas
**GET** `/api/analytics/peak-hours`

Analiza las horas del día con mayor volumen de ventas.

#### Query Parameters
- `date` (string, opcional): Fecha específica en formato `YYYY-MM-DD`
- `start_date` (string, opcional): Fecha de inicio del rango
- `end_date` (string, opcional): Fecha de fin del rango

#### Ejemplo de Request
```bash
GET /api/analytics/peak-hours?start_date=2025-11-01&end_date=2025-11-30
```

#### Ejemplo de Response (200 OK)
```json
{
  "success": true,
  "date_range": "2025-11-01 al 2025-11-30",
  "server_timestamp": "2025-11-29T10:30:00-05:00",
  "data": {
    "summary": {
      "total_revenue": 5000000,
      "total_revenue_formatted": "$5.000.000",
      "total_invoices": 120,
      "hours_with_sales": 12
    },
    "top_5_peak_hours": [
      {
        "hour": 19,
        "hour_range": "19:00 - 20:00",
        "total_revenue": 850000,
        "total_revenue_formatted": "$850.000",
        "invoice_count": 25,
        "total_items": 65,
        "average_ticket": 34000,
        "average_ticket_formatted": "$34.000"
      }
    ],
    "hourly_breakdown": [...],
    "daily_hourly_breakdown": {
      "Lunes": [...],
      "Martes": [...]
    }
  }
}
```

#### Casos de Uso
- Identificar las mejores horas para programar personal
- Optimizar horarios de atención
- Planificar promociones en horarios específicos

---

### 2. Top Clientes
**GET** `/api/analytics/top-customers`

Obtiene los clientes que más han comprado en el período especificado.

#### Query Parameters
- `date` (string, opcional): Fecha específica
- `start_date` (string, opcional): Fecha de inicio
- `end_date` (string, opcional): Fecha de fin
- `limit` (integer, opcional): Número de clientes a retornar (default: 10)

#### Ejemplo de Request
```bash
GET /api/analytics/top-customers?start_date=2025-11-01&end_date=2025-11-30&limit=10
```

#### Ejemplo de Response (200 OK)
```json
{
  "success": true,
  "date_range": "2025-11-01 al 2025-11-30",
  "data": {
    "summary": {
      "total_unique_customers": 250,
      "total_revenue": 10000000,
      "total_revenue_formatted": "$10.000.000",
      "average_customer_value": 40000,
      "average_customer_value_formatted": "$40.000",
      "recurring_customers": 85,
      "recurring_rate": 34.0
    },
    "top_customers": [
      {
        "customer_id": "804",
        "customer_name": "FEDERICO DE JESUS VEGA PAJARO",
        "identification": "9297038",
        "email": "federollo2@hotmail.com",
        "phone": "3001234567",
        "total_spent": 750000,
        "total_spent_formatted": "$750.000",
        "purchase_count": 15,
        "total_items": 45,
        "average_ticket": 50000,
        "average_ticket_formatted": "$50.000",
        "last_purchase_date": "2025-11-28",
        "first_purchase_date": "2025-11-05",
        "days_as_customer": 23,
        "favorite_payment_method": "transfer"
      }
    ],
    "total_customers": 250
  }
}
```

#### Métricas Clave
- **Total gastado**: Suma de todas las compras del cliente
- **Frecuencia de compra**: Número de facturas
- **Ticket promedio**: Gasto promedio por visita
- **Días como cliente**: Diferencia entre primera y última compra
- **Método de pago favorito**: El más utilizado por el cliente

#### Casos de Uso
- Programas de fidelización
- Segmentación de clientes VIP
- Marketing personalizado

---

### 3. Top Vendedoras
**GET** `/api/analytics/top-sellers`

Analiza el desempeño de las vendedoras.

#### Query Parameters
- `date` (string, opcional): Fecha específica
- `start_date` (string, opcional): Fecha de inicio
- `end_date` (string, opcional): Fecha de fin
- `limit` (integer, opcional): Número de vendedoras a retornar (default: 10)

#### Ejemplo de Request
```bash
GET /api/analytics/top-sellers?start_date=2025-11-01&end_date=2025-11-30
```

#### Ejemplo de Response (200 OK)
```json
{
  "success": true,
  "date_range": "2025-11-01 al 2025-11-30",
  "data": {
    "summary": {
      "total_sellers": 5,
      "total_revenue": 8000000,
      "total_revenue_formatted": "$8.000.000",
      "average_sales_per_seller": 1600000,
      "average_sales_per_seller_formatted": "$1.600.000"
    },
    "top_sellers": [
      {
        "seller_id": "12",
        "seller_name": "RITA INFANTE",
        "identification": "17105692",
        "total_sales": 3500000,
        "total_sales_formatted": "$3.500.000",
        "invoice_count": 85,
        "total_items": 250,
        "average_ticket": 41176,
        "average_ticket_formatted": "$41.176",
        "unique_customers": 65,
        "recurring_customer_rate": 23.53,
        "favorite_payment_method": "cash",
        "most_productive_hour": "19:00"
      }
    ],
    "total_sellers": 5
  }
}
```

#### Métricas Clave
- **Total de ventas**: Suma de todas las facturas
- **Número de facturas**: Cantidad de ventas realizadas
- **Ticket promedio**: Valor promedio por venta
- **Clientes únicos**: Cantidad de clientes diferentes atendidos
- **Tasa de clientes recurrentes**: % de clientes que vuelven
- **Hora más productiva**: Hora con mayores ventas

#### Casos de Uso
- Evaluación de desempeño
- Bonificaciones e incentivos
- Capacitación personalizada

---

### 4. Retención de Clientes (RFM Analysis)
**GET** `/api/analytics/customer-retention`

Analiza la retención de clientes usando el modelo RFM (Recency, Frequency, Monetary).

#### Query Parameters
- `date` (string, opcional): Fecha específica
- `start_date` (string, opcional): Fecha de inicio
- `end_date` (string, opcional): Fecha de fin

#### Ejemplo de Request
```bash
GET /api/analytics/customer-retention?start_date=2025-10-01&end_date=2025-11-30
```

#### Ejemplo de Response (200 OK)
```json
{
  "success": true,
  "date_range": "2025-10-01 al 2025-11-30",
  "data": {
    "summary": {
      "total_customers": 180,
      "new_customers": 95,
      "recurring_customers": 60,
      "loyal_customers": 25,
      "active_customers": 140,
      "at_risk_customers": 30,
      "inactive_customers": 10,
      "retention_rate": 47.22,
      "avg_recency_days": 15.5,
      "avg_frequency": 2.8,
      "avg_monetary": 125000,
      "avg_monetary_formatted": "$125.000"
    },
    "top_loyal_customers": [
      {
        "customer_id": "518",
        "customer_name": "YURLY YUSEBY GUTIERREZ ALVAREZ",
        "recency_days": 5,
        "frequency": 8,
        "monetary": 650000,
        "monetary_formatted": "$650.000",
        "avg_days_between_purchases": 7.5,
        "days_as_customer": 52,
        "customer_type": "Leal",
        "activity_status": "Activo",
        "last_purchase_date": "2025-11-28",
        "first_purchase_date": "2025-10-07"
      }
    ],
    "at_risk_customers": [...],
    "rfm_data": [...]
  }
}
```

#### Segmentación de Clientes
- **Nuevo**: 1 compra
- **Recurrente**: 2-4 compras
- **Leal**: 5+ compras

#### Estados de Actividad
- **Activo**: Última compra ≤ 90 días
- **En riesgo**: Última compra > 90 días
- **Inactivo**: Última compra > 180 días

#### Casos de Uso
- Campañas de reactivación
- Programas de lealtad
- Identificar clientes en riesgo de abandono

---

### 5. Tendencias de Ventas
**GET** `/api/analytics/sales-trends`

Analiza tendencias de ventas por día y día de la semana.

#### Query Parameters
- `date` (string, opcional): Fecha específica
- `start_date` (string, opcional): Fecha de inicio
- `end_date` (string, opcional): Fecha de fin

#### Ejemplo de Request
```bash
GET /api/analytics/sales-trends?start_date=2025-11-01&end_date=2025-11-30
```

#### Ejemplo de Response (200 OK)
```json
{
  "success": true,
  "date_range": "2025-11-01 al 2025-11-30",
  "data": {
    "summary": {
      "total_revenue": 12000000,
      "total_revenue_formatted": "$12.000.000",
      "total_invoices": 320,
      "total_days_with_sales": 28,
      "avg_revenue_per_day": 428571,
      "avg_revenue_per_day_formatted": "$428.571",
      "best_day": {
        "date": "2025-11-28",
        "day_name": "Jueves",
        "total_revenue": 850000,
        "total_revenue_formatted": "$850.000"
      },
      "worst_day": {...},
      "best_weekday": {
        "day_name": "Sábado",
        "avg_revenue_per_day": 550000,
        "avg_revenue_per_day_formatted": "$550.000"
      }
    },
    "daily_sales": [
      {
        "date": "2025-11-01",
        "day_name": "Viernes",
        "total_revenue": 450000,
        "total_revenue_formatted": "$450.000",
        "invoice_count": 12,
        "total_items": 35,
        "average_ticket": 37500,
        "average_ticket_formatted": "$37.500"
      }
    ],
    "weekday_analysis": [
      {
        "day_name": "Lunes",
        "total_revenue": 1200000,
        "total_revenue_formatted": "$1.200.000",
        "invoice_count": 42,
        "total_items": 125,
        "days_count": 4,
        "avg_revenue_per_day": 300000,
        "avg_revenue_per_day_formatted": "$300.000",
        "avg_invoices_per_day": 10.5,
        "average_ticket": 28571,
        "average_ticket_formatted": "$28.571"
      }
    ]
  }
}
```

#### Casos de Uso
- Planificación de inventario
- Programación de personal
- Identificación de patrones estacionales

---

### 6. Cross-Selling (Productos que se Venden Juntos)
**GET** `/api/analytics/cross-selling`

Analiza qué productos se compran juntos frecuentemente (Market Basket Analysis).

#### Query Parameters
- `date` (string, opcional): Fecha específica
- `start_date` (string, opcional): Fecha de inicio
- `end_date` (string, opcional): Fecha de fin
- `min_support` (integer, opcional): Mínimo de veces que deben aparecer juntos (default: 2)

#### Ejemplo de Request
```bash
GET /api/analytics/cross-selling?start_date=2025-11-01&end_date=2025-11-30&min_support=3
```

#### Ejemplo de Response (200 OK)
```json
{
  "success": true,
  "date_range": "2025-11-01 al 2025-11-30",
  "data": {
    "summary": {
      "total_product_pairs": 45,
      "min_support_used": 3,
      "total_unique_products": 180
    },
    "top_product_pairs": [
      {
        "product1": "JEAN HOMBRE 109900",
        "product2": "CAMISETA HOMBRE 42900",
        "times_bought_together": 12,
        "total_revenue": 1834800,
        "total_revenue_formatted": "$1.834.800",
        "confidence_1_to_2": 45.5,
        "confidence_2_to_1": 35.2,
        "avg_confidence": 40.35
      }
    ],
    "top_individual_products": [
      {
        "product_name": "JEAN HOMBRE 109900",
        "times_sold": 45,
        "total_revenue": 4945500,
        "total_revenue_formatted": "$4.945.500"
      }
    ],
    "all_pairs": [...]
  }
}
```

#### Métricas de Confianza
- **confidence_1_to_2**: Probabilidad de que si compran producto1, compren producto2
- **confidence_2_to_1**: Probabilidad de que si compran producto2, compren producto1
- **avg_confidence**: Promedio de ambas direcciones

#### Casos de Uso
- Crear combos y promociones
- Ubicación estratégica de productos en tienda
- Recomendaciones de compra
- Optimización de inventario

---

### 7. Dashboard Completo
**GET** `/api/analytics/dashboard`

Obtiene todos los análisis en una sola consulta (útil para dashboards).

#### Query Parameters
- `date` (string, opcional): Fecha específica
- `start_date` (string, opcional): Fecha de inicio
- `end_date` (string, opcional): Fecha de fin

#### Ejemplo de Request
```bash
GET /api/analytics/dashboard?start_date=2025-11-01&end_date=2025-11-30
```

#### Ejemplo de Response (200 OK)
```json
{
  "success": true,
  "date_range": "2025-11-01 al 2025-11-30",
  "data": {
    "peak_hours": {...},
    "top_customers": {...},
    "top_sellers": {...},
    "customer_retention": {...},
    "sales_trends": {...},
    "cross_selling": {...}
  }
}
```

---

## Códigos de Estado HTTP

- **200 OK**: Petición exitosa
- **400 Bad Request**: Parámetros inválidos
- **401 Unauthorized**: Token de autenticación inválido o ausente
- **502 Bad Gateway**: Error de conexión con Alegra
- **500 Internal Server Error**: Error interno del servidor

## Formato de Errores

```json
{
  "success": false,
  "error": "Descripción del error",
  "details": "Detalles adicionales (opcional)"
}
```

## Notas Importantes

1. **Autenticación**: Todos los endpoints requieren autenticación mediante JWT
2. **Rangos de Fechas**: Si no se especifica ninguna fecha, se usa el día actual
3. **Timezone**: Todas las fechas están en timezone de Colombia (America/Bogota)
4. **Formato de Fechas**: `YYYY-MM-DD` (ejemplo: `2025-11-28`)
5. **Formato de Moneda**: Los montos se devuelven en formato COP (pesos colombianos)
6. **Rendimiento**: Para rangos grandes (>30 días), las consultas pueden tardar más

## Ejemplos de Uso

### Con cURL
```bash
# Obtener horas pico del mes
curl -X GET "https://api.ejemplo.com/api/analytics/peak-hours?start_date=2025-11-01&end_date=2025-11-30" \
  -H "Authorization: Bearer YOUR_JWT_TOKEN"

# Obtener top 5 clientes del día
curl -X GET "https://api.ejemplo.com/api/analytics/top-customers?date=2025-11-28&limit=5" \
  -H "Authorization: Bearer YOUR_JWT_TOKEN"
```

### Con JavaScript (Fetch)
```javascript
const fetchPeakHours = async () => {
  const response = await fetch(
    'https://api.ejemplo.com/api/analytics/peak-hours?start_date=2025-11-01&end_date=2025-11-30',
    {
      headers: {
        'Authorization': `Bearer ${token}`,
        'Content-Type': 'application/json'
      }
    }
  );

  const data = await response.json();
  console.log(data);
};
```

### Con Python (requests)
```python
import requests

url = "https://api.ejemplo.com/api/analytics/top-customers"
params = {
    "start_date": "2025-11-01",
    "end_date": "2025-11-30",
    "limit": 10
}
headers = {
    "Authorization": f"Bearer {token}"
}

response = requests.get(url, params=params, headers=headers)
data = response.json()
print(data)
```

---

## Soporte

Para reportar problemas o solicitar nuevas funcionalidades, contactar al equipo de desarrollo.
