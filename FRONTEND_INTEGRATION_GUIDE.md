# Guía de Integración Frontend - Sistema de Cierre de Caja KOAJ

## 📋 Resumen General

El backend ahora cuenta con **DOS SECCIONES DE ESTADÍSTICAS** diferenciadas:

### 1. **Estadísticas Avanzadas** (APIs Directas de Alegra)
- ✨ Datos más rápidos, completos y confiables
- 📊 Obtenidos directamente de la plataforma Alegra (no documentadas públicamente)
- 🔒 Solo accesibles para usuarios con rol **admin**
- 🚀 No requieren recorrer factura por factura, Alegra calcula directamente

### 2. **Estadísticas Estándar** (APIs Documentadas de Alegra)
- 📚 Basadas en la documentación oficial de Alegra
- 🔄 Requieren procesamiento de múltiples facturas
- 🔒 Solo accesibles para usuarios con rol **admin**
- 📈 Incluyen análisis avanzados: horas pico, top clientes, retención, etc.

---

## 🔐 Sistema de Roles y Permisos

### Rol: **admin**
Tiene acceso completo a:
- ✅ Cierre de caja (`/api/sum_payments`)
- ✅ Ventas mensuales (`/api/monthly_sales`)
- ✅ **Estadísticas Estándar** (todos los endpoints de `/api/analytics/*`)
- ✅ **Estadísticas Avanzadas** (todos los endpoints de `/api/direct/*`)

### Rol: **sales**
Tiene acceso limitado a:
- ✅ Cierre de caja (`/api/sum_payments`)
- ✅ Ventas mensuales (`/api/monthly_sales`)
- ❌ NO tiene acceso a estadísticas estándar ni avanzadas

---

## 🔑 Autenticación

Todos los endpoints requieren autenticación mediante JWT token:

```javascript
// Configuración de headers para todas las peticiones
const headers = {
  'Authorization': `Bearer ${token}`,
  'Content-Type': 'application/json'
}
```

---

## 📊 SECCIÓN 1: ESTADÍSTICAS AVANZADAS (APIs Directas)

### Características
- ⚡ Respuestas ultra rápidas
- 📦 Información completa y precisa
- 🎯 Datos calculados directamente por Alegra
- 🔒 Solo para rol **admin**

---

### 1.1. **Reporte de Valor de Inventario**

**Endpoint:** `GET /api/direct/inventory/value-report`

**Descripción:** Obtiene el inventario completo con su valor. Soporta paginación para manejar grandes cantidades de items.

**Query Parameters:**
```typescript
{
  toDate?: string;    // Fecha hasta la cual generar el reporte (YYYY-MM-DD). Default: hoy
  limit?: number;     // Items por página (default: 10, max: 1000)
  page?: number;      // Número de página (default: 1)
  query?: string;     // Filtro de búsqueda (opcional)
}
```

**Ejemplo de petición:**
```javascript
// Obtener 50 items del inventario para hoy
const response = await fetch(
  `${API_URL}/api/direct/inventory/value-report?toDate=2025-12-15&limit=50&page=1`,
  { headers }
);
```

**Ejemplo de respuesta:**
```json
{
  "success": true,
  "server_timestamp": "2025-12-15T10:30:45-05:00",
  "data": [
    {
      "id": "123",
      "name": "Producto A",
      "sku": "SKU-001",
      "quantity": 50,
      "unit_price": 25000,
      "total_value": 1250000
    }
  ],
  "metadata": {
    "page": 1,
    "limit": 50,
    "query": "",
    "to_date": "2025-12-15"
  }
}
```

**Manejo de paginación:**
```javascript
// Para obtener TODO el inventario, hacer peticiones paginadas
async function getAllInventory(toDate) {
  let page = 1;
  let allItems = [];
  const limit = 1000; // Máximo permitido

  while (true) {
    const response = await fetch(
      `${API_URL}/api/direct/inventory/value-report?toDate=${toDate}&limit=${limit}&page=${page}`,
      { headers }
    );
    const data = await response.json();

    if (!data.success || data.data.length === 0) break;

    allItems = [...allItems, ...data.data];
    page++;

    // Si recibimos menos items que el límite, es la última página
    if (data.data.length < limit) break;
  }

  return allItems;
}
```

---

### 1.2. **Totales de Ventas**

**Endpoint:** `GET /api/direct/sales/totals`

**Descripción:** Obtiene totales de ventas agrupados por día o mes. Ideal para gráficas y resúmenes rápidos.

**Query Parameters:**
```typescript
{
  from: string;       // Fecha de inicio (YYYY-MM-DD) - REQUERIDO
  to: string;         // Fecha de fin (YYYY-MM-DD) - REQUERIDO
  groupBy?: string;   // Agrupación: 'day' o 'month' (default: 'day')
  limit?: number;     // Número de registros (default: 10)
  start?: number;     // Offset para paginación (default: 0)
}
```

**Ejemplo de petición:**
```javascript
// Obtener ventas del último mes agrupadas por día
const response = await fetch(
  `${API_URL}/api/direct/sales/totals?from=2025-11-15&to=2025-12-15&groupBy=day&limit=31`,
  { headers }
);
```

**Ejemplo de respuesta:**
```json
{
  "success": true,
  "server_timestamp": "2025-12-15T10:30:45-05:00",
  "data": [
    {
      "date": "2025-12-15",
      "total": 2500000,
      "count": 45,
      "avg_ticket": 55555
    },
    {
      "date": "2025-12-14",
      "total": 1800000,
      "count": 32,
      "avg_ticket": 56250
    }
  ],
  "metadata": {
    "from_date": "2025-11-15",
    "to_date": "2025-12-15",
    "group_by": "day",
    "limit": 31,
    "start": 0
  }
}
```

**Casos de uso:**
```javascript
// 1. Gráfica de ventas diarias del último mes
const dailySales = await fetch(
  `${API_URL}/api/direct/sales/totals?from=${lastMonth}&to=${today}&groupBy=day`,
  { headers }
);

// 2. Comparación mensual del último año
const monthlySales = await fetch(
  `${API_URL}/api/direct/sales/totals?from=${lastYear}&to=${today}&groupBy=month`,
  { headers }
);

// 3. Ventas de un día específico
const todaySales = await fetch(
  `${API_URL}/api/direct/sales/totals?from=${today}&to=${today}&groupBy=day`,
  { headers }
);
```

---

### 1.3. **Documentos de Ventas Discriminados**

**Endpoint:** `GET /api/direct/sales/documents`

**Descripción:** Obtiene cada factura con su información detallada para análisis específico.

**Query Parameters:**
```typescript
{
  from: string;       // Fecha de inicio (YYYY-MM-DD) - REQUERIDO
  to: string;         // Fecha de fin (YYYY-MM-DD) - REQUERIDO
  limit?: number;     // Número de documentos (default: 10)
  start?: number;     // Offset para paginación (default: 0)
}
```

**Ejemplo de petición:**
```javascript
// Obtener facturas del día de hoy
const response = await fetch(
  `${API_URL}/api/direct/sales/documents?from=2025-12-15&to=2025-12-15&limit=50`,
  { headers }
);
```

**Ejemplo de respuesta:**
```json
{
  "success": true,
  "server_timestamp": "2025-12-15T10:30:45-05:00",
  "data": [
    {
      "id": "12345",
      "number": "FV-001",
      "date": "2025-12-15",
      "client": {
        "id": "456",
        "name": "Cliente A",
        "email": "cliente@example.com"
      },
      "total": 150000,
      "payment_method": "cash",
      "items": [
        {
          "id": "789",
          "name": "Producto X",
          "quantity": 2,
          "unit_price": 75000,
          "total": 150000
        }
      ],
      "seller": {
        "id": "101",
        "name": "Vendedora 1"
      }
    }
  ],
  "metadata": {
    "from_date": "2025-12-15",
    "to_date": "2025-12-15",
    "limit": 50,
    "start": 0
  }
}
```

**Manejo de paginación:**
```javascript
// Para obtener todas las facturas de un día
async function getAllSalesDocuments(from, to) {
  let start = 0;
  let allDocuments = [];
  const limit = 50;

  while (true) {
    const response = await fetch(
      `${API_URL}/api/direct/sales/documents?from=${from}&to=${to}&limit=${limit}&start=${start}`,
      { headers }
    );
    const data = await response.json();

    if (!data.success || data.data.length === 0) break;

    allDocuments = [...allDocuments, ...data.data];
    start += limit;

    if (data.data.length < limit) break;
  }

  return allDocuments;
}
```

---

## 📈 SECCIÓN 2: ESTADÍSTICAS ESTÁNDAR (APIs Documentadas)

### Características
- 📚 Basadas en documentación oficial de Alegra
- 🔄 Procesamiento servidor recorre facturas
- 🎯 Análisis avanzados (horas pico, retención, etc.)
- 🔒 Solo para rol **admin**

---

### 2.1. **Horas Pico de Ventas**

**Endpoint:** `GET /api/analytics/peak-hours`

**Descripción:** Analiza las horas del día con más ventas.

**Query Parameters:**
```typescript
{
  date?: string;           // Fecha específica (YYYY-MM-DD)
  start_date?: string;     // Fecha inicio (YYYY-MM-DD)
  end_date?: string;       // Fecha fin (YYYY-MM-DD)
}
```

**Ejemplo:**
```javascript
const response = await fetch(
  `${API_URL}/api/analytics/peak-hours?start_date=2025-12-01&end_date=2025-12-15`,
  { headers }
);
```

---

### 2.2. **Top Clientes**

**Endpoint:** `GET /api/analytics/top-customers`

**Query Parameters:**
```typescript
{
  date?: string;
  start_date?: string;
  end_date?: string;
  limit?: number;          // Default: 10
}
```

---

### 2.3. **Top Vendedoras**

**Endpoint:** `GET /api/analytics/top-sellers`

**Query Parameters:**
```typescript
{
  date?: string;
  start_date?: string;
  end_date?: string;
  limit?: number;          // Default: 10
}
```

---

### 2.4. **Retención de Clientes**

**Endpoint:** `GET /api/analytics/customer-retention`

**Descripción:** Análisis RFM (Recency, Frequency, Monetary)

---

### 2.5. **Tendencias de Ventas**

**Endpoint:** `GET /api/analytics/sales-trends`

**Descripción:** Tendencias por día y día de la semana.

---

### 2.6. **Cross-Selling**

**Endpoint:** `GET /api/analytics/cross-selling`

**Descripción:** Productos que se compran juntos.

**Query Parameters:**
```typescript
{
  date?: string;
  start_date?: string;
  end_date?: string;
  min_support?: number;    // Mínimo de veces que aparecen juntos (default: 2)
}
```

---

### 2.7. **Dashboard Completo**

**Endpoint:** `GET /api/analytics/dashboard`

**Descripción:** Obtiene TODOS los análisis en una sola petición.

**Ejemplo:**
```javascript
const response = await fetch(
  `${API_URL}/api/analytics/dashboard?start_date=2025-12-01&end_date=2025-12-15`,
  { headers }
);
```

**Respuesta incluye:**
```json
{
  "success": true,
  "date_range": "2025-12-01 al 2025-12-15",
  "server_timestamp": "...",
  "data": {
    "peak_hours": { ... },
    "top_customers": { ... },
    "top_sellers": { ... },
    "customer_retention": { ... },
    "sales_trends": { ... },
    "cross_selling": { ... }
  },
  "invoices_summary": {
    "total_invoices_received": 150,
    "active_invoices_analyzed": 145,
    "voided_invoices_excluded": 5
  }
}
```

---

## 🎯 SECCIÓN 3: Endpoints Comunes (Admin + Sales)

### 3.1. **Cierre de Caja**

**Endpoint:** `POST /api/sum_payments`

**Roles permitidos:** admin, sales

**Body de ejemplo:**
```json
{
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
}
```

---

### 3.2. **Ventas Mensuales**

**Endpoint:** `GET /api/monthly_sales`

**Roles permitidos:** admin, sales

**Query Parameters:**
```typescript
{
  start_date?: string;     // Default: día 1 del mes actual
  end_date?: string;       // Default: fecha actual
}
```

**Ejemplo:**
```javascript
const response = await fetch(
  `${API_URL}/api/monthly_sales?start_date=2025-12-01&end_date=2025-12-15`,
  { headers }
);
```

---

## 🎨 Implementación en Frontend

### Estructura de Componentes Sugerida

```
src/
├── pages/
│   ├── admin/
│   │   ├── CierreCaja.tsx           // Admin y Sales
│   │   ├── VentasMensuales.tsx      // Admin y Sales
│   │   ├── EstadisticasAvanzadas.tsx   // Solo Admin
│   │   └── EstadisticasEstandar.tsx    // Solo Admin
│   └── sales/
│       ├── CierreCaja.tsx           // Sales
│       └── VentasMensuales.tsx      // Sales
```

### Componente de Estadísticas Avanzadas

```typescript
// EstadisticasAvanzadas.tsx
import React, { useState, useEffect } from 'react';

interface Props {
  token: string;
}

export const EstadisticasAvanzadas: React.FC<Props> = ({ token }) => {
  const [activeTab, setActiveTab] = useState<'inventory' | 'sales' | 'documents'>('inventory');

  return (
    <div className="estadisticas-avanzadas">
      <h1>Estadísticas Avanzadas (APIs Directas Alegra)</h1>
      <p className="description">
        Datos más rápidos y completos obtenidos directamente de la plataforma Alegra
      </p>

      <div className="tabs">
        <button onClick={() => setActiveTab('inventory')}>
          📦 Inventario
        </button>
        <button onClick={() => setActiveTab('sales')}>
          💰 Totales de Ventas
        </button>
        <button onClick={() => setActiveTab('documents')}>
          📄 Documentos Detallados
        </button>
      </div>

      <div className="tab-content">
        {activeTab === 'inventory' && <InventoryReport token={token} />}
        {activeTab === 'sales' && <SalesTotals token={token} />}
        {activeTab === 'documents' && <SalesDocuments token={token} />}
      </div>
    </div>
  );
};
```

### Hook para Consumir APIs

```typescript
// hooks/useAdvancedStats.ts
import { useState } from 'react';

export const useInventoryReport = (token: string) => {
  const [data, setData] = useState([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  const fetchInventory = async (toDate: string, page: number = 1, limit: number = 50) => {
    setLoading(true);
    try {
      const response = await fetch(
        `${process.env.REACT_APP_API_URL}/api/direct/inventory/value-report?toDate=${toDate}&limit=${limit}&page=${page}`,
        {
          headers: {
            'Authorization': `Bearer ${token}`,
            'Content-Type': 'application/json'
          }
        }
      );

      const result = await response.json();

      if (!result.success) {
        throw new Error(result.error || 'Error desconocido');
      }

      setData(result.data);
      return result;
    } catch (err) {
      setError(err.message);
      throw err;
    } finally {
      setLoading(false);
    }
  };

  return { data, loading, error, fetchInventory };
};
```

---

## 🔄 Manejo de Errores

### Errores comunes y cómo manejarlos:

```typescript
const handleApiCall = async (apiFunction: Function) => {
  try {
    const response = await apiFunction();

    if (!response.ok) {
      // Error HTTP
      const errorData = await response.json();

      switch (response.status) {
        case 401:
          // Token inválido o expirado - redirigir a login
          console.error('No autenticado:', errorData.message);
          // redirectToLogin();
          break;

        case 403:
          // Sin permisos - mostrar mensaje
          console.error('Sin permisos:', errorData.message);
          alert('No tienes permisos para acceder a este recurso');
          break;

        case 400:
          // Parámetros inválidos
          console.error('Parámetros inválidos:', errorData.error);
          alert(`Error: ${errorData.error}`);
          break;

        case 502:
          // Error de Alegra
          console.error('Error de Alegra:', errorData);
          alert('Error al conectar con Alegra. Intenta más tarde.');
          break;

        default:
          console.error('Error desconocido:', errorData);
      }

      return null;
    }

    return await response.json();

  } catch (error) {
    console.error('Error de red:', error);
    alert('Error de conexión. Verifica tu internet.');
    return null;
  }
};
```

---

## 📱 Diseño UI/UX Sugerido

### Para Admin:
```
┌─────────────────────────────────────────────┐
│  DASHBOARD ADMIN                             │
├─────────────────────────────────────────────┤
│                                              │
│  [Cierre de Caja]  [Ventas Mensuales]       │
│                                              │
│  ┌──────────────────┐  ┌──────────────────┐ │
│  │ Estadísticas     │  │ Estadísticas     │ │
│  │ AVANZADAS        │  │ ESTÁNDAR         │ │
│  │                  │  │                  │ │
│  │ ⚡ Más rápidas   │  │ 📊 Análisis      │ │
│  │ 📦 Inventario    │  │ 🕐 Horas pico    │ │
│  │ 💰 Ventas        │  │ 👥 Top clientes  │ │
│  │ 📄 Documentos    │  │ 🏆 Top ventas    │ │
│  │                  │  │ 📈 Tendencias    │ │
│  └──────────────────┘  └──────────────────┘ │
│                                              │
└─────────────────────────────────────────────┘
```

### Para Sales:
```
┌─────────────────────────────────────────────┐
│  DASHBOARD VENTAS                            │
├─────────────────────────────────────────────┤
│                                              │
│  [Cierre de Caja]  [Ventas Mensuales]       │
│                                              │
└─────────────────────────────────────────────┘
```

---

## ✅ Checklist de Implementación Frontend

### 1. Autenticación
- [ ] Implementar login y obtener JWT token
- [ ] Almacenar token (localStorage/sessionStorage)
- [ ] Incluir token en todas las peticiones
- [ ] Manejar expiración de token (401)
- [ ] Implementar refresh token (opcional)

### 2. Roles y Permisos
- [ ] Detectar rol del usuario desde el token
- [ ] Mostrar/ocultar secciones según rol
- [ ] Redirigir si intenta acceder sin permisos

### 3. Estadísticas Avanzadas (Admin)
- [ ] Página de Inventario con paginación
- [ ] Página de Totales de Ventas con gráficas
- [ ] Página de Documentos de Ventas
- [ ] Implementar filtros de fecha
- [ ] Implementar buscador en inventario

### 4. Estadísticas Estándar (Admin)
- [ ] Dashboard con todos los análisis
- [ ] Gráfica de horas pico
- [ ] Lista de top clientes
- [ ] Lista de top vendedoras
- [ ] Análisis de retención
- [ ] Tendencias de ventas
- [ ] Cross-selling

### 5. Funcionalidades Comunes (Admin + Sales)
- [ ] Formulario de cierre de caja
- [ ] Vista de ventas mensuales
- [ ] Selector de rango de fechas

### 6. Manejo de Errores
- [ ] Mostrar mensajes de error amigables
- [ ] Loading states
- [ ] Retry en caso de error de red
- [ ] Validación de formularios

### 7. UX/UI
- [ ] Indicadores de carga (spinners)
- [ ] Mensajes de éxito/error (toasts)
- [ ] Diseño responsive
- [ ] Accesibilidad (a11y)

---

## 🚀 Ejemplo de Integración Completa

```typescript
// services/api.ts
const API_URL = process.env.REACT_APP_API_URL;

class ApiService {
  private token: string;

  constructor(token: string) {
    this.token = token;
  }

  private async request(endpoint: string, options: RequestInit = {}) {
    const response = await fetch(`${API_URL}${endpoint}`, {
      ...options,
      headers: {
        'Authorization': `Bearer ${this.token}`,
        'Content-Type': 'application/json',
        ...options.headers
      }
    });

    if (!response.ok) {
      const error = await response.json();
      throw new Error(error.message || 'Error en la petición');
    }

    return response.json();
  }

  // ============ ESTADÍSTICAS AVANZADAS ============

  async getInventoryReport(toDate: string, page: number = 1, limit: number = 50) {
    return this.request(
      `/api/direct/inventory/value-report?toDate=${toDate}&page=${page}&limit=${limit}`
    );
  }

  async getSalesTotals(from: string, to: string, groupBy: 'day' | 'month' = 'day') {
    return this.request(
      `/api/direct/sales/totals?from=${from}&to=${to}&groupBy=${groupBy}`
    );
  }

  async getSalesDocuments(from: string, to: string, limit: number = 50) {
    return this.request(
      `/api/direct/sales/documents?from=${from}&to=${to}&limit=${limit}`
    );
  }

  // ============ ESTADÍSTICAS ESTÁNDAR ============

  async getAnalyticsDashboard(startDate: string, endDate: string) {
    return this.request(
      `/api/analytics/dashboard?start_date=${startDate}&end_date=${endDate}`
    );
  }

  async getPeakHours(startDate: string, endDate: string) {
    return this.request(
      `/api/analytics/peak-hours?start_date=${startDate}&end_date=${endDate}`
    );
  }

  // ============ COMUNES ============

  async submitCashClosing(data: any) {
    return this.request('/api/sum_payments', {
      method: 'POST',
      body: JSON.stringify(data)
    });
  }

  async getMonthlySales(startDate: string, endDate: string) {
    return this.request(
      `/api/monthly_sales?start_date=${startDate}&end_date=${endDate}`
    );
  }
}

export default ApiService;
```

---

## 📞 Contacto y Soporte

Si tienes dudas sobre la integración, revisa:
1. Este documento
2. La documentación Swagger en `/api/docs`
3. Los logs del servidor para debugging

---

**Fecha de actualización:** 2025-12-15
**Versión del backend:** 2.0.0
**Autor:** Sistema de Cierre de Caja KOAJ
