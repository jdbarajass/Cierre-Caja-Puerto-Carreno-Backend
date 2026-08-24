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

## Notas
- Documento creado el 2026-08-24 a partir de la auditoría técnica y las mejoras ya implementadas el 2026-08-19 (ver [CHANGELOG.md](CHANGELOG.md))
- Ver también la lista de mejoras pendientes del frontend en `MEJORAS_PENDIENTES.md` del repo `Cierre-Caja-Puerto-Carreno-Frontend`
