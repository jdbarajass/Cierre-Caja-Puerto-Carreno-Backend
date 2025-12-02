# Prompt para Frontend: Soporte para Nueva Estructura de Inventario

## Contexto

El backend ha sido actualizado para soportar **dos estructuras diferentes de archivos de inventario** de Alegra. El sistema ahora detecta automáticamente qué estructura tiene el archivo cargado y lo procesa correctamente.

## Cambios en el Backend

### 1. Detección Automática de Estructura

El backend ahora puede procesar dos tipos de archivos de inventario:

#### **Estructura Tipo 1: Exportación de Productos** (Antigua)
- Tipo
- Nombre
- Categoría
- Costo inicial
- Precio base

#### **Estructura Tipo 2: Reporte de Inventario** (Nueva) ✨
- **Categoría**: Categoría del producto
- **Ítem**: Nombre completo del producto
- **Referencia**: Código/SKU (puede estar vacío)
- **Descripción**: Descripción adicional (puede estar vacío)
- **Cantidad mínima**: Stock mínimo
- **Cantidad máxima**: Stock máximo
- **Cantidad**: **Inventario actual** (unidades en stock)
- **Cantidad en remisiones**: Unidades en tránsito
- **Unidad**: Tipo de unidad (ej: "Unidad")
- **Estado**: "Activo" o "Inactivo"
- **Costo promedio**: Costo unitario del producto
- **Total**: Valor total (Cantidad × Costo promedio)

### 2. Cambios en la Respuesta del API

La respuesta del endpoint `/api/inventory/upload` ahora incluye un campo adicional que indica qué tipo de archivo se detectó:

```json
{
  "success": true,
  "tipo_archivo": "inventario_alegra",  // ← NUEVO CAMPO
  "resumen_general": {
    "total_items": 1980,                 // Total de productos/variantes
    "total_unidades": 3347,              // ← NUEVO: Total de unidades en inventario
    "items_activos": 1173,               // ← NUEVO: Productos activos
    "items_inactivos": 807,              // ← NUEVO: Productos inactivos
    "valor_total_inventario": 173384928.0,  // ← RENOMBRADO (antes: valor_total_precio)
    "costo_total_inventario": 173384927.47, // ← RENOMBRADO (antes: valor_total_costo)
    "total_categorias": 73
  },
  "por_departamento": {
    "hombre": {
      "cantidad_items": 329,              // Número de productos/variantes
      "cantidad_unidades": 872,           // ← NUEVO: Total de unidades
      "valor_inventario": 62059942.0,     // Valor total del inventario
      "costo_total": 62059942.01,
      "costo_promedio": 71169.66,
      "valor_promedio": 71169.66,
      "porcentaje_unidades": 26.05,       // ← NUEVO: % del inventario total
      "porcentaje_valor": 35.79,          // % del valor total
      "items": [...]                      // Primeros 10 productos
    },
    // ... otros departamentos
  },
  "top_categorias": [...],
  "departamentos_ordenados": [
    {
      "nombre": "mujer",
      "cantidad_unidades": 1041,          // ← NUEVO
      "valor": 73329996
    },
    // ...
  ]
}
```

### 3. Valores del Campo `tipo_archivo`

- `"inventario_alegra"`: Reporte de inventario con cantidades (estructura nueva)
- `"exportacion_productos"`: Exportación de productos sin inventario (estructura antigua)

## Cambios Necesarios en el Frontend

### ✅ NO SE REQUIEREN CAMBIOS OBLIGATORIOS

El frontend actual debe seguir funcionando sin modificaciones, ya que:

1. **Retrocompatibilidad**: Los campos existentes se mantienen
2. **Nuevos campos opcionales**: Los nuevos campos son adicionales
3. **Detección automática**: El backend maneja la detección transparentemente

### 🎨 Mejoras Opcionales Recomendadas

Si deseas aprovechar la nueva funcionalidad, puedes agregar:

#### 1. Indicador del Tipo de Archivo Cargado

```tsx
// En el componente de carga de inventario
{result.tipo_archivo === 'inventario_alegra' && (
  <Alert type="info">
    📦 Archivo de inventario detectado - Incluye cantidades en stock
  </Alert>
)}

{result.tipo_archivo === 'exportacion_productos' && (
  <Alert type="info">
    📋 Archivo de exportación detectado - Catálogo de productos
  </Alert>
)}
```

#### 2. Mostrar Información de Inventario (solo si tipo_archivo === 'inventario_alegra')

```tsx
// Agregar estas métricas en el resumen general
{result.tipo_archivo === 'inventario_alegra' && (
  <>
    <StatCard
      title="Total Unidades"
      value={result.resumen_general.total_unidades.toLocaleString()}
      icon="📦"
    />
    <StatCard
      title="Productos Activos"
      value={result.resumen_general.items_activos.toLocaleString()}
      icon="✅"
      color="green"
    />
    <StatCard
      title="Productos Inactivos"
      value={result.resumen_general.items_inactivos.toLocaleString()}
      icon="⛔"
      color="gray"
    />
  </>
)}
```

#### 3. Columnas Adicionales en Tabla de Departamentos

```tsx
// Para archivos de inventario, mostrar cantidad de unidades
const columns = [
  { header: 'Departamento', accessor: 'nombre' },
  { header: 'Productos', accessor: 'cantidad_items' },
  // Condicional para inventarios
  ...(result.tipo_archivo === 'inventario_alegra' ? [
    {
      header: 'Unidades',
      accessor: 'cantidad_unidades',
      render: (val) => val.toLocaleString()
    }
  ] : []),
  {
    header: 'Valor Total',
    accessor: 'valor_inventario',
    render: (val) => formatMoney(val)
  }
];
```

#### 4. Visualización de Items con Estado

```tsx
// En la lista de productos, mostrar el estado si existe
{product.estado && (
  <Badge
    color={product.estado === 'Activo' ? 'green' : 'gray'}
  >
    {product.estado}
  </Badge>
)}

{product.cantidad !== undefined && (
  <span className="text-sm text-gray-600">
    Stock: {product.cantidad} unidades
  </span>
)}
```

## Ejemplos de Uso

### Caso 1: Archivo de Inventario Nuevo (Inventario.xlsx)

**Request:**
```http
POST /api/inventory/upload
Content-Type: multipart/form-data

file: Inventario.xlsx
```

**Response:**
```json
{
  "success": true,
  "tipo_archivo": "inventario_alegra",
  "resumen_general": {
    "total_items": 1980,
    "total_unidades": 3347,
    "items_activos": 1173,
    "items_inactivos": 807,
    "valor_total_inventario": 173384928.0,
    "costo_total_inventario": 173384927.47,
    "total_categorias": 73
  },
  "por_departamento": {
    "mujer": {
      "cantidad_items": 498,
      "cantidad_unidades": 1041,
      "valor_inventario": 73329996.0,
      "costo_total": 73329995.83,
      "costo_promedio": 70441.88,
      "valor_promedio": 70441.88,
      "porcentaje_unidades": 31.10,
      "porcentaje_valor": 42.29,
      "items": [
        {
          "nombre": "JEAN MUJER 109900 / 4010109900",
          "categoria": "JEAN MUJER",
          "cantidad": 12,
          "estado": "Activo",
          "costo_unitario": 109900.0,
          "valor_total": 1318800.0
        }
        // ... más items
      ]
    }
    // ... más departamentos
  },
  "top_categorias": [
    { "categoria": "JEAN MUJER", "cantidad": 106 },
    { "categoria": "ZAPATO HOMBRE", "cantidad": 90 }
    // ...
  ],
  "departamentos_ordenados": [
    { "nombre": "mujer", "cantidad_unidades": 1041, "valor": 73329996 },
    { "nombre": "hombre", "cantidad_unidades": 872, "valor": 62059942 }
    // ...
  ]
}
```

### Caso 2: Archivo de Exportación Antiguo (exportacion_productos.csv)

**Request:**
```http
POST /api/inventory/upload
Content-Type: multipart/form-data

file: exportacion_productos.csv
```

**Response:**
```json
{
  "success": true,
  "tipo_archivo": "exportacion_productos",  // ← Tipo diferente
  "resumen_general": {
    "total_items": 500,
    // NO incluye: total_unidades, items_activos, items_inactivos
    "valor_total_precio": 50000000.0,
    "valor_total_costo": 30000000.0,
    "margen_total": 20000000.0,
    "margen_porcentaje": 40.0,
    "total_categorias": 30
  },
  "por_departamento": {
    "hombre": {
      "cantidad": 150,  // ← Nota: "cantidad" no "cantidad_items"
      "valor_costo": 15000000.0,
      "valor_precio": 25000000.0,
      "margen_total": 10000000.0,
      "margen_porcentaje": 40.0,
      "precio_promedio": 166666.67,
      "costo_promedio": 100000.0,
      "porcentaje_inventario": 30.0,
      "items": [
        {
          "nombre": "CAMISETA HOMBRE POLO",
          "categoria": "CAMISETA HOMBRE",
          "tipo": "Producto",
          "costo": 50000.0,
          "precio": 89900.0,
          "margen": 39900.0,
          "margen_porcentaje": 44.38
        }
        // ...
      ]
    }
  }
}
```

## Compatibilidad

| Campo | Inventario Nuevo | Exportación Antigua | Notas |
|-------|------------------|---------------------|-------|
| `success` | ✅ | ✅ | Siempre presente |
| `tipo_archivo` | ✅ | ✅ | **NUEVO** - Indica el tipo |
| `total_items` | ✅ | ✅ | Presente en ambos |
| `total_unidades` | ✅ | ❌ | Solo en inventario |
| `items_activos` | ✅ | ❌ | Solo en inventario |
| `items_inactivos` | ✅ | ❌ | Solo en inventario |
| `cantidad_items` | ✅ | ❌ | Inventario usa este nombre |
| `cantidad` | ❌ | ✅ | Exportación usa este nombre |
| `cantidad_unidades` | ✅ | ❌ | Solo en inventario |
| `valor_inventario` | ✅ | ❌ | Inventario usa este nombre |
| `valor_precio` | ❌ | ✅ | Exportación usa este nombre |

## Recomendaciones

### Para el Desarrollador Frontend:

1. **Validar el campo `tipo_archivo`** para decidir qué UI mostrar
2. **Usar campos condicionales** según el tipo de archivo
3. **Mantener retrocompatibilidad** para archivos antiguos
4. **Agregar tooltips** explicando las diferencias entre tipos de archivo
5. **Actualizar la documentación de usuario** sobre los formatos soportados

### Ejemplo de Componente Adaptativo:

```tsx
function InventoryResults({ result }) {
  const isInventoryReport = result.tipo_archivo === 'inventario_alegra';
  const isProductExport = result.tipo_archivo === 'exportacion_productos';

  return (
    <div className="inventory-results">
      {/* Header con tipo de archivo */}
      <FileTypeIndicator type={result.tipo_archivo} />

      {/* Resumen general - adaptativo */}
      <GeneralSummary>
        <StatCard title="Total Items" value={result.resumen_general.total_items} />

        {isInventoryReport && (
          <>
            <StatCard title="Total Unidades" value={result.resumen_general.total_unidades} />
            <StatCard title="Activos" value={result.resumen_general.items_activos} />
            <StatCard title="Inactivos" value={result.resumen_general.items_inactivos} />
          </>
        )}

        <StatCard
          title="Valor Total"
          value={isInventoryReport
            ? result.resumen_general.valor_total_inventario
            : result.resumen_general.valor_total_precio
          }
        />

        {isProductExport && (
          <StatCard
            title="Margen Total"
            value={result.resumen_general.margen_total}
          />
        )}
      </GeneralSummary>

      {/* Tabla de departamentos - adaptativa */}
      <DepartmentsTable
        departments={result.por_departamento}
        showUnits={isInventoryReport}
        showMargin={isProductExport}
      />

      {/* Resto de la UI */}
    </div>
  );
}
```

## Testing

### Escenarios a Probar:

1. ✅ Cargar archivo de inventario nuevo (Inventario.xlsx)
2. ✅ Cargar archivo de exportación antiguo (.csv)
3. ✅ Verificar que campos condicionales se muestren correctamente
4. ✅ Verificar que la UI no se rompa con campos faltantes
5. ✅ Probar ambos tipos de archivo en diferentes navegadores

## Soporte

Si tienes preguntas o encuentras algún problema:

1. Revisa la documentación completa en `docs/FRONTEND_INVENTORY_UPLOAD.md`
2. Consulta ejemplos de respuesta en `tests/test_analytics_endpoints.py`
3. Prueba los endpoints en el Swagger docs: `http://localhost:5000/api/docs`

---

**Fecha de actualización**: Diciembre 2025
**Versión del backend**: 2.2.0
**Cambio**: Soporte para múltiples estructuras de inventario
