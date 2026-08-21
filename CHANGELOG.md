# Changelog - Cierre de Caja API (Backend)

---

## [2026-08-21] - Re-verificación del cambio del 2026-08-19 (sin cambios de código)

### ✅ Re-confirmado localmente, todo sigue pasando
- 33/33 tests unitarios, 13/13 checks funcionales, sin regresiones. No hubo cambios de código en esta sesión.

### ⚠️ Hallazgo: Render no había desplegado el commit `2678c9d`
- Dos días después del push del 2026-08-19, `GET https://cierre-caja-api.onrender.com/health` seguía respondiendo el JSON **sin** el campo `"database"` y sin el header `X-Request-Id` — es decir, el código en producción seguía siendo el anterior al commit `2678c9d`, pese a que el push a `main` fue exitoso
- No se pudo determinar la causa exacta (sin acceso al dashboard/API de Render desde este entorno): puede ser Auto-Deploy desactivado, un build fallido servido en silencio, o el webhook de GitHub desconectado
- Se agregó una sección nueva a [TROUBLESHOOTING.md](TROUBLESHOOTING.md#cómo-verificar-que-render-desplegó-los-últimos-cambios) con el procedimiento para verificar esto en el futuro antes de asumir que un push ya está en producción

---

## [2026-08-19] - Arranque seguro, caché/retries hacia Alegra, logging estructurado y health check extendido

### 🛡️ Validación de configuración al arrancar (`app/config.py`, `app/__init__.py`)
- `Config.validate()` (chequeos de negocio: `ALEGRA_USER`, `ALEGRA_PASS`, `BASE_OBJETIVO`, `UMBRAL_MENUDO`) ahora se invoca en `create_app()`, junto con el nuevo `Config.validate_security()` (chequea que `SECRET_KEY`/`JWT_SECRET_KEY` no sigan en su valor por defecto)
- En producción (`DEBUG=False`), si falta algo crítico el arranque se aborta con `RuntimeError` en vez de quedar "roto" en silencio; en DEBUG/TESTING solo advierte por log
- **Importante:** `Config.validate()` (sin `_security`) se sigue usando tal cual en `app/routes/cash_closing.py` en cada request de `/api/sum_payments` — los checks de secretos viven aparte en `validate_security()` para no bloquear cada cierre de caja solo porque `SECRET_KEY`/`JWT_SECRET_KEY` no estén rotados. (Este fue un bug real detectado y corregido durante las pruebas de esta misma sesión: la primera versión mezclaba ambos checks en `validate()` y hacía que `/api/sum_payments` devolviera 500 en cualquier entorno sin esas dos variables seteadas explícitamente.)

### ⚡ Caché + reintentos con backoff hacia Alegra (`app/services/alegra_client.py`, nuevo `app/utils/ttl_cache.py`)
- `get_invoices_by_date()` cachea en memoria las facturas de fechas **pasadas** (el día actual NUNCA se cachea, porque sigue recibiendo ventas) — TTL configurable vía `ALEGRA_CACHE_TTL_SECONDS` (default 600s)
- Reintentos automáticos con backoff exponencial (adaptador `urllib3.Retry` montado en la sesión de `requests`) para peticiones GET ante timeouts, errores de conexión y HTTP 429/500/502/503/504 — nunca reintenta POST/PUT/DELETE, para evitar duplicar operaciones

### 📋 Logging estructurado JSON + Sentry opcional (nuevo `app/utils/logging_utils.py`)
- Cada request recibe un `request_id` (header `X-Request-Id`, generado o propagado si el cliente ya lo manda) correlacionado en todos sus logs
- Formato controlado por `LOG_FORMAT` (default `json` en producción, `text` en DEBUG)
- `setup_sentry()` en `app/__init__.py`: se activa solo si se define `SENTRY_DSN`; si `sentry-sdk` no está instalado no rompe el arranque. Se agregó `sentry-sdk[flask]==2.18.0` a `requirements.txt`

### 🩺 `/health` extendido (`app/routes/health.py`)
- Ahora también verifica conectividad a la base de datos (`SELECT 1`) además del check de Alegra que ya existía

### 🧪 Fix de tests preexistentes (no relacionado a los cambios de arriba)
- `tests/test_cash_calculator.py`: `test_aplicar_ajustes` y `test_calcular_venta_efectivo_alegra` esperaban una fórmula vieja (restar gastos/préstamos) que ya no coincide con la lógica actual documentada como "Escenario A" en `cash_calculator.py` (gastos y préstamos ya se sacan físicamente del efectivo ANTES de contar, así que no se vuelven a restar). Se actualizaron las expectativas de ambos tests para que coincidan con el comportamiento real y documentado del código — no se tocó `cash_calculator.py`.

### ✅ Verificación realizada
- `pytest` no se pudo correr en este entorno por un bug pre-existente del runner en Windows (ver [TROUBLESHOOTING.md](TROUBLESHOOTING.md#pytest-falla-con-io-operation-on-closed-file), reproducible en código sin modificar). Se corrieron los tests unitarios puros (`test_cash_calculator.py`, `test_formatters.py`, `test_knapsack_solver.py`) mediante un script manual: **33/33 pasaron**.
- Pruebas funcionales manuales con `app.test_client()` contra una base SQLite temporal: `/health` (con y sin DB/Alegra simulando fallos), login correcto/incorrecto/usuario inexistente/email inválido, `/auth/verify` con y sin token, ruta protegida por rol (`/api/users`), y `/api/sum_payments` con credenciales de Alegra inválidas (confirma que devuelve un error controlado — 502 — en vez de un 500 sin manejar). **13/13 checks pasaron** (tras corregir el bug de `validate()` descrito arriba).
- Caché y retry de `AlegraClient` verificados con un script que mockea `session.get`: confirma 1 sola llamada HTTP para 2 consultas de una fecha pasada (cache hit), y que el día actual nunca se sirve desde caché.

---

## Notas Técnicas
- Backend: Python 3.14.3, Flask 2.2.5, Gunicorn 22.0.0
- Ver [README.md](README.md) para instalación y [TROUBLESHOOTING.md](TROUBLESHOOTING.md) para problemas comunes de entorno
