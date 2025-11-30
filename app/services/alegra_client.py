"""
Cliente para la API de Alegra
"""
import requests
from requests.auth import HTTPBasicAuth
from typing import Dict, List
import logging

from app.exceptions import (
    AlegraConnectionError,
    AlegraAuthError,
    AlegraTimeoutError
)
from app.utils.formatters import (
    safe_number,
    normalize_payment_method,
    get_payment_method_label,
    format_cop
)

logger = logging.getLogger(__name__)


class AlegraClient:
    """Cliente para interactuar con la API de Alegra"""

    def __init__(self, username: str, password: str, base_url: str, timeout: int = 30):
        """
        Inicializa el cliente de Alegra

        Args:
            username: Usuario de Alegra
            password: Token/Password de Alegra
            base_url: URL base de la API
            timeout: Timeout en segundos para las peticiones
        """
        self.username = username
        self.password = password
        self.base_url = base_url.rstrip('/')
        self.timeout = timeout
        self.session = requests.Session()
        self.session.auth = HTTPBasicAuth(username, password)

        # Headers comunes
        self.session.headers.update({
            'Content-Type': 'application/json',
            'Accept': 'application/json'
        })

        logger.info(f"Cliente Alegra inicializado para usuario: {username}")

    def get_invoices_by_date(self, date: str) -> List[Dict]:
        """
        Obtiene las facturas de Alegra para una fecha específica

        Args:
            date: Fecha en formato YYYY-MM-DD

        Returns:
            Lista de facturas

        Raises:
            AlegraTimeoutError: Si la petición excede el timeout
            AlegraAuthError: Si las credenciales son inválidas
            AlegraConnectionError: Para otros errores de conexión
        """
        url = f"{self.base_url}/invoices"
        params = {
            "date": date
        }

        logger.info(f"Consultando facturas de Alegra para fecha: {date}")

        try:
            response = self.session.get(
                url,
                params=params,
                timeout=self.timeout
            )

            # Log del status
            logger.debug(f"Alegra response status: {response.status_code}")

            # Manejar diferentes status codes
            if response.status_code == 401:
                logger.error("Credenciales de Alegra inválidas (401)")
                raise AlegraAuthError("Credenciales de Alegra inválidas")

            if response.status_code == 403:
                logger.error("Acceso prohibido a Alegra (403)")
                raise AlegraAuthError("Acceso prohibido. Verifique permisos de la cuenta")

            if response.status_code == 404:
                logger.warning(f"Endpoint no encontrado en Alegra (404): {url}")
                raise AlegraConnectionError(
                    "Endpoint no encontrado en Alegra",
                    details={'url': url}
                )

            if response.status_code >= 500:
                logger.error(f"Error del servidor de Alegra ({response.status_code})")
                raise AlegraConnectionError(
                    f"Error del servidor de Alegra (HTTP {response.status_code})",
                    details={'status_code': response.status_code}
                )

            # Intentar parsear JSON
            response.raise_for_status()
            data = response.json()

            # Validar que sea una lista
            if not isinstance(data, list):
                logger.warning(f"Respuesta de Alegra no es una lista: {type(data)}")
                data = []

            logger.info(f"✓ {len(data)} facturas obtenidas de Alegra para {date}")
            return data

        except requests.exceptions.Timeout:
            logger.error(f"Timeout al conectar con Alegra (>{self.timeout}s)")
            raise AlegraTimeoutError(
                f"Timeout al conectar con Alegra (>{self.timeout}s)"
            )

        except requests.exceptions.ConnectionError as e:
            logger.error(f"Error de conexión con Alegra: {str(e)}")
            raise AlegraConnectionError(
                "No se pudo conectar con Alegra. Verifique la conexión a internet",
                details={'error': str(e)}
            )

        except requests.exceptions.HTTPError as e:
            logger.error(f"Error HTTP de Alegra: {str(e)}")
            raise AlegraConnectionError(
                f"Error HTTP de Alegra: {e.response.status_code}",
                details={'error': str(e)}
            )

        except ValueError as e:
            logger.error(f"Error al parsear JSON de Alegra: {str(e)}")
            raise AlegraConnectionError(
                "Respuesta inválida de Alegra (JSON mal formado)",
                details={'error': str(e)}
            )

        except Exception as e:
            logger.error(f"Error inesperado con Alegra: {str(e)}", exc_info=True)
            raise AlegraConnectionError(
                f"Error inesperado al conectar con Alegra: {str(e)}",
                details={'error': str(e)}
            )

    def process_invoices(self, invoices: List[Dict]) -> Dict[str, float]:
        """
        Procesa facturas y suma totales por método de pago

        Args:
            invoices: Lista de facturas de Alegra

        Returns:
            Dict con totales por método: {"credit-card": X, "debit-card": Y, ...}
        """
        totals = {
            "credit-card": 0,
            "debit-card": 0,
            "transfer": 0,
            "cash": 0
        }

        for inv in invoices:
            payments = inv.get("payments", []) or []

            for p in payments:
                amount = safe_number(p.get("amount", 0))
                pm_raw = p.get("paymentMethod", "")
                method = normalize_payment_method(pm_raw)

                if method in totals:
                    totals[method] += amount
                else:
                    # Métodos desconocidos van a 'cash' por defecto
                    logger.debug(f"Método de pago desconocido '{pm_raw}' mapeado a 'cash'")
                    totals["cash"] += amount

        logger.debug(f"Totales procesados: {totals}")
        return totals

    def build_alegra_response(
        self,
        totals: Dict[str, float],
        date: str,
        username: str
    ) -> Dict:
        """
        Construye la estructura de respuesta de Alegra

        Args:
            totals: Diccionario con totales por método de pago
            date: Fecha consultada
            username: Usuario utilizado

        Returns:
            Dict con estructura completa de respuesta
        """
        result = {}

        for method, total in totals.items():
            result[method] = {
                "label": get_payment_method_label(method),
                "total": int(total),
                "formatted": format_cop(total)
            }

        total_sum = sum(totals.values())
        result_total = {
            "label": "TOTAL VENTA DEL DÍA",
            "total": int(total_sum),
            "formatted": format_cop(total_sum)
        }

        return {
            "date_requested": date,
            "username_used": username,
            "results": result,
            "total_sale": result_total
        }

    def get_sales_summary(self, date: str) -> Dict:
        """
        Obtiene el resumen completo de ventas para una fecha

        Args:
            date: Fecha en formato YYYY-MM-DD

        Returns:
            Diccionario con resumen completo de ventas
        """
        invoices = self.get_invoices_by_date(date)
        totals = self.process_invoices(invoices)
        return self.build_alegra_response(totals, date, self.username)

    def get_invoices_by_date_range(
        self,
        start_date: str,
        end_date: str,
        start: int = 0,
        limit: int = 30
    ) -> List[Dict]:
        """
        Obtiene facturas de Alegra en un rango de fechas con paginación

        IMPORTANTE: La API de Alegra tiene una limitación donde el parámetro date con formato
        "start,end" solo considera la primera fecha. Por lo tanto, este método obtiene TODAS
        las facturas y las filtra del lado del cliente para el rango especificado.

        Args:
            start_date: Fecha de inicio en formato YYYY-MM-DD
            end_date: Fecha de fin en formato YYYY-MM-DD
            start: Offset para paginación (default: 0)
            limit: Cantidad de registros por página (default: 30)

        Returns:
            Lista de facturas filtradas por el rango de fechas

        Raises:
            AlegraTimeoutError: Si la petición excede el timeout
            AlegraAuthError: Si las credenciales son inválidas
            AlegraConnectionError: Para otros errores de conexión
        """
        url = f"{self.base_url}/invoices"
        # NO usamos el parámetro date porque solo toma la primera fecha
        # En su lugar, obtenemos todas las facturas y filtramos del lado del cliente
        params = {
            "start": start,
            "limit": limit,
            "order-direction": "DESC"  # Obtener las más recientes primero
        }

        logger.info(
            f"Consultando facturas de Alegra (filtraremos del {start_date} al {end_date} del lado del cliente) "
            f"(start={start}, limit={limit})"
        )

        try:
            response = self.session.get(
                url,
                params=params,
                timeout=self.timeout
            )

            # Manejar diferentes status codes
            if response.status_code == 401:
                logger.error("Credenciales de Alegra inválidas (401)")
                raise AlegraAuthError("Credenciales de Alegra inválidas")

            if response.status_code == 403:
                logger.error("Acceso prohibido a Alegra (403)")
                raise AlegraAuthError("Acceso prohibido. Verifique permisos de la cuenta")

            if response.status_code == 404:
                logger.warning(f"Endpoint no encontrado en Alegra (404): {url}")
                raise AlegraConnectionError(
                    "Endpoint no encontrado en Alegra",
                    details={'url': url}
                )

            if response.status_code >= 500:
                logger.error(f"Error del servidor de Alegra ({response.status_code})")
                raise AlegraConnectionError(
                    f"Error del servidor de Alegra (HTTP {response.status_code})",
                    details={'status_code': response.status_code}
                )

            response.raise_for_status()
            data = response.json()

            if not isinstance(data, list):
                logger.warning(f"Respuesta de Alegra no es una lista: {type(data)}")
                data = []

            # Filtrar facturas por rango de fechas del lado del cliente
            from datetime import datetime
            filtered_data = []
            start_dt = datetime.strptime(start_date, '%Y-%m-%d').date()
            end_dt = datetime.strptime(end_date, '%Y-%m-%d').date()

            for invoice in data:
                # Obtener la fecha de la factura (puede venir en diferentes campos)
                invoice_date_str = invoice.get('date') or invoice.get('datetime', '')
                if not invoice_date_str:
                    logger.warning(f"Factura sin fecha: {invoice.get('id', 'unknown')}")
                    continue

                # Parsear la fecha (formato esperado: YYYY-MM-DD o YYYY-MM-DD HH:MM:SS)
                try:
                    if ' ' in invoice_date_str:
                        invoice_date = datetime.strptime(invoice_date_str.split(' ')[0], '%Y-%m-%d').date()
                    else:
                        invoice_date = datetime.strptime(invoice_date_str, '%Y-%m-%d').date()

                    # Filtrar por rango
                    if start_dt <= invoice_date <= end_dt:
                        filtered_data.append(invoice)
                except ValueError as e:
                    logger.warning(f"Error parseando fecha de factura {invoice.get('id')}: {invoice_date_str} - {e}")
                    continue

            logger.info(f"✓ {len(data)} facturas obtenidas, {len(filtered_data)} dentro del rango {start_date} - {end_date}")
            return filtered_data

        except requests.exceptions.Timeout:
            logger.error(f"Timeout al conectar con Alegra (>{self.timeout}s)")
            raise AlegraTimeoutError(
                f"Timeout al conectar con Alegra (>{self.timeout}s)"
            )

        except requests.exceptions.ConnectionError as e:
            logger.error(f"Error de conexión con Alegra: {str(e)}")
            raise AlegraConnectionError(
                "No se pudo conectar con Alegra. Verifique la conexión a internet",
                details={'error': str(e)}
            )

        except requests.exceptions.HTTPError as e:
            logger.error(f"Error HTTP de Alegra: {str(e)}")
            raise AlegraConnectionError(
                f"Error HTTP de Alegra: {e.response.status_code}",
                details={'error': str(e)}
            )

        except ValueError as e:
            logger.error(f"Error al parsear JSON de Alegra: {str(e)}")
            raise AlegraConnectionError(
                "Respuesta inválida de Alegra (JSON mal formado)",
                details={'error': str(e)}
            )

        except Exception as e:
            logger.error(f"Error inesperado con Alegra: {str(e)}", exc_info=True)
            raise AlegraConnectionError(
                f"Error inesperado al conectar con Alegra: {str(e)}",
                details={'error': str(e)}
            )

    def get_all_invoices_in_range(
        self,
        start_date: str,
        end_date: str,
        max_pages: int = 100
    ) -> List[Dict]:
        """
        Obtiene TODAS las facturas en un rango de fechas manejando paginación automáticamente

        OPTIMIZACIÓN: Si start_date == end_date (mismo día), usa get_invoices_by_date()
        directamente con el parámetro date de Alegra, que es más eficiente.

        NOTA: Debido a la limitación de la API de Alegra con el parámetro date, este método
        obtiene facturas de forma paginada y filtra del lado del cliente. Se detiene cuando
        todas las facturas de una página son anteriores al rango solicitado (optimización).

        Args:
            start_date: Fecha de inicio en formato YYYY-MM-DD
            end_date: Fecha de fin en formato YYYY-MM-DD
            max_pages: Máximo número de páginas a consultar (default: 100)

        Returns:
            Lista completa de facturas dentro del rango
        """
        from datetime import datetime

        # OPTIMIZACIÓN: Si las fechas son iguales, usar consulta directa por fecha única
        if start_date == end_date:
            logger.info(f"Fechas iguales detectadas ({start_date}). Usando consulta optimizada con parámetro date")
            return self.get_invoices_by_date(start_date)

        all_invoices = []
        page = 0
        limit = 30
        start_dt = datetime.strptime(start_date, '%Y-%m-%d').date()

        logger.info(f"Iniciando consulta completa de facturas desde {start_date} hasta {end_date}")

        while page < max_pages:
            start_offset = page * limit
            # get_invoices_by_date_range ya filtra del lado del cliente
            invoices = self.get_invoices_by_date_range(start_date, end_date, start_offset, limit)

            # Si no hay facturas en esta página, terminamos
            if not invoices:
                logger.info(f"No hay más facturas en el rango. Total páginas consultadas: {page + 1}")
                break

            all_invoices.extend(invoices)
            logger.info(f"Página {page + 1}: {len(invoices)} facturas en el rango. Total acumulado: {len(all_invoices)}")

            # Si obtuvimos menos registros filtrados que el límite, probablemente ya pasamos el rango
            # Continuamos paginando hasta que una página completa esté fuera del rango
            if len(invoices) < limit:
                logger.info(f"Página con menos de {limit} facturas en el rango, continuamos verificando...")
                # Verificar si deberíamos seguir paginando
                # (podría haber más facturas en el rango en páginas siguientes)
                page += 1
                continue

            page += 1

        logger.info(f"✓ Consulta completa finalizada. Total de facturas en el rango: {len(all_invoices)}")
        return all_invoices

    def get_monthly_sales_summary(
        self,
        start_date: str,
        end_date: str
    ) -> Dict:
        """
        Obtiene el resumen de ventas para un rango de fechas (mes)

        Args:
            start_date: Fecha de inicio en formato YYYY-MM-DD
            end_date: Fecha de fin en formato YYYY-MM-DD

        Returns:
            Dict con resumen de ventas mensuales
        """
        # Obtener todas las facturas del mes
        invoices = self.get_all_invoices_in_range(start_date, end_date)

        # Calcular totales
        total_vendido = 0
        cantidad_facturas = len(invoices)

        # Totales por método de pago
        totales_por_metodo = {
            "credit-card": 0,
            "debit-card": 0,
            "transfer": 0,
            "cash": 0
        }

        for inv in invoices:
            # Sumar el total de la factura
            total_invoice = safe_number(inv.get("total", 0))
            total_vendido += total_invoice

            # Procesar pagos por método
            payments = inv.get("payments", []) or []
            for p in payments:
                amount = safe_number(p.get("amount", 0))
                pm_raw = p.get("paymentMethod", "")
                method = normalize_payment_method(pm_raw)

                if method in totales_por_metodo:
                    totales_por_metodo[method] += amount
                else:
                    totales_por_metodo["cash"] += amount

        # Construir respuesta
        payment_details = {}
        for method, total in totales_por_metodo.items():
            payment_details[method] = {
                "label": get_payment_method_label(method),
                "total": int(total),
                "formatted": format_cop(total)
            }

        return {
            "date_range": {
                "start": start_date,
                "end": end_date
            },
            "total_vendido": {
                "label": "TOTAL VENDIDO EN EL PERIODO",
                "total": int(total_vendido),
                "formatted": format_cop(total_vendido)
            },
            "cantidad_facturas": cantidad_facturas,
            "payment_methods": payment_details,
            "username_used": self.username
        }

    def get_active_items(self) -> List[Dict]:
        """
        Obtiene todos los items activos con inventario de Alegra

        Returns:
            Lista de items activos con información de inventario

        Raises:
            AlegraTimeoutError: Si la petición excede el timeout
            AlegraAuthError: Si las credenciales son inválidas
            AlegraConnectionError: Para otros errores de conexión
        """
        url = f"{self.base_url}/items"
        params = {
            "status": "active"
        }

        logger.info("Consultando items activos de Alegra")

        try:
            response = self.session.get(
                url,
                params=params,
                timeout=self.timeout
            )

            # Manejar diferentes status codes
            if response.status_code == 401:
                logger.error("Credenciales de Alegra inválidas (401)")
                raise AlegraAuthError("Credenciales de Alegra inválidas")

            if response.status_code == 403:
                logger.error("Acceso prohibido a Alegra (403)")
                raise AlegraAuthError("Acceso prohibido. Verifique permisos de la cuenta")

            if response.status_code == 404:
                logger.warning(f"Endpoint no encontrado en Alegra (404): {url}")
                raise AlegraConnectionError(
                    "Endpoint no encontrado en Alegra",
                    details={'url': url}
                )

            if response.status_code >= 500:
                logger.error(f"Error del servidor de Alegra ({response.status_code})")
                raise AlegraConnectionError(
                    f"Error del servidor de Alegra (HTTP {response.status_code})",
                    details={'status_code': response.status_code}
                )

            response.raise_for_status()
            data = response.json()

            if not isinstance(data, list):
                logger.warning(f"Respuesta de Alegra no es una lista: {type(data)}")
                data = []

            logger.info(f"✓ {len(data)} items activos obtenidos de Alegra")
            return data

        except requests.exceptions.Timeout:
            logger.error(f"Timeout al conectar con Alegra (>{self.timeout}s)")
            raise AlegraTimeoutError(
                f"Timeout al conectar con Alegra (>{self.timeout}s)"
            )

        except requests.exceptions.ConnectionError as e:
            logger.error(f"Error de conexión con Alegra: {str(e)}")
            raise AlegraConnectionError(
                "No se pudo conectar con Alegra. Verifique la conexión a internet",
                details={'error': str(e)}
            )

        except requests.exceptions.HTTPError as e:
            logger.error(f"Error HTTP de Alegra: {str(e)}")
            raise AlegraConnectionError(
                f"Error HTTP de Alegra: {e.response.status_code}",
                details={'error': str(e)}
            )

        except ValueError as e:
            logger.error(f"Error al parsear JSON de Alegra: {str(e)}")
            raise AlegraConnectionError(
                "Respuesta inválida de Alegra (JSON mal formado)",
                details={'error': str(e)}
            )

        except Exception as e:
            logger.error(f"Error inesperado con Alegra: {str(e)}", exc_info=True)
            raise AlegraConnectionError(
                f"Error inesperado al conectar con Alegra: {str(e)}",
                details={'error': str(e)}
            )

    def health_check(self) -> bool:
        """
        Verifica si el servicio de Alegra está disponible

        Returns:
            True si está disponible, False en caso contrario
        """
        try:
            url = f"{self.base_url}/categories"  # Endpoint ligero para health check
            response = self.session.get(url, timeout=5)
            return response.status_code in [200, 401]  # 401 significa que API responde
        except Exception:
            return False
