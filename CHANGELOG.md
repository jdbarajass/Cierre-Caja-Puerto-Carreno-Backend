# Changelog - Cierre de Caja API (Backend)

---

## [2026-10-02] (continuación) - Fase 4 cerrada + marca de ex vendedoras

Revisado con el usuario en producción (Carreño, "Este año", 2-oct-2026 15:05):
- Fuente: facturas guardadas + hoy. % con cliente: **Mónica 65,1 %, Rita 46,2 %, Astrid 0 %** (coincide con lo calculado con el conector de Alegra).
- Descuentos $3.212.176 = $3.184.751 guardados + $27.425 de hoy. Por vendedora: Mónica $2.082.230 + Rita $1.020.046; la diferencia ($109.900) es exactamente la factura 8423 (2-ene) sin vendedora.
- Equipo por cédula: aparecieron 2 ex vendedoras (Neiby Femayor 12,7 %, Cristhian Muñoz 20 % — esta última facturada a un cliente "Koaj" con su cédula). Mónica 14,4 %, Rita 18,9 %. Total equipo $458.875.
- Descuentos altos a clientes visibles en "Facturas con descuento" (41,4 % y 50 %): para revisar si fueron autorizados.

Ajuste: `employee` (en rankings, equipo, inactivas y facturas con descuento) trae `active` (False si la vendedora está inactiva en Alegra); nueva función `employee_info`. +1 test (**93/93**, con el parche WMI local).

## [2026-10-02] (continuación) - Fase 4.3: el dashboard de clientes usa las facturas guardadas

Carga completa de Carreño verificada en producción: 274/274 días (1-ene a 1-oct), 3.093 facturas (2 anuladas), venta $380.986.649 = igual al peso al reporte de Alegra; 99,7 % con vendedora, 100 % con cédula, 107 facturas con descuento ($3.184.751).

- `GET /api/analytics/customers/summary`: si **todos los días cerrados** del periodo están en `invoice_facts`, calcula con ellos (desde la base, sin consultar Alegra) **+ las ventas de hoy en vivo** (`AlegraClient.get_invoices_by_date(hoy)`), sin anuladas. Si falta algún día, usa el reporte agregado como antes. Campo nuevo `data.source`: `'facts'` o `'report'`.
- Con facturas guardadas el resumen trae lo que el reporte no daba:
  - **% de venta con cliente por vendedora** (`sellers[].identified_pct`, `identified_documents_pct`) y **descuentos dados** por cada una (`sellers[].discount`).
  - **Descuento por cliente** (`discount`, `discount_pct`), ranking "Por descuento", total del periodo y del equipo (`discounts_available: true`).
  - **Cédula** de cada cliente; el equipo se reconoce por cédula además de por nombre.
  - Nuevo `data.discount_invoices`: las 50 facturas con más descuento (fecha, número, cliente, vendedora, subtotal, descuento, %, total, si es del equipo).
- Factura sin cliente = Consumidor final. Clientes nuevos/recurrentes e inactivas siguen con el reporte (miran compras de 2025, fuera de la copia).
- `CustomerInsightsService` recibe `invoices_client` (AlegraClient) para las ventas de hoy; nuevas funciones puras `aggregate_facts` y `discount_invoices`.
- Tests: +3 (agrupación, resumen con facturas guardadas + hoy en vivo con % por vendedora/descuentos/cédula/equipo, y respaldo al reporte si falta un día). **92/92** (con el parche WMI local; repetir en el PC personal).

## [2026-10-02] (continuación) - Fase 4.2: corrección tras la prueba en producción

**Prueba controlada (Carreño):** 1-ene = 0 facturas (Año Nuevo, sin ventas). Con la primera tanda: 24 días / 173 facturas; **con vendedora 98,8 %, con cédula 100 %, 10 facturas con descuento por $253.795** (igual al peso al descuento de enero que mostró el conector de Alegra). Confirmado: /api/v1/invoices trae vendedora, cédula y descuento → la fase 4.3 es viable.

**Error visto:** el usuario dio "Cargar siguiente tanda", salió del módulo (la carga siguió en el servidor) y volvió a darle: dos cargas simultáneas procesaron el mismo día (24-ene) y la segunda chocó con la unicidad (tienda, alegra_id) (`psycopg.errors.UniqueViolation`). No se perdió ni duplicó nada (el día fallido se deshizo completo), pero el panel mostró el error técnico de SQL.

**Correcciones:**
- **Una carga a la vez por tienda**: `store_sync_lock` (pg_try_advisory_lock con conexión propia, compartido entre los 2 workers y el cron). Si ya hay una, `POST /sync` responde **409 `sync_in_progress`** con el estado actual, sin tocar nada. En SQLite (tests) no bloquea.
- Errores internos (base de datos, etc.) ya no exponen el detalle técnico: mensaje "No se pudieron guardar las facturas de ese día" (el detalle va al log). Los de Alegra conservan su mensaje (conexión, timeout, credenciales).
- `sync_day` guarda una sola vez una factura que Alegra repita en la misma respuesta.
- Tests: +3 (409 sin tocar nada, factura repetida, mensaje sin detalle técnico). **89/89** (con el parche WMI local; repetir en el PC personal). El candado real se verifica en producción (no hay Postgres local en este PC).

## [2026-10-02] (continuación) - Fase 4.2: carga del resumen de facturas (endpoints + cron)

- **`app/routes/invoice_facts.py`** (tienda activa por `X-Store`):
  - `GET /api/analytics/invoice-facts/status` (admin): días cargados desde el 1-ene-2026 hasta ayer, faltantes, siguiente día, facturas, y **calidad de los datos** (cuántas facturas activas traen vendedora, cédula y descuento; anuladas aparte). Sirve para verificar el formato real de Alegra antes de usar los datos en el dashboard.
  - `POST /api/analytics/invoice-facts/sync` (admin **o** cron con `X-Sync-Token`): `recent_days` (0-7) vuelve a cargar los últimos días hasta hoy; `max_days` (0-31) carga la siguiente tanda de días faltantes, del más antiguo al más nuevo. Se detiene solo a los 150 s (gunicorn corta a 240 s) y devuelve hasta dónde llegó; si Alegra falla, responde 502 con lo cargado intacto. Tienda sin Alegra → 503 `alegra_not_configured`.
- **`.github/workflows/daily-accounts-sync.yml`**: paso nuevo al final, por tienda: `{"recent_days": 3, "max_days": 31}`. Con `if: always()` + `continue-on-error: true`: corre aunque falle Cuentas y, si falla él, NO dispara la alerta de Cuentas (se recupera sola la noche siguiente). Con 31 días por noche, la carga desde enero se completa sola en ~9 noches; desde Clientes se puede adelantar.
- `sync_range` acepta `deadline`; `coverage_status` calcula el estado.
- Tests: +7 (tanda y continuación, cron con token y `X-Store` de otra tienda, permisos, validación, tienda sin Alegra, error de Alegra a mitad, límite de tiempo). **86/86.**
- **Nota de entorno local (no del proyecto):** en esta máquina el servicio WMI de Windows dejó de responder y Python 3.14 (`platform._wmi_query`, llamado por SQLAlchemy y pytest-flask al importarse) se quedaba esperando para siempre: hasta `pytest --version` se colgaba. Las pruebas se corrieron con un parche local que omite WMI (no va al repo). Ver TROUBLESHOOTING.md.

## [2026-10-02] (continuación) - Fase 4.1: resumen de facturas por tienda (sin cambios visibles)

Base para el % con cliente por vendedora, los descuentos y la cédula, que el reporte agregado de /api/v1 no entrega. Decisión del usuario: cargar desde el **1 de enero de 2026**.

- **Tablas nuevas** (`app/models/invoice_fact.py`), por tienda (`store_code`). `db.create_all()` las crea al arrancar; no se toca ninguna tabla existente:
  - `invoice_facts`: una fila por factura: id de Alegra, fecha, número, cliente (id, nombre, cédula), vendedora (id, nombre), subtotal, descuento, total, anulada. Única por (tienda, id de Alegra).
  - `invoice_sync_days`: qué días de cada tienda ya están cargados y cuántas facturas tenían.
- **`app/services/invoice_facts.py`**: `sync_day` reemplaza un día completo (borrar e insertar en una transacción) usando `AlegraClient.get_invoices_by_date`, el mismo método y la misma caché que ya usa el cierre de caja. Las facturas se piden **antes** de tocar la base: si Alegra falla, lo que había queda intacto. `sync_range` carga varios días y se detiene en el primer error (se puede continuar después); `missing_days` dice qué días faltan.
  - Descuento: el de la factura (`discount`); si no viene, se calcula por ítem (% sobre precio × cantidad). Anuladas: `is_invoice_void`.
  - Una factura a la que le cambian la fecha en Alegra se mueve de día, sin duplicarse.
- Aún **no hay endpoint ni carga**: eso es la fase 4.2 (carga inicial en tandas + cron de las 9 pm).
- Tests: +7 en `tests/test_invoice_facts.py` (formato de /api/v1/invoices, recarga, fallo de Alegra, cambio de fecha, tiendas separadas, rango con error y continuación).

## [2026-10-02] Dashboard de clientes: fase 3 cerrada (revisión en producción)

Revisado con el usuario en producción (Carreño, "Este año", 1-ene a 2-oct-2026):
- Venta $380.986.649; 55,3 % con cliente identificado; 3.091 facturas (1.605 con cliente = 51,9 %); 1.109 clientes; compra promedio $190.091. Las cifras cuadran entre sí y con Alegra.
- Ventas por vendedora: Mónica 52,8 %, Rita 45,5 %, Astrid 1,5 % de la venta; $806.700 sin vendedora.
- Equipo (reconocido por nombre): Mónica, Rita y Astrid como clientas, $2.173.465 en total.
- Nuevos 853 ($146,5 M) vs recurrentes 256 ($64,3 M): suman exactamente la venta con cliente. Solo ~1 de cada 4 clientes del año ya había comprado antes.
- Inactivas (90 días): 823 clientas, $135,2 M; fechas de última compra coherentes. Casi la mitad no tiene celular en Alegra; números incompletos (ej. 9 dígitos) salen como "Sin celular" a propósito.
- Primavera: muestra "Alegra rechazó las credenciales de esta tienda" sin romper la página. Significa que en Render YA existen `ALEGRA_USER_PRIMAVERA` / `ALEGRA_PASS_PRIMAVERA` con valores que Alegra no acepta; cuando se cree la cuenta de Primavera basta con poner ahí su correo y token (sin cambiar código).
- Errores encontrados en esta fase y corregidos: montos en $0 (v1 usa `total`) y datos que /api/v1 no entrega (cédula, descuento, filtro por vendedora). Ver entradas anteriores.

Siguiente: fase 4 (detalle de facturas por tienda), ver MEJORAS_PENDIENTES.md del backend.

## [2026-10-02] (continuación) - Clientes: límites reales de /api/v1

Prueba con las credenciales reales (script de solo lectura, ya borrado):
- `/api/v1/reports/sales-by-client` trae **solo** `idLocal`, `name`, `totalDocuments`, `subTotal`, `total`. **No trae cédula ni descuento** (`subTotal` = `total`).
- `sales-by-seller` trae `idLocal`, `name`, `total`, `subTotal`, `totalPayed`, `totalDocuments`.
- **No filtra por vendedora**: `sellerId`, `seller_id`, `idSeller`, `seller`, `sellers`, `id_seller` y `sellerIds` devuelven los 1.110 clientes de toda la tienda.

Cambios:
- Se dejaron de pedir las 3 consultas por vendedora (no servían y alargaban la carga). Las vendedoras salen con `identified_available: false`.
- Nuevo `discounts_available` en el resumen: `false` cuando Alegra no manda el campo de descuento (así el frontend no muestra $0 como si fuera real).
- Las vendedoras-clientas se siguen reconociendo por nombre (Mónica y Rita, verificado en producción); por cédula no se puede porque v1 no la trae.
- Tests ajustados + uno con la respuesta real de v1. **72/72.**
- Propuesta para lo que falta (% por vendedora, descuentos, cédula): `MEJORAS_PENDIENTES.md` → "Dashboard de clientes: detalle de facturas".

## [2026-10-02] Fix: dashboard de clientes mostraba todos los montos en $0

- **Visto en producción** (fase 3): las compras salían bien pero todos los montos en $0, y la página decía "Todavía no hay ventas".
- **Causa:** `/api/v1/reports/sales-by-client` (lo que usa la plataforma, con Basic) trae el monto en `total`; reports-api v2 (la web de Alegra y el conector MCP, con los que se diseñó) lo llama `afterTaxes`. El código solo leía `afterTaxes`. Las pruebas no lo detectaron porque los datos simulados copiaban el formato de v2.
- **Solución:** `customer_insights.py` lee el monto de `afterTaxes` o `total`, el subtotal de `subTotal`/`subtotal` y el descuento de `discount`/`totalDiscount` (también en la validación del filtro por vendedora). Registra una vez en el log los nombres de campo que manda Alegra (`Campos de sales-by-client en Alegra: [...]`) para confirmar el formato.
- Test nuevo con filas en el formato de v1. **71/71.**
- Lección: los datos simulados de los tests deben copiar la respuesta del servidor que usa la plataforma (v1), no la del conector.

## [2026-10-01] (continuación) - Seguridad: credenciales fuera del repositorio

El repo es **público**. Se quitaron todas las credenciales escritas en archivos versionados (a pedido del usuario, sin cambiar las contraseñas):
- `scripts/init_admin.py` y `scripts/init_supabase.py`: ya no traen contraseñas. Se leen de `INIT_ADMIN_PASSWORD` / `INIT_SALES_PASSWORD` o se piden por consola sin mostrarse (mínimo 8 caracteres). Lo demás funciona igual (ojo: `init_supabase.py` sigue reemplazando la contraseña de los usuarios que ya existen).
- `app/routes/auth.py` (ejemplo de Swagger) y `README.md`: ejemplo genérico `usuario@ejemplo.com` / `TuContraseña123*`.
- `docs/archive/FRONTEND_ANALISIS_TALLAS.md` y `FRONTEND_API_DOCUMENTATION_1.md`: credenciales reemplazadas por ejemplos y un token JWT real abreviado.
- Verificado: ninguna contraseña ni token en los archivos de los dos repos (backend y frontend). 70/70 tests; `/apispec.json` carga con el ejemplo nuevo.
- **Limitación:** las contraseñas siguen en el **historial de git** (commits anteriores) de un repo público. Borrarlas de ahí exige reescribir el historial y forzar el push, con riesgo para los despliegues; el usuario decidió no cambiarlas. La única forma de anularlas del todo sería cambiarlas desde Usuarios.
- **Regla:** nunca escribir contraseñas, tokens ni cadenas de conexión en el código ni en la documentación. Usar variables de entorno (ver `.env.example`) o pedirlas por consola.

## [2026-10-01] (continuación) - Fase 2 del dashboard de clientes: revisión y limpieza

**Correcciones encontradas al revisar el código nuevo:**
- Clientas inactivas: si Alegra fallaba al traer el teléfono o la última compra de una clienta (ej. por demasiadas consultas seguidas), quedaba guardada "sin celular" 12 h. Ahora solo se guarda en caché cuando las dos consultas salen bien; si no, se reintenta en la siguiente carga.
- `AlegraDirectClient`: tope de 50 páginas en los reportes y en `get_sellers`, y corte si Alegra repite la misma página. Antes, si Alegra ignorara `start`, el ciclo podía quedar pidiendo páginas sin fin.

**Limpieza de pruebas:**
- `tests/test_analytics_endpoints.py`, `test_endpoints_simple.py` y `test_size_analysis.py` → `scripts/manual/check_*.py`. Eran scripts manuales contra un servidor real, no tests. `test_size_analysis.py` reemplazaba `sys.stdout` al importarse: **era la causa del "I/O operation on closed file"** que rompía la corrida completa de pytest (ver TROUBLESHOOTING.md).
- Se quitaron del código de esos scripts el correo y la contraseña reales que tenían escritos; ahora se piden por variables de entorno o por consola (`scripts/manual/_credentials.py`).
- `pytest -q` (suite completa, sin elegir archivos) vuelve a funcionar: **70/70 pasan** (+2 tests de las correcciones).

**Notas de producción (no cambian código):** el Procfile da 240 s por petición (el frontend espera 120 s). La caché es en memoria **por worker** (hay 2) y se pierde cuando Render reinicia o duerme la instancia: la primera carga después de eso vuelve a consultar Alegra.

## [2026-10-01] (continuación) - Dashboard de clientes con reportes agregados de Alegra

- **Verificado con las credenciales reales**: `/api/v1/reports/sales-by-client`, `sales-by-seller` y `sales-by-item` aceptan Basic (correo:token); `reports-api.alegra.com/api/v2` NO (401). `limit=2000` trae todos los clientes del año en una llamada; Alegra solo ordena bien con `order_field=total`, así que el backend ordena por su cuenta.
- `AlegraDirectClient`: `get_sales_by_client` (filtro opcional por vendedora), `get_sales_by_seller`, `get_sellers`, `get_contact`, `get_last_invoice_date`. Paginación defensiva hasta `metadata.total`; propagan los errores de red.
- Nuevo `app/services/customer_insights.py` + `app/routes/customer_insights.py`:
  - `GET /api/analytics/customers/summary`: % de venta con cliente identificado (total y por vendedora), top clientes por monto/frecuencia/descuento, compras del equipo (marcadas en el ranking y resumidas aparte), clientes nuevos vs recurrentes.
  - `GET /api/analytics/customers/inactive?days=`: clientas que dejaron de venir; las 50 que más compraron traen teléfono, WhatsApp y última compra.
  - Solo admin, por tienda (`X-Store`); caché en memoria con la tienda en la clave. Tienda sin Alegra configurado → 503 `alegra_not_configured` (Primavera hasta que tenga sus credenciales; con cuenta nueva sale vacío, misma lógica).
- No cambia ningún endpoint existente (`/api/analytics/top-customers` y demás siguen igual).
- Docs: sección 8 en `ANALYTICS_API_DOCUMENTATION.md`.
- Tests: +12 en `tests/test_customer_insights.py`. **68/68 pasan** (los mismos 4 archivos de antes + el nuevo; `test_analytics_endpoints.py` y `test_endpoints_simple.py` ya fallaban antes porque esperan un servidor real).

## [2026-10-01] (continuación) - Multi-tienda, Fase 5: comparativo entre tiendas

- `GET /api/stores/comparison?start_date&end_date` (solo admin; por defecto el mes en curso; máx. 92 días; fechas futuras se recortan a hoy). Por cada tienda devuelve:
  - `sales`: total, facturas, ticket promedio, anuladas, medios de pago y serie diaria. Usa **exactamente** el mismo cálculo que Ventas Mensuales: `AlegraClient.get_monthly_sales_summary` se partió en "traer facturas" + `build_sales_summary(facturas, ...)` sin cambiar su respuesta. Las consultas a Alegra de cada tienda corren **en paralelo** (hilos solo con el cliente HTTP, sin base de datos). Si una tienda no tiene Alegra configurado o Alegra falla, esa tienda viene con `available: false` + motivo y el resto sale igual.
  - `operations` (base de datos, no depende de Alegra): cierres registrados vs días del periodo, cierres con diferencia y diferencia acumulada vs Alegra, enviado/comprado en recompras y saldo disponible hoy en cuentas (sin Ahorro, igual que Cuentas → Resumen).
- Tests: +3 (ventas/operación por tienda con Alegra simulado, ambas tiendas configuradas, permisos y validación de rango). **56/56 pasan.**

---

## [2026-10-01] (continuación) - Multi-tienda, Fase 4: cron de las 9pm por tienda

- `.github/workflows/daily-accounts-sync.yml`: matriz `store: [carreno, primavera]` con `fail-fast: false`. Cada tienda corre su propio `POST /api/accounts/sync-daily` con `X-Store`; si una falla, la otra igual se sincroniza y `sync-failure` registra la alerta **solo** en la tienda que falló (clave de `app_settings` por tienda). Para sumar una tienda nueva basta con agregar su código a la matriz.
- Test nuevo que simula el cron (token de sync, sin usuario, con `X-Store`): sincroniza solo la tienda pedida, la alerta de fallo es independiente por tienda y un token inválido sigue dando 401. **53/53 pasan.**
- Pendiente para activar Primavera del todo: `ALEGRA_USER_PRIMAVERA` / `ALEGRA_PASS_PRIMAVERA` en Render (no requiere código).

---

## [2026-10-01] (continuación) - Multi-tienda, Fase 2: usuarios con tienda asignada

- `users.store_code` (nuevo, default `carreno`; la migración multi-tienda lo agrega y deja a todos los usuarios existentes en Carreño).
- Reglas (`app/stores.py: stores_for_user`): el **admin** opera todas las tiendas; cualquier otro rol (`sales`, `partner`) **solo su tienda asignada**.
- La tienda viaja en el JWT (`storeCode`), igual que el rol: un cambio de tienda de un usuario aplica cuando vuelve a iniciar sesión. Tokens anteriores sin `storeCode` = Carreño.
- **Sin header `X-Store`, la tienda activa es la del propio usuario** (antes: siempre Carreño). Así una vendedora de Primavera con un frontend viejo en caché ve Primavera, no un 403.
- `/auth/login` y `/auth/verify` devuelven `store_code` y `stores` (tiendas que puede operar). `/auth/verify` y `/api/stores` no validan `X-Store`, para que un header viejo no cierre la sesión.
- `/api/users` (listar/obtener/crear/editar): campo `store_code` (validado, 400 si no existe; opcional al crear → Carreño). Las respuestas usan `User.to_dict()`.
- Tests: +5 en `tests/test_multi_store.py` (vendedora de Primavera, token viejo, verify con header ajeno, CRUD con tienda, login). **52/52 pasan.** Migración re-probada en Postgres 16 con 2 workers en paralelo.

---

## [2026-10-01] - Multi-tienda, Fase 1: backend listo para KOAJ Primavera

Se abre una segunda tienda, **KOAJ Primavera**, con la misma lógica que Carreño pero con datos **100% independientes** (cierres, cuentas, recompras, empleadas, notas/tareas y ventas/inventario de su propia cuenta de Alegra). Comparten plataforma, usuarios y Códigos KOAJ. Esta fase deja el backend multi-tienda **sin cambiar nada visible**: sin header `X-Store` todo funciona exactamente como Carreño.

### 🏬 `app/stores.py` (nuevo)
- Registro de tiendas (`carreno`, `primavera`), tienda activa por request (header `X-Store`, sin header = `carreno`), credenciales de Alegra por tienda (`ALEGRA_USER_<TIENDA>`/`ALEGRA_PASS_<TIENDA>`; Carreño cae a `ALEGRA_USER`/`ALEGRA_PASS` de siempre), base de caja por tienda (`BASE_OBJETIVO_<TIENDA>`, default 450.000), claves de `app_settings` por tienda y fábricas `get_alegra_client()` / `get_alegra_direct_client()`.
- Permisos (`stores_for_user`): por ahora el admin opera todas las tiendas y el resto solo Carreño. Se valida en `token_required`; una vendedora que pida otra tienda recibe 403, una tienda inexistente 400.

### 🗄️ Modelos
- Nuevo `StoreScopedMixin` (`app/models/store_scoped.py`): columna `store_code` (se llena sola con la tienda del request) + `for_current_store()` / `get_for_current_store_or_404()`. Aplicado a cierres, cuentas, recompras (envíos y compras), las 5 tablas de empleadas y notas/tareas. `account_movements` no la lleva: pertenece a la tienda de su cuenta.
- `cash_closings.closing_date` y `accounts.name`/`payment_key` pasan de únicos globales a **únicos por tienda**.
- La columna nueva se llama `store_code` (no `store`) porque `repurchase_purchases.store` ya existe y es el proveedor donde compró el socio.

### 🔧 Migración (`_migrate_multi_store` en `app/__init__.py`)
- Idempotente, no destructiva, en UNA transacción: agrega `store_code` (todo lo existente queda como `carreno`), quita las unicidades globales por introspección (no asume nombres) y crea los índices únicos por tienda. En SQLite (solo desarrollo local) reconstruye `accounts` porque SQLite no permite `DROP CONSTRAINT`.
- Advisory lock de Postgres para que los 2 workers de gunicorn no la corran a la vez.
- Si falla en producción, **aborta el arranque** (Render sigue sirviendo el deploy anterior) en vez de arrancar con el código esperando una columna que no existe.
- `seed_default_accounts()` siembra las 8 cuentas por defecto en cada tienda (Primavera arranca con todas en $0).

### 🔌 Rutas
- Alegra: `analytics`, `products`, `inventory`, `direct_api` y `cash_closing` ya no crean el cliente una vez al arrancar con credenciales fijas; lo piden por request para la tienda activa. Una tienda sin Alegra configurado responde con un mensaje claro y no afecta a la otra.
- Cuentas: listado, movimientos, ajustes, transferencias, "contempla saldo hasta", sincronización diaria, estado y alerta de fallo del cron, todo por tienda. No se puede tocar una cuenta de otra tienda aunque se conozca su id (404).
- Recompras: los envíos descuentan solo las cuentas de su propia tienda.
- Aviso de cierres pendientes: el ancla de "desde cuándo vigilar" es por tienda.
- `GET /api/stores` (nuevo): tiendas que puede operar el usuario, para el selector del frontend (Fase 3).
- CORS: se permite el header `X-Store`.

### 🐛 Bugs preexistentes corregidos de paso
- **Un día sin facturas en Alegra tumbaba el cierre de caja** (`KeyError 'total_voided_amount_formatted'` en `filter_voided_invoices` con lista vacía). Le habría pasado a Primavera el día de apertura.
- **La caché de facturas guardaba el día en curso** cuando el caller pasaba un `date` en vez de string (analytics/products): la comparación con "hoy" nunca coincidía. Además la llave de caché ahora incluye el usuario de Alegra, así nunca se sirven facturas de una tienda a otra.
- El error de configuración en `/api/sum_payments` mostraba "Error inesperado: " vacío (se usaba `str(e)` en vez de `e.message`).
- `Config.validate()` ahora acepta tanto `ALEGRA_USER` como `ALEGRA_USER_CARRENO` para la tienda por defecto.

### ✅ Verificación
- `tests/test_multi_store.py` (nuevo, 14 tests, SQLite temporal y Alegra simulado): aislamiento de cuentas, movimientos, cierres del mismo día en ambas tiendas, sincronización independiente, recompras, compras del socio, empleadas, notas, permisos (403/400), tienda sin Alegra, base por tienda y caché. Junto con los existentes: **47/47 pasan**.
- Migración probada en **Postgres 16 real** (binarios locales): esquema creado con el código de `main` + datos, luego el código nuevo arrancado como **2 procesos en paralelo** → uno migró, el otro esperó el lock y no hizo nada; saldos e ids intactos. Falla simulada a mitad de la migración → arranque abortado y **rollback total** (ninguna tabla quedó con `store_code`).
- Migración probada también sobre la SQLite local existente (reconstrucción de `accounts` sin pérdida de datos) y re-ejecutada para confirmar idempotencia.

**Deploy:** Manual Deploy en Render. No requiere variables nuevas para que Carreño siga igual. Para activar Primavera: `ALEGRA_USER_PRIMAVERA` y `ALEGRA_PASS_PRIMAVERA` (Fase 4).

---

## [2026-09-14] - Fecha "Contempla saldo hasta" editable en cuentas (ej. ADDI + DATÁFONO)

El usuario explicó que ADDI (pasarela de tarjetas) paga días después de la transacción, así que el saldo mostrado en "ADDI + DATÁFONO (Tarjetas)" (Gestión → Cuentas → Resumen) solo es válido hasta cierta fecha que él conoce manualmente. Pidió poder anotar/editar esa fecha directamente en la tarjeta, para corroborar si ya le tocaba revisar que Addi hubiera consignado.

### 🗄️ `app/models/account.py`
- Nueva columna `Account.contemplated_until` (Date, nullable) — nota manual, sin impacto en `balance` ni en ningún cálculo. Expuesta en `to_dict()` como ISO `'YYYY-MM-DD'` o `null`.

### 🔧 `app/__init__.py`
- Migración segura `add_column_if_missing(conn, 'accounts', 'contemplated_until', 'DATE')` agregada a `_migrate_employee_tables()` (mismo patrón ALTER TABLE usado en migraciones anteriores).

### 🏦 `app/routes/accounts.py`
- Nuevo endpoint `PATCH /api/accounts/<id>/contemplated-until` (admin only). Acepta `{"contemplated_until": "YYYY-MM-DD"}` para fijar la fecha, o cadena vacía/`null` para limpiarla. Devuelve 400 si el formato es inválido y 404 si la cuenta no existe.
- Implementado de forma genérica a nivel de modelo/endpoint (cualquier cuenta podría usarlo); la UI por ahora solo lo expone en la tarjeta de ADDI + DATÁFONO, que es donde se pidió.

### ✅ Verificación
- Prueba funcional aislada con SQLite temporal + `app.test_client()`: login admin, `GET /api/accounts` (estado inicial `null`), `PATCH` fijando una fecha (persiste y no altera `balance`), fecha inválida → 400, cuenta inexistente → 404, `PATCH` con cadena vacía limpia el campo.
- Probado también end-to-end con Playwright contra un backend local (nunca producción): se fijó la fecha en la tarjeta desde la UI real, se confirmó visualmente en captura de pantalla, y se recargó la página confirmando que el valor persiste desde el backend (no es solo estado local del navegador).

**Deploy:** requiere Manual Deploy en Render — es solo una columna nueva (sin DEFAULT, filas existentes quedan en `NULL`) y un endpoint nuevo, sin cambios de comportamiento en lo existente.

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
