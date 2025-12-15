# 🚀 Quick Start - Integración Frontend

## 📋 TL;DR (Resumen Ejecutivo)

El backend tiene **2 secciones de estadísticas**:

1. **📊 Estadísticas AVANZADAS** → APIs directas de Alegra (rápidas, completas)
2. **📈 Estadísticas ESTÁNDAR** → APIs documentadas de Alegra (análisis procesados)

---

## 🔐 Roles

| Rol | Cierre Caja | Ventas Mensuales | Estadísticas Estándar | Estadísticas Avanzadas |
|-----|-------------|------------------|----------------------|----------------------|
| **admin** | ✅ | ✅ | ✅ | ✅ |
| **sales** | ✅ | ✅ | ❌ | ❌ |

---

## 🎯 Endpoints Principales

### 🟢 ESTADÍSTICAS AVANZADAS (Solo Admin)

```bash
# 1. Inventario completo (filtra automáticamente items con * en el nombre)
GET /api/direct/inventory/value-report?toDate=2025-12-15&limit=50&page=1

# 2. Totales de ventas por día
GET /api/direct/sales/totals?from=2025-12-01&to=2025-12-15&groupBy=day

# 3. Documentos de ventas detallados
GET /api/direct/sales/documents?from=2025-12-15&to=2025-12-15&limit=50
```

**⚠️ IMPORTANTE:** El endpoint de inventario filtra automáticamente items con nombres que empiezan con asteriscos (`*`) ya que son productos obsoletos.

### 🔵 ESTADÍSTICAS ESTÁNDAR (Solo Admin)

```bash
# Dashboard completo (TODO en una petición)
GET /api/analytics/dashboard?start_date=2025-12-01&end_date=2025-12-15

# Endpoints individuales
GET /api/analytics/peak-hours
GET /api/analytics/top-customers
GET /api/analytics/top-sellers
GET /api/analytics/customer-retention
GET /api/analytics/sales-trends
GET /api/analytics/cross-selling
```

### 🟡 COMUNES (Admin + Sales)

```bash
# Cierre de caja
POST /api/sum_payments

# Ventas mensuales
GET /api/monthly_sales?start_date=2025-12-01&end_date=2025-12-15
```

---

## 💻 Código de Ejemplo

### Headers para todas las peticiones:
```javascript
const headers = {
  'Authorization': `Bearer ${token}`,
  'Content-Type': 'application/json'
};
```

### Ejemplo: Obtener inventario
```javascript
const response = await fetch(
  'https://tu-api.com/api/direct/inventory/value-report?toDate=2025-12-15&limit=50&page=1',
  { headers }
);
const data = await response.json();

console.log(data);
// {
//   success: true,
//   data: [...items válidos (sin nombres con *)...],
//   metadata: {
//     page: 1,
//     limit: 50,
//     total_received: 75,     // Items de Alegra
//     total_filtered: 10,     // Items con * filtrados
//     total_returned: 65      // Items enviados
//   }
// }

// ✅ Los items con nombres que empiezan con * ya están filtrados
// ✅ Puedes usar data.data directamente sin filtrar
```

### Ejemplo: Obtener ventas del día
```javascript
const today = '2025-12-15';
const response = await fetch(
  `https://tu-api.com/api/direct/sales/totals?from=${today}&to=${today}&groupBy=day`,
  { headers }
);
const data = await response.json();

console.log(data);
// {
//   success: true,
//   data: [
//     { date: '2025-12-15', total: 2500000, count: 45 }
//   ]
// }
```

### Ejemplo: Dashboard completo
```javascript
const response = await fetch(
  'https://tu-api.com/api/analytics/dashboard?start_date=2025-12-01&end_date=2025-12-15',
  { headers }
);
const data = await response.json();

console.log(data);
// {
//   success: true,
//   data: {
//     peak_hours: {...},
//     top_customers: {...},
//     top_sellers: {...},
//     customer_retention: {...},
//     sales_trends: {...},
//     cross_selling: {...}
//   }
// }
```

---

## 🎨 UI Sugerida

### Vista Admin
```
┌──────────────────────────────────┐
│  📊 DASHBOARD ADMIN               │
├──────────────────────────────────┤
│                                   │
│  🔹 Cierre de Caja                │
│  🔹 Ventas Mensuales              │
│                                   │
│  ┌─────────────┐  ┌────────────┐ │
│  │ Estadísticas│  │Estadísticas│ │
│  │ AVANZADAS ⚡│  │ ESTÁNDAR 📊│ │
│  └─────────────┘  └────────────┘ │
└──────────────────────────────────┘
```

### Vista Sales
```
┌──────────────────────────────────┐
│  💼 DASHBOARD VENTAS              │
├──────────────────────────────────┤
│                                   │
│  🔹 Cierre de Caja                │
│  🔹 Ventas Mensuales              │
│                                   │
└──────────────────────────────────┘
```

---

## ⚠️ Manejo de Errores

```javascript
try {
  const response = await fetch(endpoint, { headers });

  if (!response.ok) {
    const error = await response.json();

    switch (response.status) {
      case 401: // Token inválido
        redirectToLogin();
        break;
      case 403: // Sin permisos
        alert('No tienes permisos para ver esto');
        break;
      case 400: // Parámetros inválidos
        alert(`Error: ${error.error}`);
        break;
      case 502: // Error de Alegra
        alert('Error conectando con Alegra');
        break;
    }
  }

  return await response.json();
} catch (error) {
  console.error('Error de red:', error);
  alert('Error de conexión');
}
```

---

## ✅ Checklist

### Admin debe poder:
- [ ] Ver y realizar cierre de caja
- [ ] Ver ventas mensuales
- [ ] Acceder a Estadísticas Avanzadas:
  - [ ] Ver inventario completo
  - [ ] Ver totales de ventas
  - [ ] Ver documentos detallados
- [ ] Acceder a Estadísticas Estándar:
  - [ ] Dashboard completo
  - [ ] Horas pico
  - [ ] Top clientes
  - [ ] Top vendedoras
  - [ ] Retención
  - [ ] Tendencias
  - [ ] Cross-selling

### Sales debe poder:
- [ ] Ver y realizar cierre de caja
- [ ] Ver ventas mensuales
- [ ] NO ver estadísticas (ni avanzadas ni estándar)

---

## 🔗 Links Útiles

- **Guía completa:** `FRONTEND_INTEGRATION_GUIDE.md`
- **Swagger docs:** `https://tu-api.com/api/docs`
- **Código fuente backend:** `app/routes/`

---

## 🆘 ¿Problemas?

1. **401 Unauthorized** → Verifica el token JWT
2. **403 Forbidden** → El usuario no tiene el rol necesario
3. **400 Bad Request** → Revisa los parámetros de la petición
4. **502 Bad Gateway** → Error en Alegra, intenta más tarde

---

**🎯 Lo más importante:**
- Todas las peticiones necesitan `Authorization: Bearer {token}`
- Admin ve todo, Sales solo cierre y ventas mensuales
- Usa `/api/direct/*` para estadísticas avanzadas (rápidas)
- Usa `/api/analytics/*` para estadísticas estándar (análisis)
