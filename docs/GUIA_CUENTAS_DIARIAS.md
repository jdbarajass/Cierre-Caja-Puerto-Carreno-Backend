# Guía: cómo subir y usar las Cuentas diarias

Guía paso a paso para el administrador (sin términos técnicos). Se va actualizando con cada fase. Detalle técnico: `PLAN_CUENTAS_DIARIAS.md`.

---

## Parte 1. Subir los cambios (se hace una sola vez cada vez que hay cambios nuevos)

Los cambios ya están guardados en tu computador ("commit"). Falta **subirlos a GitHub** ("push") y **actualizar el servidor** (Render). Vercel (la página) se actualiza sola al subir.

1. **Cámbiate a una red sin bloqueos** (no la de la entidad): datos del celular o la red de tu casa.
2. Abre una terminal en VS Code (menú *Terminal → New Terminal*) y pega, una línea a la vez:
   ```
   cd C:\Users\JJBarajas\Pictures\CIERRE_KOAJ\Cierre-Caja-Puerto-Carreno-Backend
   git push
   cd C:\Users\JJBarajas\Pictures\CIERRE_KOAJ\Cierre-Caja-Puerto-Carreno-Frontend
   git push
   ```
   Si al final de cada `git push` sale algo como `main -> main`, quedó subido.
3. **Render (el servidor):** entra a render.com → servicio `cierre-caja-api` → botón **Manual Deploy → Deploy latest commit**. Espera a que diga *Live* (unos minutos). Las tablas nuevas se crean solas.
4. Abre la plataforma y recarga la página (Ctrl + F5).

---

## Parte 2. Primer uso (una sola vez)

### 2.1 Cuentas → Gastos
1. Entra a **Gestión → Cuentas → Gastos**.
2. Toca **"Cargar los gastos fijos del Excel"**. Aparecen arriendo, sueldos, internet, cuotas, ganancias… Revisa los valores y cámbialos con el lápiz si no son los de ahora.
3. Registra los gastos de octubre que ya hiciste (ver la tabla de abajo). **Importante:** primero mira en **Cuentas → Resumen → Movimientos** si esos gastos de QR ya están como "Ajuste manual" (los anotaste a mano). Si están, regístralos con **"No mover cuentas"** para no restarlos dos veces.

| Gasto | Valor | Mes al que corresponde | Categoría | ¿De dónde sale la plata? |
|---|---|---|---|---|
| Arriendo parte de septiembre (1-oct) | Efectivo 426.000 | Septiembre | Gasto operativo | De la caja del día |
| Borrador, toallas, escoba… (2-oct) | Efectivo 53.200 | Octubre | Gasto operativo | De la caja del día |
| Herrajería Carreño, una parte (3-oct) | QR 308.828 (quita el ✓ de "cobrar" 4x1000) | Octubre | Inversión | No mover cuentas |
| Cuota Scotiabank (5-oct) | QR 1.500.000 | Septiembre | Cuota de crédito | No mover cuentas |
| Internet (5-oct) | QR 266.000 | Septiembre | Gasto operativo | No mover cuentas |
| YouTube (5-oct) | QR 48.000 | Septiembre | Gasto operativo | No mover cuentas |

### 2.2 Cuentas → Mes
1. Entra a **Gestión → Cuentas → Mes**.
2. Toca **"Traer ventas de Alegra"**. La primera vez trae todo desde el 1 de octubre (puede tardar un minuto). Después se carga sola cada noche a las 9 pm.
3. Revisa que la tabla de ventas diarias cuadre con tu Excel (el 5 de octubre ya se comprobó que cuadra al peso).

### 2.3 Cuentas → Año (resumen mensual y anual)
1. Entra a **Gestión → Cuentas → Año** y toca **"Traer inventario de Alegra"** (trae el inventario al cierre de agosto, septiembre y el de hoy; después se actualiza solo cada noche).
2. **Comprueba el inventario:** toca "Ver enero a agosto" y, en julio, toca **"Traer"**. Si sale **$174.013.437** (lo mismo de tu Excel), Alegra da el inventario igual que tú y la columna "G. real + inventario" sirve. Si sale distinto, avísame.
3. **Llena septiembre a mano** (sus gastos están en el Excel, no en la plataforma): en la fila de septiembre toca el lápiz ✎ y escribe (con la nota "Excel"):

| Dato | Valor | De dónde sale |
|---|---|---|
| Gastos operativos | **8.201.857** | $5.954.601 de la hoja de septiembre del Excel (arriendo, sueldos, aseo, Alegra, fletes de ropa, 4x1000…) + $2.247.256 de los gastos de septiembre que pagaste en octubre (arriendo parte, Scotiabank, internet, YouTube). |
| Préstamos | **15.008.881** | Lo que Carreño pagó por Primavera ($14.646.881: herrajería, arriendo de Primavera, fletes y envíos, Julieth, locales, gasolina) + préstamos a Mónica ($362.000). |
| Inversiones | **6.956.337** | Cámaras, computador, impresora POS, herrajería de Carreño, ganchos/silla/pistola. |
| Retiros de socios | **200.800** | Ganancia de Jhonatan enviada a Sindy. |
| Recompras | revisar | El Excel dice **$12.709.593**. Si la plataforma muestra otro valor en septiembre, escribe el del Excel. |

> Esta clasificación la hice leyendo cada gasto de la hoja de septiembre. Si ves alguno distinto (por ejemplo, el envío a la hermana de Julieth no era de Primavera), cambia el valor.

---

## Parte 3. El día a día

**Cada vez que salga plata que no sea una recompra** (sueldo, arriendo, aseo, un préstamo, una ganancia de un socio, algo para Primavera):
1. **Cuentas → Gastos → "Registrar gasto"** (o **"Registrar pago"** al lado del gasto fijo, que ya llena el formulario).
2. Llena: concepto, valor en el medio por el que salió (efectivo, QR, Nequi…), categoría.
3. **¿De dónde sale la plata?**
   - **De las cuentas:** la plata salió de una cuenta (QR, Nequi, banco, o el efectivo que ya estaba guardado). El sistema la resta de Resumen.
   - **De la caja del día:** las empleadas la sacaron de la caja ese día, antes de hacer el cierre (sueldo que se pagan ellas, aseo, arriendo pagado de la caja). **No** se vuelve a restar, porque el cierre ya la descontó.
   - **No mover cuentas:** solo para dejarlo anotado (algo viejo o que ya se restó a mano).
4. **Mes al que corresponde:** si pagas en octubre algo de septiembre (internet, cuota), elige septiembre. Sirve para saber la ganancia real de cada mes.
5. Si es un **préstamo a una empleada**, elige "Préstamo a empleada" y su nombre: queda solo en Empleadas → Préstamos. Si te lo devuelve, usa **"Registrar entrada" → "Devolución de préstamo"**.
6. Si es algo que **Carreño paga por Primavera**, elige "Préstamo a otra tienda" → Primavera. Abajo verás cuánto te debe Primavera. Cuando te devuelva, **"Registrar entrada" → "Devolución de otra tienda"**.

**Cada semana (o cuando quieras revisar):**
1. **Cuentas → Mes.** Ahí ves todo como en el Excel: ventas por día y medio de pago (con "venta mala / bajita / buena / alta"), cuánta plata hay en cada cuenta y cuánta está **por llegar** del datáfono y Addi (con la fecha en que llega).
2. En cada cuenta escribe el **"Saldo real"** que ves en el banco (o lo que hay en efectivo) y toca **Guardar**. Si dice **"Cuadra"**, todo bien; si sale una **diferencia**, falta registrar algo (un gasto, una recompra, una comisión).

**Para ver cómo va el año:** **Cuentas → Año**. Por cada mes: ventas, recompras, gastos, ganancia bruta / neta / real con su %, inventario y cuánto subió o bajó; abajo, ventas por medio de pago y la plata que salió sin ser gasto (inversiones, préstamos, retiros) y lo que tiene Jhonatan. Si un dato está mal, toca el lápiz ✎ del mes y escríbelo a mano (queda marcado con ✎ y se puede volver al calculado).

**A fin de mes:**
1. En **Cuentas → Mes**, toca **"Registrar en Gastos"** en el cuadro de comisiones: resta de ADDI + DATÁFONO lo que cobran el datáfono (3,8 %) y Addi (7,735 %).
2. Revisa los gastos fijos del mes en **Gastos**: ninguno debe quedar "Vencido" sin pagar.
3. Escribe los saldos reales, que todo diga "Cuadra" y toca **"Cerrar el mes"** (con una nota si quieres). Si después cambias algo de ese mes, la plataforma te avisa; puedes **Reabrir** y volver a cerrar.

---

## Reconstrucción de 2025 (anulación masiva de facturas POS)

Las facturas POS de 2025 se anularon todas juntas por impuestos (oct-2026). Fueron ventas reales y sus prendas volvieron al inventario de Alegra. Para arreglarlo:

1. Entra a **Estadísticas → Reconstrucción 2025** y toca **"Traer todo 2025"**. Va de a 31 días (unos 2 minutos cada tanda; son unas 12). No cierres la página mientras trae; si la cierras, vuelve a tocar el botón y sigue donde iba.
2. Revisa la lista **"Anulaciones reales"**: son las que el sistema cree que se anularon de verdad durante el año (electrónicas anuladas o POS que se volvieron a facturar enseguida con lo mismo). Si alguna sí era de la anulación masiva, toca **"Fue de la anulación masiva"**. También puedes marcar cualquier factura por su número.
3. En **"Inventario antes de la anulación masiva"** toca **Calcular**: te dice cuánto vale hoy el inventario en Alegra, cuánto hay que retirar y cuánto quedaría (debería quedar cerca de los $160-175 millones que recuerdas).
4. Toca **"Descargar Excel"** y revísalo con tu contador. Las prendas marcadas en "Revisar" hay que contarlas en físico.
5. Cuando el contador lo apruebe, avísame: se crea el ajuste en Alegra desde la plataforma (Alegra no permite cargar ajustes desde un Excel).

Mientras tanto, **Metas** y la **comparación con el año anterior** del cierre de caja ya usan la venta real de 2025 en los meses que estén cargados.

---

## Preguntas frecuentes

- **¿Lo que sobra de un mes pasa al siguiente?** Sí, solo. El "saldo inicial" de cada cuenta es lo que quedó el mes anterior. Ya no hace falta anotar recompras en el mes anterior como hacías en el Excel.
- **¿Me equivoqué en un gasto?** Edítalo o bórralo con el lápiz / la caneca en Gastos: el saldo de las cuentas se corrige solo.
- **¿Por qué la venta del mes de Alegra no es igual a "Ventas (cierres)" en una cuenta?** La tabla de ventas viene de Alegra (lo vendido); "Ventas (cierres)" es lo que se abonó a cada cuenta con el cierre de caja (el efectivo ya viene sin lo que se sacó de la caja ese día).
- **Bold:** sus ventas salen en la tabla y la plata se toma como que llega a ADDI + DATÁFONO (como dijiste, "por el momento"). Su comisión y en cuántos días llega no se conocen, así que no aparece en "por llegar".
- **¿Qué es cada ganancia?** Bruta = ventas − recompras. Neta = ventas − gastos (como tu Excel). Real = ventas − recompras − gastos. "G. real + inventario" suma lo que subió el inventario: si subió, esa plata está en la tienda en ropa.
