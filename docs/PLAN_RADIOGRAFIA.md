# Plan: Radiografía financiera de los locales

Creado: 2026-11-06. **Estado: PROPUESTA con respuestas del usuario (2026-11-06, ver §10); faltan 2 respuestas. No se ha construido nada.**
Se hace por fases, una a la vez, con el OK del usuario entre fase y fase.

| Fase | Qué | Estado |
|---|---|---|
| 0 | Reglas comunes: clasificación de salidas, costo estimado, módulo único de fórmulas | Propuesta |
| 0b | Deuda de Primavera con Carreño: tarjeta visible en las dos tiendas, saldo de partida $9.816.659 al 6-nov-2026, baja sola con cada pago | Propuesta (pedida por el usuario) |
| 0c | Tarjetas de deudas de cada tienda: mamá de Angie (Carreño, $7.500.000) y don Miguel (Primavera, 3 préstamos: $67.000.000), pago libre, detalle al dar clic | Propuesta (pedida por el usuario) |
| 1 | Mes: estado de resultados, punto de equilibrio, indicadores | Propuesta |
| 2 | Año: cierre general mes a mes | Propuesta |
| 3 | Inventario: valor, días, rotación, prendas quietas, por tipo de prenda | Propuesta |
| 4 | Flujo de caja: cuentas, por llegar, lo que se debe y le deben, cuánto se puede retirar (ESTIMADO) | Propuesta |
| 5 | Comparativo entre tiendas y consolidado | Propuesta |
| 6 | Exportar cada vista a Excel y PDF | Propuesta |

Alcance acordado (2026-11-06): **solo 2026**. Lo de 2025 se deja como está (la reconstrucción ya existe y no se toca);
de 2025 solo se leen las ventas para "mismo mes del año pasado" con las reglas que ya existen (`real_sales_total`).
Como KOAJ no tiene costos reales, mientras se organizan **el costo se estima** y todo lo que dependa de él dice ESTIMADO.

---

## 1. Lo que ya existe (no se duplica: se reutiliza)

| Dato | Dónde vive hoy | Uso en la Radiografía |
|---|---|---|
| Ventas por factura (total, descuento, vendedora, hora) | `InvoiceFact` (copia desde 1-ene-2026, cron 9 pm) | Ventas netas, transacciones, ticket |
| Prendas vendidas (cantidad, precio de lista, % descuento, total) | `InvoiceItemFact` | Unidades, precio de lista vendido → costo estimado, descuentos, por tipo de prenda |
| Ventas por medio de pago + correcciones a mano | `PaymentFact` + `SaleMethodCorrection` (`month_sheet.sale_entries`) | Flujo de caja, comisiones |
| Gastos y otras salidas, con `period` (mes al que corresponde) y 4x1000 | `Expense` (Cuentas → Gastos) | Toda la clasificación de salidas |
| Gastos fijos | `FixedExpense`, ligado a `Expense.fixed_expense_id` | Punto de equilibrio y "fijos pendientes del mes" |
| Recompras (lo enviado a Jhonatan) y sus compras | `RepurchaseEntry`, `RepurchasePurchase`, `_carryover_before` | Año ("lo que quedó"), flujo, plata en manos de Jhonatan |
| Llegadas de mercancía (precio de VENTA) | `PurchaseItemFact` (`/bills`) | Compras del mes a precio de venta, "recién llegado" |
| Inventario de fin de mes (Alegra) | `InventorySnapshot` (desde ago-2026) | Año, días de inventario, rotación |
| Cuentas: saldo inicial/final, ventas, excedentes, llegadas, recompras, gastos, entradas, ajustes, traslados | `month_sheet.account_statement` | Flujo de caja (se reutiliza tal cual) |
| Plata por llegar y lo que llegó (datáfono, Addi, Bold) | `month_sheet.transit` / `arrived`, `card_arrivals` | Flujo de caja |
| Comisiones de datáfono/Addi | `month_sheet.commissions` + gasto `auto:comisiones:AAAA-MM` | Gastos financieros (sin contarlas dos veces) |
| Préstamos entre tiendas | `GET /api/expenses/inter-store` (`lent` / `owed`) | Lo que debe y le deben |
| Préstamos a empleadas | `EmployeeLoan` (abonos en negativo) | Lo que le deben |
| Ganancia bruta/neta/real, 70/30, excedentes | `monthly_summary.build_year` (Cuentas → Año) | El Año de la Radiografía debe cuadrar con esto |
| Margen KOAJ 35 % y % de resurtido | `finance_settings` (`margin_pct`, `resurtido_pct`) | Costo estimado (ver §3) |
| Rotación por tipo de prenda, stock de Alegra | `garment_insights` (`rotation`, `stock_variants`, `parse_garment`, sin BOLSA PAPEL) | Inventario |
| Comparativo de tiendas | `GET /api/stores/comparison` + `StoreComparison.jsx` | Se le suman las cifras de la Radiografía |
| Excel y PDF en el servidor | `openpyxl` y `reportlab` (ya instalados) | Exportar |
| Rol viewer (solo lectura) | `_apply_read_only` | Ve todo; la Radiografía casi no guarda nada |

**Lo que falta de verdad:** costo de lo vendido (estimado), estado de resultados con comparaciones, punto de equilibrio,
indicadores (ticket, unidades, nómina/ventas), prendas quietas con plata parada, flujo de caja con salidas por clase y
"utilidad vs plata", lo que se debe/le deben en un solo lugar, cuánto se puede retirar, consolidado y exportación.

---

## 2. Lo que encontré revisando datos reales (Carreño, conector de Alegra, solo lectura, 2026-11-06)

1. **En Alegra el costo de cada prenda es igual a su precio de venta.** Ejemplo: BUZO CAPOTA HOMBRE 119900 → precio
   $119.900, costo unitario $119.900 (lo mismo en las variantes de 109.900). Las compras (`/bills`) también entran a
   precio de venta (ya se sabía, Fase D de Estadísticas). Consecuencias:
   - El "costo de ventas" de Alegra = ventas → margen 0 %. **No sirve.**
   - El inventario de `InventorySnapshot` (y el "Inventario total" del Dashboard) está **a precio de venta**, no a costo.
2. El inventario de Alegra antes del 7-oct-2026 estaba inflado por la anulación de 2025 (ajustes 1716-1719) y queda una
   diferencia de ~$29 M pendiente del conteo físico. La variación de inventario de agosto→octubre 2026 sale distorsionada:
   se mostrará con aviso.
3. Hoy **Cuentas → Año cuenta la cuota de crédito completa como gasto operativo** (`OPERATING_CATEGORIES` incluye
   `cuota_credito` y `otro`). Tu regla dice que la cuota no resta utilidad (solo los intereses). Ver pregunta 2.
4. **Gastos fijos y gastos registrados no se cuentan dos veces hoy**: la utilidad solo suma los `Expense` registrados;
   `FixedExpense` es un recordatorio ligado por `fixed_expense_id`. Hay que mantenerlo así: el gasto fijo configurado
   solo se usa para el punto de equilibrio y para "lo que falta por pagar este mes", nunca se suma a la utilidad.
5. Los gastos de Primavera que pagó Carreño están registrados **solo en Carreño** como `prestamo_tienda`. Primavera no
   los tiene como gasto, así que su utilidad no los muestra. Ver pregunta 4.
6. El conector no dejó consultar el reporte de rentabilidad de Alegra (error 503); da igual porque el costo de Alegra no sirve.

---

## 3. Costo de lo vendido: propuesta (necesita tu decisión)

En KOAJ la regla del Excel es "recompra ÷ (1 − 35 %) = ropa a precio de venta", o sea, **la ropa cuesta el 65 % de su
precio de lista**. Eso ya está guardado por tienda en `finance_settings.margin_pct` (35). Propongo:

**Opción A (recomendada): costo estimado = precio de LISTA de lo vendido × (1 − margen KOAJ).**
- Precio de lista vendido = Σ (cantidad × precio de lista) de `InvoiceItemFact` (sin BOLSA PAPEL ni tarjetas regalo).
- Se usa el precio de lista, no la venta neta, para que **los descuentos bajen la utilidad** (si vendo con 20 % de
  descuento, gano menos; con "ventas × 65 %" eso no se vería).
- Inventario a costo (ESTIMADO) = inventario de Alegra (a precio de venta) × (1 − margen).
- Si algún día del mes no tiene las prendas guardadas, se usa ventas netas ÷ (1 − % de descuento del mes) y se avisa.
- Cuando se corrijan los costos en Alegra (C5), solo se cambia esta función.

**Opción B (como control, no como cifra principal): costo por inventario** =
(inventario inicial + compras del mes − inventario final), todo a precio de venta, × (1 − margen).
La diferencia entre B y A muestra **merma o descuadres** (prendas que salieron sin venta, ajustes, cambios). Útil, pero
depende de que el inventario de Alegra esté bien (punto 2 de arriba): hoy saldría distorsionado.

**Opción C (la del Excel): recompras como costo.** Ya está en "lo que quedó" = ventas − recompras − gastos. Mide plata, no
ganancia (si este mes se recompra el doble, parece pérdida). Se sigue mostrando, pero no como costo.

Fletes (incluye moto carro): son costo de traer la mercancía → van en "costo de lo vendido", debajo del costo estimado.

Comprobación que haré con datos reales antes de la Fase 1: comparar las recompras de sep-oct contra lo que llegó a
precio de venta en Llegadas. Si recompra ÷ llegadas ≈ 0,65, el 35 % está bien; si no, te muestro la cifra real.

---

## 4. Clasificación de cada salida (un solo mapa en el backend)

Basado en las categorías que ya existen (`OUT_CATEGORIES`, `EXPENSE_SUBCATEGORIES`), sin cambiar la tabla:

| Clase en la Radiografía | Categorías actuales | ¿Resta utilidad? | ¿Saca plata? |
|---|---|---|---|
| Costo de mercancía | `flete` (flete, moto carro) | Sí (en costo de lo vendido) | Sí |
| Gasto operativo | `operativo` (arriendo, luz, internet, Alegra, aseo…), `sueldo` (sueldos, incentivos, sueldo Jhonatan por recompras) | Sí | Sí |
| Gasto financiero | `financiero` (cuota de manejo), 4x1000 de gastos y recompras, comisiones datáfono/Addi | Sí | Sí |
| Cuota de crédito | `cuota_credito` | **Pregunta 2** | Sí |
| Otro | `otro` / subcategoría "Otra" | **Pregunta 3** (propongo: sí, como operativo) | Sí |
| Inversión | `inversion` | No | Sí |
| Préstamo a empleada | `prestamo_empleada` | No | Sí |
| Préstamo a otra tienda | `prestamo_tienda` | No (ni gasto del que presta ni ingreso del que recibe) | Sí |
| Retiro de socio | `retiro_socio` (ganancias Jhonatan/Cristian/José) | No | Sí |
| Recompra | `RepurchaseEntry` | No (la mercancía entra al costo cuando se vende) | Sí |
| Entradas que no son venta | `devolucion_prestamo`, `devolucion_prestamo_tienda`, `ingreso_extra`, excedentes del cierre | No son venta | Entran |

- Comisiones de datáfono/Addi: si el mes ya tiene el gasto `auto:comisiones:AAAA-MM`, se usa ese; si no, se usan las
  calculadas (`month_sheet.commissions`) marcadas "calculadas, no registradas". **Nunca las dos.**
- Excedentes del cierre: nunca suman a ventas; aparecen en el flujo de caja como "otros ingresos".
- Gastos por `period` (mes al que corresponden) para la utilidad; por `date` para el flujo de caja (como ya hace Gastos).

---

## 5. Fórmulas (todas en `app/services/radiografia.py`, con pruebas; la fórmula se ve en pantalla junto a cada cifra)

COP, mes calendario en hora de Colombia, división por cero → "—".

```
Ventas netas            = Σ InvoiceFact.total no anuladas del mes        (= Cuentas → Año)
Precio de lista vendido = Σ cantidad × precio de lista (InvoiceItemFact, sin bolsa ni tarjetas regalo)
Descuentos              = Precio de lista vendido − Ventas netas
Costo estimado          = Precio de lista vendido × (1 − margen KOAJ)      ESTIMADO
Costo de lo vendido     = Costo estimado + Fletes                          ESTIMADO
Utilidad bruta          = Ventas netas − Costo de lo vendido               ESTIMADO
Margen bruto %          = Utilidad bruta ÷ Ventas netas
Gastos operativos       = operativo + sueldo (+ otro, según pregunta 3)
Utilidad operacional    = Utilidad bruta − Gastos operativos
Gastos financieros      = financiero + 4x1000 (gastos y recompras) + comisiones (+ cuota de crédito, pregunta 2)
Utilidad neta           = Utilidad operacional − Gastos financieros        (antes de impuestos)
% sobre ventas          = cada línea ÷ Ventas netas
Lo que quedó (Excel)    = Ventas − Recompras − (salidas que restan utilidad)   (= "ganancia real" de Cuentas → Año)

Transacciones           = número de facturas no anuladas
Ticket promedio         = Ventas netas ÷ Transacciones
Unidades                = Σ cantidad (sin bolsa); Prendas por factura = Unidades ÷ Transacciones
Gastos / ventas %       = (Gastos operativos + financieros) ÷ Ventas netas
Nómina / ventas %       = categoría sueldo ÷ Ventas netas

Margen de contribución %   = (Ventas − Costo estimado − Fletes − Comisiones) ÷ Ventas
Gastos fijos del mes       = gastos fijos configurados y activos que restan utilidad (sin retiros de socios ni
                             préstamos); si lo registrado en el mes es mayor, se usa lo registrado
Punto de equilibrio (mes)  = Gastos fijos ÷ Margen de contribución %
Punto de equilibrio (día)  = Punto de equilibrio ÷ días del mes (pregunta 7)
Ventas para utilidad X     = (Gastos fijos + X) ÷ Margen de contribución %    (X lo escribes tú)
Avance                     = Ventas a hoy ÷ Punto de equilibrio; ritmo al cierre = ventas a hoy ÷ días corridos × días del mes (ESTIMADO)

Inventario a costo         = Inventario de Alegra (precio de venta) × (1 − margen)   ESTIMADO
Variación de inventario    = Inventario fin de mes − Inventario fin del mes anterior
Días de inventario         = Inventario a precio de venta ÷ (Precio de lista vendido de los últimos 30 días ÷ 30)
Rotación (veces al año)    = Precio de lista vendido en 12 meses ÷ Inventario promedio (con los meses que haya foto;
                             ESTIMADO mientras no haya 12 meses de fotos)
Plata parada (prenda quieta) = stock × precio de lista × (1 − margen)

Cuánto se puede retirar (ESTIMADO) = plata en las cuentas hoy (sin lo por llegar; AHORRO aparte, pregunta 8)
                                    − gastos fijos que faltan por pagar este mes
                                    − plata para reponer lo vendido (costo estimado del mes − recompras del mes, si da positivo)
                                    − lo que esta tienda le debe a la otra
```

Comparaciones:
- Contra el mes anterior: si el mes va en curso, contra **los mismos días** del mes anterior (ventas, transacciones,
  ticket, unidades). Los gastos solo se comparan entre meses cerrados (los gastos van por mes, no por día).
- Contra el mismo mes del año pasado: solo ventas, transacciones y ticket (2025 no tiene gastos en el sistema), con
  `real_sales_total` sin tocar nada de 2025.
- **Un mes sin datos no se compara** ("sin datos" en vez de una pérdida falsa). Carreño tiene gastos desde oct-2026
  (septiembre solo como total escrito a mano en Año); Primavera desde el 25-oct-2026.

---

## 6. Fases

Cada fase: pruebas (pytest en `tests/test_radiografia.py`, con `git add -f`), verificación con datos reales de **las dos
tiendas** contra Cuentas → Mes/Año y Alegra, revisión en el navegador (1366 px y 390 px, sin desborde), CHANGELOG de los
dos repos, este plan y CLAUDE.md si cambia la arquitectura, commit (push solo cuando lo pidas).

Pantalla: una página nueva **Radiografía** (pregunta 6) con pestañas Mes · Año · Inventario · Flujo de caja · Comparativo,
para admin y viewer, siempre de la tienda activa (header `X-Store`).

### Fase 0 — Reglas comunes (sin pantalla)
- `app/services/radiografia.py`: mapa categoría → clase (§4), `estimated_cost`, `utility_lines`, `break_even`,
  `sales_for_target`, `pct_change`, `ratio` (división por cero → None), periodos en hora de Colombia, "mismos días".
- `OPERATING_CATEGORIES` de `monthly_summary` pasa a leerse de este módulo (un solo lugar). Si decides cambiar la cuota de
  crédito u "otro" (preguntas 2 y 3), **también cambian Cuentas → Año, el comparativo y la regla 70/30**: te muestro antes
  cómo quedan sep y oct con la regla nueva.
- Comprobación del 35 % (recompras vs llegadas) con datos reales.
- Sin tablas nuevas.

### Fase 1 — Mes
- `GET /api/radiografia/month?year&month` (admin y viewer; solo lee).
- Tarjetas: ventas netas, utilidad bruta, utilidad neta, punto de equilibrio con barra de avance.
- Estado de resultados con fórmula por línea, % sobre ventas, mes anterior (mismos días si va en curso) y mismo mes 2025.
- Indicadores: transacciones, ticket, unidades, prendas por factura, descuentos %, gastos/ventas, nómina/ventas.
- "¿Cuánto hay que vender?": punto de equilibrio mes y día, ritmo actual (ESTIMADO), ventas para la utilidad que escribas
  (el valor que escribas no se guarda; si quieres que se recuerde, se guarda por tienda en `finance_settings`).
- Salidas del mes por clase con "¿resta utilidad?" (inversiones, préstamos y retiros aparte).
- Verificación: ventas = Cuentas → Mes/Año = Alegra; "lo que quedó" = ganancia real de Año.

### Fase 2 — Año
- `GET /api/radiografia/year?year`: por mes ventas, costo estimado, utilidad bruta, recompras, gastos operativos y
  financieros, utilidad neta, lo que quedó, inventario de fin de mes (precio de venta y a costo) y variación; total y promedio
  (solo meses con datos). Reusa `build_year` (mismas sobrescrituras a mano) para que cuadre al peso con Cuentas → Año.
- Sin tablas nuevas.

### Fase 3 — Inventario
- `GET /api/radiografia/inventory?quiet=60|90|180`: valor (precio de venta y a costo), días de inventario, rotación,
  prendas quietas = con stock, sin venta en N días **y** sin llegada en N días (no marca lo recién llegado), con su plata
  parada; las que más rotan y baja rotación; por tipo de prenda y departamento (`parse_garment`): ventas, unidades,
  descuento %, utilidad estimada, stock, días de inventario, plata parada.
- Stock de Alegra con lo que ya usa Prendas (`stock_variants`, en caché). Ventas y llegadas desde la copia (sin descargar).
- Límite honesto: con un margen igual para todo, la "rentabilidad por prenda" solo cambia por los descuentos. La
  rentabilidad real por prenda necesita los costos reales (C5). En Primavera, todo es recién llegado hasta diciembre.

### Fase 4 — Flujo de caja
- `GET /api/radiografia/cash-flow?year&month`: saldo inicial y final por cuenta (`account_statement`), entradas
  (ventas por medio, llegadas de datáfono/Addi/Bold, excedentes, devoluciones, ingresos extra) y salidas por clase (§4);
  traslados entre cuentas propias aparte (no cuentan).
- Utilidad vs plata del mes, lado a lado, con las partidas que las separan (recompras, costo estimado, inversiones,
  retiros, préstamos, plata por llegar, cambio en la plata de Jhonatan).
- Lo que le deben: plata por llegar (datáfono, Addi, Bold, con fecha), préstamos a empleadas, la otra tienda (préstamo
  Carreño ↔ Primavera), plata en manos de Jhonatan. Lo que debe: a la otra tienda. Las facturas de proveedor de Alegra no se
  usan (están a precio de venta y no son deuda real, decisión de la Fase D de Estadísticas).
- "Cuánto se puede retirar" con la fórmula a la vista y la palabra ESTIMADO.

### Fase 5 — Comparativo y consolidado
- `GET /api/radiografia/compare?year&month`: las mismas cifras de Mes/Inventario/Flujo para cada tienda, una al lado de la
  otra (solo usuarios con acceso a las dos tiendas). Se agregan también a `StoreComparison.jsx` si prefieres no duplicar pantallas.
- Consolidado: ventas, costo, gastos, utilidad e inventario sumados; el préstamo entre tiendas **no aparece** (lo que
  Carreño "le deben" y lo que Primavera "debe" se cancelan) y nunca suma como gasto ni ingreso.

### Fase 6 — Exportar
- `?format=xlsx` y `?format=pdf` en cada endpoint (openpyxl y reportlab, ya instalados): el archivo sale de los mismos
  datos de la pantalla, no se recalcula. Nombre con la tienda y el periodo. Fórmulas y avisos ESTIMADO en una hoja de notas.

---

## 7. Lo que NO se hace, y por qué

| Pedido | Decisión | Razón |
|---|---|---|
| Balance general, ROA, ROE, endeudamiento, capital de trabajo | No | No hay activos fijos, patrimonio ni deudas en el sistema: serían números inventados. |
| EBITDA | No | Sin depreciación ni intereses separados sería la utilidad operacional con otro nombre. |
| Impuestos / utilidad después de impuestos | No | Lo lleva el contador; la utilidad se rotula "antes de impuestos". |
| Chat con IA | No | Pedido explícito. |
| Costo real de Alegra | No (por ahora) | Costo = precio de venta (§2). Se usa el estimado hasta que se corrijan los costos (C5). |
| Cuentas por pagar al proveedor | No | Facturas de compra a precio de venta y sin pagos: no son deuda real (Fase D de Estadísticas). |
| 2025 | Solo lectura de ventas | Decisión del usuario (2026-11-06). |
| Reconstruir inventario de meses sin foto | No | Solo hay fotos desde ago-2026. |
| Tablas nuevas | Ninguna prevista | Todo sale de lo que ya se guarda; si algo se guarda (utilidad deseada), va por tienda en `finance_settings`. |

---

## 8. Preguntas para el usuario

1. **Costo:** ¿apruebas la Opción A (precio de lista × 65 %)? ¿El 35 % es lo que de verdad le descuenta KOAJ a Jhonatan
   en las recompras, igual para todas las prendas? (Lo comparo con los datos antes de la Fase 1.)
2. **Cuota de crédito** (Scotiabank, Davivienda): a) que no reste utilidad (tu regla; solo saca plata), b) completa como
   gasto financiero (como hoy en Cuentas → Año), o c) separar los intereses (habría que registrar cuánto es interés).
   Si eliges a) o c), Cuentas → Año también cambia.
3. **Categoría "Otro":** ¿resta utilidad como gasto operativo? (propuesta: sí, y la Radiografía muestra cuánto hay en "Otro"
   para que lo reclasifiques).
4. **Gastos de Primavera pagados por Carreño:** hoy no aparecen como gasto en Primavera. ¿Quieres que la utilidad de
   Primavera los incluya (por ejemplo el arriendo de Primavera pagado con plata de Carreño)? Si sí, propongo registrarlos
   también en Primavera con "No mover cuentas" y que la Radiografía lo detecte; si no, Primavera se verá más rentable de lo que es.
5. ¿Cuentas → Año debe quedar con la misma clasificación que la Radiografía (una sola verdad)? Recomiendo que sí.
6. **Dónde va en el menú:** ¿una entrada nueva "Radiografía" en Estadísticas, o una pestaña más en Gestión → Cuentas?
7. **Punto de equilibrio diario:** ¿la tienda abre todos los días del mes? (si cierra domingos o festivos, se dividen solo
   los días que abre).
8. **Cuánto se puede retirar:** ¿la cuenta AHORRO cuenta como plata disponible o es un fondo que no se toca? ¿Apruebas
   restar "plata para reponer lo vendido"?
9. ¿La utilidad deseada que escribas se debe recordar (por tienda) o se escribe cada vez?

---

## 9. Para tener en cuenta al trabajar

- PC de la entidad: GitHub bloqueado (el `git pull` del 2026-11-06 no pudo; los repos locales estaban en backend 3ac316a y
  frontend 1e21a58). **Antes de construir hay que hacer el pull desde otra red.** Pytest se puede colgar (TROUBLESHOOTING.md):
  repetir las pruebas en el PC personal.
- Verificación con datos reales de producción: con un script que pide el usuario y la contraseña por consola (nunca en el
  código ni en el chat), en las dos tiendas.
- Datos raros (prendas sin precio, categorías faltantes, duplicados) se muestran con fecha y número de factura y se
  pregunta antes de corregir; toda corrección va primero en simulación y deja rastro.

---

## 10. Respuestas del usuario (2026-11-06) y cómo cambian el plan

| # | Pregunta | Respuesta | Qué cambia |
|---|---|---|---|
| 1 | Costo | **35 % de ganancia en todos los productos** | Opción A aprobada: costo estimado = precio de lista × 65 % (`finance_settings.margin_pct`, igual para todo). |
| 2 | Cuota de crédito | **Sin respuesta todavía** | Se vuelve a preguntar. |
| 3 | "Otro" resta utilidad | **Sí** | "Otro" va como gasto operativo. |
| 4 | Gastos de Primavera pagados por Carreño | **Quiere ver lo que Primavera le debe a Carreño: $9.816.659 al 6-nov-2026, en una tarjeta visible, conectada a las cuentas y que baje a medida que Primavera paga** | Fase 0b nueva (abajo). Lo que Carreño pagó por Primavera es préstamo: no es gasto de Carreño ni ingreso de Primavera. |
| 5 | Año con la misma clasificación | **Sí** | `OPERATING_CATEGORIES` sale del módulo de la Radiografía; Año, comparativo y 70/30 cambian juntos (se muestran antes sep y oct con la regla nueva). |
| 6 | Dónde | **Pestaña en Gestión → Cuentas** | Pestaña "Radiografía" dentro de `CuentasLayout` (con sus sub-pestañas Mes · Año · Inventario · Flujo · Comparativo). |
| 7 | Días que abre | **Todos los días, las dos tiendas** | Punto de equilibrio diario = mes ÷ días calendario del mes. |
| 8a | AHORRO disponible | **Sí cuenta** (hoy está en $0: se usó en la apertura de Primavera) | Entra en "cuánto se puede retirar". |
| 8b | Restar "reponer lo vendido" | **No lo entendió** | Se explica de nuevo y se vuelve a preguntar. |
| 9 | Utilidad deseada | **No es una meta: la ganancia que se saca depende de cómo le va al local cada mes** | No se guarda nada. En vez de "ventas para la utilidad X" el foco es "cuánto generó el local y cuánto se puede sacar" (Fase 4). Se deja una calculadora opcional "si quiero sacar X, ¿cuánto hay que vender?" sin guardar. |

### Fase 0b — Deuda de Primavera con Carreño (propuesta)
Hoy: `GET /api/expenses/inter-store` calcula el saldo con lo registrado en Carreño (`prestamo_tienda` − `devolucion_prestamo_tienda`)
y se ve solo dentro de Cuentas → Gastos. Si Primavera paga desde sus cuentas, hoy habría que registrarlo dos veces (en
Primavera como "otro", que además restaría su utilidad, y en Carreño como devolución).

Propuesta:
1. **Saldo de partida**: $9.816.659 al 6-nov-2026 (dato del usuario), guardado en `app_settings` (compartido: es de las dos
   tiendas). Lo registrado antes de esa fecha queda solo como historial (para no contarlo dos veces). Saldo de hoy =
   saldo de partida + préstamos nuevos de Carreño a Primavera − pagos de Primavera, ambos desde el 6-nov.
2. **Pago de Primavera a Carreño en un solo registro**: en Gastos de Primavera, salida nueva "Pago a Carreño (préstamo)"
   (`pago_prestamo_tienda`: saca plata de la cuenta de Primavera, **no resta utilidad**). Al guardarlo se crea solo, en
   Carreño, la entrada `devolucion_prestamo_tienda` en la cuenta de Carreño donde llegó la plata. Editar o borrar uno
   cambia el otro. Si el pago sale de la caja del día de Primavera, se registra con "De la caja del día".
3. **Tarjeta visible** en Gestión → Cuentas → Resumen de las dos tiendas: Carreño "Primavera nos debe $X", Primavera
   "Le debemos a Carreño $X", con los pagos hechos (fecha, valor, cuenta). También en el flujo de caja de la Radiografía.
4. El rol viewer la ve pero no registra pagos.
5. Pruebas: pago crea la entrada en Carreño, editar/borrar sincroniza, saldo con el de partida, no resta utilidad en
   ninguna tienda, no se cuenta dos veces lo anterior al 6-nov.

Preguntas de esta fase: ¿los $9.816.659 son todo lo que Primavera debe al 6-nov (aunque en el sistema haya registros
de préstamos anteriores con otros valores)? ¿Primavera ya hizo algún pago a Carreño antes de hoy que esté incluido en ese valor?

### Respuestas del 2026-11-06 (segunda ronda)

**Cuotas de crédito.** No son de banco como decía la plantilla (Scotiabank/Davivienda):
- Carreño: cuota a la mamá de Angie; quedan **$7.500.000** de la deuda de la apertura de Carreño.
- Primavera: crédito BBVA de don Miguel (papá de Cristhian).
- Ellos toman la cuota completa como algo que sale (no calculan intereses).

Propuesta (respeta las dos cosas): la cuota **no baja la utilidad neta** (pagar un préstamo no es gasto: lo que se compró
con ese préstamo fue la apertura, una inversión), **pero sí se resta en "lo que quedó" y en "cuánto se puede retirar"**,
en una línea propia "Cuotas de crédito", porque esa plata sale y no vuelve. En Cuentas → Año, "ganancia real / lo que
quedó" sigue restando las cuotas (no cambia el número que conocen); "gastos operativos" deja de incluirlas y se ven aparte.
Además, tarjeta "Lo que debe la tienda" con el saldo de cada crédito que baja con cada cuota registrada (falta el saldo
de Primavera con BBVA).

**Reponer lo vendido.** Entendido; las recompras se siguen haciendo a mano en Cuentas Recompras (no cambia nada ahí). En
"cuánto se puede retirar" se muestra en su propia línea "Falta por recomprar de lo vendido este mes" (costo estimado de
lo vendido − recompras del mes, si da positivo), para no confundir plata de mercancía con ganancia.

**Deuda de Primavera con Carreño.** $9.816.659 es el valor neto al 6-nov-2026 (los pagos anteriores ya están descontados;
lo registrado antes queda solo como historial). Cada pago de Primavera **resta de las cuentas de Primavera** (si salió de
ellas) **y resta de la deuda**, pero **no suma a las cuentas de Carreño**: Primavera a veces paga con recompras o con
ganancias de los dueños, y esa plata no llega a las cuentas de Carreño. Cambia la Fase 0b: el pago ya no crea una entrada
en Carreño (opcional, solo si la plata sí llegó a una cuenta de Carreño).

### Respuestas del 2026-11-06 (tercera ronda)

**Tarjetas de deudas (Fase 0c nueva, pedida por el usuario).** Una tarjeta por deuda que baja con cada pago; al darle
clic se abre el detalle: valor total prestado, pagos hechos (fecha, valor, cuenta de donde salió), lo pagado y el saldo.
- Carreño: **mamá de Angie**, saldo $7.500.000 (deuda de la apertura de Carreño).
- Primavera: **don Miguel (BBVA)**, una sola tarjeta con 3 préstamos: $10.000.000 + $20.000.000 + $37.000.000 = $67.000.000.
- La cuota es **libre** (cada pago se escribe con su valor; no hay cuota fija).
- Es por tienda (`StoreScopedMixin`). El viewer las ve y no registra pagos.

**Primavera paga cosas de Carreño (recompras u otras cosas).** Sale normal de la cuenta de Primavera de donde salió la
plata y se marca "para pagar cosas / deuda de Carreño": baja la deuda de Primavera con Carreño.

**Primavera paga ganancias de los dueños de Carreño.** El usuario propone registrarlo como gasto operativo de Primavera
y bajar la deuda. Ojo (por confirmar): como gasto operativo bajaría la utilidad de Primavera; se propone registrarlo
como "Pago a Carreño" con la nota de para qué fue, que también baja las cuentas de Primavera y la deuda.

**Préstamos nuevos de Carreño a Primavera** desde el 6-nov: **suman a la deuda**.

Dudas abiertas antes de construir: ver la respuesta al usuario del 2026-11-06 (saldos actuales de los 3 préstamos de
don Miguel, intereses/ajuste de saldo, desde dónde se registra el pago, cuotas ya registradas antes de hoy, recompras
de una tienda pagadas por la otra).

### Respuestas del 2026-11-06 (cuarta ronda) — Fase 0c definida

- **Mamá de Angie (Carreño):** $7.500.000 es el saldo neto de hoy; no se ha abonado nada.
- **Don Miguel (Primavera):** se deben los $67.000.000, pero puede que ya se haya pagado algo (no se sabe aún): el
  **valor prestado y el saldo de cada préstamo se pueden ajustar** a mano, con nota y rastro.
- **Los 3 préstamos de don Miguel van por separado** dentro de una misma tarjeta: al pagar se escoge a cuál préstamo
  va; baja ese préstamo y el total. La tarjeta muestra cuánto va cada uno.
- **Cuota e interés:** campos opcionales por préstamo ("valor de la cuota" e "interés del banco") para llenarlos apenas
  se sepan. Botón "Ajustar saldo" para igualar con el banco (con nota).
- **Dónde se registra el pago:** en la tarjeta ("Registrar pago") o en Cuentas → Gastos ("Cuota de crédito" + a qué
  deuda/préstamo). Es **un solo registro**: baja la cuenta una vez y baja la deuda una vez.
- **Cuotas registradas antes de hoy:** solo historial.
- **Ganancias de los dueños / cosas de Carreño pagadas por Primavera:** opción única "Pago a Carreño (abono a la deuda)"
  con nota de para qué fue; baja cuentas de Primavera y la deuda, **no baja su ganancia**. Aprobado.
- **Recompra de una tienda pagada por la otra:** la tienda dueña de la mercancía la anota en sus Recompras sin mover sus
  cuentas, con nota automática visible: "No se movió en cuentas: lo pagó <otra tienda> (abono / préstamo entre tiendas)".
  La que pagó la anota como "Pago a Carreño" (Primavera) o "Préstamo a Primavera" (Carreño, suma a la deuda).
- **Dónde se ven:** Cuentas → Resumen (Carreño: "Mamá de Angie" y "Primavera nos debe"; Primavera: "Don Miguel" y
  "Le debemos a Carreño") y el flujo de caja de la Radiografía.

### Respuestas del 2026-11-06 (quinta ronda)

- **Interés aprobado:** cuando se ponga la tasa de un préstamo, cada pago se parte: interés = saldo × tasa (gasto
  financiero, baja la ganancia) y el resto baja la deuda. Sin tasa, todo el pago baja la deuda.
- **Regla del usuario (vale para todo):** a las cuentas, a la utilidad y a las deudas **solo se resta lo que se registra
  a mano** (un gasto, una cuota, un pago). Nada pendiente o estimado se descuenta solo. Lo que falta por pagar se muestra
  como **aviso / recordatorio** (ej. "la cuota de don Miguel se paga el 28 de cada mes y este mes no está registrada").
- Por confirmar: que "Cuánto se puede retirar" muestre la plata de hoy y, aparte y sin restarlas, las líneas de aviso
  (fijos y cuotas que faltan este mes, falta por recomprar, deuda con la otra tienda); y el día de pago de cada deuda.

### Respuestas del 2026-11-06 (sexta ronda)

**Préstamos de don Miguel (Primavera):**
| Préstamo | Plazo | Cuota | Estado al 6-nov | Interés mensual que sale de cuota y plazo (ESTIMADO) |
|---|---|---|---|---|
| $20.000.000 | 60 meses | $554.633 | Cuota 1 pagada: se descontó del mismo préstamo (no salió de las cuentas) | ≈ 1,85 % |
| $10.000.000 | 24 meses | $527.600 | Cuota 1 se envía del EFECTIVO de Primavera | ≈ 1,98 % |
| $37.000.000 | por confirmar | $421.000 | Cuota se envía del EFECTIVO de Primavera | — (falta el plazo) |

Las dos cuotas que se envían suman $948.600 (salidas "Cuota banco" de Primavera desde EFECTIVO). Cuando exista la
Fase 0c se ligan como primer pago de su préstamo (no quedan como historial); la cuota 1 del de 20M se registra como
pago sin mover cuentas ("descontada del préstamo").

**"Quedarían si se pagara todo"**: en un color de aviso que resalte, con "VALOR APROXIMADO / de referencia".

**Avisos (ventana emergente de recordatorios):**
- Cuotas de las deudas: desde el **25 de cada mes** hasta que se registre el pago.
- Gastos fijos: desde **2 días antes del fin de mes** (mes de 30 → el 28; de 31 → el 29; febrero de 28 → el 26) hasta que
  se registren.

**Gastos fijos de cada tienda (lista del usuario):** cuota banco BBVA don Miguel, cuota banco mamá Angie, sueldos
empleadas 1 y 2, sueldo Jhonatan por recompras, internet, YouTube, Alegra, luz, arriendo, ganancias mes a mes de
Jhonatan, Cristian y José. La plantilla del código (`FIXED_EXPENSES_TEMPLATE`) trae "Cuota Scotiabank" en vez de las
cuotas reales y además "Cuota de manejo Bancolombia": revisar en producción qué tiene cada tienda antes de cambiar.
Las ganancias de los socios son `retiro_socio`: no bajan la utilidad (es reparto de la ganancia).
