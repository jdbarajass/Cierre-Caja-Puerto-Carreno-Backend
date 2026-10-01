# Documentación para Frontend - Análisis por Tallas

**Versión API:** 2.1.3
**Fecha:** 2025-11-28
**Para:** Equipo de Desarrollo Frontend
**De:** Equipo Backend

---

## 📢 Resumen de Cambios

Se han agregado **3 nuevos endpoints** para análisis de ventas por tallas y se ha **modificado la respuesta** del endpoint de reporte completo para incluir análisis por tallas.

### ⚠️ IMPORTANTE - Cambios en Respuestas Existentes

El endpoint `/api/products/analysis` ahora retorna **3 nuevas secciones** en su respuesta:
- `ventas_por_talla`
- `ventas_por_categoria_talla`
- `ventas_por_departamento_talla`

**Estos cambios son retrocompatibles** - las secciones existentes no han cambiado.

---

## 🆕 Nuevos Endpoints

### 1. Análisis Global por Talla

**Endpoint:** `GET /api/products/analysis/sizes`

**Descripción:** Obtiene el análisis de ventas agrupado por talla (XS, S, M, L, XL, 2-38, etc.)

**Headers:**
```http
Authorization: Bearer <token>
```

**Parámetros Query:**
| Parámetro | Tipo | Requerido | Descripción | Ejemplo |
|-----------|------|-----------|-------------|---------|
| `date` | string | No | Fecha específica (YYYY-MM-DD) | `2025-11-28` |
| `start_date` | string | No* | Fecha inicio del rango | `2025-11-01` |
| `end_date` | string | No* | Fecha fin del rango | `2025-11-30` |

*Si no se envía ningún parámetro, se usa la fecha actual.
*Si se usa rango, ambos `start_date` y `end_date` son requeridos.

**Ejemplo de Petición:**
```javascript
// Con fecha específica
fetch('http://10.28.168.57:5000/api/products/analysis/sizes?date=2025-11-28', {
  headers: {
    'Authorization': `Bearer ${token}`
  }
})

// Con rango de fechas
fetch('http://10.28.168.57:5000/api/products/analysis/sizes?start_date=2025-11-01&end_date=2025-11-30', {
  headers: {
    'Authorization': `Bearer ${token}`
  }
})
```

**Respuesta Exitosa (200):**
```json
{
  "success": true,
  "date_range": "2025-11-28",
  "data": [
    {
      "talla": "M",
      "cantidad": 150,
      "ingresos": 5250000,
      "porcentaje_participacion": 35.5,
      "cantidad_formatted": "150",
      "ingresos_formatted": "$ 5.250.000",
      "porcentaje_participacion_formatted": "35.50%"
    },
    {
      "talla": "L",
      "cantidad": 120,
      "ingresos": 4200000,
      "porcentaje_participacion": 28.0,
      "cantidad_formatted": "120",
      "ingresos_formatted": "$ 4.200.000",
      "porcentaje_participacion_formatted": "28.00%"
    },
    {
      "talla": "S",
      "cantidad": 80,
      "ingresos": 2800000,
      "porcentaje_participacion": 19.0,
      "cantidad_formatted": "80",
      "ingresos_formatted": "$ 2.800.000",
      "porcentaje_participacion_formatted": "19.00%"
    }
  ]
}
```

**Estructura de Datos:**
```typescript
interface TallaAnalisis {
  talla: string;                              // Talla: "XS", "S", "M", "L", "XL", "2", "4", "6"...
  cantidad: number;                           // Cantidad de unidades vendidas
  ingresos: number;                           // Ingresos totales en pesos
  porcentaje_participacion: number;           // % de participación sobre el total
  cantidad_formatted: string;                 // Cantidad formateada: "150"
  ingresos_formatted: string;                 // Ingresos formateados: "$ 5.250.000"
  porcentaje_participacion_formatted: string; // Porcentaje formateado: "35.50%"
}

interface SizeAnalysisResponse {
  success: boolean;
  date_range: string;       // "2025-11-28" o "2025-11-01 al 2025-11-30"
  data: TallaAnalisis[];    // Ordenado por cantidad (descendente)
}
```

---

### 2. Análisis por Categoría y Talla

**Endpoint:** `GET /api/products/analysis/category-sizes`

**Descripción:** Obtiene ventas agrupadas por categoría de producto (CAMISETA, JEAN, BLUSA, etc.) y desglosadas por talla dentro de cada categoría.

**Headers y Parámetros:** Iguales al endpoint anterior

**Ejemplo de Petición:**
```javascript
fetch('http://10.28.168.57:5000/api/products/analysis/category-sizes?date=2025-11-28', {
  headers: {
    'Authorization': `Bearer ${token}`
  }
})
```

**Respuesta Exitosa (200):**
```json
{
  "success": true,
  "date_range": "2025-11-28",
  "data": [
    {
      "categoria": "CAMISETA",
      "total_cantidad": 200,
      "total_ingresos": 7000000,
      "total_cantidad_formatted": "200",
      "total_ingresos_formatted": "$ 7.000.000",
      "tallas": [
        {
          "talla": "M",
          "cantidad": 80,
          "ingresos": 2800000,
          "porcentaje_participacion": 40.0,
          "cantidad_formatted": "80",
          "ingresos_formatted": "$ 2.800.000",
          "porcentaje_participacion_formatted": "40.00%"
        },
        {
          "talla": "L",
          "cantidad": 70,
          "ingresos": 2450000,
          "porcentaje_participacion": 35.0,
          "cantidad_formatted": "70",
          "ingresos_formatted": "$ 2.450.000",
          "porcentaje_participacion_formatted": "35.00%"
        }
      ]
    },
    {
      "categoria": "JEAN",
      "total_cantidad": 150,
      "total_ingresos": 12000000,
      "total_cantidad_formatted": "150",
      "total_ingresos_formatted": "$ 12.000.000",
      "tallas": [
        {
          "talla": "28",
          "cantidad": 45,
          "ingresos": 3600000,
          "porcentaje_participacion": 30.0,
          "cantidad_formatted": "45",
          "ingresos_formatted": "$ 3.600.000",
          "porcentaje_participacion_formatted": "30.00%"
        }
      ]
    }
  ]
}
```

**Estructura de Datos:**
```typescript
interface CategoriaConTallas {
  categoria: string;                  // "CAMISETA", "JEAN", "BLUSA", etc.
  total_cantidad: number;             // Total unidades de esta categoría
  total_ingresos: number;             // Total ingresos de esta categoría
  total_cantidad_formatted: string;   // Total cantidad formateado
  total_ingresos_formatted: string;   // Total ingresos formateado
  tallas: TallaAnalisis[];            // Desglose por talla (ordenado desc por cantidad)
}

interface CategorySizeAnalysisResponse {
  success: boolean;
  date_range: string;
  data: CategoriaConTallas[];  // Ordenado por total_cantidad (descendente)
}
```

---

### 3. Análisis por Departamento y Talla

**Endpoint:** `GET /api/products/analysis/department-sizes`

**Descripción:** Obtiene ventas agrupadas por departamento/género (HOMBRE, MUJER, NIÑO, NIÑA) y desglosadas por talla dentro de cada departamento.

**Headers y Parámetros:** Iguales a los endpoints anteriores

**Ejemplo de Petición:**
```javascript
fetch('http://10.28.168.57:5000/api/products/analysis/department-sizes?date=2025-11-28', {
  headers: {
    'Authorization': `Bearer ${token}`
  }
})
```

**Respuesta Exitosa (200):**
```json
{
  "success": true,
  "date_range": "2025-11-28",
  "data": [
    {
      "departamento": "MUJER",
      "total_cantidad": 350,
      "total_ingresos": 15000000,
      "total_cantidad_formatted": "350",
      "total_ingresos_formatted": "$ 15.000.000",
      "tallas": [
        {
          "talla": "M",
          "cantidad": 120,
          "ingresos": 5000000,
          "porcentaje_participacion": 33.3,
          "cantidad_formatted": "120",
          "ingresos_formatted": "$ 5.000.000",
          "porcentaje_participacion_formatted": "33.33%"
        },
        {
          "talla": "S",
          "cantidad": 100,
          "ingresos": 4200000,
          "porcentaje_participacion": 28.0,
          "cantidad_formatted": "100",
          "ingresos_formatted": "$ 4.200.000",
          "porcentaje_participacion_formatted": "28.00%"
        }
      ]
    },
    {
      "departamento": "HOMBRE",
      "total_cantidad": 280,
      "total_ingresos": 12000000,
      "total_cantidad_formatted": "280",
      "total_ingresos_formatted": "$ 12.000.000",
      "tallas": [
        {
          "talla": "L",
          "cantidad": 90,
          "ingresos": 4000000,
          "porcentaje_participacion": 32.1,
          "cantidad_formatted": "90",
          "ingresos_formatted": "$ 4.000.000",
          "porcentaje_participacion_formatted": "32.14%"
        }
      ]
    }
  ]
}
```

**Estructura de Datos:**
```typescript
interface DepartamentoConTallas {
  departamento: string;               // "HOMBRE", "MUJER", "NIÑO", "NIÑA"
  total_cantidad: number;             // Total unidades de este departamento
  total_ingresos: number;             // Total ingresos de este departamento
  total_cantidad_formatted: string;   // Total cantidad formateado
  total_ingresos_formatted: string;   // Total ingresos formateado
  tallas: TallaAnalisis[];            // Desglose por talla (ordenado desc por cantidad)
}

interface DepartmentSizeAnalysisResponse {
  success: boolean;
  date_range: string;
  data: DepartamentoConTallas[];  // Ordenado por total_cantidad (descendente)
}
```

---

## 🔄 Cambios en Endpoint Existente

### Reporte Completo (Modificado)

**Endpoint:** `GET /api/products/analysis`

**⚠️ CAMBIO IMPORTANTE:** Este endpoint ahora incluye **3 nuevas secciones** en su respuesta.

**Respuesta ANTES (v2.1.2):**
```json
{
  "success": true,
  "date_range": "2025-11-28",
  "data": {
    "resumen_ejecutivo": { ... },
    "top_10_productos": [ ... ],
    "top_10_productos_unificados": [ ... ],
    "todos_productos_unificados": [ ... ],
    "listado_completo": [ ... ],
    "metadata": { ... }
  }
}
```

**Respuesta AHORA (v2.1.3):**
```json
{
  "success": true,
  "date_range": "2025-11-28",
  "data": {
    "resumen_ejecutivo": { ... },
    "top_10_productos": [ ... ],
    "top_10_productos_unificados": [ ... ],
    "todos_productos_unificados": [ ... ],
    "listado_completo": [ ... ],

    // ✨ NUEVAS SECCIONES ✨
    "ventas_por_talla": [
      {
        "talla": "M",
        "cantidad": 150,
        "ingresos": 5250000,
        "porcentaje_participacion": 35.5,
        "cantidad_formatted": "150",
        "ingresos_formatted": "$ 5.250.000",
        "porcentaje_participacion_formatted": "35.50%"
      }
    ],
    "ventas_por_categoria_talla": [
      {
        "categoria": "CAMISETA",
        "total_cantidad": 200,
        "total_ingresos": 7000000,
        "total_cantidad_formatted": "200",
        "total_ingresos_formatted": "$ 7.000.000",
        "tallas": [ ... ]
      }
    ],
    "ventas_por_departamento_talla": [
      {
        "departamento": "MUJER",
        "total_cantidad": 350,
        "total_ingresos": 15000000,
        "total_cantidad_formatted": "350",
        "total_ingresos_formatted": "$ 15.000.000",
        "tallas": [ ... ]
      }
    ],

    "metadata": { ... }
  }
}
```

**Estructura TypeScript Actualizada:**
```typescript
interface ProductAnalysisCompleteResponse {
  success: boolean;
  date_range: string;
  data: {
    resumen_ejecutivo: ResumenEjecutivo;
    top_10_productos: Producto[];
    top_10_productos_unificados: ProductoUnificado[];
    todos_productos_unificados: ProductoUnificado[];
    listado_completo: Producto[];

    // ✨ NUEVAS PROPIEDADES ✨
    ventas_por_talla: TallaAnalisis[];
    ventas_por_categoria_talla: CategoriaConTallas[];
    ventas_por_departamento_talla: DepartamentoConTallas[];

    metadata: Metadata;
  };
}
```

---

## 📊 Manejo de Respuestas Vacías

Todos los endpoints pueden retornar arrays vacíos si no hay datos para el período solicitado:

```json
{
  "success": true,
  "date_range": "2025-11-28",
  "data": []
}
```

O en el caso del reporte completo:
```json
{
  "success": true,
  "date_range": "2025-11-28",
  "data": {
    "ventas_por_talla": [],
    "ventas_por_categoria_talla": [],
    "ventas_por_departamento_talla": []
  }
}
```

**Recomendación:** Siempre verificar que los arrays no estén vacíos antes de renderizar.

---

## 🎨 Notas sobre Tallas

### Tipos de Tallas que Puede Recibir el Frontend

1. **Tallas Alfabéticas:**
   - `"XS"`, `"S"`, `"M"`, `"L"`, `"XL"`
   - Usadas en: Camisetas, Polos, Blusas, Chaquetas, etc.

2. **Tallas Numéricas (van de 2 en 2):**
   - `"2"`, `"4"`, `"6"`, `"8"`, `"10"`, `"12"`, `"14"`, `"16"`, `"18"`, `"20"`, `"22"`, `"24"`, `"26"`, `"28"`, `"30"`, `"32"`, `"34"`, `"36"`, `"38"`
   - Usadas en: Jeans, Joggers, Pantalones

3. **Tallas Especiales:**
   - `"ÚNICA"` - Para productos de talla única
   - Rangos para niños (pueden aparecer): `"12-14"`, `"10-12"`, `"8-10"`, `"6-8"`

### Categorías de Productos

Las categorías que puede retornar el backend incluyen (no limitadas a):
- `"CAMISETA"`
- `"JEAN"`
- `"BLUSA"`
- `"POLO"`
- `"JOGGER"`
- `"PANTALON"`
- `"SHORT"`
- `"VESTIDO"`
- `"FALDA"`
- `"CHAQUETA"`
- Y más...

### Departamentos/Géneros

Los departamentos son fijos:
- `"HOMBRE"`
- `"MUJER"`
- `"NIÑO"`
- `"NIÑA"`

---

## ❌ Manejo de Errores

### Errores Comunes

**1. Token Inválido o Expirado (401):**
```json
{
  "success": false,
  "error": "Token inválido o expirado"
}
```

**2. Formato de Fecha Inválido (400):**
```json
{
  "success": false,
  "error": "Formato de fecha inválido: ...",
  "details": "Use YYYY-MM-DD"
}
```

**3. Error de Conexión con Alegra (502):**
```json
{
  "success": false,
  "error": "Error de conexión con Alegra",
  "details": "..."
}
```

**4. Error Interno (500):**
```json
{
  "success": false,
  "error": "Error interno del servidor",
  "details": "..."
}
```

---

## 🔐 Autenticación

Todos los endpoints requieren autenticación mediante JWT token.

**Headers requeridos:**
```http
Authorization: Bearer <token>
```

El token se obtiene del endpoint de login:
```javascript
POST /auth/login
{
  "email": "usuario@ejemplo.com",
  "password": "contraseña"
}
```

---

## 📝 Ejemplos de Implementación

### Ejemplo en React (TypeScript)

```typescript
import { useState, useEffect } from 'react';

// Tipos
interface TallaAnalisis {
  talla: string;
  cantidad: number;
  ingresos: number;
  porcentaje_participacion: number;
  cantidad_formatted: string;
  ingresos_formatted: string;
  porcentaje_participacion_formatted: string;
}

interface SizeAnalysisResponse {
  success: boolean;
  date_range: string;
  data: TallaAnalisis[];
}

// Hook personalizado
function useSizeAnalysis(date: string, token: string) {
  const [data, setData] = useState<TallaAnalisis[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const fetchData = async () => {
      try {
        setLoading(true);
        const response = await fetch(
          `http://10.28.168.57:5000/api/products/analysis/sizes?date=${date}`,
          {
            headers: {
              'Authorization': `Bearer ${token}`
            }
          }
        );

        if (!response.ok) {
          throw new Error('Error al obtener datos');
        }

        const result: SizeAnalysisResponse = await response.json();
        setData(result.data);
      } catch (err) {
        setError(err instanceof Error ? err.message : 'Error desconocido');
      } finally {
        setLoading(false);
      }
    };

    fetchData();
  }, [date, token]);

  return { data, loading, error };
}

// Componente
function SizeAnalysisChart() {
  const token = localStorage.getItem('token') || '';
  const { data, loading, error } = useSizeAnalysis('2025-11-28', token);

  if (loading) return <div>Cargando...</div>;
  if (error) return <div>Error: {error}</div>;
  if (!data || data.length === 0) return <div>No hay datos disponibles</div>;

  return (
    <div>
      <h2>Análisis de Ventas por Talla</h2>
      <table>
        <thead>
          <tr>
            <th>Talla</th>
            <th>Cantidad</th>
            <th>Ingresos</th>
            <th>% Participación</th>
          </tr>
        </thead>
        <tbody>
          {data.map((item) => (
            <tr key={item.talla}>
              <td>{item.talla}</td>
              <td>{item.cantidad_formatted}</td>
              <td>{item.ingresos_formatted}</td>
              <td>{item.porcentaje_participacion_formatted}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
```

### Ejemplo en JavaScript Vanilla

```javascript
// Función para obtener análisis por talla
async function getSizeAnalysis(date, token) {
  try {
    const response = await fetch(
      `http://10.28.168.57:5000/api/products/analysis/sizes?date=${date}`,
      {
        headers: {
          'Authorization': `Bearer ${token}`
        }
      }
    );

    if (!response.ok) {
      throw new Error(`HTTP error! status: ${response.status}`);
    }

    const result = await response.json();

    if (!result.success) {
      throw new Error(result.error || 'Error desconocido');
    }

    return result.data;
  } catch (error) {
    console.error('Error al obtener análisis por talla:', error);
    throw error;
  }
}

// Uso
const token = localStorage.getItem('token');
getSizeAnalysis('2025-11-28', token)
  .then(data => {
    console.log('Análisis por talla:', data);
    // Renderizar datos...
  })
  .catch(error => {
    console.error('Error:', error);
  });
```

### Ejemplo de Gráfico con Chart.js

```javascript
async function renderSizeChart(date, token) {
  const data = await getSizeAnalysis(date, token);

  // Preparar datos para el gráfico
  const labels = data.map(item => item.talla);
  const quantities = data.map(item => item.cantidad);
  const revenues = data.map(item => item.ingresos);

  // Crear gráfico
  const ctx = document.getElementById('sizeChart').getContext('2d');
  new Chart(ctx, {
    type: 'bar',
    data: {
      labels: labels,
      datasets: [
        {
          label: 'Cantidad Vendida',
          data: quantities,
          backgroundColor: 'rgba(54, 162, 235, 0.5)',
          borderColor: 'rgba(54, 162, 235, 1)',
          borderWidth: 1
        },
        {
          label: 'Ingresos',
          data: revenues,
          backgroundColor: 'rgba(255, 99, 132, 0.5)',
          borderColor: 'rgba(255, 99, 132, 1)',
          borderWidth: 1,
          yAxisID: 'y-axis-2'
        }
      ]
    },
    options: {
      responsive: true,
      scales: {
        'y-axis-1': {
          type: 'linear',
          position: 'left',
          title: { display: true, text: 'Cantidad' }
        },
        'y-axis-2': {
          type: 'linear',
          position: 'right',
          title: { display: true, text: 'Ingresos (COP)' },
          grid: { drawOnChartArea: false }
        }
      }
    }
  });
}
```

---

## 🧪 Testing

### URLs de Testing
- **Servidor de Desarrollo:** `http://10.28.168.57:5000`
- **Health Check:** `http://10.28.168.57:5000/health`

### Credenciales de Prueba
```
Email: <correo de un usuario de la plataforma>
Password: <su contraseña>
```

### Fechas de Prueba con Datos
- `2025-11-28` - Tiene datos reales (22 facturas)
- Puedes usar cualquier fecha en formato `YYYY-MM-DD`

### Script de Prueba Rápida (cURL)

```bash
# 1. Login
curl -X POST http://10.28.168.57:5000/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email":"usuario@ejemplo.com","password":"TuContraseña123*"}'

# 2. Obtener análisis por talla (reemplaza <TOKEN> con el token del paso 1)
curl -X GET "http://10.28.168.57:5000/api/products/analysis/sizes?date=2025-11-28" \
  -H "Authorization: Bearer <TOKEN>"

# 3. Obtener análisis por categoría y talla
curl -X GET "http://10.28.168.57:5000/api/products/analysis/category-sizes?date=2025-11-28" \
  -H "Authorization: Bearer <TOKEN>"

# 4. Obtener análisis por departamento y talla
curl -X GET "http://10.28.168.57:5000/api/products/analysis/department-sizes?date=2025-11-28" \
  -H "Authorization: Bearer <TOKEN>"

# 5. Obtener reporte completo (con nuevas secciones)
curl -X GET "http://10.28.168.57:5000/api/products/analysis?date=2025-11-28" \
  -H "Authorization: Bearer <TOKEN>"
```

---

## 📋 Checklist de Implementación

### Para el Desarrollador Frontend:

- [ ] Actualizar interfaces TypeScript con nuevos tipos
- [ ] Verificar que el código existente maneje las nuevas propiedades del reporte completo
- [ ] Implementar UI para análisis global por talla
- [ ] Implementar UI para análisis por categoría y talla
- [ ] Implementar UI para análisis por departamento y talla
- [ ] Agregar manejo de errores para los nuevos endpoints
- [ ] Agregar loading states
- [ ] Manejar casos de arrays vacíos
- [ ] Probar con diferentes rangos de fechas
- [ ] Validar formatos de fecha antes de enviar
- [ ] Actualizar tests (si existen)
- [ ] Actualizar documentación interna

### Sugerencias de UI:

**1. Dashboard de Tallas:**
- Gráfico de barras mostrando ventas por talla
- Tabla con detalles numéricos
- Filtros por fecha/rango

**2. Vista por Categoría:**
- Acordeón o tabs por categoría
- Mini-gráficos de tallas dentro de cada categoría
- Comparativa entre categorías

**3. Vista por Departamento:**
- Cards por departamento (HOMBRE, MUJER, NIÑO, NIÑA)
- Gráfico de distribución de tallas por departamento
- Insights automáticos (ej: "Talla más vendida en MUJER: M")

**4. Integración en Reporte Completo:**
- Sección adicional en el reporte existente
- Tabs o acordeón para las 3 vistas de tallas
- Botón de exportación a PDF (ya incluido en backend)

---

## 🆘 Soporte

### Contacto del Equipo Backend:
- **Email:** koaj.puertocarreno@gmail.com
- **Documentación Técnica:** `IMPLEMENTACION_ANALISIS_TALLAS.md`

### En caso de problemas:

1. Verificar que el servidor esté corriendo: `http://10.28.168.57:5000/health`
2. Verificar que el token sea válido
3. Verificar formato de fechas (YYYY-MM-DD)
4. Revisar logs del navegador (Network tab)
5. Contactar al equipo backend con:
   - Endpoint que falla
   - Parámetros enviados
   - Respuesta recibida
   - Código de error HTTP

---

## 📅 Historial de Versiones

### v2.1.3 (2025-11-28)
- ✨ Agregado: 3 nuevos endpoints de análisis por talla
- ✨ Agregado: Secciones de talla en reporte completo
- ✨ Agregado: Parser automático de SKU
- 📝 Documentado: Estructura completa de respuestas

### v2.1.2 (2025-11-28)
- 🐛 Corregido: Compatibilidad Python 3.14
- 📝 Agregada: Documentación de troubleshooting

---

## ⚡ Resumen Rápido para Implementar

**1. Actualizar tipos TypeScript:**
```typescript
// Agregar a tus interfaces existentes
interface TallaAnalisis { /* ver arriba */ }
interface CategoriaConTallas { /* ver arriba */ }
interface DepartamentoConTallas { /* ver arriba */ }
```

**2. Consumir nuevos endpoints:**
```javascript
// Análisis por talla
GET /api/products/analysis/sizes?date=YYYY-MM-DD

// Análisis por categoría y talla
GET /api/products/analysis/category-sizes?date=YYYY-MM-DD

// Análisis por departamento y talla
GET /api/products/analysis/department-sizes?date=YYYY-MM-DD
```

**3. Actualizar manejo del reporte completo:**
```javascript
const response = await getProductAnalysis(date);
// Ahora también incluye:
// - response.data.ventas_por_talla
// - response.data.ventas_por_categoria_talla
// - response.data.ventas_por_departamento_talla
```

**4. Renderizar datos:**
- Usar `*_formatted` para mostrar valores al usuario
- Usar valores numéricos para cálculos/gráficos
- Siempre verificar arrays vacíos

---

**Versión del documento:** 1.0.0
**Última actualización:** 2025-11-28
**Preparado por:** Equipo Backend - KOAJ Puerto Carreño
