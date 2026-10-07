# Plan: reconstruir 2025 tras la anulación masiva de facturas POS

Creado: 2026-10-07. **Va antes de la Fase 4 de `PLAN_CUENTAS_DIARIAS.md`** (que sigue pendiente: regla 70/30, metas e incentivos, gastos en el comparativo de tiendas).

| Fase | Qué | Estado |
|---|---|---|
| R1 | Copia de 2025 en nuestra base (facturas, prendas, también de las anuladas) y clasificación: anulación masiva vs. anulación real | **Hecha (2026-10-07), commiteada; falta push + Manual Deploy y cargar 2025 en producción** |
| R2 | Informe de inventario: unidades que volvieron por la anulación masiva y existencia antes de la anulación (pantalla + Excel) | **Hecha (2026-10-07)**; falta revisarlo con datos reales y con el contador |
| R3 | Crear en Alegra el ajuste de inventario (salida) con esas unidades, con botón y confirmación | **Hecha (2026-10-07), commiteada**; se usa en producción cuando el contador apruebe el Excel |
| R4 | Métricas que miran 2025 con la venta real (Metas: mismo mes del año anterior; comparación con el año anterior del cierre de caja) | **Hecha para Metas (total de la tienda) y la comparación del cierre (2026-10-07)**; pendiente: Clientes, reparto de la meta entre vendedoras (historial de 3 meses por vendedora) e inventario histórico de la pestaña Año |

---

## 1. Qué pasó (lo contó el usuario, 2026-10-07)

- Por impuestos, las ventas de 2025 hechas por **POS** (no electrónicas) se **anularon de forma masiva hace 2-3 días** (≈ 4-5 de octubre de 2026): a la DIAN solo le deben llegar ventas electrónicas. **No se volvieron a facturar de otra forma** (no hay factura global).
- Al anular, Alegra devolvió al inventario las prendas de esas facturas: el inventario quedó "en las nubes". Antes de la anulación estaba entre **$160 y $175 millones** (de memoria del usuario).
- Las anulaciones sueltas que hubo durante el año (no de la anulación masiva) **son anulaciones reales y se quedan así**.
- La POS 8501 del 2-oct-2026 (anulada) **no** es de la anulación masiva.

## 2. Lo que se verificó en Alegra (conector de solo lectura, 2026-10-07)

| Año | Facturas | Anuladas | Vigentes |
|---|---|---|---|
| 2024 | 4.221 | 37 (sueltas) | POS, no se tocaron |
| 2025 | 5.664 | **3.525, todas POS** (`numberTemplate.isElectronic = false`, numeración sin prefijo) | 2.139, todas electrónicas (prefijo KPC) |
| 2026 | — | 3 (ej. POS 8501) | — |

- Las POS anuladas **no son reemplazos** de las electrónicas: el 31-dic-2025 se usaban las dos numeraciones al tiempo con montos distintos (POS 8420-8422 entre KPC1461-1463).
- **Alegra no borra la factura anulada:** conserva fecha, hora (`datetime`), vendedora, medio de pago, anotación y **todas las prendas** (ej. POS 8420: short, 2 camisetas, cinturón, bóxer, bolsa, $279.800).
- Las de la anulación masiva quedaron con `totalPaid = 0` (se anularon también sus recibos). Una anulada real de 2024 (4185) conserva `totalPaid` ($120.000), pero la POS 8501 (anulada real de 2026) tiene `totalPaid = 0`: **`totalPaid` no basta para separar**.
- Alegra **no expone la fecha en que se anuló** una factura (ni en facturas ni en recibos).
- Alegra **no tiene carga masiva de ajustes de inventario por Excel** (centro de ayuda: solo "Nuevo ajuste" en pantalla); su API sí crea ajustes (`/inventory-adjustments`). La tienda tiene 1.715 ajustes de inventario (varios del 5-oct-2026).
- Nuestra copia de facturas empieza el 1-ene-2026 (`FACTS_START`) y **no guardaba las prendas de las facturas anuladas** (`invoice_to_items` devolvía `[]` para anuladas).

## 3. Reglas de la reconstrucción

**Anulación masiva** (cuenta como venta real) = factura de 2025, anulada, POS (no electrónica), **salvo**:
1. que el usuario la marque a mano como anulación real (`VoidOverride`), o
2. que parezca una anulación real del momento: hay **otra factura del mismo día, con las mismas prendas y el mismo total, hecha hasta 60 minutos después** (se volvió a facturar). Se muestra en una lista para que el usuario confirme.

Las electrónicas anuladas de 2025 son anulaciones reales.

**Venta real de 2025** = facturas vigentes + facturas de la anulación masiva.

**Existencia antes de la anulación** de cada prenda = existencia de hoy en Alegra − unidades que devolvieron las facturas de la anulación masiva. Las ventas hechas después de la anulación ya están descontadas de la existencia de hoy, así que esta resta deja la existencia que habría hoy sin la anulación. Si da negativo, se deja en 0 y se marca para revisar (algo más cambió esa prenda).

## 4. Fases

### R1 — Copia de 2025 y clasificación
- `InvoiceFact`: columnas nuevas `is_electronic`, `total_paid`, `issued_at` (hora completa de la factura) — sin DEFAULT; se llenan al cargar/recargar el día.
- Nueva tabla `invoice_void_items`: prendas de las facturas anuladas (la tabla de prendas vendidas no cambia: Prendas, Llegadas, etc. siguen igual).
- Nueva tabla `void_overrides`: marca manual por factura.
- Carga de 2025 por tandas con un botón (como "Cargar siguiente tanda"); no la hace el cron.

### R2 — Informe de inventario
- Por prenda: unidades devueltas por la anulación masiva, existencia de hoy, existencia antes de la anulación, costo unitario y valor. Totales: valor de inventario hoy, valor devuelto, valor antes (comparar con el rango de $160-175 M que recuerda el usuario).
- Descarga en Excel para revisarlo con el contador.

### R3 — Ajuste en Alegra (hecha 2026-10-07)
- Formato verificado en developer.alegra.com (`POST https://api.alegra.com/api/v1/inventory-adjustments`, requeridos `date` e `items[{id, type, unitCost, quantity}]`; `warehouse {id}` opcional, por defecto la principal) y contra un ajuste real de la tienda (n.º 1712: bodega Principal id 1, items con `type` in/out, `quantity`, `unitCost`).
- `AlegraClient.create_inventory_adjustment` (POST sin reintentos automáticos). `history_2025.create_adjustment`: exige 2025 completo, `confirm: "AJUSTAR"`, `accountant_ok: true` y que las unidades a retirar coincidan con las que el usuario revisó (`expected_units`); guarda el plan completo en `app_settings` (`history2025_inventory_adjustment`, por tienda) ANTES de enviar; crea un ajuste de salida por cada 200 prendas en la bodega 1 con observación "Reverso de la anulación masiva…"; si una parte falla, guarda lo hecho y otra llamada sigue con las partes que faltan usando el MISMO plan (no recalcula: las partes creadas ya bajaron la existencia); completado = no se vuelve a crear.
- Ruta `POST /api/history-2025/inventory-adjustment`; `GET /status` trae `adjustment` (sin la lista de prendas).
- Tests: 3 más en `tests/test_history_2025.py` (confirmación y año completo, formato y una sola vez, por partes con falla y reintento sin duplicar). Suite 241/241.
- Frontend: paso 4 de la página (casilla "Mi contador revisó y aprobó el Excel" + escribir AJUSTAR; muestra los números de ajuste creados o el estado a medias). Verificado en Chromium con Alegra simulado.

### R4 — Métricas con la venta real de 2025
- Metas (meta automática = mismo mes del año anterior +15 %) y la comparación con el año anterior del cierre de caja usan la venta real de nuestra copia cuando el mes/día de 2025 está cargado; si no, siguen con Alegra.
- Pendiente: Clientes nuevos/recurrentes e inactivas (hoy usan el reporte de Alegra para lo anterior a 2026).

## 5. Cómo quedó (2026-10-07)

**Backend**
- `InvoiceFact`: `is_electronic`, `total_paid`, `issued_at` (migración en `app/__init__.py`, sin DEFAULT). `invoice_to_fact` los llena.
- `InvoiceVoidItem` (`invoice_void_items`): prendas de las anuladas, llenadas por `invoice_to_void_items` dentro de `sync_day` (mismo reemplazo por día). `InvoiceItemFact` NO cambia (Prendas, Llegadas, Día y hora siguen igual).
- `VoidOverride` (`void_overrides`): marca manual por factura; sobrevive a recargar el día.
- `app/services/history_2025.py`: `coverage`, `classify` (regla de §3; ventana de re-facturación 60 min con mismas prendas y total), `summary` (por mes, venta vigente, venta real), `real_sales_total(store, start, end)` (None si el rango no es de 2025 o no está completo), `returned_units`, `inventory_report` (cruza con `AlegraClient.get_active_items()`: `inventory.availableQuantity` y `unitCost`), `inventory_excel` (openpyxl).
- `app/routes/history_2025.py`: `GET /api/history-2025/status`, `POST /api/history-2025/sync` (tanda de hasta 31 días faltantes de 2025; mismo candado que la carga de facturas; ~150 s por tanda), `PUT /api/history-2025/override` (por número de factura; `counts_as_sale` true/false/null), `GET /api/history-2025/inventory`, `GET /api/history-2025/inventory.xlsx`. No escribe en Alegra.
- R4: `SellerGoalsService._month_total` y la comparación con el año anterior del cierre de caja (`_real_previous_year` en `app/routes/cash_closing.py`) usan `real_sales_total` cuando el periodo de 2025 está cargado; si no, Alegra como antes. Nunca rompen la respuesta si algo falla.
- Tests: `tests/test_history_2025.py` (6, facturas con el formato real de /api/v1). Suite 238/238.

**Frontend**: `src/pages/History2025.jsx` (**Estadísticas → Reconstrucción 2025**, `/estadisticas-estandar/reconstruccion-2025`, solo admin) + `src/services/history2025Service.js`: barra de carga de 2025 con "Traer todo 2025" (tandas seguidas, se puede detener), tarjetas (anulación masiva, anulaciones reales, venta que muestra Alegra, venta real), tabla por mes, lista de anulaciones reales con "Fue de la anulación masiva" y marcar por número, informe de inventario (valor hoy, a retirar, antes) con tabla y Excel. Verificado en Chromium (1366 y 390) con Alegra simulado.

**Cálculo del inventario**: existencia antes = existencia de hoy − devueltas; unidades a retirar = mín(devueltas, existencia de hoy) (no se puede retirar más de lo que hay); si da negativo se marca "revisar en físico". El valor es a costo (`unitCost` de Alegra).

**Pendientes**
- El inventario histórico de Alegra (y el de la pestaña Año) queda inflado para fechas posteriores a las ventas anuladas: corregirlo restando el valor de las unidades devueltas hasta esa fecha.
- Clientes (nuevos/recurrentes, inactivas) con la copia de 2025.
