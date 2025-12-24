"""
Cliente para APIs directas de Alegra (no documentadas)
Estas APIs se descubrieron mediante inspección de red en la plataforma
"""
import requests
from typing import Dict, List, Any, Optional
import logging
from datetime import datetime

logger = logging.getLogger(__name__)


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
                break

        logger.info(
            f"Paginación completa: {total_received} items recibidos, "
            f"{total_filtered_asterisk} filtrados (asteriscos), "
            f"{total_filtered_disabled} filtrados (deshabilitados), "
            f"{len(all_items)} válidos retornados"
        )

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
                'pages_fetched': current_page
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

    def get_all_invoices_for_date_range(
        self,
        from_date: str,
        to_date: str
    ) -> Dict[str, Any]:
        """
        Obtiene TODAS las facturas para un rango de fechas usando paginación automática

        Este método itera día por día y hace múltiples llamadas de 30 en 30 hasta obtener
        todas las facturas del día, ya que Alegra solo retorna máximo 30 por defecto.

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
                    'days_processed': int
                }
            }
        """
        from datetime import datetime, timedelta

        try:
            # Convertir fechas a objetos datetime
            start_date = datetime.strptime(from_date, '%Y-%m-%d')
            end_date = datetime.strptime(to_date, '%Y-%m-%d')

            all_invoices = []
            days_processed = 0
            current_date = start_date

            # Iterar día por día
            while current_date <= end_date:
                date_str = current_date.strftime('%Y-%m-%d')
                logger.info(f"Obteniendo facturas para la fecha: {date_str}")

                # Para cada día, obtener todas las facturas con paginación
                start = 0
                limit = 30
                day_invoices = []

                while True:
                    params = {
                        'date': date_str,
                        'limit': limit,
                        'start': start
                    }

                    try:
                        # Llamar al endpoint /invoices con parámetro date para obtener facturas completas
                        response = self._make_request('/invoices', params)

                        # La respuesta puede ser una lista directamente o un objeto con data
                        invoices_batch = response if isinstance(response, list) else response.get('data', [])

                        # Log de debugging para ver si las facturas tienen items
                        if invoices_batch and len(invoices_batch) > 0:
                            first_invoice = invoices_batch[0]
                            logger.info(f"Primera factura de {date_str}: ID={first_invoice.get('id')}, tiene items={bool(first_invoice.get('items'))}, items count={len(first_invoice.get('items', []))}")
                            logger.debug(f"Estructura de primera factura: {list(first_invoice.keys())}")

                        if not invoices_batch or len(invoices_batch) == 0:
                            # No hay más facturas para este día
                            break

                        day_invoices.extend(invoices_batch)

                        # Si recibimos menos de 'limit' facturas, es la última página
                        if len(invoices_batch) < limit:
                            break

                        # Incrementar el offset para la siguiente página
                        start += limit

                    except Exception as e:
                        logger.error(f"Error obteniendo facturas para {date_str} (start={start}): {str(e)}")
                        # Continuar con el siguiente día si hay un error
                        break

                logger.info(f"Obtenidas {len(day_invoices)} facturas para {date_str}")
                all_invoices.extend(day_invoices)
                days_processed += 1

                # Avanzar al siguiente día
                current_date += timedelta(days=1)

            logger.info(f"Total de facturas obtenidas: {len(all_invoices)} en {days_processed} días")

            return {
                'success': True,
                'data': all_invoices,
                'metadata': {
                    'from_date': from_date,
                    'to_date': to_date,
                    'total_invoices': len(all_invoices),
                    'days_processed': days_processed
                }
            }

        except Exception as e:
            logger.error(f"Error en get_all_invoices_for_date_range: {str(e)}")
            return {
                'success': False,
                'error': str(e),
                'data': []
            }

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
