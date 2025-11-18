# API de Cierre de Caja - KOAJ Puerto Carreño

Sistema backend para procesamiento de cierres de caja con integración a Alegra.

## Versión 2.0 - Arquitectura Mejorada

Esta versión incluye una refactorización completa del código con mejores prácticas, arquitectura modular, validación robusta y documentación completa.

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

---

## 🏗️ Arquitectura

```
cierre-caja-api/
├── app/
│   ├── __init__.py           # Factory de Flask
│   ├── config.py             # Configuración centralizada
│   ├── exceptions.py         # Excepciones custom
│   ├── routes/               # Endpoints de la API
│   │   ├── cash_closing.py   # Endpoint principal
│   │   └── health.py         # Health check
│   ├── services/             # Lógica de negocio
│   │   ├── alegra_client.py  # Cliente API Alegra
│   │   ├── cash_calculator.py# Calculador de caja
│   │   └── knapsack_solver.py# Algoritmo DP
│   ├── models/               # Schemas Pydantic
│   │   ├── requests.py       # Request models
│   │   └── responses.py      # Response models
│   └── utils/                # Utilidades
│       ├── formatters.py     # Formateo de datos
│       ├── validators.py     # Validaciones
│       └── timezone.py       # Manejo de zonas horarias
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

```bash
pip install -r requirements.txt

# Para desarrollo (incluye herramientas de testing)
pip install -r requirements-dev.txt
```

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
pip install -r requirements.txt

# 3. Ejecutar servidor
python run.py
```

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

#### 3. GET /health

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

- `ALEGRA_USER`: Usuario/email de Alegra
- `ALEGRA_PASS`: Token de API de Alegra
- `SECRET_KEY`: Clave secreta de Flask
- `ALEGRA_API_BASE_URL`: URL base de la API de Alegra
- `BASE_OBJETIVO`: Monto base que debe quedar en caja (por defecto: 450000)
- `UMBRAL_MENUDO`: Valor máximo para considerar un billete/moneda como menudo (por defecto: 10000)
- `TIMEZONE`: Zona horaria (por defecto: America/Bogota)

Ver `.env.example` para todas las variables disponibles.

### 📖 Documentación Adicional

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
