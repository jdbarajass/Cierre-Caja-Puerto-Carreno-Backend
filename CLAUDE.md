# Cierre-Caja-Puerto-Carreno-Backend

API Flask del sistema de cierre de caja KOAJ (Render, Postgres). Ver `README.md` (estructura), `QUICKSTART.md`, `TROUBLESHOOTING.md` y `CHANGELOG.md` (historia y decisiones por fase).

## Despliegue y reglas
- Render **no** despliega solo: después de cada push hay que hacer **Manual Deploy**. Las tablas nuevas las crea `db.create_all()` al arrancar; las migraciones de columnas viven en `app/__init__.py`.
- El repo es **público**: nunca escribir contraseñas, tokens ni cadenas de conexión en código ni documentación (variables de entorno, ver `.env.example`; los scripts las piden por consola).
- `tests/` solo tiene tests automáticos sin red. Los scripts que llaman a un servidor real van en `scripts/manual/` (no se llaman `test_*.py`). El `.gitignore` ignora `test_*.py`: los tests nuevos se agregan con `git add -f`.
- Correr tests: `venv/Scripts/python.exe -m pytest -q`. En el PC de la entidad (WMI de Windows colgado) Python se cuelga al importar SQLAlchemy: ver TROUBLESHOOTING.md ("Python / pytest se cuelgan al arrancar").

## Multi-tienda
`app/stores.py`: tienda activa por header `X-Store`, credenciales de Alegra por tienda (`ALEGRA_USER_<TIENDA>` / `ALEGRA_PASS_<TIENDA>`), `StoreScopedMixin` para modelos por tienda. Toda tabla o dato nuevo debe decidir si es por tienda o compartido.

## Dashboard de clientes (Estadísticas → Clientes)
- `app/services/customer_insights.py` + `app/routes/customer_insights.py`: `GET /api/analytics/customers/summary` e `/inactive` (solo admin, por tienda). Documentado en `ANALYTICS_API_DOCUMENTATION.md` (sección 8).
- **Dos fuentes:**
  - `source='facts'`: si todos los días cerrados del periodo están en `invoice_facts`, se calcula con ellos + las ventas de hoy en vivo. Trae % con cliente por vendedora, descuentos (cliente, vendedora, equipo, facturas) y cédula.
  - `source='report'`: si falta algún día, reporte agregado `/api/v1/reports/sales-by-client`. **Límites verificados de /api/v1**: el monto viene en `total` (no `afterTaxes`), no trae cédula ni descuento y **no filtra por vendedora**. reports-api v2 (la web de Alegra) no acepta Basic (401).
  - Clientes nuevos/recurrentes e inactivas siempre usan el reporte (miran compras anteriores a 2026).
- **Facturas guardadas** (`app/models/invoice_fact.py`, `app/services/invoice_facts.py`, `app/routes/invoice_facts.py`): resumen de cada factura por tienda desde el 1-ene-2026, cargado con `AlegraClient.get_invoices_by_date`. Un día se reemplaza completo; si Alegra falla no se borra nada; una sola carga a la vez por tienda (`pg_try_advisory_lock` → 409). El cron de las 9 pm (`.github/workflows/daily-accounts-sync.yml`) recarga los últimos 3 días + 31 faltantes por noche.
- **Prendas guardadas** (`InvoiceItemFact`, Estadísticas → Prendas): se llenan en el mismo `sync_day`; `invoice_sync_days.items_synced` marca los días con prendas (los viejos se completan en las tandas sin afectar al dashboard de clientes, que solo mira `missing_days`). Indicadores en `app/services/garment_insights.py` (`/api/analytics/garments/summary` y `/stock`); la BOLSA PAPEL no cuenta. Plan y estado de Estadísticas: `docs/PLAN_ESTADISTICAS.md`.
- Al simular Alegra en tests, copiar el formato **real de /api/v1** (no el del conector MCP / reports-api v2): ese error dejó los montos en $0 en producción.
