# Plan: reconstruir 2025 tras la anulación masiva de facturas POS

Creado: 2026-10-07. **Va antes de la Fase 4 de `PLAN_CUENTAS_DIARIAS.md`** (que sigue pendiente: regla 70/30, metas e incentivos, gastos en el comparativo de tiendas).

| Fase | Qué | Estado |
|---|---|---|
| R1 | Copia de 2025 en nuestra base (facturas, prendas, también de las anuladas) y clasificación: anulación masiva vs. anulación real | **Hecha (2026-10-07), commiteada; falta push + Manual Deploy y cargar 2025 en producción** |
| R2 | Informe de inventario: unidades que volvieron por la anulación masiva y existencia antes de la anulación (pantalla + Excel) | **Hecha (2026-10-07)**; falta revisarlo con datos reales y con el contador |
| R3 | Crear en Alegra el ajuste de inventario (salida) con esas unidades, con botón y confirmación | **Hecha y EJECUTADA en producción (2026-10-07)**: ajustes 1716-1719 en Alegra, $395.721.300 |
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

**Anulación masiva** (cuenta como venta real) = factura de 2025, anulada, POS (no electrónica), **salvo** que el usuario la marque a mano como anulación real (`VoidOverride`).

Las que tienen **otra factura del mismo día, con las mismas prendas y el mismo total, hasta 60 minutos después** se muestran en una lista "para revisar" (`possible_real`), pero **cuentan como venta**.

> **Corrección del 2026-10-07 tras cargar 2025 en producción.** Al principio esas se tomaban como anulación real (44 facturas, $3.629.000). La prueba contra Alegra lo descartó: octubre de 2025 antes de la anulación masiva valía **$47.838.020** (dato del 3-oct en Metas); hoy Alegra muestra $7.788.300 vigentes + $39.906.620 de anulación masiva = $47.694.920; la diferencia, **$143.100, es exactamente lo de las 2 "anulaciones reales" de octubre**. Eran ventas válidas: la regla confundía a dos clientas comprando lo mismo (ej. 8385 y 8397, $15.800, 54 min).

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
- **Resto de Estadísticas (hecho 2026-10-07):** con un rango de 2025, las facturas de la anulación masiva cuentan como venta en todas las pantallas. 2026 no cambia (los ids de la anulación masiva solo existen en 2025: fuera de 2025 las funciones devuelven vacío sin consultar nada).
  - Desde nuestra copia (`sale_condition` = no anulada **o** de la anulación masiva): Clientes (`_stored_facts`), Día y hora, Metas por vendedora (`_month_sales`).
  - Prendas y unidades de Metas: `mass_voided_item_rows` (prendas de `InvoiceVoidItem` con la vendedora de la factura).
  - Clientes nuevos/recurrentes e inactivas: `mass_voided_client_rows` + `merge_client_rows` suman a lo del reporte de Alegra las compras de la anulación masiva (por cliente).
  - Lo que se descarga de Alegra (Totales de Ventas, Documentos de Venta, Ventas Mensuales, Analytics Avanzado, Análisis de Productos): `revive_for_current_store` / `revive_mass_voided` devuelven esas facturas como vigentes (`status='closed'`, marca `mass_voided`) con un pago del medio de la factura (sus recibos se anularon). Documentos de Venta las marca "Anulada 2025 (venta real)".
  - Comparativo de tiendas: los ids se calculan en el hilo del request (`mass_ids_for_range`) y se pasan a `_sales_metrics` (`revive_with_ids`, sin base de datos).
  - Requiere que 2025 esté cargado en la copia (paso 1 de Reconstrucción 2025). Tests: 3 más en `tests/test_history_2025.py`.

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

## 6. Resultado de la carga en producción (Carreño, 2026-10-07)

- 2025 completo (365 días). Antes de la corrección: 3.481 de anulación masiva ($393.998.065), 44 "reales" ($3.629.000); Alegra muestra $281.388.042 vigentes (2.139 facturas). Con la corrección, la venta real de 2025 ≈ $281.388.042 + $393.998.065 + $3.629.000 = **$679.015.107** (menos lo que el usuario marque como anulación real).
- Alegra por mes (vigentes, hoy): ene $28,4 M y feb $33,2 M (las POS de enero-febrero no se anularon), mar-oct $0,2-11 M, nov $22,7 M, dic $139,7 M (965 electrónicas, temporada).

## 7. Ajuste ejecutado en producción (Carreño, 2026-10-07)

- Verificación previa: Metas oct-2026 volvió a $55.014.000 (oct-2025 = $47.838.020, igual que antes de la anulación). Venta real 2025 = **$679.015.107** (3.525 POS de anulación masiva = $397.627.065; Alegra vigentes $281.388.042). Conteo físico: medias ≈ 356 ✓, body U 49900 17 (calculadas 18) ✓, jean 99900 / 10519990032 ya no existe (calculado 0) ✓. Aprobado por el contador.
- **Valores a precio de venta:** en 612 de 629 prendas el `unitCost` de Alegra = precio de etiqueta (costos sin cargar). Las cifras de inventario de la plataforma y del Excel del usuario están en esa misma base.
- Informe: inventario hoy $589.677.800, a retirar $395.721.300 (8.335 unidades en 629 prendas; 142 tarjetas regalo por $6.526.000; 1.323 bolsas), antes $193.956.500. 21 para revisar (10 con 1-2 unidades menos de las devueltas, 11 inactivas sin ajustar).
- **Ajustes creados en Alegra (verificados con el conector):** 1716 ($315.824.300), 1717 ($58.714.200), 1718 ($20.417.000), 1719 ($765.800) = **$395.721.300**, fecha 2026-10-07, bodega Principal, observación "Reverso de la anulación masiva…". **No volver a crearlo.**
- **Diferencia sin explicar (~$29 M):** Alegra hoy da junio-2026 = $617.659.541; menos lo de la anulación ≈ $222 M, contra $192.873.771 del Excel del usuario (y hoy $194 M contra los $160-175 M que recordaba). No viene de la anulación masiva: revisar con un conteo físico completo más adelante.
- Pendiente: el inventario histórico de la pestaña Año (y de Alegra) sigue inflado para fechas anteriores al 2026-10-07 (el ajuste quedó con fecha de hoy).
- 2026-10-07 (tarde): la comparación con el año anterior de la parte de arriba del Cierre de Caja salía de `/api/sales/quick-summary` (no de `sales_comparison_yoy`) y seguía con lo de Alegra; ahora también usa `real_sales_total`. Pendiente: el listado de facturas de Totales de Ventas para rangos de 2025 sigue mostrando solo las vigentes de Alegra.
