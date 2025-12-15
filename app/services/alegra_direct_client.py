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

    def get_inventory_value_report(
        self,
        to_date: str,
        limit: int = 10,
        page: int = 1,
        query: str = ""
    ) -> Dict[str, Any]:
        """
        Obtiene el reporte de valor de inventario filtrando items obsoletos

        IMPORTANTE: Filtra automáticamente items con nombres que empiezan con asteriscos (*)
        ya que estos son productos que ya no se venden pero no pudieron eliminarse de Alegra.

        Args:
            to_date: Fecha hasta la cual generar el reporte (YYYY-MM-DD)
            limit: Número de items por página (default: 10, max: 1000)
            page: Número de página (1-indexed)
            query: Filtro de búsqueda opcional

        Returns:
            Dict con estructura:
            {
                'success': True,
                'data': [...],  # Lista de items de inventario (sin items con asteriscos)
                'metadata': {
                    'page': int,
                    'limit': int,
                    'query': str,
                    'to_date': str,
                    'total_received': int,      # Items recibidos de Alegra
                    'total_filtered': int,      # Items filtrados (asteriscos)
                    'total_returned': int       # Items enviados al frontend
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

            # FILTRAR items con asteriscos en el nombre
            # Estos son items que ya no se venden pero no pudieron eliminarse de Alegra
            filtered_data = []
            items_filtered_count = 0

            for item in raw_data:
                item_name = item.get('name', '') if isinstance(item, dict) else ''

                # Filtrar si el nombre comienza con asteriscos o es solo asteriscos
                if item_name and item_name.strip().startswith('*'):
                    items_filtered_count += 1
                    logger.debug(f"Item filtrado (asteriscos): {item_name}")
                    continue

                # Si el item pasa el filtro, agregarlo
                filtered_data.append(item)

            logger.info(
                f"Inventario procesado: {len(raw_data)} items recibidos, "
                f"{items_filtered_count} filtrados (asteriscos), "
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
                    'total_filtered': items_filtered_count,
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
