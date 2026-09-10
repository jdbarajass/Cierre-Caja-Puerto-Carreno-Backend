# Changelog - Cierre de Caja API (Backend)

---

## [2026-09-10] (continuación) - "Saldo total" ya no mezcla el Ahorro con la plata disponible para recomprar

El usuario notó que, al agregar la cuenta AHORRO (ver entrada anterior, mismo día), el "Saldo total (real)" la sumaba junto con las demás - dando la impresión de que hay más plata disponible para recomprar de la que realmente hay, con el riesgo de terminar gastando sin querer el ahorro.

### 🏦 `app/routes/accounts.py` — `GET /api/accounts`
- Nueva constante `ACCOUNTS_EXCLUDED_FROM_RECOMPRA_TOTAL = {'ahorro'}`. `total_balance` ya no suma las cuentas de esa lista - el ahorro se sigue viendo en su propia tarjeta y sigue disponible para ajustes/transferencias, simplemente no participa del total "disponible para recomprar".

### ✅ Verificación
- Prueba funcional: QR con $1.000.000 y AHORRO con $4.360.000 → `total_balance` devuelve $1.000.000 (sin el ahorro).
- Verificado también visualmente contra un backend local: "Saldo total (real)" y "Total Recompras" (ver CHANGELOG del frontend) muestran $1.000.000, sin mezclar el $4.360.000 de Ahorro.

**Deploy:** requiere Manual Deploy en Render — sin migración de datos, es solo un cambio de qué se suma en la respuesta del endpoint.

---

## [2026-09-10] - Nueva cuenta AHORRO en Resumen

El usuario pidió agregar una tarjeta de "Ahorro" (saldo real actual: $4.360.000) a Cuentas → Resumen, con la misma flexibilidad de las demás cuentas: poder sumarle/restarle dinero manualmente, y poder transferirle desde cualquier otra cuenta (ej. una parte de las ganancias de fin de mes) o sacarle plata hacia otra cuenta.

### 🏦 `app/routes/accounts.py`
- Nueva cuenta por defecto **AHORRO** (`payment_key='ahorro'`, color `emerald`, `sort_order=8`) en `DEFAULT_ACCOUNTS`. Como `seed_default_accounts()` ya es idempotente y no destructivo (solo agrega cuentas que falten, igual que cuando se agregó BBVA), esta se crea sola en el próximo arranque sin tocar el saldo de ninguna cuenta existente.
- **No fue necesario tocar ningún otro endpoint**: "Ajuste manual de saldo" y "Transferir entre cuentas" ya operan de forma genérica sobre cualquier `account_id` — en cuanto la cuenta existe, ambos flujos funcionan con ella automáticamente.

### ✅ Verificación
- Prueba funcional contra `app.test_client()` + SQLite temporal: la cuenta AHORRO se siembra sola (arranca en $0, sin afectar el saldo $0 de las demás en una BD nueva); un ajuste manual de entrada por $4.360.000 la deja en $4.360.000; una transferencia de $500.000 desde QR hacia AHORRO deja QR en $500.000 y AHORRO en $4.860.000.
- Probado también visualmente con Playwright contra un backend local: la tarjeta aparece en el grid de Resumen y en ambos selects de "Transferir entre cuentas".

**Deploy:** requiere Manual Deploy en Render — la cuenta se crea sola al arrancar, arranca en $0. **El usuario debe hacer un "Ajuste manual → Entrada → $4.360.000" una sola vez** después del deploy para reflejar el saldo real actual (a propósito no se hardcodeó ese monto en el código: `seed_default_accounts()` es una función genérica de estructura, no de datos reales).

---

## [2026-09-09] (continuación 2) - Cuentas Recompras: la comisión no se estaba descontando de ninguna cuenta

El usuario detectó, revisando un envío real ($189.800 por QR), que el "Valor neto" mostrado (comisión ya restada) no correspondía a lo que realmente pasa: a Jhonatan le llega el monto completo que se digita, y la comisión la debería asumir la tienda descontándola de la cuenta de origen — no del socio.

### 🐛 La causa
- `_sync_entry_account_movements()` descontaba de cada cuenta (efectivo/QR/etc.) exactamente el monto digitado, **sin sumarle la comisión**. La comisión (4‰) se calculaba y se mostraba en pantalla, pero nunca salía de ninguna cuenta real - dinero "invisible" que el banco sí cobra pero el sistema nunca registraba como salida.
- El balance de Jhonatan (`recibido = total_enviado + sobrante_acumulado`) ya usaba el monto completo (sin restar comisión) - esa parte ya estaba bien, coincidiendo con lo que el usuario espera.

### 🔧 `app/routes/repurchase.py` — `_sync_entry_account_movements()`
- Ahora descuenta de cada cuenta el monto enviado **más su parte proporcional de la comisión** del envío. Si todo el envío sale de un solo medio (el caso típico), toda la comisión sale de esa cuenta. Si un envío se reparte entre varios medios, la comisión se reparte proporcionalmente, con el resto exacto del redondeo asignado al último medio procesado (para que la suma cuadre exacto, sin perder ni sobrar un peso).
- Ejemplo real verificado: QR=$189.800, comisión 4‰=$759 → antes se descontaban $189.800 de QR; ahora se descuentan $190.559 (correcto).

### 🗄️ `app/models/repurchase.py`
- Nueva propiedad `total_a_descontar` = `total_enviado + fee_4mil` (lo que realmente sale de las cuentas), expuesta en `to_dict()`. `valor_sobrante` (enviado − comisión) se deja intacta en el modelo por compatibilidad, pero ya no se usa en el frontend para mostrar el "valor neto" de cada envío.

### ✅ Verificación
- Prueba funcional contra `app.test_client()` + SQLite temporal: envío de $189.800 solo por QR → cuenta QR descontada exactamente $190.559. Envío repartido en 2 medios (efectivo $100.000 + QR $89.800, mismo total) → comisión repartida $400/$359, suma exacta $190.559 entre ambas cuentas, sin error de redondeo.
- Probado end-to-end con Playwright contra un backend local (nunca producción): guardar el envío real de $189.800 por QR desde la UI dejó la cuenta QR en **-$190.559** y el "Balance disponible (Jhonatan)" en **$189.800** - exactamente el comportamiento esperado.
- **No es retroactivo**: los envíos ya sincronizados antes de este fix no se recalculan ni se les descuenta la comisión faltante con efecto retroactivo - solo los envíos nuevos (creados/editados desde este cambio) aplican la comisión correctamente.

**Deploy:** requiere Manual Deploy en Render — sin migración de datos (cambio de comportamiento hacia adelante únicamente).

## [2026-09-09] (continuación) - Fix: "Diferencia con Alegra" en Cuentas usaba una fórmula distinta a la del cierre

Tras desplegar el fix de zona horaria (ver entrada anterior, mismo día), el usuario hizo el cierre del 8, vio "¡Cierre Exitoso! Los montos registrados coinciden con los datos de Alegra", pero en Cuentas la pantalla de sincronización mostraba "Diferencia con Alegra: $253.200" para ese mismo cierre. Investigado: son dos fórmulas distintas.

### 🐛 La causa
- `validar_cierre()` (`cash_calculator.py`), la que decide si el cierre sale "exitoso", compara `Alegra efectivo + Excedente efectivo - Gastos operativos - Préstamos + Desfases` contra el total a consignar — los ajustes existen porque Alegra reporta el efectivo de venta ANTES de sacar excedentes/gastos/préstamos.
- La comparación de `accounts.py` (`_claim_and_credit_closing`, ejecutada al sincronizar) volvía a golpear la API de Alegra por su cuenta y comparaba `efectivo_para_consignar_final` (YA con esos ajustes aplicados) directo contra el efectivo crudo de Alegra, **sin sumar el excedente ni restar gastos/préstamos**. Un cierre con un excedente/gasto de $X mostraba una "diferencia" de $X en Cuentas aunque el cierre hubiera validado perfecto.
- Reproducido con un caso sintético idéntico al reportado (excedente de $253.200, cierre válido): la fórmula vieja daba exactamente $253.200 de diferencia; la correcta da $0.

### 🔧 `app/routes/cash_closing.py` — `_apply_closing_fields()`
- Ahora guarda en el `CashClosing` la comparación con Alegra que **ya se calculó** al momento del cierre (`validacion_cierre`, con todos los ajustes), en vez de dejar que `accounts.py` la recalcule después con una fórmula distinta: `alegra_total_efectivo`, `alegra_total_transferencia`, `alegra_total_tarjeta`, `alegra_discrepancy` (= `suma_efectivo_ajustada - efectivo_para_consignar`, la misma resta que decide si el cierre validó), `alegra_checked = True`.

### 🔧 `app/routes/accounts.py` — `_claim_and_credit_closing()`
- Eliminada la segunda consulta a Alegra y el recálculo de discrepancia durante la sincronización — ahora simplemente reutiliza `closing.alegra_discrepancy`, ya correcto desde que se guardó el cierre. Efecto secundario positivo: una llamada menos a la API de Alegra por cada sincronización, y un punto menos de falla (ya no hay un `try/except AlegraConnectionError` en este paso). Imports de `AlegraClient`/`AlegraConnectionError` removidos por quedar sin uso en este archivo.
- **Nota para cierres históricos ya sincronizados** (antes de este fix): su `alegra_discrepancy` guardado quedó calculado con la fórmula vieja (potencialmente incorrecto si esos días tuvieron excedentes/gastos/préstamos). No es recalculable automáticamente porque el cierre no guarda esos valores por separado (solo el total final ya ajustado) — si hace falta auditar un día específico, hay que revisarlo a mano. Los cierres nuevos, de aquí en adelante, ya quedan correctos desde el momento en que se guardan.

### ✅ Verificación
- `python -c "import ast; ..."` sin errores en los 2 archivos.
- La app arranca correctamente (99 rutas registradas) tras remover los imports sin uso.
- Prueba dedicada llamando directamente a `validar_cierre()` con el escenario exacto reportado (Alegra $1.000.000 en efectivo, excedente $253.200, cierre válido): confirma `cierre_validado=True`, la fórmula vieja da $253.200 de "diferencia" inexistente, la nueva da $0.

**Deploy:** requiere Manual Deploy en Render — sin migración de datos adicional (los cierres nuevos se guardan correctos desde que se suben estos cambios; los históricos quedan con el valor viejo, sin corrección automática por lo explicado arriba).

---

## [2026-09-09] - Fix crítico: bug de zona horaria en `parse_colombia_date` corría 1 día toda fecha de cierre + corrección de datos históricos

El usuario reportó que hizo el cierre del 8 de septiembre, vio "¡Cierre Exitoso!", pero el aviso de "cierre pendiente" seguía diciendo que faltaba. Investigado a fondo: no fue un error del usuario, es un bug real que lleva casi un año en el código.

### 🐛 `app/utils/timezone.py` — `parse_colombia_date()`
- **La causa raíz:** para una fecha simple sin hora (ej. `"2026-09-08"`, exactamente lo que manda el frontend), `parser.isoparse()` devuelve un `datetime` **naive** (sin zona horaria). Llamarle `.astimezone(COLOMBIA_TZ)` a un datetime naive hace que Python asuma que representa la hora **local del servidor** — y Render corre sus contenedores en **UTC**, no en hora de Colombia. Resultado: convertir "medianoche asumida como UTC" a Colombia (UTC-5) da las 7pm del día ANTERIOR, y `.date()` sobre eso devuelve un día menos.
- Reproducido y confirmado exactamente: `parse_colombia_date("2026-09-08")` en un servidor con hora de sistema en UTC devolvía `closing_date = 2026-09-07`.
- **Bug presente desde el commit `4461655` (2025-11-16)** — existe desde que se creó esta función, casi un año antes de este fix.
- **Qué SÍ estuvo bien todo este tiempo:** los montos del cierre y la comparación con Alegra (`client.get_sales_summary(str(cash_request.date))`, línea 252 de `cash_closing.py`) usan el string de fecha crudo, nunca pasan por esta función — así que ningún cierre calculó mal su dinero. Solo la ETIQUETA `closing_date` guardada en la tabla `cash_closings` (usada por `pending-dates`, `sync-daily`, `sync-status` y el filtro de fecha de `list_movements`) quedaba corrida un día.
- **Fix:** si el datetime parseado es naive (sin offset explícito), ahora se localiza directamente como hora de Colombia (`COLOMBIA_TZ.localize(dt)`) en vez de convertirse desde una zona ambigua. Si el string SÍ trae un offset explícito, se sigue convirtiendo normalmente. Verificado que ya no depende en absoluto de la zona horaria del sistema operativo.
- Afecta (y corrige de una sola vez, por ser la misma función compartida) los 4 puntos donde se usaba: `cash_closing.py` (persistencia del cierre y preconsulta), `accounts.py` (`list_movements` por rango de fechas, `sync-daily` con fecha explícita).

### 🗄️ `app/__init__.py` — `_fix_historical_closing_dates_timezone_bug()` (nueva migración de datos, una sola vez)
- Como el bug existe desde antes de que se creara el módulo Cuentas (28 de agosto), **todo** cierre guardado hasta ahora tiene `closing_date` corrida 1 día hacia atrás respecto al día real que seleccionó la vendedora. A pedido del usuario, se corrige automáticamente en el próximo arranque: suma 1 día a cada `CashClosing` que ya existía antes de este deploy.
- **Riesgo real identificado y resuelto:** como `closing_date` es única, sumar 1 día en cualquier orden puede chocar momentáneamente con el cierre del día siguiente (ej. el 6 se convierte en 7 mientras el 7 original todavía no se ha tocado → violación de la restricción única). Se procesa en orden **descendente** (`closing_date DESC`) con un `flush()` por fila, así la fecha destino siempre queda libre antes de escribirla. Verificado con 3 cierres en días **consecutivos** (el caso de riesgo exacto): sin errores.
- Guardada con una bandera en `app_settings` (`closing_date_timezone_offset_fix_applied`) para que **nunca se repita**, ni en el próximo reinicio ni en ningún deploy futuro — los cierres creados con el código ya corregido no se tocan.

### ✅ Verificación
- `parse_colombia_date("2026-09-08")` ya no depende de la zona horaria del sistema (confirmado simulando explícitamente un sistema en UTC, como Render).
- Migración probada con `app.test_client()`/`create_app()` real contra SQLite temporal: 3 cierres en fechas consecutivas (7, 8, 9 de septiembre) corregidos correctamente a (8, 9, 10) en la primera corrida, sin violar la restricción única; una segunda llamada a `create_app()` confirma que no se vuelve a aplicar.

**Deploy:** requiere Manual Deploy en Render — la migración de datos corre sola en el próximo arranque, no requiere ningún paso manual en la base de datos. **Importante para el usuario:** después de este deploy, el cierre del 8 de septiembre (que quedó guardado como 7) debe aparecer corregido a la fecha real automáticamente.

---

## [2026-09-08] - Aviso de cierres pendientes; sincronización automática cubre días atrasados; estado y alertas de sincronización

A raíz de una pregunta del usuario sobre qué pasa si no se hace el cierre de caja un día y se hace atrasado al día siguiente: se confirmó que ni el botón "Sincronizar ahora" ni el cron de las 9pm sincronizaban nada que no fuera la fecha de **hoy**, así que un cierre atrasado nunca se acreditaba a las cuentas. Esta entrada corrige eso y agrega visibilidad sobre el estado de la sincronización.

### 🗄️ `app/models/app_setting.py` (nuevo)
- Tabla genérica clave/valor (`app_settings`) para banderas que el sistema necesita recordar entre reinicios sin ameritar su propia tabla. Se crea sola en el próximo arranque vía `db.create_all()` (registrada en `app/__init__.py`), sin necesitar `ALTER TABLE` manual.

### 🔔 `app/routes/cash_closing.py` — `GET /api/cash_closing/pending-dates`
- Nuevo endpoint (roles admin/sales) que devuelve las fechas pasadas sin cierre de caja registrado, para alimentar el aviso fijo del dashboard.
- **Ancla de "empezar desde hoy"** (`_get_or_init_pending_closings_tracking_start`, usa `app_settings`): la primera vez que se consulta este endpoint (en la práctica, el día del deploy) se guarda esa fecha como punto de partida y **nunca se mueve hacia atrás**. Sin esto, una tienda que ya viene usando el sistema hace meses (con cierres a veces llevados a mano, o días sueltos sin registrar antes de que existiera este aviso) habría visto aparecer de golpe todo ese historial como "pendiente" el día que se activa la función. Verificado con una BD sembrada con huecos históricos reales (mayo-julio): la primera consulta devuelve `missing_dates: []`.
- Tope adicional de 30 días hacia atrás (`PENDING_LOOKBACK_DAYS`) como salvaguarda, aunque en la práctica el ancla de arriba es la que manda casi siempre.

### 🔄 `app/routes/accounts.py` — `POST /api/accounts/sync-daily` reescrito
- **Antes:** sin `date` en el body, sincronizaba únicamente el cierre de **hoy**. Un cierre atrasado (ej. el de ayer, hecho hoy porque no se alcanzó a tiempo) nunca se sincronizaba automáticamente — ni el botón ni el cron lo cubrían jamás.
- **Ahora:** sin `date`, sincroniza **todos** los cierres con `synced_to_accounts=False` hasta hoy inclusive, del más antiguo al más reciente, en una sola llamada. Con `date` explícito se mantiene el comportamiento anterior (sincronizar solo ese día puntual), para llamadas directas a la API contra una fecha específica.
- Lógica de acreditado extraída a `_claim_and_credit_closing(closing, user_id)` (reutilizada tanto para el modo "una fecha" como "todas las pendientes"), conservando el mismo "claim" atómico (`UPDATE ... WHERE synced_to_accounts=False`) que evita doble acreditado ante llamadas concurrentes (cron + clic manual, reintentos de GitHub Actions, etc.).
- El cron (`.github/workflows/daily-accounts-sync.yml`) ya llama sin `date`, así que este cambio lo beneficia automáticamente sin tocar el workflow para esa parte.

### 📊 `app/routes/accounts.py` — `GET /api/accounts/sync-status` (nuevo, solo admin)
- Devuelve `last_synced_date`, `last_synced_at`, `last_discrepancy` (del cierre sincronizado más recientemente), `pending_count` (cuántos cierres existen pero siguen sin sincronizar) y `last_failure` (ver abajo). Alimenta la línea de estado junto al botón "Sincronizar ahora" en Cuentas.
- **Fix (mismo día, encontrado por el usuario al revisar la pantalla):** "el cierre sincronizado más recientemente" estaba ordenado por `synced_at` (cuándo se ejecutó la sincronización), no por `closing_date` (qué día es el cierre). Si un cierre atrasado (ej. el del día 6) se sincronizaba DESPUÉS que uno más reciente (ej. el del día 7, ya sincronizado anoche por el cron), la pantalla mostraba el del día 6 — tapando el hecho de que el día 7 ya estaba al día, y confundiendo al usuario sobre a qué día correspondía la diferencia con Alegra mostrada. Corregido: ahora ordena por `closing_date DESC` (con `synced_at DESC` como desempate), mostrando siempre el día calendario más reciente ya sincronizado. Verificado replicando el escenario exacto (día 7 sincronizado anoche, día 6 atrasado sincronizado hoy en la mañana): ahora sí muestra el día 7 con su propia discrepancia.
- **Segundo ajuste (mismo día, a pedido del usuario):** aunque ya mostraba el día correcto, seguía existiendo el riesgo de mostrar la diferencia con Alegra de un día de **antes** de que existiera esta pantalla (ej. -$132.620 de un cierre viejo) como si fuera "lo último" - el usuario prefirió que esta línea solo considere cierres de **hoy en adelante** (mismo ancla que ya usa `pending-dates`, reutilizando `_get_or_init_pending_closings_tracking_start`). Ahora `last_synced`/`last_discrepancy` se filtran por `closing_date >= tracking_start`: mientras no exista un cierre sincronizado desde esa fecha en adelante, la pantalla muestra "Aún no se ha sincronizado ningún cierre" en vez de un dato viejo. **Importante:** este filtro es solo de pantalla — `pending_count` y el acreditado real de `sync_daily` NO se filtran por esta ancla, así que un cierre atrasado de antes de hoy sigue acreditándose a las cuentas con normalidad (verificado con una prueba dedicada: un cierre viejo sin sincronizar se sigue contando en `pending_count` y se acredita igual al llamar `sync-daily`, pese al ancla).

### 🚨 `app/routes/accounts.py` — `POST /api/accounts/sync-failure` (nuevo) + `.github/workflows/daily-accounts-sync.yml`
- El workflow de GitHub Actions ahora tiene un segundo paso (`if: failure()`) que llama a este endpoint cuando el cron falla después de sus 3 reintentos — así el fallo queda visible en el sistema (banner rojo en Cuentas) en vez de perderse en un log de CI que nadie revisa a diario. Reutiliza el mismo `X-Sync-Token` que ya existía, sin secrets nuevos.
- La alerta se limpia sola en la siguiente `sync_daily` exitosa (`_clear_sync_failure_alert()`), **incluso si no había nada pendiente que sincronizar** — llegar hasta ahí ya prueba que el backend y la base de datos responden bien. Bug real encontrado y corregido durante las pruebas: la primera versión solo limpiaba la alerta en la rama "sí había algo que sincronizar", dejando la alerta pegada para siempre si alguien hacía clic en "Sincronizar ahora" sin que hubiera nada pendiente.

### ✅ Verificación
- `python -m py_compile` sin errores en los 4 archivos tocados.
- Pruebas funcionales con `app.test_client()` + SQLite temporal (sin tocar producción): ancla de `pending-dates` fijándose en la primera llamada y no listando historial viejo con huecos; `sync-daily` sincronizando 3 días pendientes (2 atrasados + hoy) en una sola llamada y sumando el monto correcto; segunda llamada sin duplicar saldo; `sync-status` reflejando última sincronización y discrepancia; `sync-failure` registrando la alerta y `sync-daily` limpiándola después, incluso sin cierres pendientes.
- Bug real encontrado y corregido antes de dar por buena la implementación: faltaba `from datetime import datetime` a nivel de módulo en `cash_closing.py`, causando `NameError` en la primera llamada real a `pending-dates` (no se detectó con `ast.parse`, solo al ejecutar el endpoint).

**Deploy:** requiere Manual Deploy en Render (este servicio no tiene auto-deploy activo) — la tabla `app_settings` se crea sola al arrancar, sin pasos manuales en la base de datos.

---

## [2026-09-02] - Fix: import roto en metas de ventas; timeout de Gunicorn insuficiente para inventario completo

### 🐛 `app/routes/cash_closing.py`
- `/api/sales_comparison_yoy` (usado por "Metas de Ventas" en Totales de Ventas) fallaba con 500 en el 100% de los casos: `from app.utils.formatting import format_cop` referenciaba un módulo inexistente (el módulo real es `app.utils.formatters`, como ya se importaba correctamente unas líneas más abajo en el mismo archivo). Typo corregido. Confirmado en producción antes del fix: `{"details": "No module named 'app.utils.formatting'", "error": "Error inesperado al procesar la solicitud"}`.

### ⏱️ `Procfile`
- El botón "Consultar Inventario" (`GET /api/direct/inventory/value-report?limit=3000`) pagina secuencialmente contra Alegra (200 items por página) y la propia UI advierte "puede tardar entre 1 y 3 minutos" — pero Gunicorn tenía `--timeout 120`, por debajo de lo que la app promete. Reproducido en producción: a los 120.7s exactos el worker es matado y el cliente recibe un 500 HTML crudo (no el error JSON controlado de Flask). Se subió `--timeout 120` → `--timeout 240` para dar margen sobre los 3 minutos anunciados. No resuelve la causa de fondo (la paginación secuencial contra Alegra), solo evita que la petición se corte a mitad de camino; documentado en `MEJORAS_PENDIENTES.md` como candidato a paralelizar más adelante.

### ✅ Verificación
- `python -m py_compile` sin errores en `cash_closing.py`
- Fix de `format_cop` verificado por inspección: `app/utils/formatters.py` sí exporta `format_cop` (se usa igual en la línea 860 del mismo archivo)
- Cambio de timeout es de una sola línea en `Procfile`, sin lógica que probar; se verificará en producción tras el deploy manual en Render

**Deploy:** requiere Manual Deploy en Render (este servicio no tiene auto-deploy activo).

## [2026-09-01] - Comisión editable por envío; quitar "valor no enviado" de la UI

### 💰 Comisión editable (`app/models/repurchase.py`, `app/routes/repurchase.py`)
- Nueva columna `RepurchaseEntry.fee_override` (Float, nullable): si está seteada, `fee_4mil` la usa en vez de calcular el 4‰ automático sobre `total_enviado`. `to_dict()` la expone.
- `create_entry`/`update_entry` aceptan `fee_override` en el payload (número o `null` para volver al cálculo automático)
- `list_entries`: el total de comisión del mes ahora es la **suma de `fee_4mil` de cada envío** (respeta los overrides) en vez de recalcular 4‰ sobre el total agregado
- `monthly_summary`: mismo ajuste, acumula `fee_4mil` por envío en vez de recalcular por mes

### 🗑️ `valor_no_enviado` sigue existiendo en el modelo/DB (sin cambios) pero se quitó de la interfaz del frontend — ver [CHANGELOG del frontend](../Cierre-Caja-Puerto-Carreno-Frontend/CHANGELOG.md). No se tocó el backend para este campo: no participaba de ningún cálculo, así que dejar de enviarlo desde el formulario no requiere ningún cambio aquí (el default sigue siendo 0).

### 🗄️ Migración
- `app/__init__.py`: nueva columna `repurchase_entries.fee_override` (`ALTER TABLE`, sin DEFAULT — NULL = comisión automática, comportamiento idéntico al de siempre para todos los envíos existentes)

### ✅ Verificación
- `python -m py_compile` sin errores
- Probado end-to-end contra backend local: envío de $1.000.000 en efectivo muestra $4.000 de comisión automática (4‰); al sobrescribirla a $10.000 y guardar, la tabla y el pie de página ("Total Facturas") reflejan $10.000 / $990.000 neto correctamente, con un ícono ✎ indicando que la comisión fue editada a mano

---

## [2026-09-01] - Conectar Cuentas Recompras con Resumen: los envíos descuentan saldo real

### 💸 `app/routes/repurchase.py`
- Nuevo mapeo `REPURCHASE_ACCOUNT_MAP` (medio de pago del envío → `payment_key` de la cuenta en Resumen: efectivo→cash, datafono→addi_datafono, qr→qr, daviplata→daviplata, nequi→nequi, bbva→bbva)
- Nueva función `_sync_entry_account_movements()`: al crear un envío, descuenta automáticamente cada cuenta según el medio de pago usado (crea un `AccountMovement` tipo `repurchase_send`, ligado al envío vía `reference_id=f'repurchase-entry-{id}'`); al editar, revierte los movimientos anteriores y crea los nuevos según los montos actualizados; al eliminar, revierte (repone el saldo). Todo bloqueando las cuentas tocadas (`with_for_update`, orden determinístico por id) para evitar carreras con ajustes/transferencias concurrentes
- **No retroactivo:** solo los envíos creados desde este cambio (`synced_to_accounts=True`) participan de esta sincronización. Los envíos ya existentes en la base no se tocan, ni siquiera si se editan después — quedan como estaban, sin conectar a ninguna cuenta
- `valor_no_enviado` (plata aún no enviada) y `sobrante_mes_anterior` (plata que el socio ya tenía) quedan fuera del descuento a propósito: no representan salida de dinero de una cuenta en ese movimiento

### 🏦 `app/routes/accounts.py`
- Nueva cuenta por defecto **BBVA** (`payment_key='bbva'`, saldo inicial $0) — el campo BBVA de los envíos no tenía cuenta equivalente en Resumen
- `seed_default_accounts()` ahora agrega cuentas que falten sin volver a tocar las existentes (antes solo sembraba si la tabla estaba completamente vacía) — así la cuenta BBVA se crea también en producción sin afectar los saldos ya acumulados de las otras 6

### 🗄️ Modelos y migración
- `app/models/repurchase.py`: nueva columna `synced_to_accounts` (Boolean, sin default SQL a propósito — los envíos existentes quedan en NULL/False)
- `app/models/account.py`: nuevo tipo de movimiento documentado `repurchase_send`
- `app/__init__.py`: migración seguro (`ALTER TABLE`) para la columna nueva

### ✅ Verificación
- `python -m py_compile` sin errores
- Probado end-to-end contra un backend local (SQLite, sin tocar producción): replicando el ejemplo real del usuario — ADDI+DATÁFONO con $8.000.000, se registra un envío con datáfono=$2.000.000 → el saldo de Resumen baja a $6.000.000 automáticamente. Se probó también editar ese envío (subir a $5.000.000 → saldo baja a $3.000.000, revirtiendo primero el movimiento viejo) y eliminarlo (saldo vuelve a $8.000.000)

---

## [2026-09-01] - Categorizar compras de Cuentas Recompras (ropa vs. gasto operacional)

### 🏷️ `app/models/repurchase_purchase.py`
- Nueva columna `category` en `RepurchasePurchase` (`VARCHAR(20)`, default `'ropa'`). Valores válidos: `'ropa'` (compra de mercancía, se soporta con factura) u `'operacional'` (gasolina, bolsas, cajas de cartón, etc.)
- Incluida en `to_dict()`

### 🔧 `app/__init__.py`
- Migración segura (mismo patrón `ALTER TABLE ADD COLUMN` ya usado en el proyecto) para agregar `category` a `repurchase_purchases` sin borrar datos existentes — filas antiguas quedan como `'ropa'` por defecto

### 🔀 `app/routes/repurchase.py`
- `POST /api/repurchase/purchases` y `PUT /api/repurchase/purchases/<id>` validan y persisten `category` (rechaza valores fuera de `('ropa', 'operacional')` con 400)
- `GET /api/repurchase/purchases` ahora devuelve `total_ropa` y `total_operacional` además de `total_compras`, para que el frontend muestre subtotales por categoría

### Por qué
El socio que hace las recompras de ropa (Jhonatan) también incurre en gastos operacionales (gasolina, bolsas, cajas) con el mismo dinero enviado. El balance ya restaba cualquier "compra" registrada — esto solo agrega la distinción para poder ver cuánto se fue en mercancía vs. en gastos operacionales, sin cambiar la matemática del balance (`recibido - compras`, sin importar la categoría).

### ✅ Verificación
- `python -m py_compile` sin errores en los 3 archivos tocados
- Probado end-to-end contra un backend local (SQLite local, sin tocar producción/Render): migración de columna confirmada en logs de arranque, creación de compra con `category='operacional'` y `category='ropa'` (default), subtotales y balance recalculados correctamente en la UI tras cada guardado

---

## [2026-08-21] - Re-verificación del cambio del 2026-08-19 (sin cambios de código)

### ✅ Re-confirmado localmente, todo sigue pasando
- 33/33 tests unitarios, 13/13 checks funcionales, sin regresiones. No hubo cambios de código en esta sesión.

### ⚠️ Hallazgo: Render no había desplegado el commit `2678c9d`
- Dos días después del push del 2026-08-19, `GET https://cierre-caja-api.onrender.com/health` seguía respondiendo el JSON **sin** el campo `"database"` y sin el header `X-Request-Id` — es decir, el código en producción seguía siendo el anterior al commit `2678c9d`, pese a que el push a `main` fue exitoso
- No se pudo determinar la causa exacta (sin acceso al dashboard/API de Render desde este entorno): puede ser Auto-Deploy desactivado, un build fallido servido en silencio, o el webhook de GitHub desconectado
- Se agregó una sección nueva a [TROUBLESHOOTING.md](TROUBLESHOOTING.md#cómo-verificar-que-render-desplegó-los-últimos-cambios) con el procedimiento para verificar esto en el futuro antes de asumir que un push ya está en producción

---

## [2026-08-19] - Arranque seguro, caché/retries hacia Alegra, logging estructurado y health check extendido

### 🛡️ Validación de configuración al arrancar (`app/config.py`, `app/__init__.py`)
- `Config.validate()` (chequeos de negocio: `ALEGRA_USER`, `ALEGRA_PASS`, `BASE_OBJETIVO`, `UMBRAL_MENUDO`) ahora se invoca en `create_app()`, junto con el nuevo `Config.validate_security()` (chequea que `SECRET_KEY`/`JWT_SECRET_KEY` no sigan en su valor por defecto)
- En producción (`DEBUG=False`), si falta algo crítico el arranque se aborta con `RuntimeError` en vez de quedar "roto" en silencio; en DEBUG/TESTING solo advierte por log
- **Importante:** `Config.validate()` (sin `_security`) se sigue usando tal cual en `app/routes/cash_closing.py` en cada request de `/api/sum_payments` — los checks de secretos viven aparte en `validate_security()` para no bloquear cada cierre de caja solo porque `SECRET_KEY`/`JWT_SECRET_KEY` no estén rotados. (Este fue un bug real detectado y corregido durante las pruebas de esta misma sesión: la primera versión mezclaba ambos checks en `validate()` y hacía que `/api/sum_payments` devolviera 500 en cualquier entorno sin esas dos variables seteadas explícitamente.)

### ⚡ Caché + reintentos con backoff hacia Alegra (`app/services/alegra_client.py`, nuevo `app/utils/ttl_cache.py`)
- `get_invoices_by_date()` cachea en memoria las facturas de fechas **pasadas** (el día actual NUNCA se cachea, porque sigue recibiendo ventas) — TTL configurable vía `ALEGRA_CACHE_TTL_SECONDS` (default 600s)
- Reintentos automáticos con backoff exponencial (adaptador `urllib3.Retry` montado en la sesión de `requests`) para peticiones GET ante timeouts, errores de conexión y HTTP 429/500/502/503/504 — nunca reintenta POST/PUT/DELETE, para evitar duplicar operaciones

### 📋 Logging estructurado JSON + Sentry opcional (nuevo `app/utils/logging_utils.py`)
- Cada request recibe un `request_id` (header `X-Request-Id`, generado o propagado si el cliente ya lo manda) correlacionado en todos sus logs
- Formato controlado por `LOG_FORMAT` (default `json` en producción, `text` en DEBUG)
- `setup_sentry()` en `app/__init__.py`: se activa solo si se define `SENTRY_DSN`; si `sentry-sdk` no está instalado no rompe el arranque. Se agregó `sentry-sdk[flask]==2.18.0` a `requirements.txt`

### 🩺 `/health` extendido (`app/routes/health.py`)
- Ahora también verifica conectividad a la base de datos (`SELECT 1`) además del check de Alegra que ya existía

### 🧪 Fix de tests preexistentes (no relacionado a los cambios de arriba)
- `tests/test_cash_calculator.py`: `test_aplicar_ajustes` y `test_calcular_venta_efectivo_alegra` esperaban una fórmula vieja (restar gastos/préstamos) que ya no coincide con la lógica actual documentada como "Escenario A" en `cash_calculator.py` (gastos y préstamos ya se sacan físicamente del efectivo ANTES de contar, así que no se vuelven a restar). Se actualizaron las expectativas de ambos tests para que coincidan con el comportamiento real y documentado del código — no se tocó `cash_calculator.py`.

### ✅ Verificación realizada
- `pytest` no se pudo correr en este entorno por un bug pre-existente del runner en Windows (ver [TROUBLESHOOTING.md](TROUBLESHOOTING.md#pytest-falla-con-io-operation-on-closed-file), reproducible en código sin modificar). Se corrieron los tests unitarios puros (`test_cash_calculator.py`, `test_formatters.py`, `test_knapsack_solver.py`) mediante un script manual: **33/33 pasaron**.
- Pruebas funcionales manuales con `app.test_client()` contra una base SQLite temporal: `/health` (con y sin DB/Alegra simulando fallos), login correcto/incorrecto/usuario inexistente/email inválido, `/auth/verify` con y sin token, ruta protegida por rol (`/api/users`), y `/api/sum_payments` con credenciales de Alegra inválidas (confirma que devuelve un error controlado — 502 — en vez de un 500 sin manejar). **13/13 checks pasaron** (tras corregir el bug de `validate()` descrito arriba).
- Caché y retry de `AlegraClient` verificados con un script que mockea `session.get`: confirma 1 sola llamada HTTP para 2 consultas de una fecha pasada (cache hit), y que el día actual nunca se sirve desde caché.

---

## Notas Técnicas
- Backend: Python 3.14.3, Flask 2.2.5, Gunicorn 22.0.0
- Ver [README.md](README.md) para instalación y [TROUBLESHOOTING.md](TROUBLESHOOTING.md) para problemas comunes de entorno
