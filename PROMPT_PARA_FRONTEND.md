# 📋 Prompt para Implementación en Frontend - Módulo de Analytics Avanzado

---

## 🎯 Objetivo

Implementar una nueva sección en el frontend llamada **"Analytics Avanzado"** o **"Análisis de Ventas"** que contenga 7 nuevas funcionalidades de análisis. Esta sección debe estar ubicada junto a las secciones existentes de "Análisis de Productos" y "Ver Ventas Mensuales".

---

## 📍 Ubicación en el Frontend

**Crear una nueva sección del menú:**
```
Menú Principal
├── Dashboard (existente)
├── Cierre de Caja (existente)
├── Análisis de Productos (existente)
├── Ventas Mensuales (existente)
└── 📊 Analytics Avanzado (NUEVO) ← Agregar aquí
    ├── Horas Pico
    ├── Top Clientes
    ├── Top Vendedoras
    ├── Retención de Clientes
    ├── Tendencias de Ventas
    ├── Cross-Selling
    └── Dashboard Completo
```

**Alternativa (si prefieres submenu):**
```
Menú Principal
├── Dashboard (existente)
├── Cierre de Caja (existente)
├── 📊 Análisis (NUEVO - con submenu)
│   ├── Análisis de Productos (mover aquí)
│   ├── Ventas Mensuales (mover aquí)
│   └── Analytics Avanzado (NUEVO)
│       ├── Horas Pico
│       ├── Top Clientes
│       ├── Top Vendedoras
│       ├── Retención de Clientes
│       ├── Tendencias de Ventas
│       ├── Cross-Selling
│       └── Dashboard Completo
```

---

## 🔗 Endpoints del Backend Disponibles

**Base URL:** `http://tu-servidor:5000/api/analytics`

Todos los endpoints requieren autenticación JWT en el header:
```javascript
headers: {
  'Authorization': `Bearer ${token}`,
  'Content-Type': 'application/json'
}
```

### Lista de Endpoints:

| Endpoint | Método | Descripción |
|----------|--------|-------------|
| `/api/analytics/peak-hours` | GET | Horas pico de ventas |
| `/api/analytics/top-customers` | GET | Top clientes |
| `/api/analytics/top-sellers` | GET | Top vendedoras |
| `/api/analytics/customer-retention` | GET | Retención de clientes (RFM) |
| `/api/analytics/sales-trends` | GET | Tendencias de ventas |
| `/api/analytics/cross-selling` | GET | Productos que se venden juntos |
| `/api/analytics/dashboard` | GET | Dashboard completo (todos los análisis) |

---

## 📊 Detalle de Cada Funcionalidad

---

## 1️⃣ HORAS PICO DE VENTAS

### Endpoint
```
GET /api/analytics/peak-hours
```

### Query Parameters
```javascript
{
  date: "2025-11-28",           // Opcional: Fecha específica
  start_date: "2025-11-01",     // Opcional: Fecha inicio
  end_date: "2025-11-30"        // Opcional: Fecha fin
}
```

### Respuesta del Backend
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
      },
      {
        "hour": 18,
        "hour_range": "18:00 - 19:00",
        "total_revenue": 720000,
        "total_revenue_formatted": "$720.000",
        "invoice_count": 20,
        "total_items": 50,
        "average_ticket": 36000,
        "average_ticket_formatted": "$36.000"
      }
      // ... Top 5 completo
    ],
    "hourly_breakdown": [
      {
        "hour": 0,
        "hour_range": "00:00 - 01:00",
        "total_revenue": 0,
        "total_revenue_formatted": "$0",
        "invoice_count": 0,
        "total_items": 0,
        "average_ticket": 0,
        "average_ticket_formatted": "$0"
      }
      // ... Array de 24 horas (0-23)
    ],
    "daily_hourly_breakdown": {
      "Lunes": [
        {
          "hour": 10,
          "hour_range": "10:00 - 11:00",
          "total_revenue": 120000,
          "total_revenue_formatted": "$120.000",
          "invoice_count": 3,
          "average_ticket": 40000,
          "average_ticket_formatted": "$40.000"
        }
        // ... Horas con venta del lunes
      ],
      "Martes": [...],
      "Miércoles": [...],
      "Jueves": [...],
      "Viernes": [...],
      "Sábado": [...],
      "Domingo": [...]
    }
  }
}
```

### Componentes de UI Sugeridos
1. **Gráfico de Barras Principal**: Muestra las 24 horas con ingresos por hora
2. **Cards del Top 5**: Cards destacadas con las 5 mejores horas
3. **Selector de Rango de Fechas**: Para filtrar por período
4. **Tabla por Día de Semana**: Tabs o acordeón con breakdown por día

### Ejemplo de Código (React/Next.js)
```jsx
import { useState, useEffect } from 'react';
import { BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer } from 'recharts';

export default function PeakHoursAnalysis() {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(false);
  const [dateRange, setDateRange] = useState({
    start_date: '2025-11-01',
    end_date: '2025-11-30'
  });

  const fetchPeakHours = async () => {
    setLoading(true);
    try {
      const token = localStorage.getItem('token');
      const params = new URLSearchParams(dateRange);

      const response = await fetch(
        `http://localhost:5000/api/analytics/peak-hours?${params}`,
        {
          headers: {
            'Authorization': `Bearer ${token}`,
            'Content-Type': 'application/json'
          }
        }
      );

      const result = await response.json();
      if (result.success) {
        setData(result.data);
      }
    } catch (error) {
      console.error('Error:', error);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchPeakHours();
  }, [dateRange]);

  if (loading) return <div>Cargando...</div>;
  if (!data) return null;

  return (
    <div className="peak-hours-container">
      <h1>Horas Pico de Ventas</h1>

      {/* Resumen */}
      <div className="summary-cards">
        <div className="card">
          <h3>Total Ingresos</h3>
          <p>{data.summary.total_revenue_formatted}</p>
        </div>
        <div className="card">
          <h3>Total Facturas</h3>
          <p>{data.summary.total_invoices}</p>
        </div>
        <div className="card">
          <h3>Horas con Ventas</h3>
          <p>{data.summary.hours_with_sales}</p>
        </div>
      </div>

      {/* Top 5 Horas Pico */}
      <div className="top-5-hours">
        <h2>Top 5 Horas Pico</h2>
        {data.top_5_peak_hours.map((hour, index) => (
          <div key={hour.hour} className="peak-hour-card">
            <span className="rank">#{index + 1}</span>
            <div className="hour-info">
              <h3>{hour.hour_range}</h3>
              <p className="revenue">{hour.total_revenue_formatted}</p>
              <p className="invoices">{hour.invoice_count} facturas</p>
              <p className="avg-ticket">Ticket promedio: {hour.average_ticket_formatted}</p>
            </div>
          </div>
        ))}
      </div>

      {/* Gráfico de 24 horas */}
      <div className="hourly-chart">
        <h2>Ventas por Hora del Día</h2>
        <ResponsiveContainer width="100%" height={400}>
          <BarChart data={data.hourly_breakdown}>
            <XAxis dataKey="hour_range" />
            <YAxis />
            <Tooltip />
            <Bar dataKey="total_revenue" fill="#8884d8" />
          </BarChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}
```

---

## 2️⃣ TOP CLIENTES

### Endpoint
```
GET /api/analytics/top-customers
```

### Query Parameters
```javascript
{
  date: "2025-11-28",           // Opcional
  start_date: "2025-11-01",     // Opcional
  end_date: "2025-11-30",       // Opcional
  limit: 10                      // Opcional (default: 10)
}
```

### Respuesta del Backend
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
      // ... más clientes
    ],
    "total_customers": 250
  }
}
```

### Componentes de UI Sugeridos
1. **Cards de Resumen**: Total clientes, ingresos, tasa de recurrencia
2. **Tabla de Top Clientes**: Con ranking, nombre, gasto, frecuencia
3. **Badges**: Para clientes VIP, recurrentes, nuevos
4. **Selector de Límite**: Dropdown para elegir top 5, 10, 20, 50
5. **Filtros de Fecha**: DatePicker para rango

### Ejemplo de Tabla
```jsx
<table className="top-customers-table">
  <thead>
    <tr>
      <th>Rank</th>
      <th>Cliente</th>
      <th>Total Gastado</th>
      <th>Compras</th>
      <th>Ticket Promedio</th>
      <th>Última Compra</th>
      <th>Tipo</th>
    </tr>
  </thead>
  <tbody>
    {data.top_customers.map((customer, index) => (
      <tr key={customer.customer_id}>
        <td>#{index + 1}</td>
        <td>
          <div className="customer-info">
            <strong>{customer.customer_name}</strong>
            <small>{customer.email}</small>
          </div>
        </td>
        <td className="amount">{customer.total_spent_formatted}</td>
        <td>{customer.purchase_count}</td>
        <td>{customer.average_ticket_formatted}</td>
        <td>{customer.last_purchase_date}</td>
        <td>
          <span className={`badge ${customer.purchase_count >= 5 ? 'vip' : 'regular'}`}>
            {customer.purchase_count >= 5 ? 'VIP' : 'Regular'}
          </span>
        </td>
      </tr>
    ))}
  </tbody>
</table>
```

---

## 3️⃣ TOP VENDEDORAS

### Endpoint
```
GET /api/analytics/top-sellers
```

### Query Parameters
```javascript
{
  date: "2025-11-28",
  start_date: "2025-11-01",
  end_date: "2025-11-30",
  limit: 10
}
```

### Respuesta del Backend
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
      // ... más vendedoras
    ],
    "total_sellers": 5
  }
}
```

### Componentes de UI Sugeridos
1. **Podio Visual**: Top 3 vendedoras con medallas (oro, plata, bronce)
2. **Cards de Vendedora**: Con foto, nombre, métricas principales
3. **Gráfico de Comparación**: Barras comparando ventas entre vendedoras
4. **Badges de Logros**: Mejor ticket, más clientes, hora productiva

### Ejemplo de Card
```jsx
<div className="seller-podium">
  {data.top_sellers.slice(0, 3).map((seller, index) => (
    <div key={seller.seller_id} className={`podium-card rank-${index + 1}`}>
      <div className="medal">
        {index === 0 && '🥇'}
        {index === 1 && '🥈'}
        {index === 2 && '🥉'}
      </div>
      <h3>{seller.seller_name}</h3>
      <div className="stats">
        <div className="stat-item">
          <label>Total Ventas</label>
          <strong>{seller.total_sales_formatted}</strong>
        </div>
        <div className="stat-item">
          <label>Facturas</label>
          <strong>{seller.invoice_count}</strong>
        </div>
        <div className="stat-item">
          <label>Ticket Promedio</label>
          <strong>{seller.average_ticket_formatted}</strong>
        </div>
        <div className="stat-item">
          <label>Hora más productiva</label>
          <strong>{seller.most_productive_hour}</strong>
        </div>
      </div>
    </div>
  ))}
</div>
```

---

## 4️⃣ RETENCIÓN DE CLIENTES (RFM)

### Endpoint
```
GET /api/analytics/customer-retention
```

### Query Parameters
```javascript
{
  start_date: "2025-10-01",
  end_date: "2025-11-30"
}
```

### Respuesta del Backend
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
      // ... más clientes leales
    ],
    "at_risk_customers": [
      {
        "customer_id": "221",
        "customer_name": "DIEGO LEONARDO ZARATE MEJIA",
        "recency_days": 95,
        "frequency": 4,
        "monetary": 340000,
        "monetary_formatted": "$340.000",
        "customer_type": "Recurrente",
        "activity_status": "En riesgo",
        "last_purchase_date": "2025-08-25"
      }
      // ... más clientes en riesgo
    ],
    "rfm_data": [
      // ... Todos los clientes con análisis RFM completo
    ]
  }
}
```

### Componentes de UI Sugeridos
1. **Métricas RFM**: Cards con Recency, Frequency, Monetary
2. **Gráfico de Segmentación**: Pie chart con Nuevos/Recurrentes/Leales
3. **Semáforo de Actividad**: Verde (Activo), Amarillo (En riesgo), Rojo (Inactivo)
4. **Tabla de Clientes en Riesgo**: Para acciones de reactivación
5. **Lista de Clientes Leales**: Para programas VIP

### Ejemplo de Segmentación
```jsx
<div className="customer-segmentation">
  <h2>Segmentación de Clientes</h2>

  <div className="segments-grid">
    <div className="segment-card new">
      <h3>Nuevos</h3>
      <p className="count">{data.summary.new_customers}</p>
      <p className="description">1 compra</p>
    </div>

    <div className="segment-card recurring">
      <h3>Recurrentes</h3>
      <p className="count">{data.summary.recurring_customers}</p>
      <p className="description">2-4 compras</p>
    </div>

    <div className="segment-card loyal">
      <h3>Leales</h3>
      <p className="count">{data.summary.loyal_customers}</p>
      <p className="description">5+ compras</p>
    </div>
  </div>

  <div className="activity-status">
    <h3>Estado de Actividad</h3>
    <div className="status-item active">
      <span className="indicator"></span>
      <span>Activos: {data.summary.active_customers}</span>
    </div>
    <div className="status-item at-risk">
      <span className="indicator"></span>
      <span>En Riesgo: {data.summary.at_risk_customers}</span>
    </div>
    <div className="status-item inactive">
      <span className="indicator"></span>
      <span>Inactivos: {data.summary.inactive_customers}</span>
    </div>
  </div>

  <div className="retention-rate">
    <h3>Tasa de Retención</h3>
    <div className="rate-circle">
      <span className="percentage">{data.summary.retention_rate}%</span>
    </div>
  </div>
</div>
```

---

## 5️⃣ TENDENCIAS DE VENTAS

### Endpoint
```
GET /api/analytics/sales-trends
```

### Query Parameters
```javascript
{
  start_date: "2025-11-01",
  end_date: "2025-11-30"
}
```

### Respuesta del Backend
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
        "total_revenue_formatted": "$850.000",
        "invoice_count": 25
      },
      "worst_day": {
        "date": "2025-11-05",
        "day_name": "Martes",
        "total_revenue": 120000,
        "total_revenue_formatted": "$120.000",
        "invoice_count": 3
      },
      "best_weekday": {
        "day_name": "Sábado",
        "total_revenue": 2200000,
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
      // ... un objeto por cada día con ventas
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
      // ... un objeto por cada día de la semana (L-D)
    ]
  }
}
```

### Componentes de UI Sugeridos
1. **Gráfico de Línea Temporal**: Ventas día por día
2. **Cards de Mejor/Peor Día**: Destacar días extremos
3. **Gráfico de Barras por Día de Semana**: Comparar L-M-M-J-V-S-D
4. **Calendario de Calor**: Heatmap con intensidad de ventas

### Ejemplo de Gráfico
```jsx
import { LineChart, Line, BarChart, Bar, XAxis, YAxis, Tooltip } from 'recharts';

<div className="sales-trends">
  <h1>Tendencias de Ventas</h1>

  {/* Resumen */}
  <div className="summary-grid">
    <div className="card">
      <h3>Total Período</h3>
      <p className="amount">{data.summary.total_revenue_formatted}</p>
    </div>
    <div className="card">
      <h3>Promedio Diario</h3>
      <p className="amount">{data.summary.avg_revenue_per_day_formatted}</p>
    </div>
    <div className="card best">
      <h3>Mejor Día</h3>
      <p className="date">{data.summary.best_day.date}</p>
      <p className="amount">{data.summary.best_day.total_revenue_formatted}</p>
    </div>
    <div className="card worst">
      <h3>Peor Día</h3>
      <p className="date">{data.summary.worst_day.date}</p>
      <p className="amount">{data.summary.worst_day.total_revenue_formatted}</p>
    </div>
  </div>

  {/* Gráfico de Línea Temporal */}
  <div className="daily-chart">
    <h2>Ventas Diarias</h2>
    <ResponsiveContainer width="100%" height={400}>
      <LineChart data={data.daily_sales}>
        <XAxis dataKey="date" />
        <YAxis />
        <Tooltip />
        <Line type="monotone" dataKey="total_revenue" stroke="#8884d8" />
      </LineChart>
    </ResponsiveContainer>
  </div>

  {/* Análisis por Día de la Semana */}
  <div className="weekday-chart">
    <h2>Ventas por Día de la Semana</h2>
    <ResponsiveContainer width="100%" height={300}>
      <BarChart data={data.weekday_analysis}>
        <XAxis dataKey="day_name" />
        <YAxis />
        <Tooltip />
        <Bar dataKey="avg_revenue_per_day" fill="#82ca9d" />
      </BarChart>
    </ResponsiveContainer>
  </div>
</div>
```

---

## 6️⃣ CROSS-SELLING (PRODUCTOS QUE SE VENDEN JUNTOS)

### Endpoint
```
GET /api/analytics/cross-selling
```

### Query Parameters
```javascript
{
  start_date: "2025-11-01",
  end_date: "2025-11-30",
  min_support: 2  // Mínimo de veces que deben comprarse juntos
}
```

### Respuesta del Backend
```json
{
  "success": true,
  "date_range": "2025-11-01 al 2025-11-30",
  "data": {
    "summary": {
      "total_product_pairs": 45,
      "min_support_used": 2,
      "total_unique_products": 180
    },
    "top_product_pairs": [
      {
        "product1": "JEAN HOMBRE 109900 / 105110990034",
        "product2": "CAMISETA HOMBRE 42900 / 1051429001",
        "times_bought_together": 12,
        "total_revenue": 1834800,
        "total_revenue_formatted": "$1.834.800",
        "confidence_1_to_2": 45.5,
        "confidence_2_to_1": 35.2,
        "avg_confidence": 40.35
      }
      // ... más pares de productos
    ],
    "top_individual_products": [
      {
        "product_name": "JEAN HOMBRE 109900",
        "times_sold": 45,
        "total_revenue": 4945500,
        "total_revenue_formatted": "$4.945.500"
      }
      // ... más productos individuales
    ],
    "all_pairs": [
      // ... Todos los pares encontrados
    ]
  }
}
```

### Componentes de UI Sugeridos
1. **Cards de Combos**: Cada par de productos en una card
2. **Indicador de Confianza**: Barra de progreso o porcentaje
3. **Badges de Frecuencia**: "Muy frecuente", "Frecuente", "Ocasional"
4. **Botón de Acción**: "Crear Combo", "Ver más"

### Ejemplo de Vista
```jsx
<div className="cross-selling">
  <h1>Productos que se Compran Juntos</h1>

  <div className="summary">
    <p>Se encontraron <strong>{data.summary.total_product_pairs}</strong> combinaciones de productos</p>
  </div>

  <div className="product-pairs-grid">
    {data.top_product_pairs.map((pair, index) => (
      <div key={index} className="pair-card">
        <div className="rank">#{index + 1}</div>

        <div className="products">
          <div className="product">{pair.product1}</div>
          <div className="plus-sign">+</div>
          <div className="product">{pair.product2}</div>
        </div>

        <div className="metrics">
          <div className="metric">
            <label>Comprados juntos</label>
            <strong>{pair.times_bought_together} veces</strong>
          </div>
          <div className="metric">
            <label>Ingresos generados</label>
            <strong>{pair.total_revenue_formatted}</strong>
          </div>
          <div className="metric">
            <label>Confianza</label>
            <div className="confidence-bar">
              <div
                className="fill"
                style={{width: `${pair.avg_confidence}%`}}
              ></div>
              <span>{pair.avg_confidence}%</span>
            </div>
          </div>
        </div>

        <button className="create-combo-btn">
          Crear Combo
        </button>
      </div>
    ))}
  </div>
</div>
```

---

## 7️⃣ DASHBOARD COMPLETO

### Endpoint
```
GET /api/analytics/dashboard
```

### Query Parameters
```javascript
{
  start_date: "2025-11-01",
  end_date: "2025-11-30"
}
```

### Respuesta del Backend
```json
{
  "success": true,
  "date_range": "2025-11-01 al 2025-11-30",
  "server_timestamp": "2025-11-29T10:30:00-05:00",
  "data": {
    "peak_hours": {
      // ... Datos completos de horas pico
    },
    "top_customers": {
      // ... Datos completos de top clientes
    },
    "top_sellers": {
      // ... Datos completos de top vendedoras
    },
    "customer_retention": {
      // ... Datos completos de retención
    },
    "sales_trends": {
      // ... Datos completos de tendencias
    },
    "cross_selling": {
      // ... Datos completos de cross-selling
    }
  }
}
```

### Componentes de UI Sugeridos
1. **Grid de KPIs**: Cards con métricas principales de cada análisis
2. **Gráficos Compactos**: Versión mini de cada gráfico
3. **Tabs o Acordeón**: Para navegar entre análisis
4. **Botón "Ver Detalles"**: Link a vista completa de cada análisis

### Ejemplo de Dashboard
```jsx
<div className="analytics-dashboard">
  <h1>Dashboard de Analytics</h1>
  <p className="date-range">{data.date_range}</p>

  <div className="dashboard-grid">
    {/* Horas Pico - Resumen */}
    <div className="dashboard-card">
      <h3>🕐 Horas Pico</h3>
      <div className="mini-stats">
        <p>Mejor hora: <strong>{data.peak_hours.top_5_peak_hours[0].hour_range}</strong></p>
        <p>Ingresos: <strong>{data.peak_hours.top_5_peak_hours[0].total_revenue_formatted}</strong></p>
      </div>
      <a href="/analytics/peak-hours">Ver detalles →</a>
    </div>

    {/* Top Clientes - Resumen */}
    <div className="dashboard-card">
      <h3>👥 Top Clientes</h3>
      <div className="mini-stats">
        <p>Total clientes: <strong>{data.top_customers.summary.total_unique_customers}</strong></p>
        <p>Tasa recurrencia: <strong>{data.top_customers.summary.recurring_rate}%</strong></p>
      </div>
      <a href="/analytics/top-customers">Ver detalles →</a>
    </div>

    {/* Top Vendedoras - Resumen */}
    <div className="dashboard-card">
      <h3>🏆 Top Vendedoras</h3>
      <div className="mini-stats">
        <p>#1: <strong>{data.top_sellers.top_sellers[0].seller_name}</strong></p>
        <p>Ventas: <strong>{data.top_sellers.top_sellers[0].total_sales_formatted}</strong></p>
      </div>
      <a href="/analytics/top-sellers">Ver detalles →</a>
    </div>

    {/* Retención - Resumen */}
    <div className="dashboard-card">
      <h3>🔄 Retención</h3>
      <div className="mini-stats">
        <p>Tasa retención: <strong>{data.customer_retention.summary.retention_rate}%</strong></p>
        <p>En riesgo: <strong>{data.customer_retention.summary.at_risk_customers}</strong></p>
      </div>
      <a href="/analytics/retention">Ver detalles →</a>
    </div>

    {/* Tendencias - Resumen */}
    <div className="dashboard-card">
      <h3>📈 Tendencias</h3>
      <div className="mini-stats">
        <p>Mejor día: <strong>{data.sales_trends.summary.best_day.day_name}</strong></p>
        <p>Promedio diario: <strong>{data.sales_trends.summary.avg_revenue_per_day_formatted}</strong></p>
      </div>
      <a href="/analytics/trends">Ver detalles →</a>
    </div>

    {/* Cross-Selling - Resumen */}
    <div className="dashboard-card">
      <h3>🛍️ Cross-Selling</h3>
      <div className="mini-stats">
        <p>Combos encontrados: <strong>{data.cross_selling.summary.total_product_pairs}</strong></p>
        <p>Top combo: <strong>{data.cross_selling.top_product_pairs[0].times_bought_together} veces</strong></p>
      </div>
      <a href="/analytics/cross-selling">Ver detalles →</a>
    </div>
  </div>
</div>
```

---

## 📱 Estructura de Archivos Sugerida

```
src/
├── components/
│   └── analytics/
│       ├── PeakHours.jsx
│       ├── TopCustomers.jsx
│       ├── TopSellers.jsx
│       ├── CustomerRetention.jsx
│       ├── SalesTrends.jsx
│       ├── CrossSelling.jsx
│       ├── AnalyticsDashboard.jsx
│       └── shared/
│           ├── DateRangePicker.jsx
│           ├── MetricCard.jsx
│           └── LoadingSpinner.jsx
├── services/
│   └── analyticsApi.js
├── hooks/
│   └── useAnalytics.js
└── styles/
    └── analytics.css
```

---

## 🔧 Servicio API Compartido

Crea un archivo `src/services/analyticsApi.js`:

```javascript
const BASE_URL = 'http://localhost:5000/api/analytics';

const getAuthHeaders = () => ({
  'Authorization': `Bearer ${localStorage.getItem('token')}`,
  'Content-Type': 'application/json'
});

export const analyticsApi = {
  // Horas Pico
  getPeakHours: async (params) => {
    const query = new URLSearchParams(params);
    const response = await fetch(`${BASE_URL}/peak-hours?${query}`, {
      headers: getAuthHeaders()
    });
    return response.json();
  },

  // Top Clientes
  getTopCustomers: async (params) => {
    const query = new URLSearchParams(params);
    const response = await fetch(`${BASE_URL}/top-customers?${query}`, {
      headers: getAuthHeaders()
    });
    return response.json();
  },

  // Top Vendedoras
  getTopSellers: async (params) => {
    const query = new URLSearchParams(params);
    const response = await fetch(`${BASE_URL}/top-sellers?${query}`, {
      headers: getAuthHeaders()
    });
    return response.json();
  },

  // Retención
  getCustomerRetention: async (params) => {
    const query = new URLSearchParams(params);
    const response = await fetch(`${BASE_URL}/customer-retention?${query}`, {
      headers: getAuthHeaders()
    });
    return response.json();
  },

  // Tendencias
  getSalesTrends: async (params) => {
    const query = new URLSearchParams(params);
    const response = await fetch(`${BASE_URL}/sales-trends?${query}`, {
      headers: getAuthHeaders()
    });
    return response.json();
  },

  // Cross-Selling
  getCrossSelling: async (params) => {
    const query = new URLSearchParams(params);
    const response = await fetch(`${BASE_URL}/cross-selling?${query}`, {
      headers: getAuthHeaders()
    });
    return response.json();
  },

  // Dashboard Completo
  getDashboard: async (params) => {
    const query = new URLSearchParams(params);
    const response = await fetch(`${BASE_URL}/dashboard?${query}`, {
      headers: getAuthHeaders()
    });
    return response.json();
  }
};
```

---

## 🎨 Estilos CSS Sugeridos

```css
/* analytics.css */

.analytics-container {
  padding: 20px;
  max-width: 1400px;
  margin: 0 auto;
}

/* Cards de Resumen */
.summary-cards {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(250px, 1fr));
  gap: 20px;
  margin-bottom: 30px;
}

.summary-cards .card {
  background: white;
  padding: 20px;
  border-radius: 8px;
  box-shadow: 0 2px 4px rgba(0,0,0,0.1);
}

.summary-cards .card h3 {
  font-size: 14px;
  color: #666;
  margin-bottom: 10px;
}

.summary-cards .card p {
  font-size: 24px;
  font-weight: bold;
  color: #333;
}

/* Tabla */
.analytics-table {
  width: 100%;
  background: white;
  border-radius: 8px;
  overflow: hidden;
  box-shadow: 0 2px 4px rgba(0,0,0,0.1);
}

.analytics-table th {
  background: #f5f5f5;
  padding: 15px;
  text-align: left;
  font-weight: 600;
}

.analytics-table td {
  padding: 15px;
  border-top: 1px solid #eee;
}

/* Badges */
.badge {
  padding: 4px 12px;
  border-radius: 12px;
  font-size: 12px;
  font-weight: 600;
}

.badge.vip {
  background: #ffd700;
  color: #333;
}

.badge.regular {
  background: #e0e0e0;
  color: #666;
}

.badge.active {
  background: #4caf50;
  color: white;
}

.badge.at-risk {
  background: #ff9800;
  color: white;
}

.badge.inactive {
  background: #f44336;
  color: white;
}

/* Gráficos */
.chart-container {
  background: white;
  padding: 20px;
  border-radius: 8px;
  box-shadow: 0 2px 4px rgba(0,0,0,0.1);
  margin-bottom: 20px;
}

/* Podio de Vendedoras */
.seller-podium {
  display: flex;
  justify-content: center;
  gap: 20px;
  margin: 30px 0;
}

.podium-card {
  background: white;
  padding: 30px;
  border-radius: 12px;
  box-shadow: 0 4px 8px rgba(0,0,0,0.1);
  text-align: center;
  position: relative;
}

.podium-card.rank-1 {
  order: 2;
  transform: scale(1.1);
  border: 3px solid #ffd700;
}

.podium-card.rank-2 {
  order: 1;
  border: 3px solid #c0c0c0;
}

.podium-card.rank-3 {
  order: 3;
  border: 3px solid #cd7f32;
}

.medal {
  font-size: 48px;
  margin-bottom: 10px;
}
```

---

## 📝 Checklist de Implementación

- [ ] Crear nueva sección "Analytics Avanzado" en el menú
- [ ] Crear servicio API (`analyticsApi.js`)
- [ ] Implementar componente de Horas Pico
- [ ] Implementar componente de Top Clientes
- [ ] Implementar componente de Top Vendedoras
- [ ] Implementar componente de Retención
- [ ] Implementar componente de Tendencias
- [ ] Implementar componente de Cross-Selling
- [ ] Implementar Dashboard Completo
- [ ] Agregar DateRangePicker compartido
- [ ] Agregar manejo de errores
- [ ] Agregar estados de carga
- [ ] Agregar estilos CSS
- [ ] Probar con datos reales
- [ ] Optimizar rendimiento
- [ ] Responsive design

---

## 🚀 Ejemplo Completo de Integración

```jsx
// App.jsx o Router
import PeakHours from './components/analytics/PeakHours';
import TopCustomers from './components/analytics/TopCustomers';
import TopSellers from './components/analytics/TopSellers';
import CustomerRetention from './components/analytics/CustomerRetention';
import SalesTrends from './components/analytics/SalesTrends';
import CrossSelling from './components/analytics/CrossSelling';
import AnalyticsDashboard from './components/analytics/AnalyticsDashboard';

// Rutas
<Routes>
  {/* Rutas existentes */}
  <Route path="/dashboard" element={<Dashboard />} />
  <Route path="/cierre-caja" element={<CierreCaja />} />
  <Route path="/productos" element={<Productos />} />
  <Route path="/ventas-mensuales" element={<VentasMensuales />} />

  {/* Nuevas rutas de Analytics */}
  <Route path="/analytics" element={<AnalyticsDashboard />} />
  <Route path="/analytics/peak-hours" element={<PeakHours />} />
  <Route path="/analytics/top-customers" element={<TopCustomers />} />
  <Route path="/analytics/top-sellers" element={<TopSellers />} />
  <Route path="/analytics/retention" element={<CustomerRetention />} />
  <Route path="/analytics/trends" element={<SalesTrends />} />
  <Route path="/analytics/cross-selling" element={<CrossSelling />} />
</Routes>
```

---

## 🎯 Priorización Sugerida de Implementación

### Fase 1 (Semana 1):
1. Dashboard Completo (vista general)
2. Horas Pico (más simple visualmente)
3. Top Vendedoras (motivación del equipo)

### Fase 2 (Semana 2):
4. Top Clientes (programas VIP)
5. Tendencias (planificación)

### Fase 3 (Semana 3):
6. Retención (campañas)
7. Cross-Selling (ventas adicionales)

---

## 📞 Soporte

Si tienes dudas durante la implementación:
1. Revisa la documentación técnica completa en `ANALYTICS_API_DOCUMENTATION.md`
2. Usa el script de prueba `test_analytics_endpoints.py` para validar el backend
3. Consulta la guía de uso en `GUIA_USO_ANALYTICS.md`

---

**¡Éxito con la implementación!** 🚀
