# Mejoras Pendientes - Backend (Cierre de Caja API)

Lista de mejoras identificadas en la auditoría técnica del 2026-08-19 que **no** se implementaron todavía. Para cada una: qué cambio concreto hay que hacer, qué efectos/riesgos tiene hacerlo, y qué beneficio trae.

---

## 1. Migraciones versionadas con Alembic (Flask-Migrate)

**Qué cambiar:**
- Instalar `Flask-Migrate` (envuelve Alembic) y agregarlo a `requirements.txt`
- Generar una migración "baseline" que capture el esquema actual tal como existe hoy en producción (sin intentar recrear tablas existentes)
- Reemplazar el patrón manual `_migrate_employee_tables()` en `app/__init__.py` (que hace `ALTER TABLE ADD COLUMN` a mano en cada arranque) por migraciones versionadas: `flask db migrate` para generar, `flask db upgrade` para aplicar
- Correr `flask db upgrade` como paso del deploy en Render (build command o comando de arranque), en vez de dejar que `db.create_all()` cree tablas implícitamente

**Efectos de hacer este cambio:**
- Cambia el flujo de deploy: hay que agregar el paso de migración al build/start command de Render, y probarlo primero contra una copia de la base de datos de producción (Supabase/PostgreSQL) para confirmar que la migración baseline no intenta tocar columnas que ya existen
- Toca `app/__init__.py` (se elimina el bloque de `_migrate_employee_tables`), `requirements.txt`, y agrega una carpeta nueva `migrations/` con el historial de cambios de esquema
- Riesgo si se hace mal: una migración baseline incorrecta podría intentar recrear o alterar tablas con datos reales — por eso se recomienda generarla y revisarla manualmente antes de aplicarla en producción, y probar primero en un entorno con una copia de los datos

**Beneficios:**
- Historial real y versionado del esquema de la base de datos, con posibilidad de hacer rollback si una migración sale mal
- Reemplaza un patrón frágil (`ALTER TABLE` manual con comentarios de "agregar aquí futuros cambios") que depende de que alguien recuerde escribir el código correcto cada vez que se agrega una columna
- Reduce el riesgo de fallos silenciosos en producción cuando el esquema cambia (hoy, si una migración manual falla, solo se registra un `warning` en el log y la app sigue arrancando con el esquema desactualizado)

---

## 2. Ampliar cobertura de tests automatizados

**Qué cambiar:**
- Agregar tests para `app/routes/auth.py` (login exitoso, credenciales incorrectas, cuenta bloqueada por intentos fallidos, tokens expirados/inválidos)
- Agregar tests para `app/services/alegra_client.py` mockeando `requests` (sin llamar a la API real de Alegra) — cubrir el manejo de timeouts, errores 401/403/5xx, y la caché/retry agregados en la sesión del 2026-08-19
- Agregar tests para los middlewares (`token_required`, `role_required`, `role_required_any`)
- Agregar tests de al menos las rutas críticas de negocio que hoy no tienen ninguno: `users.py`, `direct_api.py`
- Activar medición real de cobertura con `pytest-cov` (ya está en `requirements-dev.txt` pero no se usa activamente en ningún comando/CI)

**Efectos de hacer este cambio:**
- No modifica código de producción, solo agrega archivos de test nuevos — riesgo bajo
- Hay que resolver primero (o rodear) el problema de `pytest` en este entorno local específico (ver [TROUBLESHOOTING.md](TROUBLESHOOTING.md#pytest-falla-con-io-operation-on-closed-file)) — probablemente no ocurra en un runner de CI como GitHub Actions, que sería el lugar ideal para correr estos tests automáticamente en cada push/PR
- También conviene renombrar `tests/test_analytics_endpoints.py` y `tests/test_size_analysis.py` (son scripts de prueba manual contra un servidor real, no tests automatizados) a algo como `manual_check_*.py`, para que pytest deje de intentar recolectarlos como si fueran tests

**Beneficios:**
- El módulo más crítico del negocio (autenticación de usuarios y conexión con Alegra) hoy no tiene ninguna red de seguridad automatizada — un cambio futuro podría romper el login o la integración contable sin que nadie se entere hasta que una vendedora reporte el problema
- Con CI configurado, cualquier PR futuro mostraría automáticamente si rompió algo, en vez de depender de pruebas manuales

---

## 3. Paralelizar la paginación de inventario contra Alegra

**Qué cambiar:**
- `AlegraDirectClient.get_inventory_value_report_paginated()` (`app/services/alegra_direct_client.py`) trae el inventario completo (hasta 3000 items) en páginas secuenciales de 200 items, una llamada HTTP a Alegra tras otra. Con el catálogo completo de la tienda, esto puede tomar más de 2 minutos.
- El 2026-09-02 se subió el timeout de Gunicorn de 120s a 240s (`Procfile`) como parche para que la petición no se corte a mitad de camino, pero la causa de fondo (paginación 100% secuencial) sigue igual.
- Alternativas a evaluar: paralelizar las páginas con `concurrent.futures`/`asyncio` (cuidado con el rate limit de Alegra, que es la razón por la que ya se usa `page_size=200` en vez de un límite mayor — ver comentario "para evitar error 503" en el código), o cachear el resultado completo por `to_date` con el mismo `ttl_cache.py` que ya existe para `alegra_client.py` (el inventario de un día pasado no cambia).

**Efectos de hacer este cambio:**
- Mientras esta consulta está en curso (con solo `--workers 2` en el Procfile), el resto del sistema (cierres de caja, login) queda con un solo worker libre para atender a todos los demás usuarios — en horario de tienda esto podría notarse
- Cualquier paralelización debe respetar el límite de tasa de Alegra (ya causó errores 503 antes con páginas más grandes)

**Beneficios:**
- Elimina el riesgo de que "Consultar Inventario" falle con un error crudo del servidor si el catálogo crece
- Libera antes los 2 workers de Gunicorn para el resto de usuarios del sistema

---

## Notas
- Documento creado el 2026-08-24 a partir de la auditoría técnica y las mejoras ya implementadas el 2026-08-19 (ver [CHANGELOG.md](CHANGELOG.md))
- Ítem 3 agregado el 2026-09-02 tras reproducir en producción un timeout de Gunicorn en "Consultar Inventario" durante una revisión de la sección Estadísticas
- Ver también la lista de mejoras pendientes del frontend en `MEJORAS_PENDIENTES.md` del repo `Cierre-Caja-Puerto-Carreno-Frontend`
