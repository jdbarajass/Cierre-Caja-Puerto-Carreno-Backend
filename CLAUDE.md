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
- **Llegadas** (Estadísticas → Llegadas, Fase D1): `app/models/purchase_fact.py`, `app/services/purchase_facts.py`, `app/routes/arrivals.py`. Compras de mercancía (`/bills`) desde el 1-ene-2026, recargadas completas con la carga de facturas. La compra está al precio de VENTA (no costo).
- **Día y hora** (Fase D2): `app/services/sales_patterns.py`, `app/routes/sales_patterns.py`; usa `invoice_facts.hour`. `invoice_sync_days.fact_version` < `FACT_VERSION` = el día se recarga en las tandas (subir la versión cuando se agregue un dato nuevo a la copia).
- **Metas por vendedora** (Fase D3): `app/services/seller_goals.py`, `app/routes/seller_goals.py`, modelo `SellerGoal` (solo ajustes del admin). Automática = mismo mes del año anterior +15 % repartida por los 3 meses anteriores. Distinta de la meta del cierre de caja (+25 %).
- **Alertas diarias** (Fase D4): `app/services/daily_alerts.py`, `app/routes/daily_alerts.py`, modelo `DailyAlert`; las calcula el cron de las 9 pm (paso "Calcular alertas del día") y se ven en el Dashboard del admin.
- Al simular Alegra en tests, copiar el formato **real de /api/v1** (no el del conector MCP / reports-api v2): ese error dejó los montos en $0 en producción.

## Cuentas diarias (reemplazo del Excel KOAJ_CARRENO2026.xlsx)
- Plan, análisis del Excel, criterio contable y estado por fase: **`docs/PLAN_CUENTAS_DIARIAS.md`** (leerlo antes de seguir con la Fase 2).
- Fase 1 (Gastos): `app/models/expense.py`, `app/routes/expenses.py`, `tests/test_expenses.py`. `account_mode='caja'` = salió de la caja del día (el cierre ya lo descontó de EFECTIVO: no restar otra vez).
- Fase 2 (Mes): `app/models/month_sheet.py`, `app/services/payment_facts.py` (recibos de Alegra → 10 medios, festivos, llegada datáfono/Addi), `app/services/month_sheet.py`, `app/routes/month_sheet.py`, `tests/test_month_sheet.py`. Los pagos se cargan dentro de `invoice-facts/sync` (cron 9 pm).
- Fase 3 (Año): `app/models/monthly_summary.py`, `app/services/monthly_summary.py`, `app/routes/monthly_summary.py`, `tests/test_monthly_summary.py`. El inventario de fin de mes también se carga dentro de `invoice-facts/sync`.
- Fase 4 (metas e incentivos): `app/services/finance_settings.py` (config por tienda en `app_settings`), `app/models/incentive.py`, `app/routes/finance.py`, `tests/test_finance.py`; regla 70/30 en `monthly_summary.build_year`; gastos en `_operational_metrics` del comparativo.
- Guía para el usuario (sin términos técnicos): `docs/GUIA_CUENTAS_DIARIAS.md`.
- **Orden de las cuentas** (pedido del usuario, 2026-10-08): `sort_order` en `DEFAULT_ACCOUNTS` (EFECTIVO, QR, ADDI + DATÁFONO, NEQUI, DAVIPLATA, SisteCrédito, BBVA, AHORRO); `apply_account_order()` reordena una vez las existentes (bandera en `app_settings`, solo `sort_order`). Lo usan Gestión → Cuentas y Cuentas → Mes. Jhonatan (no es cuenta) lo ubica el frontend después de NEQUI.
- **Excedentes y sincronización (2026-10-08)**: plan y análisis del Excel de cierre en **`docs/PLAN_EXCEDENTES_Y_CARGA_EXCEL.md`**. `CashClosing.efectivo` es la plata física y ya trae `excedente_efectivo`; los demás medios no traen su excedente. Al sincronizar, ventas (`cash_closing`) y excedentes (`excedente`) van separados. Solo se sincroniza un cierre con `can_sync` (Cierre exitoso o cierre viejo sin estado). Los excedentes no son venta: nunca sumarlos a ventas/metas/incentivos. Fase 2 (subir el Excel para llenar el cierre): `app/services/closing_excel.py` + `POST /api/cash_closing/parse-excel`; busca las celdas por etiqueta, no guarda nada.

## Reconstrucción de 2025 (anulación masiva de POS, oct-2026)
- Plan, verificación en Alegra y reglas: **`docs/PLAN_RECONSTRUCCION_2025.md`**. Código: `app/services/history_2025.py`, `app/routes/history_2025.py`, `InvoiceVoidItem` / `VoidOverride` en `app/models/invoice_fact.py`, `tests/test_history_2025.py`.
- En 2025 **las facturas POS anuladas fueron ventas reales** (salvo las marcadas como anulación real): cualquier cálculo de 2025 debe usar `real_sales_total` / `mass_voided_ids`, no solo `voided=False` (consultas a la copia: `sale_condition`; facturas descargadas de Alegra: `revive_for_current_store`; dentro de hilos: `revive_with_ids` con los ids calculados antes). El inventario de Alegra está inflado hasta que se haga el ajuste (R3).

## Blindaje de la copia (congelar antes de una anulación masiva, 2026-10-08)
- Plan: **`docs/PLAN_BLINDAJE_COPIA.md`**. Código: `app/services/facts_freeze.py`, `app/routes/facts_freeze.py`, `tests/test_facts_freeze.py`.
- Con la copia congelada hasta una fecha, esos días **nunca** se vuelven a descargar de Alegra (ni subiendo `FACT_VERSION`) y lo que Alegra muestre anulado después cuenta como venta en las pantallas en vivo. Cualquier cálculo nuevo con facturas descargadas de Alegra debe pasar por `revive_for_current_store` (o `revive_with_ids` + `live_revive_ids` en hilos).

## Recordatorios del admin (2026-10-08)
- `app/services/reminders.py` (+ `app/routes/reminders.py`, `tests/test_reminders.py`): ventana emergente al entrar. Para agregar uno, escribir un `_builder(store, today)` que devuelva `{key, title, body, steps, path, action_label, done_label}` (o None) y sumarlo a `BUILDERS`. La `key` lleva el periodo (ej. `backup-2026-11`).
