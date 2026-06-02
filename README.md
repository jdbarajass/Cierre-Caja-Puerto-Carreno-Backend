# API de Cierre de Caja - KOAJ Puerto Carreño

Sistema backend para procesamiento de cierres de caja con integración a Alegra.

## Versión 2.3.0 - Control de Empleadas y Cuentas Recompras

Esta versión incluye una refactorización completa del código con mejores prácticas, arquitectura modular, validación robusta y documentación completa. Ahora incluye análisis completo de productos vendidos con reportes en JSON y PDF, más un **sistema completo de análisis de inventario** con métricas ejecutivas, clasificación ABC, alertas de stock y análisis por departamento.

---

## 📋 Características

- ✅ **Cálculo automático de base de caja** usando algoritmo Knapsack (Programación Dinámica)
- ✅ **Integración con Alegra** para obtener ventas del día
- ✅ **Validación de datos** con Pydantic
- ✅ **Logging profesional** con diferentes niveles
- ✅ **Manejo robusto de errores** con excepciones custom
- ✅ **Documentación automática** con Swagger/Flasgger
- ✅ **Rate limiting** para prevenir abuso
- ✅ **Health check endpoint** para monitoreo
- ✅ **Tests unitarios** con pytest
- ✅ **Soporte Docker** para despliegue containerizado
- ✅ **CORS configurado** para frontend
- ✅ **Autenticación JWT** con tokens seguros
- ✅ **Control de intentos de login** con bloqueo temporal
- ✅ **Middlewares de autenticación** para proteger rutas
- ✅ **Análisis de productos** con reportes en JSON y PDF
- ✅ **Top productos más vendidos** con unificación de variantes
- ✅ **Análisis por categorías** de productos
- ✅ **Generación de PDFs** profesionales para reportes
- ✅ **Análisis de inventario** completo con métricas ejecutivas
- ✅ **Clasificación ABC** de productos por valor
- ✅ **Alertas de stock** bajo y productos sin inventario
- ✅ **Análisis por departamento** (HOMBRE, MUJER, NIÑO, NIÑA)
- ✅ **Control de Empleadas** — ropa, préstamos, permisos, vacaciones, pagos
- ✅ **Cuentas Recompras** — tabla mensual de dinero enviado al socio con cálculo 4‰
- ✅ **Migración segura** de base de datos (ADD COLUMN, nunca DROP TABLE)

---

## 🏗️ Arquitectura

```
cierre-caja-api/
├── app/
│   ├── __init__.py           # Factory de Flask
│   ├── config.py             # Configuración centralizada
│   ├── exceptions.py         # Excepciones custom
│   ├── routes/               # Endpoints de la API
│   │   ├── cash_closing.py   # Endpoint principal de cierre
│   │   ├── health.py         # Health check
│   │   ├── auth.py           # Autenticación JWT
│   │   ├── products.py       # Análisis de productos
│   │   ├── analytics.py      # Análisis de ventas
│   │   ├── inventory.py      # Análisis de inventario
│   │   ├── direct_api.py     # APIs directas de Alegra
│   │   ├── users.py          # CRUD de usuarios (admin)
│   │   ├── koaj_codes.py     # Códigos y precios KOAJ
│   │   ├── employee_records.py  # Control de empleadas
│   │   └── repurchase.py     # Cuentas de recompras
│   ├── services/             # Lógica de negocio
│   │   ├── alegra_client.py  # Cliente API Alegra
│   │   ├── cash_calculator.py# Calculador de caja
│   │   ├── knapsack_solver.py# Algoritmo DP
│   │   ├── jwt_service.py    # Servicio JWT
│   │   ├── product_analytics.py # Análisis de productos
│   │   ├── inventory_analytics.py # Análisis de inventario
│   │   ├── sku_parser.py     # Parser de SKU/códigos
│   │   └── pdf_generator.py  # Generador de PDFs
│   ├── middlewares/          # Middlewares
│   │   └── auth.py           # Middleware de autenticación
│   ├── models/               # Schemas y modelos SQLAlchemy
│   │   ├── user.py              # Usuario (auth, roles: admin/sales/partner)
│   │   ├── koaj_code.py         # Códigos de categorías KOAJ
│   │   ├── employee_records.py  # Empleadas: ropa, préstamos, permisos, vacaciones, pagos
│   │   ├── repurchase.py        # Entradas de cuentas recompras
│   │   ├── requests.py          # Request models (Pydantic)
│   │   └── responses.py         # Response models
│   └── utils/                # Utilidades
│       ├── formatters.py     # Formateo de datos
│       ├── validators.py     # Validaciones
│       └── timezone.py       # Manejo de zonas horarias
├── scripts/                  # Scripts utilitarios
│   ├── generate_jwt_secret.py# Generador de claves JWT
│   └── init_admin.py         # Inicializador de admin
├── tests/                    # Tests unitarios
├── logs/                     # Archivos de log
├── run.py                    # Entry point
├── requirements.txt          # Dependencias
├── Dockerfile                # Docker image
└── Procfile                  # Config Render/Heroku

```

---

## 🚀 Instalación

### Prerequisitos

- Python 3.11+
- pip
- virtualenv (recomendado)

### Paso 1: Clonar el repositorio

```bash
git clone <url-del-repo>
cd cierre-caja-api
```

### Paso 2: Crear entorno virtual

```bash
python -m venv venv

# Windows
venv\Scripts\activate

# Linux/Mac
source venv/bin/activate
```

### Paso 3: Instalar dependencias

**Opción A - Instalación Manual:**
```bash
pip install -r requirements.txt

# Para desarrollo (incluye herramientas de testing)
pip install -r requirements-dev.txt
```

**Opción B - Script Automático (Recomendado):**
```bash
# Windows
install_dependencies.bat

# Linux/Mac
chmod +x install_dependencies.sh
./install_dependencies.sh
```

**Si tienes problemas:** Lee [TROUBLESHOOTING.md](TROUBLESHOOTING.md) para soluciones detalladas.

### Paso 4: Configurar variables de entorno

```bash
# Copiar el template
cp .env.example .env

# Editar .env con tus credenciales
# IMPORTANTE: Configura ALEGRA_USER y ALEGRA_PASS
```

### Paso 5: Ejecutar la aplicación

```bash
# Modo desarrollo
python run.py

# Modo producción con Gunicorn
gunicorn run:app --bind 0.0.0.0:8000 --workers 2
```

La API estará disponible en `http://localhost:5000` (desarrollo) o `http://localhost:8000` (producción).

---

## 🖥️ Despliegue Local (Pruebas)

### Inicio rápido

```bash
# 1. Activar entorno virtual
venv\Scripts\activate

# 2. Instalar dependencias
# Opción recomendada (script automático):
install_dependencies.bat

# O instalación manual:
# pip install -r requirements.txt

# 3. Ejecutar servidor
python run.py
```

**Problemas al instalar?** → Ver [TROUBLESHOOTING.md](TROUBLESHOOTING.md)

### URLs de acceso local

- **Local (pruebas):** http://10.28.168.57:5000
- **Health Check:** http://10.28.168.57:5000/health
- **API Docs:** http://10.28.168.57:5000/api/docs

---

## 🐳 Docker

### Construir imagen

```bash
docker build -t cierre-caja-api:latest .
```

### Ejecutar container

```bash
docker run -d \
  -p 8000:8000 \
  --env-file .env \
  --name cierre-caja \
  cierre-caja-api:latest
```

### Docker Compose (opcional)

```yaml
version: '3.8'

services:
  api:
    build: .
    ports:
      - "8000:8000"
    env_file:
      - .env
    restart: unless-stopped
```

---

## 📚 Documentación de la API

### Swagger UI

Una vez ejecutada la aplicación, accede a:

```
http://localhost:5000/api/docs
```

### Endpoints Principales

#### 1. POST /api/sum_payments

Procesa un cierre de caja completo.

**Request:**

```json
{
  "date": "2025-11-06",
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
  "excedente": 13500,
  "gastos_operativos": 0,
  "prestamos": 0
}
```

**Response (200):**

```json
{
  "request_datetime": "2025-11-14T10:30:00-05:00",
  "date_requested": "2025-11-06",
  "cash_count": {
    "totals": {
      "total_general": 556400,
      "total_general_formatted": "$556.400"
    },
    "base": {
      "total_base": 450000,
      "exact_base_obtained": true
    },
    "consignar": {
      "efectivo_para_consignar_final": 106400
    }
  },
  "alegra": {
    "total_sale": {
      "label": "TOTAL VENTA DEL DÍA",
      "total": 500000
    }
  }
}
```

#### 2. GET /api/monthly_sales

Consulta el resumen de ventas del mes desde Alegra.

**Query Parameters (opcionales):**

- `start_date` (string): Fecha de inicio en formato YYYY-MM-DD. Si no se proporciona, usa el día 1 del mes actual
- `end_date` (string): Fecha de fin en formato YYYY-MM-DD. Si no se proporciona, usa la fecha actual

**Ejemplos:**

```
GET /api/monthly_sales
GET /api/monthly_sales?start_date=2025-11-01&end_date=2025-11-16
```

**Response (200):**

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
    }
  },
  "username_used": "tu-usuario@alegra.com"
}
```

#### 3. GET /api/products/analysis

Análisis completo de productos vendidos en formato JSON.

**Query Parameters (opcionales):**

- `date` (string): Fecha específica en formato YYYY-MM-DD
- `start_date` (string): Fecha de inicio para rango
- `end_date` (string): Fecha de fin para rango

**Ejemplos:**

```
GET /api/products/analysis?date=2025-11-21
GET /api/products/analysis?start_date=2025-11-01&end_date=2025-11-30
```

**Response (200):**

```json
{
  "success": true,
  "date_range": "2025-11-01 al 2025-11-30",
  "data": {
    "resumen_ejecutivo": {
      "total_productos_vendidos": 450,
      "ingresos_totales": 15250000,
      "producto_mas_vendido": "CAMISETA MUJER",
      "unidades_mas_vendido": 85,
      "numero_facturas": 120
    },
    "top_10_productos": [...],
    "top_10_productos_unificados": [...],
    "todos_productos_unificados": [...],
    "listado_completo": [...],
    "metadata": {
      "fecha_generacion": "2025-11-21T14:30:45",
      "numero_facturas_procesadas": 120,
      "numero_items_procesados": 450
    }
  }
}
```

#### 4. GET /api/products/analysis/pdf

Descarga reporte de productos en formato PDF.

**Query Parameters:** Igual que `/api/products/analysis`

**Response:** Archivo PDF descargable

#### 5. GET /api/products/summary

Resumen ejecutivo de productos (métricas principales).

**Query Parameters:** Igual que `/api/products/analysis`

**Response (200):**

```json
{
  "success": true,
  "date_range": "2025-11-21",
  "summary": {
    "total_productos_vendidos": 42,
    "ingresos_totales": 1569300.0,
    "numero_facturas": 17,
    "producto_mas_vendido": "MEDIAS 7900 / 10487900",
    "unidades_mas_vendido": 3
  }
}
```

#### 6. GET /api/products/top-sellers

Top productos más vendidos.

**Query Parameters:**

- `date`, `start_date`, `end_date`: Igual que otros endpoints
- `limit` (int, opcional): Número de productos (default: 10)
- `unified` (bool, opcional): Agrupar variantes (default: false)

**Ejemplo:**

```
GET /api/products/top-sellers?start_date=2025-11-01&end_date=2025-11-30&limit=10&unified=true
```

#### 7. GET /api/products/categories

Análisis de productos por categorías (CAMISETA, JEAN, BLUSA, etc.).

**Query Parameters:** `date`, `start_date`, `end_date`

#### 8. GET /api/inventory/summary

**Resumen Ejecutivo del Inventario**

Retorna métricas principales del inventario actual.

**Headers:** `Authorization: Bearer <token>` (Requiere autenticación)

**Response (200):**

```json
{
  "success": true,
  "summary": {
    "total_items": 25,
    "total_items_con_stock": 7,
    "total_unidades": 22,
    "valor_total_inventario": 1505850,
    "valor_potencial_venta": 2007800,
    "margen_esperado": 501950,
    "porcentaje_margen": 25.0,
    "costo_promedio_por_unidad": 68447.73,
    "precio_promedio_venta": 91263.64
  }
}
```

#### 9. GET /api/inventory/by-department

**Análisis de Inventario por Departamento**

Desglose completo por HOMBRE, MUJER, NIÑO, NIÑA con subcategorías.

**Headers:** `Authorization: Bearer <token>` (Requiere autenticación)

**Response (200):**

```json
{
  "success": true,
  "data": {
    "HOMBRE": {
      "total_items": 25,
      "total_unidades": 22,
      "valor_inventario": 1505850,
      "valor_potencial_venta": 2007800,
      "margen": 501950,
      "por_categoria": {
        "BERMUDA": {
          "total_items": 7,
          "total_unidades": 22,
          "valor_inventario": 1505850
        }
      }
    }
  }
}
```

#### 10. GET /api/inventory/analysis

**Análisis Completo de Inventario (TODO EN UNO)**

Retorna toda la información del inventario en una sola petición: resumen, departamentos, categorías, tallas, alertas de stock, top productos y análisis ABC.

**Headers:** `Authorization: Bearer <token>` (Requiere autenticación)

**Uso recomendado:** Dashboard completo, exportación de reportes

#### 11. GET /api/inventory/by-category

**Análisis por Categoría de Producto**

Lista de categorías ordenadas por valor de inventario.

**Headers:** `Authorization: Bearer <token>` (Requiere autenticación)

#### 12. GET /api/inventory/by-size

**Análisis por Talla**

Distribución del inventario por tallas (28, 30, S, M, L, XL, etc.).

**Headers:** `Authorization: Bearer <token>` (Requiere autenticación)

#### 13. GET /api/inventory/out-of-stock

**Productos Sin Stock**

Lista de productos activos con cantidad = 0.

**Headers:** `Authorization: Bearer <token>` (Requiere autenticación)

**Response (200):**

```json
{
  "success": true,
  "total": 18,
  "products": [
    {
      "id": "1596",
      "nombre": "BERMUDA 109900 / 1051421099028",
      "categoria": "BERMUDA",
      "departamento": "HOMBRE",
      "precio_venta": 109900
    }
  ]
}
```

#### 14. GET /api/inventory/low-stock?threshold=5

**Productos con Bajo Stock**

Lista de productos con cantidad <= threshold.

**Headers:** `Authorization: Bearer <token>` (Requiere autenticación)

**Query Parameters:**
- `threshold` (int, opcional): Umbral de stock bajo (default: 5)

**Response (200):**

```json
{
  "success": true,
  "threshold": 5,
  "total": 6,
  "products": [
    {
      "id": "1598",
      "nombre": "BERMUDA 109900 / 1051421099032",
      "categoria": "BERMUDA",
      "departamento": "HOMBRE",
      "cantidad_disponible": 1,
      "precio_venta": 109900
    }
  ]
}
```

#### 15. GET /api/inventory/top-by-value?limit=20

**Top Productos por Valor de Inventario**

Lista de productos ordenados por valor total en inventario (cantidad × costo).

**Headers:** `Authorization: Bearer <token>` (Requiere autenticación)

**Query Parameters:**
- `limit` (int, opcional): Cantidad de productos (default: 20)

#### 16. GET /api/inventory/abc-analysis

**Análisis ABC (Pareto)**

Clasificación de productos según su contribución al valor total del inventario:
- **Clase A**: ~20% de productos que representan ~80% del valor (CRÍTICOS)
- **Clase B**: ~30% de productos que representan ~15% del valor (IMPORTANTES)
- **Clase C**: ~50% de productos que representan ~5% del valor (NORMALES)

**Headers:** `Authorization: Bearer <token>` (Requiere autenticación)

**Response (200):**

```json
{
  "success": true,
  "data": {
    "clase_A": {
      "cantidad_items": 2,
      "porcentaje_items": 28.57,
      "valor_inventario": 1183725,
      "porcentaje_valor": 78.61
    },
    "clase_B": {
      "cantidad_items": 3,
      "porcentaje_items": 42.86,
      "valor_inventario": 217275,
      "porcentaje_valor": 14.43
    },
    "clase_C": {
      "cantidad_items": 2,
      "porcentaje_items": 28.57,
      "valor_inventario": 104850,
      "porcentaje_valor": 6.96
    }
  }
}
```

#### 17. GET /health

Health check para monitoreo.

**Response (200):**

```json
{
  "status": "healthy",
  "service": "cierre-caja-api",
  "version": "2.0.0",
  "alegra": "connected"
}
```

---

## 🔐 Autenticación JWT

El sistema incluye autenticación basada en tokens JWT para proteger endpoints sensibles.

### Endpoints de Autenticación

#### POST /auth/login

Autentica al usuario y retorna un token JWT.

**Request:**

```json
{
  "email": "ventaspuertocarreno@gmail.com",
  "password": "VentasCarreno2025.*"
}
```

**Response (200):**

```json
{
  "success": true,
  "token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
  "user": {
    "email": "ventaspuertocarreno@gmail.com",
    "name": "Usuario Ventas Puerto Carreño",
    "role": "admin"
  }
}
```

**Errores posibles:**

- `400`: Datos de entrada inválidos
- `401`: Credenciales incorrectas
- `403`: Cuenta bloqueada por múltiples intentos fallidos

#### GET /auth/verify

Verifica si un token JWT es válido.

**Headers:**

```
Authorization: Bearer <token>
```

**Response (200):**

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

### Protección de Rutas

Para proteger endpoints con autenticación JWT, usa los decoradores:

```python
from app.middlewares.auth import token_required, role_required, get_current_user

@app.route('/protected')
@token_required
def protected_route():
    user = get_current_user()
    return jsonify({'user': user})

@app.route('/admin-only')
@token_required
@role_required('admin')
def admin_route():
    return jsonify({'message': 'Admin access granted'})
```

### Seguridad

- **Bloqueo de cuenta**: Después de 5 intentos fallidos, la cuenta se bloquea por 15 minutos
- **Expiración de tokens**: Los tokens expiran después de 8 horas (configurable)
- **Algoritmo**: HS256

---

## 🔧 Scripts Utilitarios

### Generar clave secreta JWT

```bash
python scripts/generate_jwt_secret.py
```

Genera una clave secreta segura de 64 caracteres para usar en `JWT_SECRET_KEY`.

### Inicializar usuario administrador

```bash
python scripts/init_admin.py
```

Crea o actualiza el usuario administrador en la base de datos. Útil para configuración inicial.

---

## 🧪 Testing

### Ejecutar todos los tests

```bash
pytest
```

### Con cobertura

```bash
pytest --cov=app --cov-report=html
```

### Tests específicos

```bash
pytest tests/test_formatters.py
pytest tests/test_knapsack_solver.py
pytest tests/test_cash_calculator.py
```

---

## 🔧 Configuración

### Variables de Entorno Críticas

#### Configuración General
- `FLASK_ENV`: Ambiente (development, production, testing)
- `DEBUG`: Modo debug (True/False)
- `SECRET_KEY`: Clave secreta de Flask
- `PORT`: Puerto del servidor (por defecto: 5000)

#### Credenciales Alegra
- `ALEGRA_USER`: Usuario/email de Alegra
- `ALEGRA_PASS`: Token de API de Alegra
- `ALEGRA_API_BASE_URL`: URL base de la API de Alegra
- `ALEGRA_TIMEOUT`: Timeout para requests (por defecto: 30)

#### Configuración de Negocio
- `BASE_OBJETIVO`: Monto base que debe quedar en caja (por defecto: 450000)
- `UMBRAL_MENUDO`: Valor máximo para considerar un billete/moneda como menudo (por defecto: 10000)

#### Autenticación JWT
- `JWT_SECRET_KEY`: Clave secreta para firmar tokens (mínimo 32 caracteres)
- `JWT_EXPIRATION_HOURS`: Tiempo de expiración del token en horas (por defecto: 8)

#### Seguridad
- `MAX_LOGIN_ATTEMPTS`: Intentos de login antes de bloquear (por defecto: 5)
- `LOCKOUT_TIME_MINUTES`: Tiempo de bloqueo en minutos (por defecto: 15)

#### CORS
- `ALLOWED_ORIGINS`: Lista de orígenes permitidos separados por comas

#### Otros
- `TIMEZONE`: Zona horaria (por defecto: America/Bogota)
- `DATABASE_URL`: URL de conexión a la base de datos

Ver `.env.example` para todas las variables disponibles con ejemplos.

### 📖 Documentación Adicional

- **[TROUBLESHOOTING.md](TROUBLESHOOTING.md)** - Guía completa de solución de problemas al instalar y ejecutar el servidor (RECOMENDADO LEER)
- **[CONFIGURACION_VARIABLES_RENDER.md](CONFIGURACION_VARIABLES_RENDER.md)** - Guía completa para configurar variables de entorno en Render con explicaciones detalladas de cada variable
- **[CAMBIOS_FRONTEND.md](CAMBIOS_FRONTEND.md)** - Documentación de cambios en la API que requieren actualización del frontend
- **[generate_secret_key.py](generate_secret_key.py)** - Script para generar claves secretas seguras para Flask

---

## 📊 Logging

Los logs incluyen:

- Operaciones de cierre de caja
- Peticiones a Alegra
- Errores y warnings
- Métricas de performance

**Ubicación:** `logs/cierre_caja.log` (local) o stdout (Render)

---

## 🚢 Despliegue en Render

1. Conecta tu repositorio de GitHub
2. Render detectará automáticamente el `Procfile`
3. Configura las variables de entorno
4. Despliegue automático

---

## 🎯 Algoritmo Knapsack

Usa **Bounded Knapsack con Programación Dinámica** para calcular la base exacta de $450,000.

**Ver:** `app/services/knapsack_solver.py`

---

## 📝 Changelog

### v2.3.0 (2026-06-02)

#### ✨ Módulo Control de Empleadas

Nuevo conjunto de endpoints para gestión interna del personal de la tienda.
Las tablas se crean automáticamente en Supabase/SQLite al arrancar el servidor.

**Identificación**: campo `nombre_empleada` de texto libre (no FK a usuarios), permite
que varias personas compartan la misma cuenta y se identifiquen por nombre (Mónica, Camila, etc.)

| Endpoint | Método | Auth | Descripción |
|---|---|---|---|
| `/api/employee-records/clothing` | GET | JWT | Lista prendas (filtro opcional: `?nombre_empleada=Monica`) |
| `/api/employee-records/clothing` | POST | JWT | Registra prenda con descuento |
| `/api/employee-records/clothing/<id>` | PUT/DELETE | JWT Admin | Edita o elimina |
| `/api/employee-records/loans` | GET/POST | JWT | Préstamos de dinero |
| `/api/employee-records/loans/<id>` | PUT/DELETE | JWT Admin | — |
| `/api/employee-records/permissions` | GET/POST | JWT | Permisos/incapacidades/llegadas tarde |
| `/api/employee-records/permissions/<id>` | PUT/DELETE | JWT Admin | — |
| `/api/employee-records/vacations` | GET/POST | JWT | Vacaciones (calcula días automáticamente) |
| `/api/employee-records/vacations/<id>` | PUT/DELETE | JWT Admin | — |
| `/api/employee-records/payments` | GET | JWT | Ver pagos |
| `/api/employee-records/payments` | POST | JWT Admin | Registrar quincena/prima/comisión |
| `/api/employee-records/payments/<id>` | PUT/DELETE | JWT Admin | — |
| `/api/employee-records/summary` | GET | JWT Admin | Resumen agrupado por empleada |

**Reglas de negocio**:
- Cualquier usuario autenticado puede crear y ver registros
- Solo `admin` puede editar, eliminar y registrar pagos

#### ✨ Módulo Cuentas Recompras

Seguimiento del dinero enviado al socio para recompra de mercancía.
Replica la estructura del cuadro Excel de control.

| Endpoint | Método | Auth | Descripción |
|---|---|---|---|
| `/api/repurchase` | GET | JWT Admin | Lista entradas (filtros: `?year=2026&month=6`) |
| `/api/repurchase` | POST | JWT Admin | Crea una fila |
| `/api/repurchase/<id>` | PUT/DELETE | JWT Admin | Edita o elimina |
| `/api/repurchase/monthly-summary` | GET | JWT Admin | Resumen agrupado por mes |

**Cálculos automáticos** (propiedades del modelo, no almacenadas):
- `total_enviado` = efectivo + datafono + qr + daviplata + nequi + bbva
- `fee_4mil` = total_enviado × 4 / 1000 (comisión 4‰)
- `valor_sobrante` = total_enviado − fee_4mil

**Campos de la tabla**:
```
date, descripcion, valor_no_enviado,
efectivo, datafono, qr, daviplata, nequi, bbva,
sobrante_mes_anterior, fecha_compra, notes
```

#### 🔒 Migración segura de base de datos

La función `_migrate_employee_tables()` en `app/__init__.py` usa únicamente
`ALTER TABLE ADD COLUMN` para cambios de esquema. **Nunca borra tablas ni datos**.

Para agregar una columna en el futuro:
```python
# En _migrate_employee_tables(), dentro del bloque with db.engine.connect() as conn:
add_column_if_missing(conn, 'employee_clothing', 'nueva_columna', 'VARCHAR(100)')
```

### v2.2.1 (2025-12-02)

- 🔧 **Filtros de Inventario**: Mejoras en el procesamiento de archivos de inventario
  - Filtro automático para descartar productos con asterisco (*) en el nombre
  - Filtro automático para descartar productos con estado "Inactivo"
  - Los filtros se aplican en ambos métodos de procesamiento (inventario nuevo y exportación antigua)
- 📊 **Lista Completa de Items**: Nueva funcionalidad en endpoint `/api/inventory/upload-file`
  - Se agregó campo `items_completos` en la respuesta del endpoint
  - Contiene TODOS los items del archivo procesado (después de aplicar filtros)
  - Formato simplificado con solo campos necesarios: `item`, `categoria`, `cantidad`, `costo_promedio`, `total`
  - Permite al frontend implementar paginación y análisis personalizados
  - Optimizado para envío eficiente de datos al cliente

### v2.2.0 (2025-11-30)

- ✨ **Sistema de Análisis de Inventario** completamente funcional
  - Nuevo método `get_active_items()` en AlegraClient para obtener inventario de Alegra
  - Nuevo servicio `InventoryAnalytics` para análisis completo de inventario
  - Parser de SKU mejorado para extracción de género, departamento y tallas
  - 9 endpoints nuevos de inventario protegidos con JWT:
    - `/api/inventory/summary` - Resumen ejecutivo con métricas clave
    - `/api/inventory/by-department` - Desglose por HOMBRE/MUJER/NIÑO/NIÑA
    - `/api/inventory/analysis` - Análisis completo (todo en uno)
    - `/api/inventory/by-category` - Por categoría de producto
    - `/api/inventory/by-size` - Distribución por tallas
    - `/api/inventory/out-of-stock` - Productos sin inventario
    - `/api/inventory/low-stock` - Alertas de stock bajo (threshold configurable)
    - `/api/inventory/top-by-value` - Top productos por valor
    - `/api/inventory/abc-analysis` - Clasificación ABC (Pareto)
- 📊 **Análisis ABC**: Clasificación automática de productos en clases A/B/C según valor
- 🎯 **Métricas de Negocio**: Cálculo de márgenes, valor potencial de venta, promedios
- ⚠️ **Alertas Inteligentes**: Detección automática de productos sin stock o stock bajo
- 🏢 **Análisis por Departamento**: Desglose completo con subcategorías
- 📏 **Análisis por Talla**: Distribución del inventario por tallas

### v2.1.2 (2025-11-28)

- 📚 **Documentación**: Agregada guía completa de solución de problemas
  - Nuevo archivo [TROUBLESHOOTING.md](TROUBLESHOOTING.md) con soluciones a todos los errores comunes
  - Nuevo archivo [QUICKSTART.md](QUICKSTART.md) para inicio rápido en menos de 5 minutos
  - Scripts de instalación automática para Windows ([install_dependencies.bat](install_dependencies.bat)) y Linux/Mac ([install_dependencies.sh](install_dependencies.sh))
- 🔧 **Compatibilidad**: Actualizado `requirements.txt` para compatibilidad con Python 3.14+
  - Werkzeug actualizado a 3.0.0 (soluciona error `AttributeError: module 'ast' has no attribute 'Str'`)
  - pydantic cambiado a `>=2.9.2` para usar binarios precompilados (evita necesidad de Rust)
- 📖 **README**: Actualizado con referencias a nueva documentación y scripts de instalación

### v2.1.1 (2025-11-21)

- 🐛 **Bug Fix**: Corregido error en endpoints de análisis de productos con rangos de fechas
  - Arreglado problema donde los parámetros `start_date` y `end_date` causaban error `strptime() argument 1 must be str, not datetime.date`
  - Afectaba a todos los endpoints de productos: `/api/products/analysis`, `/api/products/analysis/pdf`, `/api/products/top-sellers`, `/api/products/categories`, `/api/products/summary`
  - Ahora los endpoints pasan strings directamente a `get_all_invoices_in_range()` en lugar de objetos `datetime.date`
  - Validación mejorada de formato de fechas antes de procesamiento
- ✅ Todos los endpoints de productos ahora funcionan correctamente con rangos de fechas

### v2.1.0 (2025-11-19)

- ✨ Sistema de autenticación JWT completo
- ✨ Endpoints de login y verificación de token
- ✨ Middlewares de autenticación (`@token_required`, `@role_required`)
- ✨ Control de intentos de login con bloqueo temporal
- ✨ Scripts utilitarios para generar claves y crear admin
- ✨ Modelo de usuario para base de datos
- ✨ Análisis completo de productos vendidos con reportes JSON y PDF
- ✨ Top productos más vendidos con unificación de variantes
- ✨ Análisis por categorías de productos
- 🔒 Mejoras de seguridad en configuración

### v2.0.0 (2025-11-14)

- ✨ Refactorización completa con arquitectura modular
- ✨ Validación con Pydantic
- ✨ Logging profesional
- ✨ Tests unitarios
- ✨ Documentación Swagger
- ✨ Rate limiting y Health checks
- ✨ Soporte Docker

### v1.0.0

- Primera versión funcional (monolítica)

---

## 📧 Soporte

Email: koaj.puertocarreno@gmail.com

---

**Sistema de Cierre de Caja KOAJ v2.0 🎉**
