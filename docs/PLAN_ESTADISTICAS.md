# Plan: revisión y arreglos de la sección Estadísticas

Estado al 2026-10-02. Auditoría inicial solo de lectura del código; luego verificado con el conector de Alegra. **Fases A, B y C (C1-C4) hechas** (errores 1-11 y los 2 pendientes que salieron en la A, ver CHANGELOG). Las fases se hacen en orden, cada una con aprobación del usuario.

Secciones revisadas (menú Estadísticas): Totales de Ventas, Documentos de Venta, Analytics Avanzado, Análisis de Productos, Análisis de Inventario. (Clientes y Comparativo de tiendas son nuevos y ya fueron revisados en producción: ver CHANGELOG.)

## Errores confirmados en el código

| # | Sección | Error | Dónde |
|---|---|---|---|
| ✅ 1 | Inventario | Las pestañas (Alertas, ABC, Top, Categoría/Talla; Dashboard y Departamentos con botón) **ignoran** el `data` que les pasa la página y llaman `/api/inventory/*`, que usa `AlegraClient.get_active_items()` **sin paginación** → Alegra devuelve máx. 30 ítems. Solo el resumen de arriba (value-report, hasta 3000) es completo. | Front: `src/components/inventory/*.jsx` (declarados `() =>`, sin props) y `UnifiedInventoryAnalysis.jsx`. Back: `app/services/alegra_client.py::get_active_items`, `app/routes/inventory.py` |
| ✅ 2 | Totales de Ventas | `doc.seller` es objeto `{id, name}` y se usa como texto → tabla de vendedores con una fila "[object Object]". | Front: `src/components/direct/DirectSalesTotals.jsx::analyzeMonthlyData` |
| ✅ 3 | Totales / Documentos | Si falla un día, `get_all_invoices_for_date_range` hace `break` y sigue → faltan días en silencio con `success: True`. | Back: `app/services/alegra_direct_client.py::get_all_invoices_for_date_range` |
| ✅ 4 | Totales / Documentos / Productos | Suman **facturas anuladas** (`status: void`). Cierre de caja y Analytics sí las filtran (`app/utils/formatters.py::filter_voided_invoices`). | Front: `DirectSalesTotals.jsx`, `DirectSalesDocuments.jsx`. Back: `app/routes/products.py` + `app/services/product_analytics.py` |
| ✅ 5 | Analytics → Retención | `if recency > 90 ... elif recency > 180` → "Inactivo" nunca se asigna. "Nuevo" = 1 compra en el rango (no primera vez en la tienda). | Back: `app/services/sales_analytics.py::get_customer_retention_analysis` |
| ✅ 6 | Analytics → Top clientes | No excluye "Consumidor final" (client id 1 / NIT 222222222222): sale #1 con ~45 %. | Back: `sales_analytics.py::get_top_customers_analysis` |
| ✅ 7 | Totales de Ventas | Fecha inicial por defecto `new Date(); setDate(1); toISOString()` → después de las 7 pm (Colombia) sale el día 2. | Front: `DirectSalesTotals.jsx` (estados `quickFromDate`, `monthlyFromDate`) |
| ✅ 8 | Totales de Ventas | Ingresos por producto = `quantity * price` (sin descuento). "Métodos de pago" usa `paymentMethod` crudo (ej. `DEBIT_TRANSFER`) y es el declarado en la factura, no los pagos reales (`payments[]`). | Front: `DirectSalesTotals.jsx` |
| ✅ 9 | Documentos de Venta | Paginación falsa: el front no envía `limit/start` y el backend devuelve todo. | Front: `DirectSalesDocuments.jsx`, `src/services/directApiService.js::getSalesDocuments` |
| ✅ 10 | Totales de Ventas | Probable: `new Date("YYYY-MM-DD HH:MM:SS")` es inválido en Safari/iPhone → análisis por hora vacío. | Front: `DirectSalesTotals.jsx` (ventas por hora) |
| ✅ 11 | Totales de Ventas | Reintenta 3 veces (~24 s) cuando `total_sales === 0` (lo confunde con servidor dormido). | Front: `DirectSalesTotals.jsx::fetchQuickSummary` |

## Verificado con el conector (2026-10-02, solo lectura, Carreño)

- Totales mensuales 2026 del conector = los del plan al peso. Por día llegan en orden **descendente** (31→1): si `/api/v1/invoices/sales-totals` cortara en 30, se perdería el **día 1** (mar 1.186.800, may 3.033.500, jul 3.307.800, ago 3.525.710; 1-ene = $0). El conector usa reports-api v2, así que el tope de v1 **sigue sin verificar**: en producción, Totales de Ventas del 1 al 31 de agosto debe dar 51.909.564 (si da 48.383.854, se pierde el día 1).
- Factura `/invoices`: `seller` objeto; anuladas `status: "void"`; `items[].discount` en porcentaje y `items[].total` con descuento (sin IVA); `payments[]` con pagos reales (mixtos posibles).
- Anuladas 2026: 2 (24-feb $379.900, 19-mar $36.900). Notas crédito 2026: 0.
- Inventario: 1.608 ítems activos (2.461 en total). Balance contable "Inventarios" $174.167.315 al 2-oct (a costo).
- Septiembre 2026: Mónica $25.849.150 / 229, Rita $16.389.990 / 163 (= 42.239.140). Consumidor final $8.283.510 / 103; top identificado ZURIMA SALDARRIAGA $700.200; 260 clientes.

## Por verificar contra Alegra (necesita el conector MCP "AlegraCarreno", solo lectura)

- **Tope de `/invoices/sales-totals`**: `/api/sales/quick-summary` pide `groupBy=day&limit=100`. Si Alegra corta en 30, faltaría el día 31. Verificar sumando por día un mes de 31 días (o comparando con los totales mensuales 2026 de Alegra: ene 32.485.825; mar 45.211.260; may 51.514.890; jul 48.122.795; ago 51.909.564; sep 42.239.140). En producción también se puede con el selector "Ver ventas del [fecha]" de Cierre de Caja eligiendo el último día del mes.
- **`item.total` en facturas de /api/v1/invoices**: ¿incluye descuento? ¿impuestos? (lo usa Análisis de Productos).
- **Inventario**: el valor total de Inventario (value-report) vs. el reporte de valor de inventario de Alegra a la misma fecha.
- **Totales de un mes** en Totales de Ventas y en Documentos vs. el total de Alegra (diferencia esperada = anuladas + días saltados, si hubo).
- **Retención/Top clientes** vs. ventas por cliente de Alegra en el mismo rango.

## Fases

- ✅ **Fase A — errores que cambian números (1-6)** (2026-10-02, sin push). Inventario con los datos completos (las pestañas reciben `data` o el backend pagina `get_active_items`); vendedores por `seller.id`/`seller.name`; no saltar días en silencio (reintentar y/o devolver `failed_days` y avisar); quitar anuladas donde falta; corregir Retención (orden de condiciones; "nuevo" = primera compra registrada, o renombrar); excluir Consumidor final del Top clientes viejo.
- ✅ **Fase B — menores (7-11)** (2026-10-02, sin push). Además: Productos/Analytics/Ventas Mensuales/Comparativo avisan los días que Alegra no entregó (header `X-Alegra-Failed-Days`), e Inventario con archivo muestra el análisis del archivo. Fechas sin `toISOString` (usar `getColombiaTodayString`), ingresos con descuento, etiquetas de medios de pago (y, si se puede, pagos reales), paginación real o quitarla, parseo de hora compatible con Safari, no reintentar por $0.
- ✅ **Fase C — C1 a C4 hechas** (2026-10-02, sin push; pestaña Estadísticas → Prendas, sin BOLSA PAPEL). C5 (devoluciones y margen por categoría) pendiente: 0 notas crédito en 2026 y costos de Alegra poco confiables. Plan original: Guardar las prendas de cada factura (como `invoice_facts`, por tienda) para calcular sin descargas día por día: unidades por factura, precio promedio por prenda, más vendidos agotados, curva de tallas venta vs. stock, rotación/días de inventario, devoluciones, margen por categoría (cuando se corrijan los costos en Alegra).

## Reglas para quien continúe
- Multi-tienda: todo por `store_code` / header `X-Store` (`app/stores.py`).
- Alegra MCP: **solo herramientas de lectura**; nunca crear/editar/borrar en Alegra. El backend NO usa el MCP: usa `/api/v1` con Basic (ver límites en `CLAUDE.md`).
- Tests sin red en `tests/` (agregar con `git add -f`); documentar en CHANGELOG; commit sí, push solo cuando el usuario lo pida (Render necesita Manual Deploy).
