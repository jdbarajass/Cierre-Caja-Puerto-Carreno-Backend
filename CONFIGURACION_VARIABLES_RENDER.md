# 📝 Configuración de Variables de Entorno en Render

**Fecha:** 17 de Noviembre, 2025
**Proyecto:** cierre-caja-api

---

## 📊 Resumen del Análisis

Se compararon las variables de entorno configuradas en Render con las que tiene el proyecto localmente. Se encontró que **faltan varias variables importantes** que son necesarias para el correcto funcionamiento de la aplicación en producción.

---

## ✅ Variables que YA TIENES en Render (correctas)

Estas variables ya están configuradas correctamente en Render:

| Variable | Valor | Estado |
|----------|-------|--------|
| `ALEGRA_USER` | koaj.puertocarreno@gmail.com | ✅ Correcto |
| `ALEGRA_PASS` | 31da3f1f57261b590130 | ✅ Correcto |
| `FLASK_ENV` | production | ✅ Correcto |

---

## ⚠️ PROBLEMA 1: ALLOWED_ORIGINS incompleto

### Estado Actual en Render:
```
https://jdbarajass.pythonanywhere.com,http://localhost:5173,http://localhost:5174,http://10.28.168.57:5000
```

### ❌ Problema:
Falta incluir la URL de tu propio backend en Render: `https://cierre-caja-api.onrender.com`

### ✅ Valor Correcto (actualizar):
```
https://jdbarajass.pythonanywhere.com,https://cierre-caja-api.onrender.com,http://localhost:5173,http://localhost:5174
```

### 🤔 ¿Para qué sirve ALLOWED_ORIGINS?
CORS (Cross-Origin Resource Sharing) es un mecanismo de seguridad que controla qué dominios pueden hacer peticiones a tu API. Esta variable lista los dominios permitidos:

- `https://jdbarajass.pythonanywhere.com` - Tu aplicación frontend en PythonAnywhere
- `https://cierre-caja-api.onrender.com` - Tu propio backend (para llamadas internas)
- `http://localhost:5173` - Desarrollo local (Vite)
- `http://localhost:5174` - Desarrollo local alternativo

**Nota:** Las URLs locales (localhost) están bien para desarrollo, pero en producción solo se usarán las URLs HTTPS.

---

## ➕ Variables FALTANTES que debes AGREGAR en Render

### 1. ALEGRA_API_BASE_URL
```
ALEGRA_API_BASE_URL=https://api.alegra.com/api/v1
```
**¿Para qué sirve?**
Define la URL base de la API de Alegra. Tu aplicación usa esta URL para hacer todas las peticiones a Alegra (obtener facturas, ventas, etc.). Sin esta variable, la app no sabrá dónde conectarse.

---

### 2. ALEGRA_TIMEOUT
```
ALEGRA_TIMEOUT=30
```
**¿Para qué sirve?**
Define cuántos segundos esperar antes de cancelar una petición a Alegra que no responde. 30 segundos es un tiempo razonable para no dejar colgada la aplicación si Alegra está lento.

---

### 3. BASE_OBJETIVO
```
BASE_OBJETIVO=450000
```
**¿Para qué sirve?**
Es la cantidad base (en pesos) que debe quedar en caja. Tu aplicación usa este valor para calcular cuánto dinero se debe retirar de la caja al final del día, dejando siempre esta base mínima.

**Ejemplo:**
- Si hay $800,000 en caja
- Y BASE_OBJETIVO es $450,000
- Entonces se pueden retirar $350,000

---

### 4. UMBRAL_MENUDO
```
UMBRAL_MENUDO=10000
```
**¿Para qué sirve?**
Define el valor máximo (en pesos) para considerar un billete o moneda como "menudo". Todo lo que sea menor o igual a $10,000 se considera menudo.

**Ejemplo:**
- Billetes de $1,000, $2,000, $5,000, $10,000 → Menudo ✅
- Billetes de $20,000, $50,000, $100,000 → No menudo ❌

Esto ayuda a separar y contabilizar el efectivo de forma organizada.

---

### 5. TIMEZONE
```
TIMEZONE=America/Bogota
```
**¿Para qué sirve?**
Define la zona horaria de Colombia para que todas las fechas y horas se muestren correctamente. Sin esto, las fechas podrían aparecer en UTC (hora de Londres) en lugar de hora colombiana.

**Ejemplo:**
- Con TIMEZONE: "2025-11-17 14:30:00" (hora Colombia)
- Sin TIMEZONE: "2025-11-17 19:30:00" (hora UTC, 5 horas adelante)

---

### 6. SECRET_KEY (MUY IMPORTANTE) 🔐
```
SECRET_KEY=ff357dfef89b09bf2356f87559cc7a4bf29ef79c382b0ca6fefa30cef346335e
```

**¿Para qué sirve?**
Es una clave secreta que Flask usa para:
1. **Firmar sesiones de usuario** - Para mantener sesiones seguras
2. **Cifrar cookies** - Protege la información en cookies
3. **Tokens CSRF** - Previene ataques de falsificación de peticiones
4. **Cualquier operación criptográfica** - Firma y verifica datos

**⚠️ MUY IMPORTANTE:**
- **Debe ser única y aleatoria** - Nunca uses claves predecibles
- **Debe ser secreta** - No la compartas públicamente
- **Debe ser diferente en cada ambiente** - Una para desarrollo, otra para producción
- **No debe cambiar** - Si la cambias, invalidas todas las sesiones activas

**Opciones generadas para ti (elige UNA):**
```
Opción 1: ff357dfef89b09bf2356f87559cc7a4bf29ef79c382b0ca6fefa30cef346335e
Opción 2: 9370bffdee5409689b16d4246f546a4688f3697d5916b57af2b78f452a262433
Opción 3: 136d729c523277bb265f6a5e290c87aca36793542098c0937a0fd926d51e4bd7
```

**Cómo se usa:**
Flask la usa automáticamente en segundo plano. Solo necesitas configurarla como variable de entorno y Flask se encarga del resto. Tu código no necesita hacer nada especial.

---

### 7. RATELIMIT_STORAGE_URL (OPCIONAL)
```
RATELIMIT_STORAGE_URL=memory://
```
**¿Para qué sirve?**
Controla dónde se almacena la información de rate limiting (límites de peticiones). `memory://` significa que se guarda en memoria RAM. Es suficiente para empezar.

**Alternativas:**
- `memory://` - Para desarrollo o apps pequeñas (se pierde al reiniciar)
- `redis://...` - Para producción con múltiples servidores (persistente)

---

### 8. RATELIMIT_DEFAULT (OPCIONAL)
```
RATELIMIT_DEFAULT=200 per day;50 per hour
```
**¿Para qué sirve?**
Limita cuántas peticiones puede hacer un usuario a tu API para evitar abuso:
- Máximo 200 peticiones por día
- Máximo 50 peticiones por hora

Si un usuario excede estos límites, recibirá un error 429 (Too Many Requests).

**Ejemplo:**
Si alguien intenta hacer 51 peticiones en una hora, la petición 51 será rechazada.

---

## 📋 CHECKLIST COMPLETO - Variables en Render

Copia y pega estas variables en la configuración de Render:

### ✅ Variables a ACTUALIZAR:

1. **ALLOWED_ORIGINS** (modificar la existente):
   ```
   https://jdbarajass.pythonanywhere.com,https://cierre-caja-api.onrender.com,http://localhost:5173,http://localhost:5174
   ```

### ➕ Variables a AGREGAR (nuevas):

2. **ALEGRA_API_BASE_URL**:
   ```
   https://api.alegra.com/api/v1
   ```

3. **ALEGRA_TIMEOUT**:
   ```
   30
   ```

4. **BASE_OBJETIVO**:
   ```
   450000
   ```

5. **UMBRAL_MENUDO**:
   ```
   10000
   ```

6. **TIMEZONE**:
   ```
   America/Bogota
   ```

7. **SECRET_KEY** (elige una de las opciones generadas):
   ```
   ff357dfef89b09bf2356f87559cc7a4bf29ef79c382b0ca6fefa30cef346335e
   ```

8. **RATELIMIT_STORAGE_URL** (opcional):
   ```
   memory://
   ```

9. **RATELIMIT_DEFAULT** (opcional):
   ```
   200 per day;50 per hour
   ```

---

## 🎯 Pasos para Agregar Variables en Render

1. Ve a tu dashboard de Render
2. Selecciona tu servicio: **cierre-caja-api**
3. Ve a **Environment** en el menú lateral
4. Haz clic en **Edit** (botón superior derecho)
5. Para cada variable:
   - Haz clic en **Add Environment Variable**
   - Escribe el nombre de la variable (KEY)
   - Escribe el valor (VALUE)
6. Haz clic en **Save Changes**
7. Render reiniciará automáticamente tu servicio con las nuevas variables

---

## 📊 Tabla Resumen de TODAS las Variables

| Variable | Valor | Estado | Prioridad |
|----------|-------|--------|-----------|
| FLASK_ENV | production | ✅ Ya existe | Alta |
| ALEGRA_USER | koaj.puertocarreno@gmail.com | ✅ Ya existe | Alta |
| ALEGRA_PASS | 31da3f1f57261b590130 | ✅ Ya existe | Alta |
| ALEGRA_API_BASE_URL | https://api.alegra.com/api/v1 | ➕ Agregar | Alta |
| ALEGRA_TIMEOUT | 30 | ➕ Agregar | Media |
| BASE_OBJETIVO | 450000 | ➕ Agregar | Alta |
| UMBRAL_MENUDO | 10000 | ➕ Agregar | Alta |
| ALLOWED_ORIGINS | (ver arriba) | 🔄 Actualizar | Alta |
| TIMEZONE | America/Bogota | ➕ Agregar | Alta |
| SECRET_KEY | (elige una opción) | ➕ Agregar | Alta |
| RATELIMIT_STORAGE_URL | memory:// | ➕ Agregar | Baja |
| RATELIMIT_DEFAULT | 200 per day;50 per hour | ➕ Agregar | Baja |

---

## ⚠️ Variables que NO debes agregar en Render

Estas variables son solo para desarrollo local:

- ❌ `HOST` - Render lo maneja automáticamente
- ❌ `PORT` - Render lo asigna automáticamente
- ❌ `DEBUG=True` - NUNCA en producción (es inseguro)

---

## 🔒 Seguridad - Buenas Prácticas

1. ✅ **SECRET_KEY debe ser única** - Usa una de las generadas
2. ✅ **FLASK_ENV=production** - Ya lo tienes correcto
3. ✅ **No incluir DEBUG** - Correcto, no lo agregues
4. ✅ **ALLOWED_ORIGINS específico** - Solo dominios confiables
5. ✅ **Credenciales como variables** - Nunca en el código

---

## 📁 Archivos Relacionados

- **generate_secret_key.py** - Script para generar nuevas SECRET_KEY si las necesitas
- **.env** - Variables locales (NO subir a Git)
- **.env.example** - Plantilla de variables (SÍ está en Git)

---

## 🆘 Si algo falla después de agregar las variables

1. Revisa los logs en Render (pestaña "Logs")
2. Verifica que no haya espacios extra en los valores
3. Asegúrate de haber guardado los cambios
4. Espera a que Render reinicie completamente (puede tomar 1-2 minutos)
5. Prueba hacer una petición a tu API

---

## ✨ Resultado Final

Después de agregar todas estas variables, tu aplicación en Render tendrá:

- ✅ Conexión completa con Alegra
- ✅ Configuración de negocio correcta
- ✅ CORS configurado para todos tus dominios
- ✅ Zona horaria de Colombia
- ✅ Seguridad con SECRET_KEY
- ✅ Rate limiting para prevenir abuso (opcional)

---

**¡Todo listo para producción! 🚀**

---

*Generado el: 17 de Noviembre, 2025*
*Proyecto: cierre-caja-api*
*Backend: Flask + Alegra API*
