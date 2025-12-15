# 📊 API de Estadísticas - KOAJ Puerto Carreño

**Versión:** 2.0.1
**Última actualización:** 2025-12-15

---

## 🚀 Inicio Rápido

### Dos Secciones de Estadísticas:

1. **📊 Estadísticas AVANZADAS** → APIs directas de Alegra (rápidas y completas)
2. **📈 Estadísticas ESTÁNDAR** → APIs documentadas de Alegra (análisis procesados)

**Roles:**
- **Admin:** Acceso completo (cierre, ventas, estadísticas avanzadas y estándar)
- **Sales:** Solo cierre de caja y ventas mensuales

---

## 🔑 Autenticación

Todas las peticiones requieren JWT token:

```javascript
const headers = {
  'Authorization': `Bearer ${token}`,
  'Content-Type': 'application/json'
};
```

---

## 📊 Estadísticas Avanzadas (Solo Admin)

### 1. Inventario
```bash
GET /api/direct/inventory/value-report?toDate=2025-12-15&limit=100&page=1
```

⚠️ **IMPORTANTE:** Filtra automáticamente items con nombres que empiezan con `*` (productos obsoletos).

**Respuesta:**
```json
{
  "success": true,
  "data": [...items válidos...],
  "metadata": {
    "page": 1,
    "limit": 100,
    "total_received": 150,    // Items de Alegra
    "total_filtered": 25,     // Items con * filtrados
    "total_returned": 125     // Items enviados
  }
}
```

### 2. Totales de Ventas
```bash
GET /api/direct/sales/totals?from=2025-12-01&to=2025-12-15&groupBy=day
```

### 3. Documentos de Ventas
```bash
GET /api/direct/sales/documents?from=2025-12-15&to=2025-12-15&limit=50
```

---

## 📈 Estadísticas Estándar (Solo Admin)

```bash
GET /api/analytics/dashboard           # Dashboard completo
GET /api/analytics/peak-hours          # Horas pico
GET /api/analytics/top-customers       # Top clientes
GET /api/analytics/top-sellers         # Top vendedoras
GET /api/analytics/customer-retention  # Retención
GET /api/analytics/sales-trends        # Tendencias
GET /api/analytics/cross-selling       # Cross-selling
```

---

## 🔹 Endpoints Comunes (Admin + Sales)

```bash
POST /api/sum_payments        # Cierre de caja
GET  /api/monthly_sales       # Ventas mensuales
```

---

## 💻 Ejemplo de Código

```javascript
// Obtener inventario (ya filtrado)
const response = await fetch(
  `${API_URL}/api/direct/inventory/value-report?limit=100`,
  { headers }
);
const data = await response.json();

// ✅ Usar directamente (sin filtrar)
setInventory(data.data);

// (Opcional) Mostrar estadísticas
console.log(`Items filtrados: ${data.metadata.total_filtered}`);
```

---

## ⚠️ Importante

1. **Filtrado automático:** El inventario NO incluye items con `*` en el nombre
2. **No filtrar en frontend:** El backend ya filtra los items obsoletos
3. **Metadata ampliada:** Incluye estadísticas del filtrado

---

## 📚 Documentación Adicional

- **`FRONTEND_QUICK_START.md`** - Guía rápida con ejemplos
- **`FRONTEND_INTEGRATION_GUIDE.md`** - Guía completa detallada
- **`TEST_ENDPOINTS.md`** - Comandos para testing
- **`ACTUALIZACION_INVENTARIO_FILTRADO.md`** - Detalles del filtrado

---

## 🧪 Testing Rápido

```bash
# 1. Login
curl -X POST "http://localhost:5000/auth/login" \
  -H "Content-Type: application/json" \
  -d '{"email":"user@example.com","password":"pass"}'

# 2. Guardar token
export TOKEN="token_recibido"

# 3. Probar inventario
curl -X GET "http://localhost:5000/api/direct/inventory/value-report?limit=10" \
  -H "Authorization: Bearer $TOKEN"
```

---

**🎯 El backend está 100% funcional y listo para integrarse.**
