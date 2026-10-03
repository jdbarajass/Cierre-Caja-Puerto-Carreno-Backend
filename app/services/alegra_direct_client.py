"""
Cliente para APIs directas de Alegra (no documentadas)
Estas APIs se descubrieron mediante inspección de red en la plataforma
"""
import time
import requests
from typing import Dict, List, Any, Optional
import logging
from datetime import datetime

logger = logging.getLogger(__name__)

# Facturas día por día (Totales de Ventas / Documentos): intentos por página
# antes de dar el día por fallido, con espera creciente (1 s, 2 s, ...).
INVOICE_PAGE_ATTEMPTS = 3
INVOICE_RETRY_BASE_SECONDS = 1.0


class AlegraDirectClient:
    """
    Cliente para consumir las APIs directas de Alegra
    que proporcionan información más detallada y rápida
    """

    def __init__(self, username: str, token: str, base_url: str = "https://app.alegra.com/api/v1", timeout: int = 30):
        """
        Inicializa el cliente de APIs directas de Alegra

        Args:
            username: Email del usuario de Alegra
            token: Token de API de Alegra
            base_url: URL base de la API
            timeout: Timeout para las peticiones en segundos
        """
        self.username = username
        self.token = token
        self.base_url = base_url.rstrip('/')
        self.timeout = timeout
        self.auth = (username, token)

        logger.info(f"Cliente Alegra Direct API inicializado para usuario: {username}")

    def _make_request(self, endpoint: str, params: Optional[Dict] = None) -> Dict[str, Any]:
        """
        Realiza una petición HTTP a la API de Alegra

        Args:
            endpoint: Endpoint relativo (ej: '/reports/inventory-value')
            params: Parámetros de query

        Returns:
            Respuesta JSON decodificada

        Raises:
            requests.exceptions.RequestException: Si hay error en la petición
        """
        url = f"{self.base_url}{endpoint}"
        
        try:
            logger.debug(f"Petición a API directa: {url} con params: {params}")
            
            response = requests.get(
                url,
                auth=self.auth,
                params=params or {},
                timeout=self.timeout,
                headers={'Content-Type': 'application/json'}
            )
            
            response.raise_for_status()
            data = response.json()
            
            logger.debug(f"Respuesta exitosa de API directa: {endpoint}")
            return data
            
        except requests.exceptions.Timeout:
            logger.error(f"Timeout en petición a {url}")
            raise
        except requests.exceptions.HTTPError as e:
            logger.error(f"Error HTTP {e.response.status_code} en {url}: {e.response.text}")
            raise
        except requests.exceptions.RequestException as e:
            logger.error(f"Error en petición a {url}: {str(e)}")
            raise
        except ValueError as e:
            logger.error(f"Error decodificando JSON de {url}: {str(e)}")
            raise

    def get_inventory_value_report_paginated(
        self,
        to_date: str,
        max_items: int = 3000,
        page_size: int = 200,
        query: str = ""
    ) -> Dict[str, Any]:
        """
        Obtiene el reporte de inventario completo usando paginación automática

        Args:
            to_date: Fecha hasta la cual generar el reporte (YYYY-MM-DD)
            max_items: Máximo número total de items a obtener (default: 3000)
            page_size: Items por página (default: 200, para evitar error 503)
            query: Filtro de búsqueda opcional

        Returns:
            Dict con todos los items combinados y filtrados
        """
        all_items = []
        total_received = 0
        total_filtered_asterisk = 0
        total_filtered_disabled = 0
        current_page = 1
        failed_error = None  # si una página falla, el inventario queda incompleto

        logger.info(f"Iniciando consulta paginada de inventario (max: {max_items}, page_size: {page_size})")

        while total_received < max_items:
            try:
                # Calcular cuántos items faltan
                remaining = max_items - total_received
                current_limit = min(page_size, remaining)

                logger.info(f"Obteniendo página {current_page} ({current_limit} items)...")

                # Llamar al método original con paginación
                page_result = self.get_inventory_value_report(
                    to_date=to_date,
                    limit=current_limit,
                    page=current_page,
                    query=query
                )

                if not page_result.get('success'):
                    logger.error(f"Error en página {current_page}: {page_result.get('error')}")
                    failed_error = page_result.get('error') or 'Error desconocido'
                    break

                page_data = page_result.get('data', [])
                page_metadata = page_result.get('metadata', {})

                # Acumular estadísticas
                total_received += page_metadata.get('total_received', 0)
                total_filtered_asterisk += page_metadata.get('total_filtered_asterisk', 0)
                total_filtered_disabled += page_metadata.get('total_filtered_disabled', 0)
                all_items.extend(page_data)

                logger.info(
                    f"Página {current_page}: recibidos={page_metadata.get('total_received', 0)}, "
                    f"válidos={len(page_data)}, total acumulado={len(all_items)}"
                )

                # Si recibimos menos items de los solicitados, ya no hay más páginas
                if page_metadata.get('total_received', 0) < current_limit:
                    logger.info("Última página alcanzada")
                    break

                current_page += 1

            except Exception as e:
                logger.error(f"Error obteniendo página {current_page}: {str(e)}")
                failed_error = str(e)
                break

        logger.info(
            f"Paginación completa: {total_received} items recibidos, "
            f"{total_filtered_asterisk} filtrados (asteriscos), "
            f"{total_filtered_disabled} filtrados (deshabilitados), "
            f"{len(all_items)} válidos retornados"
        )

        if failed_error and not all_items:
            return {'success': False, 'error': failed_error, 'data': []}

        return {
            'success': True,
            'data': all_items,
            'metadata': {
                'page': 1,  # Resultado combinado
                'limit': max_items,
                'query': query,
                'to_date': to_date,
                'total_received': total_received,
                'total_filtered_asterisk': total_filtered_asterisk,
                'total_filtered_disabled': total_filtered_disabled,
                'total_filtered': total_filtered_asterisk + total_filtered_disabled,
                'total_returned': len(all_items),
                'pages_fetched': current_page,
                # Antes se cortaba en silencio: ahora el frontend avisa que faltan productos.
                'incomplete': failed_error is not None,
                'failed_page': current_page if failed_error else None,
                'error': failed_error,
            }
        }

    def get_inventory_value_report(
        self,
        to_date: str,
        limit: int = 200,
        page: int = 1,
        query: str = ""
    ) -> Dict[str, Any]:
        """
        Obtiene el reporte de valor de inventario filtrando items obsoletos y deshabilitados

        IMPORTANTE: Filtra automáticamente:
        - Items con nombres que empiezan con asteriscos (*): productos obsoletos
        - Items deshabilitados (status != 'active'): productos inactivos

        Args:
            to_date: Fecha hasta la cual generar el reporte (YYYY-MM-DD)
            limit: Número de items por página (default: 3000 para traer todo el inventario)
            page: Número de página (1-indexed)
            query: Filtro de búsqueda opcional

        Returns:
            Dict con estructura:
            {
                'success': True,
                'data': [...],  # Lista de items de inventario (sin items obsoletos ni deshabilitados)
                'metadata': {
                    'page': int,
                    'limit': int,
                    'query': str,
                    'to_date': str,
                    'total_received': int,          # Items recibidos de Alegra
                    'total_filtered_asterisk': int, # Items filtrados por asteriscos
                    'total_filtered_disabled': int, # Items filtrados por estar deshabilitados
                    'total_filtered': int,          # Total items filtrados
                    'total_returned': int           # Items enviados al frontend
                }
            }
        """
        params = {
            'toDate': to_date,
            'page': page,
            'limit': limit,
            'start': (page - 1) * limit,
            'query': query
        }

        try:
            response = self._make_request('/reports/inventory-value', params)

            # Extraer datos de la respuesta
            raw_data = response if isinstance(response, list) else response.get('data', [])

            # FILTRAR items con asteriscos y deshabilitados
            filtered_data = []
            items_filtered_asterisk = 0
            items_filtered_disabled = 0

            for item in raw_data:
                item_name = item.get('name', '') if isinstance(item, dict) else ''
                item_status = item.get('status', 'active') if isinstance(item, dict) else 'active'

                # Filtrar si el nombre comienza con asteriscos o es solo asteriscos
                if item_name and item_name.strip().startswith('*'):
                    items_filtered_asterisk += 1
                    logger.debug(f"Item filtrado (asteriscos): {item_name}")
                    continue

                # Filtrar si el item está deshabilitado
                if item_status != 'active':
                    items_filtered_disabled += 1
                    logger.debug(f"Item filtrado (deshabilitado): {item_name} (status: {item_status})")
                    continue

                # Si el item pasa ambos filtros, agregarlo
                filtered_data.append(item)

            total_filtered = items_filtered_asterisk + items_filtered_disabled

            logger.info(
                f"Inventario procesado: {len(raw_data)} items recibidos, "
                f"{items_filtered_asterisk} filtrados (asteriscos), "
                f"{items_filtered_disabled} filtrados (deshabilitados), "
                f"{len(filtered_data)} enviados al frontend"
            )

            # Agregar metadata de paginación
            return {
                'success': True,
                'data': filtered_data,
                'metadata': {
                    'page': page,
                    'limit': limit,
                    'query': query,
                    'to_date': to_date,
                    'total_received': len(raw_data),
                    'total_filtered_asterisk': items_filtered_asterisk,
                    'total_filtered_disabled': items_filtered_disabled,
                    'total_filtered': total_filtered,
                    'total_returned': len(filtered_data)
                }
            }
        except Exception as e:
            logger.error(f"Error obteniendo inventory value report: {str(e)}")
            return {
                'success': False,
                'error': str(e),
                'data': []
            }

    def get_sales_totals(
        self,
        from_date: str,
        to_date: str,
        group_by: str = 'day',
        limit: int = 10,
        start: int = 0
    ) -> Dict[str, Any]:
        """
        Obtiene totales de ventas agrupados por día o mes

        Args:
            from_date: Fecha de inicio (YYYY-MM-DD)
            to_date: Fecha de fin (YYYY-MM-DD)
            group_by: Agrupación ('day' o 'month')
            limit: Número de registros a retornar
            start: Offset para paginación

        Returns:
            Dict con estructura:
            {
                'success': True,
                'data': [
                    {
                        'date': '2025-12-01',
                        'total': 1500000,
                        'count': 45,
                        ...
                    }
                ],
                'metadata': {...}
            }
        """
        params = {
            'from': from_date,
            'to': to_date,
            'groupBy': group_by,
            'limit': limit,
            'start': start
        }

        try:
            response = self._make_request('/invoices/sales-totals', params)
            
            return {
                'success': True,
                'data': response if isinstance(response, list) else response.get('data', []),
                'metadata': {
                    'from_date': from_date,
                    'to_date': to_date,
                    'group_by': group_by,
                    'limit': limit,
                    'start': start
                }
            }
        except Exception as e:
            logger.error(f"Error obteniendo sales totals: {str(e)}")
            return {
                'success': False,
                'error': str(e),
                'data': []
            }

    # Página de /invoices/sales-totals por día. No se sabe si /api/v1 corta en
    # 30 filas (verificación pendiente en producción, docs/PLAN_ESTADISTICAS.md):
    # se pagina hasta tener todos los días del rango, sin depender del tope.
    SALES_TOTALS_PAGE_SIZE = 30
    SALES_TOTALS_MAX_PAGES = 30  # ~2,5 años de días

    def get_all_sales_totals_by_day(self, from_date: str, to_date: str) -> Dict[str, Any]:
        """
        Totales por día de TODO el rango. Antes se pedía una sola página con
        limit=100: un rango de más de 100 días (o de 31 si Alegra cortara en
        30) salía incompleto sin aviso. Cada fecha se cuenta una sola vez
        (si Alegra ignorara `start` y repitiera la página, no se duplica).
        """
        expected_days = (datetime.strptime(to_date, '%Y-%m-%d') - datetime.strptime(from_date, '%Y-%m-%d')).days + 1
        by_date: Dict[str, Dict[str, Any]] = {}
        start = 0
        for _ in range(self.SALES_TOTALS_MAX_PAGES):
            page = self.get_sales_totals(from_date, to_date, group_by='day',
                                         limit=self.SALES_TOTALS_PAGE_SIZE, start=start)
            if not page.get('success'):
                return page
            rows = page.get('data') or []
            new_rows = [r for r in rows if str(r.get('date')) not in by_date]
            for r in new_rows:
                by_date[str(r.get('date'))] = r
            # Fin: página vacía, repetida o ya están todos los días del rango
            if not new_rows or len(by_date) >= expected_days:
                break
            start += len(rows)
        return {
            'success': True,
            'data': list(by_date.values()),
            'metadata': {'from_date': from_date, 'to_date': to_date, 'group_by': 'day'},
        }

    def get_all_invoices_for_date_range(
        self,
        from_date: str,
        to_date: str
    ) -> Dict[str, Any]:
        """
        Obtiene TODAS las facturas para un rango de fechas usando paginación automática

        Este método itera día por día y hace múltiples llamadas de 30 en 30 hasta obtener
        todas las facturas del día, ya que Alegra solo retorna máximo 30 por defecto.

        Cada página se reintenta (INVOICE_PAGE_ATTEMPTS). Si un día sigue fallando se
        deja por fuera COMPLETO (nunca medio día) y se reporta en `failed_days`: antes
        se saltaba en silencio y la respuesta decía éxito con días faltantes.

        Args:
            from_date: Fecha de inicio (YYYY-MM-DD)
            to_date: Fecha de fin (YYYY-MM-DD)

        Returns:
            Dict con estructura:
            {
                'success': True,
                'data': [lista completa de facturas],
                'metadata': {
                    'from_date': str,
                    'to_date': str,
                    'total_invoices': int,
                    'days_processed': int,
                    'failed_days': [str],   # días que no se pudieron traer
                    'complete': bool
                }
            }
        """
        from datetime import datetime, timedelta

        try:
            start_date = datetime.strptime(from_date, '%Y-%m-%d')
            end_date = datetime.strptime(to_date, '%Y-%m-%d')

            all_invoices = []
            failed_days = []
            days_processed = 0
            current_date = start_date

            while current_date <= end_date:
                date_str = current_date.strftime('%Y-%m-%d')
                try:
                    day_invoices = self._get_invoices_for_day(date_str)
                    logger.info(f"Obtenidas {len(day_invoices)} facturas para {date_str}")
                    all_invoices.extend(day_invoices)
                    days_processed += 1
                except Exception as e:
                    logger.error(f"Día {date_str} sin datos tras {INVOICE_PAGE_ATTEMPTS} intentos: {e}")
                    failed_days.append(date_str)
                current_date += timedelta(days=1)

            logger.info(
                f"Total de facturas obtenidas: {len(all_invoices)} en {days_processed} días"
                + (f"; días fallidos: {failed_days}" if failed_days else "")
            )

            return {
                'success': True,
                'data': all_invoices,
                'metadata': {
                    'from_date': from_date,
                    'to_date': to_date,
                    'total_invoices': len(all_invoices),
                    'days_processed': days_processed,
                    'failed_days': failed_days,
                    'complete': not failed_days,
                }
            }

        except Exception as e:
            logger.error(f"Error en get_all_invoices_for_date_range: {str(e)}")
            return {
                'success': False,
                'error': str(e),
                'data': []
            }

    def _get_invoices_for_day(self, date_str: str) -> List[Dict[str, Any]]:
        """Todas las facturas de un día (páginas de 30). Lanza excepción si una página falla tras reintentar."""
        limit = 30
        start = 0
        day_invoices: List[Dict[str, Any]] = []
        seen_ids = set()
        while True:
            params = {'date': date_str, 'limit': limit, 'start': start}
            batch = None
            for attempt in range(1, INVOICE_PAGE_ATTEMPTS + 1):
                try:
                    response = self._make_request('/invoices', params)
                    batch = response if isinstance(response, list) else response.get('data', [])
                    break
                except Exception as e:
                    logger.warning(f"Facturas {date_str} start={start}: intento {attempt}/{INVOICE_PAGE_ATTEMPTS} falló ({e})")
                    if attempt == INVOICE_PAGE_ATTEMPTS:
                        raise
                    time.sleep(INVOICE_RETRY_BASE_SECONDS * attempt)
            if not batch:
                return day_invoices
            new_invoices = [inv for inv in batch if inv.get('id') not in seen_ids]
            if not new_invoices:
                # Alegra ignoró `start` y repitió la página: no quedarse en ciclo
                logger.warning(f"Alegra repitió la página de facturas de {date_str} (start={start})")
                return day_invoices
            seen_ids.update(inv.get('id') for inv in new_invoices)
            day_invoices.extend(new_invoices)
            if len(batch) < limit:
                return day_invoices
            start += limit

    def get_sales_documents(
        self,
        from_date: str,
        to_date: str,
        limit: int = 10,
        start: int = 0
    ) -> Dict[str, Any]:
        """
        Obtiene documentos de ventas discriminados

        Args:
            from_date: Fecha de inicio (YYYY-MM-DD)
            to_date: Fecha de fin (YYYY-MM-DD)
            limit: Número de documentos a retornar
            start: Offset para paginación

        Returns:
            Dict con estructura:
            {
                'success': True,
                'data': [
                    {
                        'id': '123',
                        'number': 'FV-001',
                        'date': '2025-12-01',
                        'client': {...},
                        'total': 150000,
                        'items': [...],
                        ...
                    }
                ],
                'metadata': {...}
            }
        """
        params = {
            'from': from_date,
            'to': to_date,
            'limit': limit,
            'start': start
        }

        try:
            response = self._make_request('/invoices/sales-documents', params)

            return {
                'success': True,
                'data': response if isinstance(response, list) else response.get('data', []),
                'metadata': {
                    'from_date': from_date,
                    'to_date': to_date,
                    'limit': limit,
                    'start': start
                }
            }
        except Exception as e:
            logger.error(f"Error obteniendo sales documents: {str(e)}")
            return {
                'success': False,
                'error': str(e),
                'data': []
            }

    def get_inventory_value_totals(
        self,
        to_date: str,
        query: str = "",
        force_inventory_parallel: bool = False
    ) -> Dict[str, Any]:
        """
        Obtiene el total del valor del inventario para una fecha específica

        Este endpoint es extremadamente rápido ya que solo retorna el total agregado
        sin detalles de cada producto.

        Args:
            to_date: Fecha hasta la cual calcular el inventario (YYYY-MM-DD)
            query: Filtro de búsqueda opcional
            force_inventory_parallel: Forzar procesamiento paralelo

        Returns:
            Dict con estructura:
            {
                'success': True,
                'data': {
                    'total': 123456789
                }
            }

        Nota:
            Alegra retorna únicamente el valor total del inventario,
            no la cantidad de unidades.
        """
        params = {
            'toDate': to_date,
            'query': query,
            'forceInventoryParallel': str(force_inventory_parallel).lower()
        }

        try:
            response = self._make_request('/reports/inventory-value-totals', params)

            return {
                'success': True,
                'data': response,
                'metadata': {
                    'to_date': to_date,
                    'query': query
                }
            }
        except Exception as e:
            logger.error(f"Error obteniendo inventory value totals: {str(e)}")
            return {
                'success': False,
                'error': str(e),
                'data': {}
            }

    def get_bills_open_totals(
        self,
        from_date: str,
        to_date: str
    ) -> Dict[str, Any]:
        """
        Obtiene el total de cuentas por pagar pendientes para un rango de fechas

        Este endpoint es rápido ya que solo retorna totales agregados
        sin detalles de cada factura de proveedor.

        Args:
            from_date: Fecha de inicio (YYYY-MM-DD)
            to_date: Fecha de fin (YYYY-MM-DD)

        Returns:
            Dict con estructura:
            {
                'success': True,
                'data': {
                    'missingAmount': 13699200,
                    'totalDocuments': 4
                }
            }
        """
        params = {
            'from': from_date,
            'to': to_date
        }

        try:
            response = self._make_request('/reports/bills-open-totals', params)

            return {
                'success': True,
                'data': response,
                'metadata': {
                    'from_date': from_date,
                    'to_date': to_date
                }
            }
        except Exception as e:
            logger.error(f"Error obteniendo bills open totals: {str(e)}")
            return {
                'success': False,
                'error': str(e),
                'data': {}
            }

    # ------------------------------------------------------------------
    # Reportes de ventas agregados (clientes / vendedoras) y contactos.
    # Verificado 2026-10-01 con Basic en /api/v1: Alegra suma el rango en
    # el servidor; limit=2000 trae todos los clientes de un año en una sola
    # llamada. Solo order_field=total ordena bien, así que quien consume
    # estos métodos ordena por su cuenta. A diferencia de los métodos de
    # arriba, estos NO atrapan errores: los propaga para que el servicio
    # decida (requests.exceptions.*).
    # ------------------------------------------------------------------

    REPORT_PAGE_SIZE = 2000
    # Tope de páginas por consulta: si Alegra ignorara `start` y devolviera
    # siempre la misma página, el ciclo no puede quedar pidiendo sin fin.
    MAX_PAGES = 50

    def _get_report_rows(self, endpoint: str, params: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        Todas las filas de un reporte paginado ({data, metadata.total}).
        Pide páginas grandes y sigue mientras falten filas, por si Alegra
        llega a limitar el tamaño de página.
        """
        rows: List[Dict[str, Any]] = []
        start = 0
        for _ in range(self.MAX_PAGES):
            response = self._make_request(endpoint, {**params, 'limit': self.REPORT_PAGE_SIZE, 'start': start})
            if isinstance(response, list):
                return response
            page = response.get('data') or []
            if rows and page and page[0] == rows[0]:
                logger.warning(f"{endpoint}: Alegra repitió la primera página; se usan {len(rows)} filas")
                return rows
            rows.extend(page)
            total = (response.get('metadata') or {}).get('total')
            if not page or total is None or len(rows) >= int(total):
                return rows
            start += len(page)
        logger.warning(f"{endpoint}: se alcanzó el tope de {self.MAX_PAGES} páginas")
        return rows

    def get_sales_by_client(self, from_date: str, to_date: str, seller_id: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        Ventas agregadas por cliente en el rango (una fila por cliente).
        En /api/v1 (verificado 2026-10-02) cada fila trae SOLO idLocal (= id
        del contacto), name, totalDocuments, subTotal y total: sin cédula ni
        descuento. seller_id se manda como `sellerId`, pero v1 lo IGNORA
        (devuelve toda la tienda); solo sirve contra reports-api v2.
        """
        params = {'from': from_date, 'to': to_date, 'creditNoteFilter': 'creditNote'}
        if seller_id:
            params['sellerId'] = seller_id
        return self._get_report_rows('/reports/sales-by-client', params)

    def get_sales_by_seller(self, from_date: str, to_date: str) -> List[Dict[str, Any]]:
        """Ventas agregadas por vendedora en el rango (una fila por vendedora)."""
        params = {'from': from_date, 'to': to_date, 'creditNoteFilter': 'creditNote'}
        return self._get_report_rows('/reports/sales-by-seller', params)

    def get_sellers(self) -> List[Dict[str, Any]]:
        """Todas las vendedoras (activas e inactivas): id, name, identification, status."""
        sellers: List[Dict[str, Any]] = []
        seen = set()
        start = 0
        for _ in range(self.MAX_PAGES):
            page = self._make_request('/sellers', {'start': start, 'limit': 30})
            page = page if isinstance(page, list) else page.get('data') or []
            new = [s for s in page if str(s.get('id')) not in seen]
            seen.update(str(s.get('id')) for s in new)
            sellers.extend(new)
            # Página corta = última; página sin vendedoras nuevas = Alegra ignoró `start`.
            if len(page) < 30 or not new:
                return sellers
            start += 30
        return sellers

    def get_contact(self, contact_id: str) -> Dict[str, Any]:
        """Contacto de Alegra (teléfonos en phonePrimary / phoneSecondary / mobile)."""
        return self._make_request(f'/contacts/{contact_id}')

    def get_last_invoice_date(self, client_id: str) -> Optional[str]:
        """Fecha (YYYY-MM-DD) de la factura más reciente del cliente, o None."""
        response = self._make_request('/invoices', {
            'client_id': client_id,
            'order_field': 'date',
            'order_direction': 'DESC',
            'limit': 1,
        })
        invoices = response if isinstance(response, list) else response.get('data') or []
        if not invoices:
            return None
        invoice = invoices[0]
        # Si Alegra ignorara el filtro devolvería la factura de otro cliente.
        if str((invoice.get('client') or {}).get('id')) != str(client_id):
            return None
        return invoice.get('date')
