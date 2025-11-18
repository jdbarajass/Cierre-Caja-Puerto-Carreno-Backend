# Cambios en la API - Actualización para Frontend

## 🚨 CAMBIOS CRÍTICOS QUE REQUIEREN ACTUALIZACIÓN DEL FRONTEND

### 1. Cambio en las URLs de los Endpoints (BREAKING CHANGE)

**IMPORTANTE:** Todos los endpoints del blueprint de cierre de caja ahora tienen el prefijo `/api/`

#### Antes:
```
POST /sum_payments
```

#### Ahora:
```
POST /api/sum_payments
```

**Acción requerida:**
- Actualizar todas las llamadas al endpoint de cierre de caja
- Cambiar la URL base de `/sum_payments` a `/api/sum_payments`

#### Ejemplo de actualización en el código del frontend:

**Antes:**
```javascript
const response = await fetch('https://tu-api.com/sum_payments', {
  method: 'POST',
  headers: {
    'Content-Type': 'application/json'
  },
  body: JSON.stringify(datos)
});
```

**Ahora:**
```javascript
const response = await fetch('https://tu-api.com/api/sum_payments', {
  method: 'POST',
  headers: {
    'Content-Type': 'application/json'
  },
  body: JSON.stringify(datos)
});
```

---

## ✨ NUEVO ENDPOINT DISPONIBLE

### 2. Endpoint de Ventas Mensuales

Se agregó un nuevo endpoint para consultar el resumen de ventas del mes.

**Endpoint:** `GET /api/monthly_sales`

**Query Parameters (opcionales):**
- `start_date` (string): Fecha de inicio en formato YYYY-MM-DD. Si no se proporciona, usa el día 1 del mes actual
- `end_date` (string): Fecha de fin en formato YYYY-MM-DD. Si no se proporciona, usa la fecha actual

**Ejemplos de uso:**

```javascript
// Consultar ventas del mes actual (desde el día 1 hasta hoy)
const response = await fetch('https://tu-api.com/api/monthly_sales', {
  method: 'GET',
  headers: {
    'Content-Type': 'application/json'
  }
});

// Consultar ventas de un rango específico
const response = await fetch('https://tu-api.com/api/monthly_sales?start_date=2025-11-01&end_date=2025-11-16', {
  method: 'GET',
  headers: {
    'Content-Type': 'application/json'
  }
});
```

**Respuesta exitosa (200):**
```json
{
  "success": true,
  "server_timestamp": "2025-11-16 15:30:45",
  "timezone": "America/Bogota",
  "date_range": {
    "start": "2025-11-01",
    "end": "2025-11-16"
  },
  "total_vendido": {
    "label": "TOTAL VENDIDO EN EL PERIODO",
    "total": 15750000,
    "formatted": "$15.750.000 COP"
  },
  "cantidad_facturas": 145,
  "payment_methods": {
    "credit-card": {
      "label": "Tarjeta de Crédito",
      "total": 8500000,
      "formatted": "$8.500.000 COP"
    },
    "debit-card": {
      "label": "Tarjeta Débito",
      "total": 4250000,
      "formatted": "$4.250.000 COP"
    },
    "transfer": {
      "label": "Transferencia",
      "total": 2000000,
      "formatted": "$2.000.000 COP"
    },
    "cash": {
      "label": "Efectivo",
      "total": 1000000,
      "formatted": "$1.000.000 COP"
    }
  },
  "username_used": "tu-usuario@alegra.com"
}
```

**Respuesta de error (502 - Error de conexión con Alegra):**
```json
{
  "success": false,
  "error": "Error al conectar con Alegra",
  "details": "mensaje de error detallado",
  "server_timestamp": "2025-11-16 15:30:45",
  "timezone": "America/Bogota"
}
```

**Respuesta de error (500 - Error del servidor):**
```json
{
  "success": false,
  "error": "Error inesperado al procesar la solicitud",
  "details": "mensaje de error detallado",
  "server_timestamp": "2025-11-16 15:30:45",
  "timezone": "America/Bogota"
}
```

---

## ℹ️ CAMBIOS QUE NO AFECTAN AL FRONTEND (Solo informativos)

### 3. Eliminación de validación de 7 días

**Antes:** El endpoint `/sum_payments` rechazaba cierres de caja con fechas mayores a 7 días en el pasado.

**Ahora:** Esta validación se eliminó, permitiendo hacer cierres de caja de fechas más antiguas.

**Impacto:** El frontend ya no recibirá errores por intentar cerrar cajas antiguas. Esto solo hace la API más permisiva.

---

### 4. Mejoras en CORS

Se mejoró la configuración de CORS para soportar:
- Más métodos HTTP (GET, POST, PUT, DELETE, OPTIONS, PATCH)
- Más headers permitidos
- Soporte para credenciales (cookies/auth)

**Impacto:** El frontend tendrá mejor compatibilidad y menos problemas de CORS, pero no requiere cambios.

---

### 5. Corrección en el filtrado de fechas (Backend interno)

Se corrigió un bug en la API donde el filtrado por rango de fechas solo consideraba la primera fecha. Ahora el filtrado es preciso.

**Impacto:** Las respuestas del endpoint `/api/monthly_sales` ahora serán precisas y mostrarán el total correcto del período solicitado. No requiere cambios en el frontend, solo mejora la precisión de los datos.

---

## 📋 CHECKLIST DE ACTUALIZACIÓN DEL FRONTEND

- [ ] Actualizar URL de `/sum_payments` a `/api/sum_payments`
- [ ] Probar que el cierre de caja siga funcionando correctamente
- [ ] (Opcional) Implementar llamada al nuevo endpoint `/api/monthly_sales` para mostrar ventas del mes
- [ ] (Opcional) Crear UI para mostrar el resumen de ventas mensuales
- [ ] Verificar que el manejo de errores siga funcionando correctamente

---

## 🔧 CÓDIGO DE EJEMPLO COMPLETO PARA EL FRONTEND

### Actualizar endpoint de cierre de caja:

```javascript
// Constantes de configuración
const API_BASE_URL = 'https://tu-api.com/api'; // ⚠️ Agregar /api al final

// Función para hacer cierre de caja
async function hacerCierreCaja(datosCierre) {
  try {
    const response = await fetch(`${API_BASE_URL}/sum_payments`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify(datosCierre)
    });

    if (!response.ok) {
      const error = await response.json();
      throw new Error(error.error || 'Error al hacer cierre de caja');
    }

    const data = await response.json();
    return data;
  } catch (error) {
    console.error('Error en cierre de caja:', error);
    throw error;
  }
}
```

### Nuevo: Consultar ventas mensuales:

```javascript
// Función para obtener ventas del mes
async function obtenerVentasMensuales(startDate = null, endDate = null) {
  try {
    let url = `${API_BASE_URL}/monthly_sales`;

    // Agregar parámetros de fecha si se proporcionan
    const params = new URLSearchParams();
    if (startDate) params.append('start_date', startDate);
    if (endDate) params.append('end_date', endDate);

    if (params.toString()) {
      url += `?${params.toString()}`;
    }

    const response = await fetch(url, {
      method: 'GET',
      headers: {
        'Content-Type': 'application/json',
      }
    });

    if (!response.ok) {
      const error = await response.json();
      throw new Error(error.error || 'Error al consultar ventas');
    }

    const data = await response.json();
    return data;
  } catch (error) {
    console.error('Error al obtener ventas mensuales:', error);
    throw error;
  }
}

// Ejemplos de uso:

// Obtener ventas del mes actual (del día 1 hasta hoy)
const ventasMesActual = await obtenerVentasMensuales();

// Obtener ventas de un rango específico
const ventasRango = await obtenerVentasMensuales('2025-11-01', '2025-11-16');

// Mostrar los datos
console.log('Total vendido:', ventasMesActual.total_vendido.formatted);
console.log('Cantidad de facturas:', ventasMesActual.cantidad_facturas);
console.log('Desglose por método de pago:', ventasMesActual.payment_methods);
```

### Componente React de ejemplo (opcional):

```jsx
import { useState, useEffect } from 'react';

function VentasMensuales() {
  const [ventas, setVentas] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  useEffect(() => {
    async function cargarVentas() {
      try {
        setLoading(true);
        const response = await fetch('https://tu-api.com/api/monthly_sales');

        if (!response.ok) {
          throw new Error('Error al cargar ventas');
        }

        const data = await response.json();
        setVentas(data);
      } catch (err) {
        setError(err.message);
      } finally {
        setLoading(false);
      }
    }

    cargarVentas();
  }, []);

  if (loading) return <div>Cargando ventas...</div>;
  if (error) return <div>Error: {error}</div>;
  if (!ventas) return null;

  return (
    <div className="ventas-mensuales">
      <h2>Ventas del Mes</h2>
      <p>Período: {ventas.date_range.start} - {ventas.date_range.end}</p>

      <div className="total">
        <h3>{ventas.total_vendido.label}</h3>
        <p className="monto">{ventas.total_vendido.formatted}</p>
        <p>Facturas: {ventas.cantidad_facturas}</p>
      </div>

      <div className="metodos-pago">
        <h4>Desglose por Método de Pago</h4>
        {Object.entries(ventas.payment_methods).map(([key, method]) => (
          <div key={key} className="metodo">
            <span>{method.label}:</span>
            <span>{method.formatted}</span>
          </div>
        ))}
      </div>
    </div>
  );
}

export default VentasMensuales;
```

---

## 📞 SOPORTE

Si tienes dudas sobre estos cambios, consulta:
- Repositorio del backend: [cierre-caja-api]
- Documentación de la API en `/api/docs` (si está disponible)

---

**Fecha de actualización:** 2025-11-16
**Versión de la API:** Commits a456a81 - 6aca893
