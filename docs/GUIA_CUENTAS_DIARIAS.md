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

**A fin de mes:**
1. En **Cuentas → Mes**, toca **"Registrar en Gastos"** en el cuadro de comisiones: resta de ADDI + DATÁFONO lo que cobran el datáfono (3,8 %) y Addi (7,735 %).
2. Revisa los gastos fijos del mes en **Gastos**: ninguno debe quedar "Vencido" sin pagar.
3. Escribe los saldos reales, que todo diga "Cuadra" y toca **"Cerrar el mes"** (con una nota si quieres). Si después cambias algo de ese mes, la plataforma te avisa; puedes **Reabrir** y volver a cerrar.

---

## Preguntas frecuentes

- **¿Lo que sobra de un mes pasa al siguiente?** Sí, solo. El "saldo inicial" de cada cuenta es lo que quedó el mes anterior. Ya no hace falta anotar recompras en el mes anterior como hacías en el Excel.
- **¿Me equivoqué en un gasto?** Edítalo o bórralo con el lápiz / la caneca en Gastos: el saldo de las cuentas se corrige solo.
- **¿Por qué la venta del mes de Alegra no es igual a "Ventas (cierres)" en una cuenta?** La tabla de ventas viene de Alegra (lo vendido); "Ventas (cierres)" es lo que se abonó a cada cuenta con el cierre de caja (el efectivo ya viene sin lo que se sacó de la caja ese día).
- **Una cuenta del Excel no aparece (Bold, SisteCrédito):** sus ventas sí salen en la tabla de ventas; a qué cuenta llega la plata de Bold queda por confirmar.
