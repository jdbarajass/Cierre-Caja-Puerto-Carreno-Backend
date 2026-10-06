# Plan: Cuentas diarias y cierre de mes (reemplazo del Excel KOAJ_CARRENO2026.xlsx)

Creado: 2026-10-06. **Guía para el usuario (subir y usar, sin términos técnicos): `GUIA_CUENTAS_DIARIAS.md`** (actualizarla en cada fase). Se construye **por fases, una a la vez**, cada una probada, documentada (CHANGELOG de cada repo + este archivo) y commiteada antes de pasar a la siguiente. **Arranca el 1-oct-2026** (lo anterior se queda en el Excel; para el resumen mensual se cargará septiembre, ver Fase 3).

Estado de las fases (actualizar al cerrar cada una):

| Fase | Qué | Estado |
|---|---|---|
| 1 | Gastos y otros movimientos de plata + gastos fijos + préstamos entre tiendas + enlace con Empleadas | **Hecha (2026-10-06), commiteada; falta push + Manual Deploy y probar en producción** |
| 2 | Hoja del mes: ventas diarias por los 10 medios, plata en tránsito (datáfono/Addi), estado por medio de pago, conciliación, cerrar/reabrir mes | **Hecha (2026-10-06), commiteada; falta push + Manual Deploy y probar en producción** |
| 3 | Resumen mensual y anual (CierreGeneral + DATOS_ANUALES) con inventario a fin de mes | Pendiente |
| 4 | Extras: bonos regalo, regla 70/30, incentivos/metas, gastos en el comparativo de tiendas | Pendiente |

---

## 1. Qué hace el Excel hoy (análisis completo)

Archivo `KOAJ_CARRENO2026.xlsx` (raíz de `CIERRE_KOAJ`, no versionado). Una hoja por mes (ENERO…OCTUBRE) con la misma plantilla, más `DATOS_ANUALES_2026`, `CierreGeneral2026` y `Bonos Regalos_2026`.

### Hoja de cada mes
1. **Ventas diarias** (A3:L35): fecha, EFECTIVO, QR, AHORRO (datáfono débito), CRÉDITO (datáfono crédito), NEQUI, ADDI, BBVA, DAVIPLATA, BOLD; total del día; excedente (medio + valor). Calificación del día: `≤680.000 VENTA MALA`, `≤1.000.000 BAJITA`, `≤2.000.000 BUENA`, `>2.000.000 ALTA` (con conteo y suma por categoría, M36:O41). Subtotales 1-15 y 16-31.
2. **Recompras** (Q:AC), en dos bloques (1-15 y 16-31): fecha, "valor aún no enviado", EFECTIVO, DATÁFONO, QR, DAVIPLATA, NEQUI, BBVA, total, 4x1000 y "valor sobrante". → **Ya existe en el sistema: Cuentas Recompras** (descuenta cuentas y cobra el 4‰ sola; balance de Jhonatan arrastrado desde sep-2026).
3. **Gastos operacionales** (AE:AM), dos bloques: concepto, fecha, EFECTIVO, DATÁFONO, QR, DAVIPLATA, NEQUI, BBVA, total. El 4x1000 se suma a mano en las transferencias (`=X+(X*4)/1000`). → **No existe en el sistema (Fase 1).**
4. **Saldo por medio** (B43:J50, B55:G61): ventas del mes − recompras − gastos de cada medio, + lo que quedó de los meses anteriores ("TOTAL LO QUE HAY EN TODAS LAS CUENTAS. ACUMULADO"). Datáfono −3,8 %, Addi −7,7 % y "falta que consigne Addi". "Acople efectivo (siempre debe dar cero)" y alerta de saldos negativos. → **El sistema lo tiene a medias**: Cuentas → Resumen lleva el saldo vivo de cada cuenta (cierres + recompras + ajustes), sin gastos ni vista por mes (Fases 1 y 2).
5. **Gastos fijos** (K54:S74): concepto, valor de inicio y fin de mes, valor de referencia y un aviso "registrado / NO registrado" (`COUNTIF` por el texto del concepto en la tabla de gastos): cuota Davivienda (15), cuota Scotiabank (5) $1.110.000, sueldos empleadas 1 (15) y 2 (30), sueldo Jhonatan por recompras $200.000 ×2, internet (5) $266.000, YouTube (20) $41.900, Alegra (22) $139.900, luz (30) ~$380-500 mil, arriendo (30) ~$1.052.000-1.110.000, cuota de manejo y 4x1000 Bancolombia, incentivos 1 y 2 (si se pasa la meta), ganancias de los socios (Cristhian, Jhonatan, José $1.000.000). → **Fase 1.**
6. Otros bloques: metas 1 y 2 (venta del año anterior +25 %), 70 % resurtido / 30 % utilidad, "utilidad bruta" y "% de ganancia", fórmulas de recompra con el 35 %, préstamos y ropa de empleadas (ya existe en Empleadas), ahorro y deudas (notas a mano).

### DATOS_ANUALES_2026
Por mes: lo vendido por medio (efectivo, QR, datáfono, Nequi, Addi, BBVA, Daviplata), "descontado" (lo que quedó de cada medio), venta total, ganancia, fletes, lo que tiene Jhonatan; totales del año y "total movido en el año" por medio. **Desde agosto las fórmulas apuntan a la hoja JULIO** (ganancia = venta completa): la idea se conserva, los números de ago-oct no sirven.

### CierreGeneral2026
Por mes: ventas, recompras, gastos operativos, ganancia neta (= ventas − gastos), ganancia real (= ventas − recompras − gastos), % de ganancia, total y promedio del año. Aparte: inventario al 30/31 de cada mes y cuánto aumentó. Lleno hasta julio. **El usuario quiere llenarlo desde septiembre.**

### Bonos Regalos_2026
Tarjetas de regalo: valor, número, medio de pago, fecha de compra, fecha de redención, nota. (Fase 4.)

### Errores encontrados en el Excel (informados al usuario)
1. Septiembre y octubre tienen fechas de agosto en la columna A (pestaña duplicada; los valores sí son del mes: sep = $42.239.140, cuadra con Alegra).
2. DATOS_ANUALES de agosto en adelante apunta a JULIO.
3. CierreGeneral vacío desde agosto; inventario hasta julio.
4. Sumas largas dentro de una celda (`=569900+610900+…-850000…`): no se sabe qué es cada número.
5. El 4x1000 a veces dentro del valor y a veces en fila aparte ("Impuesto 4X1000 de recompras").

---

## 2. Cómo opera la tienda (lo explicó el usuario, 2026-10-06)

- La tienda está a distancia. Lo vendido en efectivo **se acumula** día a día en la tienda hasta que las empleadas lo consignan; de ahí sale para recompras, sueldos (a veces ellas mismas se pagan el sueldo de la caja), arriendo, etc. Por eso el Excel tiene sumas y restas acumuladas.
- Las empleadas piden **préstamos** (ya existe la sección Préstamos en Empleadas: debe quedar conectada).
- **Primavera** se está montando: varios gastos (herrajería, arriendo, fletes, equipos) se pagaron con plata de Carreño. **Primavera se los debe devolver** → se manejan como **préstamo de Carreño a Primavera** (cuadro momentáneo).
- Las ganancias que retira cada socio se anotan porque la plata sale de una cuenta (no son gasto: son retiro de socio).
- Las recompras no son gasto, pero se restan del medio de pago porque la plata sí salió.
- **Fechas mezcladas a propósito**: si en agosto quedaron $6 M de QR y el 3-sep se hace una recompra de $3 M con esa plata, el usuario la anotaba en la hoja de agosto para que agosto mostrara lo que realmente quedó (en septiembre solo habían entrado $1 M de QR).
  - **Cómo lo resuelve el sistema:** cada cuenta lleva **saldo acumulado** (lo que sobra de un mes pasa solo al siguiente, como ya pasa en Resumen y en el balance de Jhonatan). La recompra se registra con su fecha real (3-sep) y sale de un saldo que ya incluye los $6 M de agosto: queda bien sin cambiar de mes. Para la **ganancia** cada gasto tiene además **"mes al que corresponde"** (por defecto el mes de la fecha; editable): el internet de septiembre pagado el 5-oct cuenta como gasto de septiembre.

### Medios de pago (decisión del usuario)
Ventas: **EFECTIVO, QR, AHORRO (datáfono débito), CRÉDITO (datáfono crédito), NEQUI, ADDI, BBVA, DAVIPLATA, SISTECRÉDITO, BOLD.**

Cuentas donde vive la plata (ya existen en Resumen): EFECTIVO (`cash`), QR BANCOLOMBIA (`qr`, cuenta …5494), ADDI + DATÁFONO (`addi_datafono`, Bancolombia …6018: ahí llegan datáfono y Addi), NEQUI, DAVIPLATA, BBVA, SisteCrédito, AHORRO (`ahorro`, fondo de ahorro: no confundir con "AHORRO" = tarjeta débito del datáfono).

### Cuándo llega la plata (para la Fase 2)
- **Datáfono (débito/crédito):** llega el **siguiente día hábil** a la cuenta …6018, menos **3,8 %**.
- **Addi:** llega a la misma cuenta …6018 unos **30 días después** de la venta (reporte de pagos de Addi: venta 5-oct → pago 4-nov; 29-sep → 29-oct; 25-sep → 26-oct, se corre si cae en fin de semana). Descuento: **tarifa de intermediación 6,5 % + IVA 19 % sobre esa tarifa = 7,735 %** (ej.: venta $204.700 → tarifa $13.305,50 + IVA $2.528,05 → llega $188.866,45). El Excel usaba 7,7 %.
- Mientras no llegue, es **plata en tránsito**: se muestra aparte y **no cuenta como disponible** hasta su fecha de pago.

---

## 3. Criterio contable (para la Fase 3, explicado al usuario)

Clasificación de cada salida de plata (en septiembre había $28,1 M de "gastos" de los cuales ~$4,1 M eran gasto operativo real):

| Categoría | Ejemplos | ¿Resta de la cuenta? | ¿Resta de la ganancia del mes? |
|---|---|---|---|
| Gasto operativo | Sueldos, arriendo, servicios, aseo, bolsas, motocarro, Alegra | Sí | Sí |
| Flete / costo de mercancía | Flete Bogotá–Carreño | Sí | Sí (como costo de la ropa) |
| Gasto financiero | 4x1000, cuotas de manejo, intereses | Sí | Sí |
| Cuota de crédito | Scotiabank, Davivienda | Sí | Solo los intereses (por ahora se toma completa como gasto; ver Fase 3) |
| Inversión / activo | Cámaras, computador, impresora, herrajería | Sí | No (se usa por años) |
| Préstamo a empleada | Préstamos a Mónica | Sí | No (se recupera) |
| Préstamo a otra tienda | Lo pagado por Carreño para Primavera | Sí | No (Primavera lo devuelve) |
| Retiro de socio | Ganancia de Jhonatan/Cristhian/José | Sí | No (es reparto de la ganancia) |
| Recompra | Envíos a Jhonatan | Sí (Cuentas Recompras) | No directamente: ver fórmula |

```
Costo de lo vendido = Inventario inicial + Compras del mes − Inventario final
Ganancia real       = Ventas − Costo de lo vendido − Gastos operativos (− financieros)
```
Si el inventario sube, esa plata no se perdió: está en la tienda. Por eso el inventario mes a mes es clave (Fase 3). La "ganancia real" del Excel (ventas − recompras − gastos) se seguirá mostrando, porque es la que el usuario usa para saber cuánta plata quedó.

---

## 4. Fases

### Fase 1 — Gastos y otros movimientos de plata (desde 1-oct-2026)
Nueva pestaña **Cuentas → Gastos** (solo admin, por tienda).

**Backend**
- Modelo `Expense` (`expenses`, por tienda): fecha de pago, `period` (mes al que corresponde, `YYYY-MM`), concepto, categoría, `direction` (`out` salida / `in` entrada), montos por medio (`efectivo`, `datafono` = cuenta ADDI + DATÁFONO, `qr`, `daviplata`, `nequi`, `bbva`, `ahorro`), 4x1000 (automático sobre lo que no es efectivo, o editado a mano con `fee_override`), `account_mode`, notas, enlace a gasto fijo, tienda relacionada (préstamos entre tiendas), empleada y enlaces a `EmployeeLoan` / `EmployeePayment`.
- `account_mode`:
  - `cuentas` (por defecto): descuenta (o suma, si es entrada) de las cuentas de Resumen con movimientos tipo `expense` / `expense_in` ligados por `reference_id='expense-{id}'`; al editar se revierte y se rehace, al borrar se revierte (mismo patrón que las recompras).
  - `caja`: **salió de la caja del día**. El cierre de caja ya abona a EFECTIVO lo que queda después de sacar los gastos y préstamos del día, así que **no** se vuelve a descontar (solo cuenta para la ganancia y para Empleadas).
  - `sin_mover`: no toca cuentas (históricos o algo ya descontado por otro lado).
- Categorías de salida: `operativo`, `flete`, `financiero`, `cuota_credito`, `inversion`, `prestamo_empleada`, `prestamo_tienda`, `retiro_socio`, `sueldo`, `otro`. De entrada: `devolucion_prestamo`, `devolucion_prestamo_tienda`, `ingreso_extra`.
- Enlace con **Empleadas**: `prestamo_empleada` con empleada → crea/actualiza/borra el `EmployeeLoan`; `sueldo` con empleada → `EmployeePayment` (quincena). No registrar el mismo préstamo también a mano en Empleadas.
- **Gastos fijos** (`FixedExpense`, por tienda): nombre, valor de referencia, día de pago, categoría, medio por defecto, activo. Estado por mes: **pagado / pendiente / vencido** (vencido = pasó el día de pago y no hay gasto ligado con ese `period`). Plantilla del Excel cargable con un botón (solo si la tienda no tiene gastos fijos).
- **Préstamos entre tiendas**: saldo = préstamos (`prestamo_tienda`, salida de la tienda que presta) − devoluciones (`devolucion_prestamo_tienda`, entrada en la tienda que presta). Cada tienda ve lo que prestó y lo que debe.
- Endpoints `/api/expenses…` (ver CHANGELOG del backend).

**Frontend**
- Pestaña Gastos: selector de mes; tarjetas (total gastos del mes por categoría y por medio, entradas); tabla editable con notas; formulario; panel de gastos fijos del mes; panel de préstamos entre tiendas. Resumen se refresca al guardar. Movimientos muestra los tipos nuevos.

**Cómo quedó (2026-10-06)**
- Backend: `app/models/expense.py` (`Expense`, `FixedExpense`, mapas de medios y categorías), `app/routes/expenses.py`:
  - `GET /api/expenses?year&month`: movimientos con fecha en el mes **o** que corresponden al mes. `totals.out_total` / `in_total` / `fee_total` (por fecha, todos los modos), `by_method` (por fecha, **solo `account_mode='cuentas'`**: lo que movió Resumen), `by_category` (por `period`, para la ganancia).
  - `POST /api/expenses`, `PUT|DELETE /api/expenses/<id>`.
  - `GET /api/expenses/fixed?year&month` (estado del mes), `POST /api/expenses/fixed`, `PUT|DELETE /api/expenses/fixed/<id>` (al borrar, los pagos se conservan sin enlace), `POST /api/expenses/fixed/load-template` (14 gastos fijos del Excel; 409 si ya hay).
  - `GET /api/expenses/inter-store`: `lent` (lo que esta tienda prestó) y `owed` (lo que debe), con sus movimientos.
  - Movimientos en Resumen: tipos `expense` (salida) y `expense_in` (entrada), `reference_id='expense-{id}'`. Si a la tienda le falta la cuenta del medio → 400 (no se omite en silencio como en recompras).
  - Empleadas: `prestamo_empleada` → `EmployeeLoan` por el total; `devolucion_prestamo` con empleada → `EmployeeLoan` **negativo** (abono: baja el total acumulado); `sueldo` con empleada → `EmployeePayment` tipo quincena. Al cambiar de categoría o borrar el gasto, el registro ligado se borra.
  - Tests: `tests/test_expenses.py` (13). Suite completa 215/215.
- Frontend: `src/pages/CuentasGastos.jsx` (pestaña **Cuentas → Gastos**), `src/services/expensesService.js`; `LiveMoneyInput` pasó a `src/components/common/LiveMoneyInput.jsx` (compartido con Cuentas Recompras). En celular las tablas se ven como tarjetas.
- Verificado en Chromium (escritorio 1366 y celular 390) con backend local: gasto fijo pagado, préstamo a Primavera con 4x1000, aseo "de la caja del día" (no mueve EFECTIVO), saldos de Resumen correctos, sin desborde horizontal.
- **Limitaciones conocidas / para después:**
  - Si Primavera devuelve plata desde SUS cuentas, hoy se registra la entrada en Carreño (`devolucion_prestamo_tienda`) y, aparte, la salida en Primavera (categoría `otro` o la que aplique). El saldo del préstamo solo mira lo registrado en la tienda que prestó.
  - Editar a mano en Empleadas un préstamo/pago que vino de Gastos no cambia el gasto (se recomienda editarlo desde Gastos).
  - Las recompras siguen con su propia lógica (`app/routes/repurchase.py`); unificar con la de gastos queda pendiente si hace falta.

### Fase 2 — Hoja del mes (estado por medio de pago)
- Vista "todo de una" como el Excel: días del mes × 10 medios de pago con total y calificación del día (umbrales configurables), recompras y gastos del mes.
- **Fuente de las ventas por medio: los recibos de pago de Alegra** (`/payments` tipo `in`; verificado 2026-10-06 con el conector de Alegra de Carreño). Cada recibo trae `paymentMethod` **y** `bankAccount`, que es lo que permite separar los 10 medios sin digitar nada:
  - `bankAccount` **QR** → QR; **ADDI** → Addi (llega con `paymentMethod` transfer o credit-card); **DATAFONO** + `debit-card` → AHORRO (débito), + `credit-card` → CRÉDITO; `cash` (Efectivo POS / Caja general) → EFECTIVO. Nequi, Daviplata, BBVA, Bold y SisteCrédito: confirmar el nombre de su cuenta en Alegra al empezar (no salieron en la muestra).
  - Ignorar los recibos sin factura ("Apertura de turno", "Cierre de turno", cuentas Caja chica).
  - **Agrupar por la fecha de la FACTURA**, no la del recibo (ej.: recibo del 6-oct en efectivo de una factura del 5-oct cuenta para el 5).
  - Caso raro: un recibo `transfer` con cuenta "Caja general" (34.900 el 5-oct) el usuario lo contó como QR → regla: `transfer` sin cuenta de banco = QR, mostrarlo marcado para revisar.
  - **Prueba del 5-oct-2026 contra el Excel: cuadra exacto** (efectivo 384.500, QR 391.350, ahorro 170.000, crédito 193.950, Addi 204.700 = 1.344.500).
  - Guardarlo en la copia de facturas que ya carga el cron de las 9 pm (nueva tabla de pagos por factura, por tienda), para no llamar a Alegra cada vez.
- Plata en tránsito: datáfono (D+1 hábil, −3,8 %) y Addi (~30 días, −7,735 %): fecha estimada de llegada, monto neto, y pasa a disponible al llegar (con confirmación manual o ajuste de la fecha/monto real).
- Estado por medio: saldo inicial (final del mes anterior) + ventas − comisiones − recompras − gastos ± ajustes/transferencias = saldo final; "saldo real" digitado → diferencia (el "acople debe dar cero"). Día por día al desplegar.
- Cerrar mes (foto guardada) y reabrir; todo editable con comentarios.
- **Saldos de partida (decisión del usuario, 2026-10-06): los de Cuentas → Resumen al 5-oct-2026 a las 9 pm son los reales.** El saldo al 1-oct se calcula hacia atrás (saldo − movimientos de octubre). Captura de ese momento: Efectivo $3.485.000, Nequi $397.350, Daviplata $0, QR $3.067.991, ADDI + DATÁFONO $3.506.103 (contempla hasta 5-oct), SisteCrédito $0, BBVA $0, Ahorro $3.924.204, Jhonatan $2.710.000.
  - Cruce con el Excel de octubre: Efectivo = "valor aún no enviado" del Excel; QR = ventas QR de octubre ($5.198.075) − gastos QR de octubre ($2.130.084) → **esos gastos ya están descontados en Resumen** (probablemente con ajustes manuales); Nequi = ventas de octubre; Ahorro = Excel. **ADDI + DATÁFONO difiere $29.592** del Excel ($3.506.103 vs $3.476.511): revisar en la conciliación.
  - El efectivo que abona el cierre ya viene sin lo pagado de la caja: 1-oct 1.845.800 + 1.300 excedente − 426.000 arriendo = 1.421.100 consignado; 2-oct 1.007.400 + 700 − 53.200 aseo = 954.900.

**Cómo quedó (2026-10-06)**
- Backend:
  - `app/models/month_sheet.py`: `PaymentFact` (`payment_facts`, un recibo por factura, con `medio` ya clasificado y `needs_review`), `AccountReconciliation` (saldo real por cuenta y mes), `MonthClose` (foto JSON del mes).
  - `app/services/payment_facts.py`: festivos de Colombia (Ley Emiliani, calculados), `arrival_date` (datáfono D+1 hábil; Addi +30 días o el siguiente hábil: **coincide con el reporte de pagos de Addi del usuario**), `net_amount`, `classify_payment`, `sync_payments` (pagina `/payments` del más nuevo al más viejo hasta pasar `since`; descarga todo y solo después reemplaza). Primera carga desde `PAYMENTS_START` (1-oct-2026), luego los últimos 7 días.
  - `AlegraClient.get_payments_page` (`/payments?type=in&order_direction=DESC`).
  - `app/services/month_sheet.py`: ventas por día y medio + calificación; estado por cuenta con la **fecha de negocio** de cada movimiento (cierre → fecha del cierre, recompra → fecha del envío, gasto → fecha del gasto, ajustes/transferencias → día de registro en Colombia); saldo final del mes = saldo actual − movimientos posteriores; tránsito; comisiones; foto del cierre.
  - `app/routes/month_sheet.py`: `GET /api/month-sheet?year&month`, `POST /api/month-sheet/sync-payments` (admin o `X-Sync-Token`; body `since` opcional), `PUT /api/month-sheet/reconciliation`, `POST /api/month-sheet/commissions` (un gasto financiero por mes en ADDI + DATÁFONO, marcado `auto:comisiones:AAAA-MM` en notes; idempotente), `POST|DELETE /api/month-sheet/close`.
  - El cron de las 9 pm ya carga los pagos: `invoice_facts/sync` llama `_sync_payments` (si falla no marca error). **No se tocó el workflow.**
  - Tests: `tests/test_month_sheet.py` (12; el 5-oct con recibos de formato real de `/api/v1/payments` cuadra con el Excel). Suite 227/227.
- Frontend: `src/pages/CuentasMes.jsx` (pestaña **Cuentas → Mes**, después de Resumen), `src/services/monthSheetService.js`. Tarjetas (venta, calificaciones, comisiones con botón "Registrar en Gastos", por llegar), tabla de ventas diarias (los 10 medios; oculta Bold/BBVA/Daviplata/SisteCrédito si el mes no tiene), estado por cuenta con saldo real y día por día, plata por llegar y cerrar/reabrir. En celular, tarjetas.
- Verificado en Chromium (1366 y 390) con las ventas del 1 al 5-oct del Excel y los saldos de Resumen del 5-oct: total $14.793.275 (= Excel), QR $5.198.075, Addi por llegar 3-nov y 4-nov.
- **Limitaciones / pendientes:**
  - Cuenta a la que llega Bold: sin confirmar (`MEDIO_ACCOUNT['bold'] = None`); no entra al tránsito.
  - El saldo real no admite negativos en el campo (LiveMoneyInput solo dígitos).
  - Las comisiones de meses sin "Registrar en Gastos" no se arrastran al disponible estimado de meses siguientes (solo las del mes).
  - Las ventas en el estado de cuenta vienen de los cierres (lo abonado), no de Alegra; la tabla de ventas sí es Alegra.

### Fase 3 — Resumen mensual y anual
- Por mes (desde **sep-2026**): ventas totales y por medio, recompras, gastos por categoría, ganancia neta, ganancia real, % de ganancia, fletes, inventario al último día del mes y su variación, con total y promedio del año, y gráfico.
- **Inventario a fin de mes**: el sistema ya consulta `/reports/inventory-value-totals` de Alegra con `to_date` (`GET /api/inventory/quick-total?to_date=…`, el "Inventario total" del Dashboard). Llamándolo con el último día de cada mes se tiene el histórico sin digitar; guardarlo en una tabla al cerrar el mes. **Verificar si el valor es a costo o a precio de venta** comparando con el Excel (ene $151.871.964, feb $172.911.621, mar $178.821.276, abr $186.063.892, may $189.017.262, jun $192.873.771, jul $174.013.437).
- Septiembre: cargar los gastos del Excel como `sin_mover` (no tocan cuentas) para que el resumen arranque en septiembre.

### Fase 4 — Extras
Bonos regalo; regla 70/30 (resurtido/utilidad) configurable; metas e incentivos (el sistema usa +15 % en Estadísticas → Metas, el Excel +25 %); gastos en el comparativo de tiendas.

---

## 5. Decisiones tomadas
- 2026-10-06 (2): ventas por medio desde los recibos de pago de Alegra (cuenta + método); saldos de partida = Resumen al 5-oct 9 pm. Los gastos de octubre ya descontados en Resumen se registran en Gastos con "No mover cuentas" (o se borran los ajustes manuales y se registran con "De las cuentas"); arriendo parte de sep. y aseo del 2-oct con "De la caja del día".
- 2026-10-06: empezar el 1-oct-2026; fases una por una; medios de pago listados arriba; Addi y datáfono separados como medio de venta, pero llegan a la misma cuenta …6018; gastos de Primavera pagados por Carreño = préstamo de Carreño a Primavera; resumen mensual desde septiembre.
