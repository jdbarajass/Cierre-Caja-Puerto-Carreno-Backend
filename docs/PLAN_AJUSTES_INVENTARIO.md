# Plan: solicitudes de ajuste de inventario (aprobadas por el admin)

Pedido del usuario (2026-11-03). Hoy las vendedoras le mandan por chat los
ajustes ("Entra 1510000015 / Sale 104110990012 / Excedente 9.900 efectivo", o
"1054399004 Disminuir 1, Sistema 7, Físico 6") y él los pasa a mano en
Alegra → Inventario → Ajustes de inventario y les manda el comprobante.

Ahora: ellas lo registran en la plataforma, en su tienda, y **nada toca
Alegra hasta que el admin lo acepta**. Al aceptar se crea el ajuste en
Alegra y la vendedora ve el número.

## Decisiones (con el usuario, 2026-11-03)

- Tipos: **conteo de inventario**, **redimir tarjeta regalo** y **cambio de
  prenda** (agregado el mismo día: el usuario aclaró que el cambio siempre es un
  ajuste y que nunca se devuelve plata, así que no depende del contador).
- Cambio de prenda: entran las prendas que devuelve el cliente y salen las que
  se lleva. A precio de venta de Alegra, lo que sale debe valer igual o más que
  lo que entra (si vale menos, debe llevar otra prenda); si vale más, el
  excedente y su medio son obligatorios (se reporta también en el cierre).
- **Nunca se devuelve plata, en ningún caso** (regla del usuario): la tarjeta
  regalo valida igual que el cambio (lo que sale vale igual o más que la tarjeta).
- Fecha del ajuste en Alegra: la del día de la solicitud (hora Colombia). El
  admin acepta a los pocos minutos, así que es el mismo día.
- "¿Quién lo pide?": obligatorio, se elige entre las empleadas de la tienda.
- Un ajuste de Alegra por solicitud (fácil de rastrear); "Aceptar todas" es un
  solo clic.
- El excedente de la tarjeta regalo es SOLO una nota: la plata entra por el
  cierre de caja (excedentes). Aquí no se suma a Cuentas (se contaría dos veces).

## Cómo se encuentra la prenda

En Alegra el código NO está en "referencia" (vacía): va al final del nombre de
la variante, "CAMISETA NIÑA 39900 / 1054399004" (verificado con el ajuste 1785
de Carreño). Se busca en la lista de ítems activos (la que ya usa Inventario,
en caché 5 min) por el código después de " / " o por la referencia. Al
aceptar se vuelve a leer cada ítem directo de Alegra (existencia y costo
promedio del momento).

## Reglas

- Conteo: la vendedora pone la cantidad física; el backend calcula la
  diferencia contra Alegra al enviar y guarda la diferencia (+N / −N). Si
  entre el envío y la aprobación se vende algo, bajan sistema y físico por
  igual: la diferencia sigue siendo correcta. Se avisa si la existencia cambió.
- Tarjeta regalo: entra 1 tarjeta (el código debe ser una TARJETA/BONO
  REGALO), salen una o más prendas.
- Costo de cada renglón: costo promedio del ítem en Alegra (lo que Alegra pone
  solo en "Costo promedio"); si no tiene, el precio.
- Bodega: la bodega por defecto del ítem (Carreño "Principal" id 1; Primavera
  se lee de Alegra, no se fija en el código).
- No se deja una existencia en negativo: esa solicitud se devuelve a pendiente
  con el motivo.
- Que nunca se aplique dos veces: la solicitud pasa a "aplicando" antes de
  llamar a Alegra; la observación del ajuste lleva la marca `[KOAJ-AJ-<id>]`.
  Si Alegra no respondió (caída/timeout) queda "por revisar" y, al reintentar,
  primero se busca en los ajustes de ese día uno con la marca.
- Por tienda (StoreScopedMixin + X-Store). Vendedoras (sales) y admin crean;
  solo el admin acepta/rechaza; el admin de solo lectura solo ve.

## Fases

1. **Backend** (`app/models/inventory_request.py`,
   `app/services/inventory_requests.py`, `app/routes/inventory_requests.py`,
   recordatorio "ajustes pendientes" en `app/services/reminders.py`, pruebas en
   `tests/test_inventory_requests.py`).
2. **Pantalla de las vendedoras**: Inventario → Ajustes de inventario, dos
   opciones, búsqueda del código al escribirlo (nombre + existencia).
3. **Pantalla del admin**: pendientes con existencia actual y avisos,
   Aceptar / Aceptar todas / Rechazar con motivo; historial con el número de
   Alegra.

## Estado

- 2026-11-03: fases 1-3 hechas, más cambio de prenda y "nunca se devuelve plata"
  también en tarjeta regalo. SUBIDO 2026-11-03 (backend 347e2fb..277bcdd,
  frontend 28748d2..709cedc). Backend: 13 pruebas de ajustes OK (suite 319/320
  con el parche de WMI; la que falla, de llegadas datáfono/Addi, ya fallaba
  antes). Frontend: npm test, eslint y build OK.
- Pendiente: Manual Deploy en Render; probar en producción con UNA solicitud real
  pequeña (crea un ajuste de verdad en Alegra); repetir pruebas en el PC personal.
