# 📚 Documentación Completa de API para Frontend

**Backend URL Base:** `http://localhost:5000`

---

## 🎯 IMPORTANTE: URLs Correctas de los Endpoints

### ❌ URLS INCORRECTAS (NO USAR):
```
http://localhost:5000/sum_payments       ❌ INCORRECTO
http://localhost:5000/monthly_sales      ❌ INCORRECTO
http://localhost:5000/login              ❌ INCORRECTO
```

### ✅ URLS CORRECTAS (USAR):
```
http://localhost:5000/auth/login         ✅ CORRECTO (Login)
http://localhost:5000/auth/verify        ✅ CORRECTO (Verificar token)
http://localhost:5000/api/sum_payments   ✅ CORRECTO (Cierre de caja)
http://localhost:5000/api/monthly_sales  ✅ CORRECTO (Ventas mensuales)
http://localhost:5000/health             ✅ CORRECTO (Health check)
```

---

## 📋 Tabla Resumen de Endpoints

| Endpoint | Método | URL Completa | Requiere Auth | Descripción |
|----------|--------|--------------|---------------|-------------|
| Login | `POST` | `/auth/login` | ❌ No | Autenticar usuario y obtener token JWT |
| Verificar Token | `GET` | `/auth/verify` | ✅ Sí | Validar si el token es válido |
| Health Check | `GET` | `/health` | ❌ No | Verificar estado del servidor |
| Cierre de Caja | `POST` | `/api/sum_payments` | ✅ Sí | Procesar cierre de caja diario |
| Ventas Mensuales | `GET` | `/api/monthly_sales` | ✅ Sí | Obtener resumen de ventas del mes |

---

## 🔐 1. AUTENTICACIÓN - `/auth/login`

### Descripción
Autentica al usuario con email y password, retorna un token JWT para usar en peticiones protegidas.

### URL
```
POST http://localhost:5000/auth/login
```

### Headers
```javascript
{
  "Content-Type": "application/json"
}
```

### Body (JSON)
```json
{
  "email": "ventaspuertocarreno@gmail.com",
  "password": "VentasCarreno2025.*"
}
```

### Respuesta Exitosa (200)
```json
{
  "success": true,
  "token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJ1c2VySWQiOjEsImVtYWlsIjoidmVudGFzcHVlcnRvY2FycmVub0BnbWFpbC5jb20iLCJyb2xlIjoiYWRtaW4iLCJleHAiOjE3MzI0OTg0MTZ9.xyz",
  "user": {
    "email": "ventaspuertocarreno@gmail.com",
    "name": "Usuario Ventas Puerto Carreño",
    "role": "admin"
  }
}
```

### Errores Posibles
```json
// 400 - Datos inválidos
{
  "success": false,
  "message": "Email y password son requeridos"
}

// 401 - Credenciales incorrectas
{
  "success": false,
  "message": "Credenciales inválidas"
}

// 403 - Cuenta bloqueada
{
  "success": false,
  "message": "Cuenta bloqueada por múltiples intentos fallidos. Intente de nuevo en 15 minutos.",
  "locked_until": "2025-11-21T00:45:30.123456"
}
```

### Ejemplo con Axios
```javascript
// Login y guardar token
async function login(email, password) {
  try {
    const response = await axios.post('http://localhost:5000/auth/login', {
      email,
      password
    }, {
      headers: {
        'Content-Type': 'application/json'
      }
    });

    // Guardar token en localStorage
    localStorage.setItem('token', response.data.token);
    localStorage.setItem('user', JSON.stringify(response.data.user));

    return response.data;
  } catch (error) {
    console.error('Error en login:', error.response?.data);
    throw error;
  }
}
```

### Ejemplo con Fetch
```javascript
async function login(email, password) {
  const response = await fetch('http://localhost:5000/auth/login', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json'
    },
    body: JSON.stringify({ email, password })
  });

  const data = await response.json();

  if (!response.ok) {
    throw new Error(data.message || 'Error en login');
  }

  // Guardar token
  localStorage.setItem('token', data.token);
  return data;
}
```

---

## 🔍 2. VERIFICAR TOKEN - `/auth/verify`

### Descripción
Verifica si un token JWT es válido y retorna información del usuario.

### URL
```
GET http://localhost:5000/auth/verify
```

### Headers
```javascript
{
  "Authorization": "Bearer <token>"
}
```

### Respuesta Exitosa (200)
```json
{
  "success": true,
  "message": "Token válido",
  "user": {
    "userId": 1,
    "email": "ventaspuertocarreno@gmail.com",
    "role": "admin"
  }
}
```

### Errores Posibles
```json
// 401 - Token no proporcionado
{
  "success": false,
  "message": "Token no proporcionado"
}

// 401 - Token expirado
{
  "success": false,
  "message": "Token expirado. Por favor inicie sesión nuevamente."
}

// 401 - Token inválido
{
  "success": false,
  "message": "Token inválido"
}
```

### Ejemplo con Axios
```javascript
async function verifyToken() {
  const token = localStorage.getItem('token');

  const response = await axios.get('http://localhost:5000/auth/verify', {
    headers: {
      'Authorization': `Bearer ${token}`
    }
  });

  return response.data;
}
```

---

## 🏥 3. HEALTH CHECK - `/health`

### Descripción
Verifica el estado del servidor y la conexión con Alegra.

### URL
```
GET http://localhost:5000/health
```

### Headers
```
No requiere headers
```

### Respuesta Exitosa (200)
```json
{
  "status": "healthy",
  "service": "cierre-caja-api",
  "version": "2.0.0",
  "alegra": "connected"
}
```

### Ejemplo con Axios
```javascript
async function checkHealth() {
  const response = await axios.get('http://localhost:5000/health');
  return response.data;
}
```

---

## 💰 4. CIERRE DE CAJA - `/api/sum_payments`

### Descripción
Procesa un cierre de caja diario, calcula totales, consulta ventas en Alegra y valida diferencias.

### URL
```
POST http://localhost:5000/api/sum_payments
```

### Headers
```javascript
{
  "Content-Type": "application/json",
  "Authorization": "Bearer <token>"
}
```

### Body (JSON)
```json
{
  "date": "2025-11-20",
  "timezone": "America/Bogota",
  "utc_offset": -5,
  "request_timestamp": "2025-11-20T19:30:00-05:00",
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
      "metodo": "efectivo",
      "monto": 13500
    },
    {
      "metodo": "datafono",
      "monto": 0
    }
  ],
  "metodos_pago": {
    "efectivo": 1500000,
    "datafono": 500000,
    "transferencias": 300000,
    "nequi": 100000,
    "daviplata": 50000,
    "qr": 25000
  },
  "gastos_operativos": 0,
  "prestamos": 0
}
```

### Campos del Body

| Campo | Tipo | Requerido | Descripción |
|-------|------|-----------|-------------|
| `date` | string | ✅ Sí | Fecha del cierre (YYYY-MM-DD) |
| `timezone` | string | ❌ No | Zona horaria (default: America/Bogota) |
| `utc_offset` | number | ❌ No | Offset UTC en horas |
| `request_timestamp` | string | ❌ No | Timestamp de la petición |
| `coins` | object | ✅ Sí | Cantidad de monedas por denominación |
| `bills` | object | ✅ Sí | Cantidad de billetes por denominación |
| `excedentes` | array | ❌ No | Lista de excedentes por método |
| `metodos_pago` | object | ❌ No | Totales esperados por método de pago |
| `gastos_operativos` | number | ❌ No | Gastos operativos del día |
| `prestamos` | number | ❌ No | Préstamos realizados |

### Respuesta Exitosa (200)
```json
{
  "success": true,
  "request_datetime": "2025-11-20T19:30:00",
  "request_date": "2025-11-20",
  "request_time": "19:30:00",
  "request_tz": "America/Bogota",
  "server_timestamp": "2025-11-21T00:30:00",
  "timezone": "America/Bogota",
  "date_requested": "2025-11-20",
  "username_used": "koaj.puertocarreno@gmail.com",
  "cash_count": {
    "base": {
      "total_base": 450000,
      "total_base_formatted": "$450.000",
      "estado_base": "completa",
      "mensaje_base": "Base completa"
    },
    "totals": {
      "total_monedas": 9200,
      "total_billetes": 1532000,
      "total_general": 1541200,
      "total_general_formatted": "$1.541.200"
    },
    "consignar": {
      "efectivo_para_consignar_final": 1077700,
      "efectivo_para_consignar_final_formatted": "$1.077.700"
    },
    "adjustments": {
      "excedente": 13500,
      "excedente_formatted": "$13.500",
      "gastos_operativos": 0,
      "prestamos": 0
    }
  },
  "alegra": {
    "date_requested": "2025-11-20",
    "username_used": "koaj.puertocarreno@gmail.com",
    "results": {
      "cash": {
        "label": "Efectivo",
        "total": 1500000,
        "formatted": "$1.500.000"
      },
      "debit-card": {
        "label": "Tarjeta débito",
        "total": 500000,
        "formatted": "$500.000"
      },
      "transfer": {
        "label": "Transferencia",
        "total": 300000,
        "formatted": "$300.000"
      }
    },
    "total_sale": {
      "label": "TOTAL VENTA DEL DÍA",
      "total": 2300000,
      "formatted": "$2.300.000"
    }
  },
  "validation": {
    "validation_status": "ok",
    "mensaje_validacion": "Cierre validado correctamente"
  }
}
```

### Errores Posibles
```json
// 400 - Validación fallida
{
  "success": false,
  "error": "Errores de validación: date: field required"
}

// 401 - No autenticado
{
  "success": false,
  "message": "Token no proporcionado"
}

// 502 - Error con Alegra
{
  "success": false,
  "cash_count": { /* datos del conteo */ },
  "alegra": {
    "error": "Error al conectar con Alegra"
  }
}
```

### Ejemplo con Axios
```javascript
async function submitCashClosing(cierreData) {
  const token = localStorage.getItem('token');

  const response = await axios.post(
    'http://localhost:5000/api/sum_payments',
    cierreData,
    {
      headers: {
        'Content-Type': 'application/json',
        'Authorization': `Bearer ${token}`
      }
    }
  );

  return response.data;
}
```

---

## 📊 5. VENTAS MENSUALES - `/api/monthly_sales`

### Descripción
Obtiene el resumen de ventas de un período específico, consultando todas las facturas de Alegra en ese rango.

### URL
```
GET http://localhost:5000/api/monthly_sales?start_date=2025-11-01&end_date=2025-11-20
```

### Headers
```javascript
{
  "Authorization": "Bearer <token>"
}
```

### Query Parameters

| Parámetro | Tipo | Requerido | Descripción |
|-----------|------|-----------|-------------|
| `start_date` | string | ❌ No | Fecha de inicio (YYYY-MM-DD). Default: día 1 del mes actual |
| `end_date` | string | ❌ No | Fecha de fin (YYYY-MM-DD). Default: fecha actual |

### ⚠️ IMPORTANTE: Timeout
Esta petición puede tardar **1-3 minutos** dependiendo de la cantidad de facturas.

**DEBES configurar un timeout de al menos 180 segundos (3 minutos):**

```javascript
// Con Axios
axios.get(url, {
  timeout: 180000  // 3 minutos
});

// Con Fetch
const controller = new AbortController();
const timeoutId = setTimeout(() => controller.abort(), 180000);

fetch(url, { signal: controller.signal })
  .finally(() => clearTimeout(timeoutId));
```

### Respuesta Exitosa (200)
```json
{
  "success": true,
  "server_timestamp": "2025-11-21T00:30:00",
  "timezone": "America/Bogota",
  "date_range": {
    "start": "2025-11-01",
    "end": "2025-11-20"
  },
  "total_vendido": {
    "label": "TOTAL VENDIDO EN EL PERIODO",
    "total": 28156210,
    "formatted": "$28.156.210"
  },
  "cantidad_facturas": 248,
  "payment_methods": {
    "credit-card": {
      "label": "Tarjeta crédito",
      "total": 585000,
      "formatted": "$585.000"
    },
    "debit-card": {
      "label": "Tarjeta débito",
      "total": 2986300,
      "formatted": "$2.986.300"
    },
    "transfer": {
      "label": "Transferencia",
      "total": 9567860,
      "formatted": "$9.567.860"
    },
    "cash": {
      "label": "Efectivo",
      "total": 15017050,
      "formatted": "$15.017.050"
    }
  },
  "username_used": "koaj.puertocarreno@gmail.com"
}
```

### Errores Posibles
```json
// 401 - No autenticado
{
  "success": false,
  "message": "Token no proporcionado"
}

// 502 - Error con Alegra
{
  "success": false,
  "error": "Error al conectar con Alegra",
  "details": "Error de conexión..."
}
```

### Ejemplo con Axios
```javascript
async function getMonthlySales(startDate, endDate) {
  const token = localStorage.getItem('token');

  const response = await axios.get('http://localhost:5000/api/monthly_sales', {
    params: {
      start_date: startDate,
      end_date: endDate
    },
    headers: {
      'Authorization': `Bearer ${token}`
    },
    timeout: 180000  // ⚠️ IMPORTANTE: 3 minutos de timeout
  });

  return response.data;
}

// Uso
const ventas = await getMonthlySales('2025-11-01', '2025-11-20');
console.log(ventas.total_vendido.formatted); // "$28.156.210"
```

---

## 🛠️ Configuración Recomendada del Cliente HTTP

### Opción 1: Crear una instancia de Axios configurada

```javascript
// src/services/api.js
import axios from 'axios';

const API_BASE_URL = 'http://localhost:5000';

// Crear instancia de Axios
const apiClient = axios.create({
  baseURL: API_BASE_URL,
  timeout: 30000, // 30 segundos por defecto
  headers: {
    'Content-Type': 'application/json'
  }
});

// Interceptor para agregar token automáticamente
apiClient.interceptors.request.use(
  (config) => {
    const token = localStorage.getItem('token');
    if (token) {
      config.headers.Authorization = `Bearer ${token}`;
    }
    return config;
  },
  (error) => {
    return Promise.reject(error);
  }
);

// Interceptor para manejar errores de autenticación
apiClient.interceptors.response.use(
  (response) => response,
  (error) => {
    if (error.response?.status === 401) {
      // Token expirado o inválido
      localStorage.removeItem('token');
      localStorage.removeItem('user');
      window.location.href = '/login';
    }
    return Promise.reject(error);
  }
);

export default apiClient;
```

### Opción 2: Crear servicios específicos por funcionalidad

```javascript
// src/services/authService.js
import apiClient from './api';

export const authService = {
  async login(email, password) {
    const response = await apiClient.post('/auth/login', {
      email,
      password
    });

    // Guardar token
    localStorage.setItem('token', response.data.token);
    localStorage.setItem('user', JSON.stringify(response.data.user));

    return response.data;
  },

  async verifyToken() {
    const response = await apiClient.get('/auth/verify');
    return response.data;
  },

  logout() {
    localStorage.removeItem('token');
    localStorage.removeItem('user');
  }
};
```

```javascript
// src/services/cashService.js
import apiClient from './api';

export const cashService = {
  async submitCashClosing(data) {
    const response = await apiClient.post('/api/sum_payments', data);
    return response.data;
  },

  async getMonthlySales(startDate, endDate) {
    const response = await apiClient.get('/api/monthly_sales', {
      params: {
        start_date: startDate,
        end_date: endDate
      },
      timeout: 180000 // ⚠️ 3 minutos para esta petición específica
    });
    return response.data;
  }
};
```

---

## 📝 Checklist de Integración

### 1. Actualizar URLs
- [ ] Cambiar `/sum_payments` → `/api/sum_payments`
- [ ] Cambiar `/monthly_sales` → `/api/monthly_sales`
- [ ] Cambiar `/login` → `/auth/login`
- [ ] Verificar que todas las URLs incluyan el prefijo correcto

### 2. Configurar Autenticación
- [ ] Guardar token JWT después del login
- [ ] Incluir header `Authorization: Bearer <token>` en peticiones protegidas
- [ ] Manejar errores 401 (token expirado/inválido)
- [ ] Implementar logout para limpiar token

### 3. Configurar Timeouts
- [ ] `/api/monthly_sales`: timeout de 180000ms (3 minutos)
- [ ] Otras peticiones: timeout de 30000ms (30 segundos)

### 4. Manejo de Errores
- [ ] Capturar y mostrar errores de validación (400)
- [ ] Redirigir a login en errores 401
- [ ] Mostrar mensaje de cuenta bloqueada (403)
- [ ] Manejar errores de Alegra (502)

### 5. Testing
- [ ] Probar login con credenciales correctas
- [ ] Probar login con credenciales incorrectas
- [ ] Probar cierre de caja con token válido
- [ ] Probar ventas mensuales con diferentes rangos
- [ ] Verificar que el timeout de 3 minutos funciona

---

## 🔍 Debugging

### Ver peticiones en Network Tab

1. Abre DevTools (F12)
2. Ve a la pestaña **Network**
3. Filtra por **Fetch/XHR**
4. Haz una petición
5. Verifica:
   - ✅ URL correcta (debe incluir `/api` o `/auth`)
   - ✅ Headers correctos (Authorization con Bearer token)
   - ✅ Status code de la respuesta
   - ✅ Tiempo de respuesta (especialmente en monthly_sales)

### Errores Comunes

| Error | Causa | Solución |
|-------|-------|----------|
| CORS Error | URL incorrecta o sin prefijo | Verificar que use `/api/` o `/auth/` |
| 401 Unauthorized | Token no enviado o inválido | Verificar header Authorization |
| 400 Bad Request | Datos de body incorrectos | Revisar formato JSON y campos requeridos |
| Timeout | Petición tarda más del timeout | Aumentar timeout a 180000ms en monthly_sales |

---

## 🎯 Ejemplo Completo de Flujo de Autenticación

```javascript
// 1. Login
const loginData = await authService.login(
  'ventaspuertocarreno@gmail.com',
  'VentasCarreno2025.*'
);
console.log('Token:', loginData.token);
console.log('Usuario:', loginData.user);

// 2. Verificar token (opcional, se hace automáticamente en cada petición)
const verification = await authService.verifyToken();
console.log('Token válido:', verification.success);

// 3. Hacer petición protegida (cierre de caja)
const cierre = await cashService.submitCashClosing({
  date: '2025-11-20',
  coins: { /* ... */ },
  bills: { /* ... */ }
});
console.log('Cierre procesado:', cierre.success);

// 4. Consultar ventas mensuales
const ventas = await cashService.getMonthlySales(
  '2025-11-01',
  '2025-11-20'
);
console.log('Total vendido:', ventas.total_vendido.formatted);
```

---

## 🚀 Variables de Entorno Recomendadas

```env
# .env.local (desarrollo)
VITE_API_URL=http://localhost:5000
VITE_API_TIMEOUT=30000
VITE_API_MONTHLY_SALES_TIMEOUT=180000

# .env.production (producción)
VITE_API_URL=https://cierre-caja-api.onrender.com
VITE_API_TIMEOUT=30000
VITE_API_MONTHLY_SALES_TIMEOUT=180000
```

```javascript
// Usar en el código
const API_BASE_URL = import.meta.env.VITE_API_URL || 'http://localhost:5000';
```

---

**✅ Con esta documentación el frontend debería poder consumir correctamente todos los endpoints del backend.**
