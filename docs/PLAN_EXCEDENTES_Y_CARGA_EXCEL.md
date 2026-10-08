# Plan: excedentes del cierre en Cuentas, bloqueo de la sincronización y carga del Excel de cierre

Pedido del usuario (2026-10-08). Las vendedoras hacen el cierre de las 8 pm en el Excel `Formato Cierre Caja <día>.xlsx` (pestañas CIERRE CAJA y CIERRE ALEGRA) y después lo pasan a mano a la plataforma (Cierre diario de caja). Se quería: (1) que los excedentes queden bien en las cuentas, (2) que solo un **Cierre exitoso** pase a Cuentas y (3) poder subir el Excel para que llene el cierre.

| Fase | Qué | Estado |
|---|---|---|
| 1 | Excedentes por medio en Cuentas (subtotal ventas + excedentes = total) y bloquear "Sincronizar" si el cierre no salió exitoso | **Hecha 2026-10-08** (commit local; falta push y Manual Deploy) |
| 2 | Subir el Excel del cierre para llenar el formulario (sin guardarlo), con avisos; la vendedora revisa y envía | Pendiente (después de probar la Fase 1) |

---

## Análisis del Excel (Formato Cierre Caja 07 de OCTUBRE 2026)

**CIERRE CAJA**
- Cuadro "Total Dinero En Caja 1": cantidades `C5:C8` (monedas 100, 200, 500, 1.000) y `C13:C18` (billetes 2.000 … 100.000). `D29` = total real en caja.
- Cuadro "Cierre de turno (Base en Caja 1 = $450.000)": cantidades que se dejan de base `G5:G18` (las escogen a mano). `H22` = total base; `F23` avisa si la base está completa.
- Cuadro "Efectivo a Consignar en Caja 2": `K = C − G` por denominación; `L22` = **valor efectivo a consignar** (plata física sin base).
- "Excedentes Gastos y Préstamos": `D23` excedente datáfono, `D24` excedente QR/transferencias, `D25` excedente efectivo, `D26` gastos operativos, `D27` préstamos. `D30` base 450.000.
- `D34 = D31 + D26 + D27 − D25` (efectivo sin base + gastos + préstamos − excedente) se compara con el efectivo de Alegra (`D37 = 'CIERRE ALEGRA'!F10`): `D38 = D34 − D37`, "Cierre de caja exitoso" si da 0.

**CIERRE ALEGRA** (se copia a mano de Alegra)
- `C13` total facturación, `F10` efectivo, `F11` Nequi, `F12` Daviplata, `F13` QR, `F15` Datáfono Addi (Alegra lo cuenta como transferencia), `F16` débito, `F17` crédito.
- `F14 = F11+F12+F13+F15` (transferencias como las ve Alegra), `F18 = F16+F17` (datáfono Alegra), `F19 = F16+F17+F15` (datáfono real: Addi cae al datáfono).
- `C17 = F10+F14+F18` vs `C15` (total): `C18` diferencia. `D30` "Cierre Exitoso" si efectivo + QR + datáfono + Nequi + Daviplata = total.
- La sección de tarjetas regalo (`B37:F48`) queda fuera (decisión del usuario: se quedan en el Excel).

**Ejemplo 7-oct-2026:** caja 1.184.000 − base 450.000 = 734.000 a consignar; 734.000 + gastos 3.000 − excedente 600 = 736.400 = efectivo de Alegra → exitoso.

**La plataforma ya hace lo mismo** (`cash_calculator.py`): calcula sola la base (knapsack), consulta Alegra sola y valida `efectivo Alegra + excedente efectivo − gastos − préstamos + desfases = a consignar` (diferencia < $100), más transferencias (Nequi+Daviplata+QR+Addi vs transfer de Alegra) y datáfono (débito+crédito vs tarjetas de Alegra). Lo único que escribe una persona: conteo, reparto de transferencias, débito/crédito, excedentes, gastos y préstamos.

---

## Qué es un excedente y cómo se interpreta

Plata que entra a la caja o a una cuenta **pero no es venta de Alegra**: la diferencia de un cambio de prenda (camiseta de 49.900 por jean de 109.900: el cliente paga 60.000), la diferencia al redimir una tarjeta regalo, las vueltas que deja un cliente (100, 600 pesos).

**Decisión:** el excedente es un **otro ingreso**, aparte de las ventas.
- **No** cambia ventas, metas, incentivos, estadísticas ni la regla 70/30 (todo eso sale de las facturas de Alegra).
- **Sí** entra a la cuenta del medio por el que llegó, para que el saldo de Cuentas coincida con el banco. Ejemplo del usuario: QR con $15.000.000 de ventas netas + $200.000 de excedentes = $15.200.000; una recompra de $15.200.000 deja la cuenta en 0 y no en −200.000.

### Lo que estaba mal antes (corregido en la Fase 1)
- El excedente en **efectivo** sí entraba a EFECTIVO (el cierre abona la plata física, que lo trae adentro) pero mezclado con las ventas.
- Los excedentes en **Nequi, Daviplata, QR y datáfono no entraban a ninguna cuenta**: el cierre abonaba lo registrado (= Alegra). Además no se guardaban.

### Cambios de prenda: ¿ajuste de inventario o nota crédito?
Hoy el usuario cuadra el inventario con un **ajuste de inventario** en Alegra. El inventario queda bien, pero: la diferencia que paga el cliente no queda facturada (no aparece en ventas y queda como excedente), la factura original sigue diciendo que se vendió la camiseta y el jean sale sin factura (el costo va a la cuenta de ajustes, no al costo de ventas). Lo estándar en Alegra es **nota crédito (devolución) sobre la factura original + factura nueva del jean** pagada con ese saldo + la diferencia. Así no hay excedente, el inventario se mueve solo y la venta es la real. **Por confirmar con el contador** (incluida la parte de facturación electrónica). Mientras tanto se sigue registrando como excedente.

---

## Fase 1 (hecha 2026-10-08)

### Backend
- `CashClosing` (`app/models/cash_closing.py`): columnas `excedente_efectivo`, `excedente_nequi`, `excedente_daviplata`, `excedente_qr`, `excedente_datafono`, `validation_status` (`success` | `warning` | `error`) y `validation_message`. Migración en `_migrate_employee_tables` (`app/__init__.py`), sin DEFAULT: los cierres viejos quedan en NULL. `excedentes()` (por payment_key) y `can_sync` (`validation_status` NULL o `success`). `to_dict` los incluye.
  - OJO: `efectivo` sigue siendo la plata física a consignar y **ya incluye** `excedente_efectivo`; `nequi`, `daviplata`, `qr`, `addi_datafono` son lo registrado (= Alegra) y **no** incluyen su excedente.
- `POST /api/sum_payments` (`app/routes/cash_closing.py`): guarda excedentes y el estado de la validación en cada envío (si se corrige y reenvía, se actualiza; si ya estaba sincronizado no se toca, como antes).
- Sincronización (`app/routes/accounts.py`):
  - `_claim_and_credit_closing`: ventas como movimiento `cash_closing` (efectivo = `efectivo − excedente_efectivo`) y cada excedente como movimiento **`excedente`** (nuevo tipo en `MOVEMENT_TYPES`) en su cuenta, con `cash_closing_id`. `credited[].kind` = `venta` | `excedente`. El total abonado es el mismo de antes para el efectivo; los demás medios ahora suman su excedente.
  - `POST /api/accounts/sync-daily`: sin fecha (botón y cron de las 9 pm) sincroniza solo los pendientes con `can_sync`; los demás vuelven en `blocked` [{date, validation_status, validation_message, message}] y se quedan pendientes. Con fecha de un cierre bloqueado → **409**. El cron sigue recibiendo 200.
  - `GET /api/accounts/sync-status`: agrega `blocked` (pendientes sin Cierre exitoso); `pending_count` los sigue contando.
- Cuentas → Mes (`app/services/month_sheet.py`): columna `excedentes` (movimientos `excedente`) en el estado por cuenta y por día, e `ingresos_cierres` = ventas + excedentes. Las fotos de meses cerrados antes de esto no traen `excedentes` (el frontend lo toma como 0).
- Cuentas → Año (`app/services/monthly_summary.py`): `excedentes` del mes = movimientos `excedente` de cierres con fecha en el mes (solo lo sincronizado = cierres exitosos) y `ventas_mas_excedentes`; también en `totals`. Ventas, ganancias y 70/30 **no cambian**.
- Tests: `tests/test_excedentes_cierre.py` (4: exitoso con excedentes y abono separado + Mes + Año; no exitoso bloqueado hasta corregir, también con fecha; sin excedentes igual que antes; cierre viejo sin estado se sincroniza). `tests/test_multi_store.py`: el Alegra simulado ahora cuadra con el cierre de prueba (antes salía no exitoso). **263/263** (en el PC de la entidad con el parche de WMI: repetir en el PC personal).

### Frontend
- `CuentasLayout.jsx` (Gestión de cuentas): etiqueta del movimiento "Excedente del cierre (no es venta)"; al sincronizar dice qué es excedente y muestra en rojo los cierres que no se sincronizaron; junto al botón, la lista de fechas "Sin Cierre exitoso".
- `CuentasMes.jsx`: columna **Excedentes** (resumen y día por día) y "Ventas + excedentes" en cada cuenta que tenga excedentes.
- `CuentasAnual.jsx`: columna **Excedentes** junto a Ventas (tabla, celular y total) y en la tarjeta de Ventas "+ excedentes = total".
- `Dashboard.jsx` (Cierre diario): si la validación no es `success`, aviso "no se va a sincronizar con Cuentas hasta que salga Cierre exitoso".

### Límites conocidos
- Los excedentes que no son en efectivo de cierres **anteriores** al cambio no se guardaron: no se pueden recuperar (si hace falta, Ajuste manual).
- El excedente de datáfono entra bruto a ADDI + DATÁFONO; su comisión no entra en "Registrar en Gastos" (las comisiones salen de los recibos de Alegra). Montos pequeños.
- "warning" (efectivo cuadra pero transferencias o datáfono no) también bloquea: el abono a las cuentas saldría mal. Se corrige el reparto y se reenvía.

### Probar en producción (después del Manual Deploy)
1. Hacer un cierre con un excedente en QR (o uno de prueba en un día ya cerrado que no esté sincronizado) → debe salir Cierre exitoso.
2. Gestión de cuentas → Sincronizar: el mensaje muestra "QR (excedente) $…" aparte.
3. Cuentas → Mes: la cuenta muestra Ventas, Excedentes y "Ventas + excedentes".
4. Un cierre con diferencia: en Gestión de cuentas aparece "Sin Cierre exitoso: fecha" y no se abona.

---

## Fase 2 (pendiente): subir el Excel para llenar el cierre

Decisión: **solo llena el formulario**, no envía el cierre solo. El archivo **no se guarda**.

1. En Cierre diario, después de la preconsulta, botón "Subir Excel del cierre".
2. Backend `POST /api/cash_closing/parse-excel` (multipart, `openpyxl` ya está en requirements, `data_only=True`; el archivo trae los valores calculados porque Excel los guarda): lee
   - fecha (`CIERRE ALEGRA!B3`, "Reporte de ventas diarias del d/m/aaaa"),
   - conteo `CIERRE CAJA!C5:C8` y `C13:C18`,
   - excedentes `D23` (datáfono), `D24` (QR: preguntar a qué subtipo: por defecto QR), `D25` (efectivo); gastos `D26`, préstamos `D27`,
   - transferencias y tarjetas `CIERRE ALEGRA!F11` Nequi, `F12` Daviplata, `F13` QR, `F15` Addi, `F16` débito, `F17` crédito,
   - y lo que escribieron de Alegra (`F10`, `C13`) solo para avisar si no coincide con lo que trae la plataforma.
   Buscar las celdas por el texto de la etiqueta (ej. "Total Dinero En Caja 1") y no solo por posición, para aguantar filas movidas; si algo no se encuentra, error claro.
3. Avisos: fecha del Excel ≠ fecha del cierre; valores de Alegra del Excel ≠ Alegra; base escogida en el Excel ≠ base que calcula la plataforma (el total a consignar es el mismo).
4. El formulario queda lleno; la vendedora revisa y toca Enviar como hoy. Se guarda en el borrador local como si lo hubiera escrito.
5. Tests con un Excel de ejemplo armado con openpyxl en el test (no versionar el Excel real).
