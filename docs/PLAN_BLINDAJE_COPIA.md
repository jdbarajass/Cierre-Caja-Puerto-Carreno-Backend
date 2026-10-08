# Blindaje de la copia de facturas (2026-10-08)

## Por qué

En oct-2026 se anularon en Alegra, de forma masiva y por impuestos, las facturas POS de 2025 (ver `PLAN_RECONSTRUCCION_2025.md`). Alegra quedó mostrando ventas, clientes y prendas de 2025 muy por debajo de lo real y hubo que reconstruirlas.

El usuario avisó que **el año siguiente puede pasar lo mismo con facturas de 2026**, en un momento puntual. Pidió:

- Que la plataforma se base en **lo que ya tiene guardado** de 2026 y no en el bajón de Alegra.
- Que **solo** la anulación masiva cuente como venta. Las anulaciones reales del año (una venta mal hecha, una devolución) deben seguir anuladas.

## Qué había antes

- Copia propia de las facturas desde el 1-ene-2026 (`InvoiceFact`, prendas en `InvoiceItemFact`, prendas de anuladas en `InvoiceVoidItem`), cargada cada noche a las 9 pm (`.github/workflows/daily-accounts-sync.yml`, paso "Cargar resumen de facturas": últimos 3 días + 31 faltantes).
- Un día ya guardado no se vuelve a descargar. **Excepción:** si sube `FACT_VERSION`, todos los días se recargan en las tandas.
- Las pantallas que leen Alegra en vivo solo corregían 2025:
  - Totales de Ventas, Documentos de Venta, Ventas Mensuales.
  - Analytics, Productos.
  - Comparativo de tiendas.
  - Resumen del Dashboard, comparación con el año anterior, Metas.

## Diseño: congelar la copia

El admin **congela** la copia hasta una fecha (por ejemplo, el 31-dic-2026) **antes** de la anulación masiva. Esto se hace en **Estadísticas → Respaldo de facturas**. Queda guardado por tienda en `app_settings` (`invoice_facts_freeze`).

### Pasos para el usuario

1. **Repasar todo (recomendado).**
   - `POST /api/facts-freeze/review` marca los días ya cargados hasta esa fecha (`fact_version = 0`).
   - Las tandas (`invoice-facts/sync`, la página o el cron) los vuelven a descargar **una vez**.
   - Así la copia recoge las anulaciones reales hechas más de 3 días después de la venta.
2. **Congelar.**
   - `POST /api/facts-freeze/freeze`, con la palabra `CONGELAR`.
   - Solo si no falta ningún día por cargar o repasar, solo hasta ayer, y solo para extender (no se puede reducir ni deshacer).

### Qué cambia después de congelar (y nada antes)

| Pieza | Cambio |
|---|---|
| `invoice_facts.sync_day` | Un día congelado que ya está guardado no se vuelve a descargar (devuelve lo que había) |
| `invoice_facts.pending_days` | Excluye los días congelados ya guardados, aunque suba `FACT_VERSION` |
| `payment_facts.sync_payments` | No borra ni reemplaza pagos por medio de facturas de días congelados |
| `history_2025.revive_mass_voided` / `revive_for_current_store` | En descargas de Alegra, las facturas de días congelados que Alegra trae anuladas y que la copia tenía vigentes vuelven a contar (marca `mass_voided`). Cubre Totales, Documentos, Ventas Mensuales, Analytics y Productos |
| `history_2025.live_revive_ids` | Lo mismo para el Comparativo, que corre en hilos. `revive_with_ids` solo revive las que vienen anuladas |
| `history_2025.real_sales_total` | Si todo el rango está congelado y completo, devuelve la venta de la copia. Lo usan el Dashboard, la comparación con el año anterior y Metas |
| `customer_insights` | Clientes nuevos/recurrentes e inactivas: la parte congelada del rango sale de la copia (`copy_client_rows`) y el resto de Alegra (`unfrozen_parts`). No se suma dos veces |
| Clientes (periodo), Prendas, Día y hora, Metas por vendedora, Cuentas → Año | Ya leían la copia: como no cambia, siguen igual |

Las anulaciones que ya estaban en la copia al congelar siguen anuladas: son las reales.

### Límite conocido

Si después de congelar se anula de verdad una factura de un día congelado (por ejemplo, una devolución en enero de una venta de diciembre), la copia la sigue contando. Para eso Alegra normalmente usa notas crédito, no anulación. Si hiciera falta, se agregaría una marca manual como la de 2025.

### Respaldo

`GET /api/facts-freeze/backup.xlsx?year=2026` descarga un Excel con 4 hojas:
- Información.
- Facturas (fecha, hora, número, electrónica, anulada, cliente con cédula, vendedora, subtotal, descuento, total, pagado).
- Prendas vendidas.
- Prendas de anuladas.

## Código y pruebas

- `app/services/facts_freeze.py`, `app/routes/facts_freeze.py` (solo admin), `tests/test_facts_freeze.py` (7 pruebas). La prueba simula: copia guardada, congelada, y luego Alegra anula todo. Revisa la copia, la venta real, Documentos, Comparativo, pagos, el repaso, clientes y el Excel.
- Frontend: `src/pages/FactsBackup.jsx` (`/estadisticas-estandar/respaldo-facturas`), `src/services/factsFreezeService.js`.

## Regla para el futuro

Cualquier cálculo nuevo que lea Alegra en vivo debe pasar sus facturas por `revive_for_current_store`, o por `revive_with_ids` con `live_revive_ids` si corre en hilos. Así cuenta tanto 2025 como lo congelado.
