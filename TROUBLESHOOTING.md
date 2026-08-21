# Guía de Solución de Problemas - Cierre de Caja API

Esta guía documenta todos los problemas comunes al levantar el servidor y cómo solucionarlos.

---

## Tabla de Contenidos

1. [Problemas con Dependencias](#problemas-con-dependencias)
2. [Problemas de Compatibilidad Python 3.14](#problemas-de-compatibilidad-python-314)
3. [Configuración de Variables de Entorno](#configuración-de-variables-de-entorno)
4. [Pasos para Levantar el Servidor Manualmente](#pasos-para-levantar-el-servidor-manualmente)
5. [pytest falla con "I/O operation on closed file"](#pytest-falla-con-io-operation-on-closed-file)
6. [Cómo verificar que Render desplegó los últimos cambios](#cómo-verificar-que-render-desplegó-los-últimos-cambios)

---

## Problemas con Dependencias

### Problema 1: ModuleNotFoundError: No module named 'flask_limiter'

**Error:**
```
ModuleNotFoundError: No module named 'flask_limiter'
```

**Causa:** Las dependencias no están instaladas.

**Solución:**
```bash
pip install -r requirements.txt
```

Si esto falla con errores de compilación, instalar dependencias manualmente:

```bash
# Instalar dependencias principales sin pydantic primero
pip install Flask==2.2.5 Werkzeug==2.2.3 flask-cors==4.0.0 Flask-Limiter==3.5.0 flasgger==0.9.7.1 python-dotenv==1.0.0 tzdata==2023.3 pytz==2023.3 python-dateutil==2.8.2 PyJWT==2.8.0 bcrypt==4.1.2 Flask-SQLAlchemy==3.1.1 email-validator==2.1.0 reportlab==4.0.7

# Luego instalar pydantic
pip install pydantic --upgrade
```

---

### Problema 2: Error al compilar pydantic-core (requiere Rust)

**Error:**
```
error: metadata-generation-failed
Cargo, the Rust package manager, is not installed or is not on PATH.
```

**Causa:** La versión específica de `pydantic==2.9.2` requiere compilación con Rust para `pydantic-core`.

**Solución:**

**Opción 1 (Recomendada):** Instalar versión más reciente con binarios precompilados:
```bash
pip install pydantic --upgrade
```

Esto instalará la versión más reciente (ej: 2.12.5) que tiene binarios precompilados para Windows.

**Opción 2:** Instalar Rust (si necesitas versión específica):
1. Descargar e instalar Rust desde https://rustup.rs/
2. Reiniciar terminal
3. Ejecutar: `pip install pydantic==2.9.2`

---

## Problemas de Compatibilidad Python 3.14

### Problema 3: AttributeError: module 'ast' has no attribute 'Str'

**Error completo:**
```
File "C:\...\werkzeug\routing\rules.py", line 751, in _parts
    parts = parts or [ast.Str("")]
                      ^^^^^^^
AttributeError: module 'ast' has no attribute 'Str'
```

**Causa:** Python 3.14 removió `ast.Str`. Werkzeug 2.2.3 no es compatible con Python 3.14.

**Solución:**

**Opción 1 (Recomendada):** Actualizar Werkzeug a versión compatible:
```bash
pip install Werkzeug==3.0.0
```

**Opción 2:** Usar Python 3.11 o 3.12 en lugar de 3.14:
```bash
# Crear entorno virtual con Python 3.11/3.12
python3.11 -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
```

---

## Configuración de Variables de Entorno

### Problema 4: Warning 'FLASK_ENV' is deprecated

**Warning:**
```
'FLASK_ENV' is deprecated and will not be used in Flask 2.3. Use 'FLASK_DEBUG' instead.
```

**Causa:** Flask 2.3+ deprecó la variable `FLASK_ENV` en favor de `FLASK_DEBUG`.

**Solución:**

Editar archivo `.env` y cambiar:
```bash
# Antiguo (deprecado)
FLASK_ENV=development

# Nuevo (recomendado)
FLASK_DEBUG=True
```

O actualizar [run.py](run.py:9) para usar `FLASK_DEBUG`:
```python
# En lugar de:
config_name = os.getenv('FLASK_ENV', 'production')

# Usar:
debug = os.getenv('FLASK_DEBUG', 'False').lower() == 'true'
config_name = 'development' if debug else 'production'
```

---

## Pasos para Levantar el Servidor Manualmente

Sigue estos pasos en orden si encuentras problemas:

### Paso 1: Verificar versión de Python

```bash
python --version
```

**Versiones compatibles:** Python 3.11, 3.12, 3.13
**Versión con problemas:** Python 3.14 (requiere Werkzeug 3.0.0+)

### Paso 2: Activar entorno virtual (si existe)

```bash
# Windows
venv\Scripts\activate

# Linux/Mac
source venv/bin/activate
```

### Paso 3: Instalar dependencias (método robusto)

```bash
# Paso 3.1: Instalar dependencias básicas (sin pydantic)
pip install Flask==2.2.5 flask-cors==4.0.0 Flask-Limiter==3.5.0 flasgger==0.9.7.1 python-dotenv==1.0.0 tzdata==2023.3 pytz==2023.3 python-dateutil==2.8.2 PyJWT==2.8.0 bcrypt==4.1.2 Flask-SQLAlchemy==3.1.1 email-validator==2.1.0 reportlab==4.0.7 requests==2.31.0 gunicorn==20.1.0 openpyxl==3.1.2 xlrd==2.0.1

# Paso 3.2: Instalar Werkzeug compatible con tu Python
# Para Python 3.14:
pip install Werkzeug==3.0.0

# Para Python 3.11-3.13:
pip install Werkzeug==2.2.3

# Paso 3.3: Instalar pydantic
pip install pydantic --upgrade
```

### Paso 4: Verificar archivo .env

Asegúrate de que el archivo `.env` existe y contiene:

```bash
# Credenciales Alegra (CRÍTICO)
ALEGRA_USER=tu-email@alegra.com
ALEGRA_PASS=tu-token-api

# Configuración servidor
HOST=10.28.168.57
PORT=5000
DEBUG=False

# JWT Secret (generar con: python scripts/generate_jwt_secret.py)
JWT_SECRET_KEY=tu-clave-secreta-segura-de-64-caracteres

# Base de datos (opcional si no usas autenticación)
DATABASE_URL=sqlite:///instance/cierre_caja.db
```

### Paso 5: Levantar el servidor

```bash
python run.py
```

**Salida esperada:**
```
INFO in alegra_client: Cliente Alegra inicializado para usuario: tu-email@alegra.com
INFO in __init__: ============================================================
INFO in __init__: Sistema de Cierre de Caja - KOAJ Puerto Carreño
INFO in __init__: Versión: 2.0.0
INFO in __init__: Ambiente: Producción
INFO in __init__: ============================================================
INFO in run: Iniciando servidor en 10.28.168.57:5000
INFO in run: Modo debug: False
 * Serving Flask app 'app'
 * Debug mode: off
```

### Paso 6: Verificar que funciona

Abre en navegador o usa curl:

```bash
# Health check
curl http://10.28.168.57:5000/health

# Documentación API
# Navegar a: http://10.28.168.57:5000/api/docs
```

Respuesta esperada:
```json
{
  "status": "healthy",
  "service": "cierre-caja-api",
  "version": "2.0.0",
  "alegra": "connected"
}
```

---

## Resumen de Versiones Compatibles

### Para Python 3.14:
```
Flask==2.2.5
Werkzeug==3.0.0  # ← IMPORTANTE: Usar versión 3.x
pydantic>=2.12.5  # ← Versión con binarios precompilados
Flask-Limiter==3.5.0
flask-cors==4.0.0
# ... resto igual
```

### Para Python 3.11-3.13:
```
Flask==2.2.5
Werkzeug==2.2.3  # ← Versión original funciona bien
pydantic==2.9.2  # ← O superior
Flask-Limiter==3.5.0
flask-cors==4.0.0
# ... resto igual
```

---

## Script de Instalación Automática

Puedes usar este script para instalar todo automáticamente:

```bash
# install.bat (Windows)
@echo off
echo Instalando dependencias del servidor...

echo Paso 1: Instalando dependencias base...
pip install Flask==2.2.5 flask-cors==4.0.0 Flask-Limiter==3.5.0 flasgger==0.9.7.1 python-dotenv==1.0.0 tzdata==2023.3 pytz==2023.3 python-dateutil==2.8.2 PyJWT==2.8.0 bcrypt==4.1.2 Flask-SQLAlchemy==3.1.1 email-validator==2.1.0 reportlab==4.0.7 requests==2.31.0 gunicorn==20.1.0 openpyxl==3.1.2 xlrd==2.0.1

echo Paso 2: Instalando Werkzeug compatible...
pip install Werkzeug==3.0.0

echo Paso 3: Instalando pydantic...
pip install pydantic --upgrade

echo Instalación completada!
echo Para iniciar el servidor ejecuta: python run.py
pause
```

```bash
# install.sh (Linux/Mac)
#!/bin/bash
echo "Instalando dependencias del servidor..."

echo "Paso 1: Instalando dependencias base..."
pip install Flask==2.2.5 flask-cors==4.0.0 Flask-Limiter==3.5.0 flasgger==0.9.7.1 python-dotenv==1.0.0 tzdata==2023.3 pytz==2023.3 python-dateutil==2.8.2 PyJWT==2.8.0 bcrypt==4.1.2 Flask-SQLAlchemy==3.1.1 email-validator==2.1.0 reportlab==4.0.7 requests==2.31.0 gunicorn==20.1.0 openpyxl==3.1.2 xlrd==2.0.1

echo "Paso 2: Instalando Werkzeug compatible..."
pip install Werkzeug==3.0.0

echo "Paso 3: Instalando pydantic..."
pip install pydantic --upgrade

echo "Instalación completada!"
echo "Para iniciar el servidor ejecuta: python run.py"
```

---

## pytest falla con "I/O operation on closed file"

**Error:**
```
File "...\_pytest\capture.py", line X, in snap
    self.tmpfile.seek(0)
ValueError: I/O operation on closed file.
1 error in ~22s
```

**Causa:** Es un problema **del entorno** (Windows + Python 3.14 + captura de stdout/stderr de pytest en ciertos runners/terminales), no del código del proyecto. Se confirmó reproducible incluso en checkouts limpios sin modificar, con distintas versiones de pytest (7.4.3 y 9.0.3) y tanto desde `venv/` como desde el Python global. Siempre ocurre alrededor de los ~22 segundos, lo que sugiere que algo externo al proceso de pytest (el propio terminal/runner) interfiere con el descriptor de archivo usado para la captura.

También hay que tener en cuenta que `tests/test_analytics_endpoints.py` y `tests/test_size_analysis.py` **no son tests automatizados reales**: son scripts de prueba manual pensados para ejecutarse contra un servidor local ya corriendo (`http://localhost:5000`) con credenciales reales, pero sus funciones se llaman `test_*` y por eso pytest las intenta recolectar igual. Si se decide arreglar esto a futuro, lo correcto sería renombrarlos (ej. `manual_check_analytics.py`) para que pytest deje de recolectarlos.

**Solución (mientras tanto):**
- Ejecutar los tests unitarios puros (`test_cash_calculator.py`, `test_formatters.py`, `test_knapsack_solver.py`) importándolos directamente en un script Python en vez de vía `pytest`, por ejemplo instanciando cada clase `Test*` y llamando sus métodos `test_*` manualmente.
- Para probar rutas/endpoints, usar `app.test_client()` directamente en un script (como hace `conftest.py`), sin pasar por el runner de pytest.
- Si en tu máquina pytest sí funciona normalmente, ignora esta sección — es específico de ciertos entornos.

---

## Cómo verificar que Render desplegó los últimos cambios

**Importante:** un `git push` exitoso a `main` **no garantiza** que Render haya desplegado el cambio. El 2026-08-21 se detectó que el commit `2678c9d` (pusheado el 2026-08-19) seguía sin estar en producción dos días después — Render seguía sirviendo la versión anterior.

**Cómo comprobarlo:** pedir `GET /health` a la URL de producción y revisar si la respuesta refleja el cambio esperado. Ejemplo (a partir del commit `2678c9d`, el JSON debe incluir el campo `"database"` y la respuesta debe traer el header `X-Request-Id`):

```bash
curl -sI https://cierre-caja-api.onrender.com/health | grep -i x-request-id
curl -s https://cierre-caja-api.onrender.com/health
```

Si no aparecen los campos/headers esperados del último commit, el deploy no se aplicó. Revisar en el dashboard de Render:
1. Que el servicio tenga **Auto-Deploy** activado y apuntando a la rama `main`
2. La pestaña **Events/Deploys** para ver si el build más reciente falló o quedó pendiente
3. Si hace falta, disparar un **Manual Deploy** desde el dashboard

---

## Contacto y Soporte

Si continúas teniendo problemas después de seguir esta guía:

1. Verifica los logs en `logs/cierre_caja.log`
2. Revisa las variables de entorno en `.env`
3. Consulta la documentación en [README.md](README.md)
4. Email: koaj.puertocarreno@gmail.com

---

**Última actualización:** 2025-11-28
**Versión del documento:** 1.0.0
