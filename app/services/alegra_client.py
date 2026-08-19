"""
Cliente para la API de Alegra
"""
import os
import requests
from requests.auth import HTTPBasicAuth
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
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
    format_cop,
    filter_voided_invoices
)
from app.utils.ttl_cache import TTLCache
from app.utils.timezone import get_colombia_today_string

logger = logging.getLogger(__name__)

# Caché compartida entre todas las instancias del cliente (se crea una por request).
# Solo se usa para fechas PASADAS: las facturas de un día que ya cerró no cambian,
# mientras que las del día en curso siguen llegando y nunca deben servirse desde caché.
_invoices_cache = TTLCache()
ALEGRA_CACHE_TTL_SECONDS = int(os.getenv('ALEGRA_CACHE_TTL_SECONDS', '600'))


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

        # Reintentos automáticos con backoff exponencial para peticiones GET
        # (idempotentes) ante timeouts, errores de conexión y 5xx/429 de Alegra.
        # No se reintentan POST/PUT/DELETE para evitar operaciones duplicadas.
        retry_strategy = Retry(
            total=3,
            connect=3,
            read=3,
            status=3,
            backoff_factor=1.5,
            status_forcelist=[429, 500, 502, 503, 504],
            allowed_methods=["GET", "HEAD", "OPTIONS"],
            raise_on_status=False,
        )
        adapter = HTTPAdapter(max_retries=retry_strategy)
        self.session.mount("https://", adapter)
        self.session.mount("http://", adapter)

        logger.info(f"Cliente Alegra inicializado para usuario: {username}")

    def get_invoices_by_date(self, date: str) -> List[Dict]:
        """
        Obtiene TODAS las facturas de Alegra para una fecha específica usando paginación

        Este método implementa paginación automática para obtener todas las facturas del día,
        sin importar si son más de 30 (límite por defecto de Alegra).

        Args:
            date: Fecha en formato YYYY-MM-DD

        Returns:
            Lista completa de facturas del día

        Raises:
            AlegraTimeoutError: Si la petición excede el timeout
            AlegraAuthError: Si las credenciales son inválidas
            AlegraConnectionError: Para otros errores de conexión
        """
        # Las facturas de un día que ya cerró no cambian: servir desde caché si está disponible.
        # El día actual NUNCA se cachea porque sigue recibiendo ventas nuevas.
        is_past_date = date != get_colombia_today_string()
        if is_past_date:
            cached = _invoices_cache.get(date)
            if cached is not None:
                logger.info(f"[CACHE HIT] Facturas de {date} servidas desde caché ({len(cached)} facturas)")
                return cached

        url = f"{self.base_url}/invoices"
        all_invoices = []
        start = 0  # Empezar desde 0 para no omitir la primera factura
        limit = 30  # Máximo permitido por Alegra
        total_invoices = None

        logger.info(f"Consultando facturas de Alegra para fecha: {date} (con paginación automática)")

        try:
            # Primera petición con metadata para conocer el total de facturas
            params = {
                "date": date,
                "start": start,
                "metadata": "true"
            }

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
            response_data = response.json()

            # Con metadata=true, la respuesta tiene estructura: {"metadata": {...}, "data": [...]}
            if isinstance(response_data, dict):
                metadata = response_data.get("metadata", {})
                total_invoices = metadata.get("total", 0)
                data = response_data.get("data", [])
                logger.info(f"Metadata recibido: Total de facturas para {date}: {total_invoices}")
            else:
                # Si por alguna razón no viene con metadata, asumir que es la lista directa
                data = response_data if isinstance(response_data, list) else []
                total_invoices = len(data)
                logger.warning(f"No se recibió metadata, asumiendo {total_invoices} facturas")

            # Validar que data sea una lista
            if not isinstance(data, list):
                logger.warning(f"Respuesta de Alegra no es una lista: {type(data)}")
                data = []

            # Agregar las primeras facturas
            all_invoices.extend(data)
            logger.info(f"✓ Primera página: {len(data)} facturas obtenidas (de {total_invoices} totales)")

            # Si hay más facturas, hacer peticiones adicionales
            if total_invoices > limit:
                pages_needed = (total_invoices + limit - 1) // limit  # Redondeo hacia arriba
                logger.info(f"Se necesitan {pages_needed} páginas para obtener todas las facturas")

                # Iterar desde la página 2 en adelante
                for page in range(2, pages_needed + 1):
                    start = (page - 1) * limit  # Página 2: start=30, Página 3: start=60, etc.
                    params = {
                        "date": date,
                        "start": start
                    }

                    logger.info(f"Consultando página {page}/{pages_needed} (start={start})...")

                    response = self.session.get(
                        url,
                        params=params,
                        timeout=self.timeout
                    )

                    response.raise_for_status()
                    page_data = response.json()

                    # Manejar respuesta con o sin metadata
                    if isinstance(page_data, dict):
                        page_invoices = page_data.get("data", [])
                    else:
                        page_invoices = page_data if isinstance(page_data, list) else []

                    if not isinstance(page_invoices, list):
                        logger.warning(f"Página {page} no retornó lista válida")
                        continue

                    all_invoices.extend(page_invoices)
                    logger.info(f"✓ Página {page}/{pages_needed}: {len(page_invoices)} facturas obtenidas. Total acumulado: {len(all_invoices)}")

            logger.info(f"✓ TOTAL: {len(all_invoices)} facturas obtenidas para {date} (esperadas: {total_invoices})")

            if is_past_date:
                _invoices_cache.set(date, all_invoices, ALEGRA_CACHE_TTL_SECONDS)

            return all_invoices

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

    def process_invoices(self, invoices: List[Dict]) -> Dict:
        """
        Procesa facturas y suma totales por método de pago
        IMPORTANTE: Filtra facturas anuladas antes de calcular totales

        Args:
            invoices: Lista de facturas de Alegra

        Returns:
            Dict con:
                - totals: Dict con totales por método: {"credit-card": X, "debit-card": Y, ...}
                - voided_info: Información sobre facturas anuladas
                - processed_count: Cantidad de facturas procesadas (activas)
                - total_invoices: Total de facturas recibidas
        """
        # Filtrar facturas anuladas ANTES de procesar
        filter_result = filter_voided_invoices(invoices)
        active_invoices = filter_result['active_invoices']
        voided_info = {
            'voided_count': filter_result['voided_count'],
            'total_voided_amount': filter_result['total_voided_amount'],
            'total_voided_amount_formatted': filter_result['total_voided_amount_formatted'],
            'voided_summary': filter_result['voided_summary']
        }

        # Log información sobre facturas anuladas
        if filter_result['voided_count'] > 0:
            logger.info(
                f"⚠️  Se encontraron {filter_result['voided_count']} facturas anuladas "
                f"(Total: {filter_result['total_voided_amount_formatted']}) - "
                f"Estas NO se incluyen en los cálculos de venta"
            )
            for voided in filter_result['voided_summary']:
                logger.info(
                    f"   - Factura anulada #{voided['number']} (ID: {voided['id']}): "
                    f"{voided['total_formatted']} - Cliente: {voided['client_name']}"
                )

        # Calcular totales SOLO con facturas activas
        totals = {
            "credit-card": 0,
            "debit-card": 0,
            "transfer": 0,
            "cash": 0
        }

        for inv in active_invoices:
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

        logger.debug(f"Totales procesados (facturas activas): {totals}")

        return {
            'totals': totals,
            'voided_info': voided_info,
            'processed_count': len(active_invoices),
            'total_invoices': len(invoices)
        }

    def build_alegra_response(
        self,
        totals: Dict[str, float],
        date: str,
        username: str,
        voided_info: Dict = None,
        processed_count: int = 0,
        total_invoices: int = 0
    ) -> Dict:
        """
        Construye la estructura de respuesta de Alegra

        Args:
            totals: Diccionario con totales por método de pago
            date: Fecha consultada
            username: Usuario utilizado
            voided_info: Información sobre facturas anuladas
            processed_count: Cantidad de facturas procesadas (activas)
            total_invoices: Total de facturas recibidas

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

        response = {
            "date_requested": date,
            "username_used": username,
            "results": result,
            "total_sale": result_total,
            "invoices_summary": {
                "total_invoices": total_invoices,
                "active_invoices": processed_count,
                "voided_invoices": voided_info.get('voided_count', 0) if voided_info else 0
            }
        }

        # Agregar información de facturas anuladas si existen
        if voided_info and voided_info.get('voided_count', 0) > 0:
            response['voided_invoices'] = voided_info

        return response

    def get_sales_summary(self, date: str) -> Dict:
        """
        Obtiene el resumen completo de ventas para una fecha
        IMPORTANTE: Filtra facturas anuladas automáticamente

        Args:
            date: Fecha en formato YYYY-MM-DD

        Returns:
            Diccionario con resumen completo de ventas (sin facturas anuladas)
        """
        invoices = self.get_invoices_by_date(date)
        process_result = self.process_invoices(invoices)

        return self.build_alegra_response(
            totals=process_result['totals'],
            date=date,
            username=self.username,
            voided_info=process_result['voided_info'],
            processed_count=process_result['processed_count'],
            total_invoices=process_result['total_invoices']
        )

    def get_invoices_by_date_range(
        self,
        start_date: str,
        end_date: str,
        start: int = 0,
        limit: int = 30
    ) -> tuple:
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
            Tupla (filtered_data, has_older_invoices, total_fetched) donde:
            - filtered_data: Lista de facturas filtradas por el rango de fechas
            - has_older_invoices: bool indicando si hay facturas más antiguas que el rango
            - total_fetched: int con el total de facturas obtenidas de la API (antes de filtrar)

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
            has_older_invoices = False
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
                    # Detectar si hay facturas más antiguas que el rango (para continuar paginando)
                    elif invoice_date < start_dt:
                        has_older_invoices = True
                except ValueError as e:
                    logger.warning(f"Error parseando fecha de factura {invoice.get('id')}: {invoice_date_str} - {e}")
                    continue

            logger.info(f"✓ {len(data)} facturas obtenidas, {len(filtered_data)} dentro del rango {start_date} - {end_date}, hay facturas más antiguas: {has_older_invoices}")
            return filtered_data, has_older_invoices, len(data)

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
        Obtiene TODAS las facturas en un rango de fechas consultando día por día

        Este método itera desde start_date hasta end_date, consultando las facturas
        de cada día individualmente usando el parámetro 'date' de Alegra (que funciona
        correctamente para fechas únicas). Luego combina todos los resultados.

        Args:
            start_date: Fecha de inicio en formato YYYY-MM-DD
            end_date: Fecha de fin en formato YYYY-MM-DD
            max_pages: No usado, mantenido por compatibilidad

        Returns:
            Lista completa de facturas dentro del rango
        """
        from datetime import datetime, timedelta

        # Si las fechas son iguales, usar consulta directa por fecha única
        if start_date == end_date:
            logger.info(f"Fechas iguales detectadas ({start_date}). Usando consulta optimizada con parámetro date")
            return self.get_invoices_by_date(start_date)

        # Parsear fechas
        start_dt = datetime.strptime(start_date, '%Y-%m-%d').date()
        end_dt = datetime.strptime(end_date, '%Y-%m-%d').date()

        logger.info(f"[DEBUG] Iniciando consulta día por día desde {start_date} hasta {end_date}")
        print(f"[DEBUG CONSOLE] Iniciando consulta día por día desde {start_date} hasta {end_date}")

        all_invoices = []
        current_date = start_dt
        days_processed = 0

        # Iterar día por día
        while current_date <= end_dt:
            date_str = current_date.strftime('%Y-%m-%d')
            logger.info(f"Consultando facturas para el día: {date_str}")

            try:
                # Consultar facturas del día usando el método que funciona correctamente
                daily_invoices = self.get_invoices_by_date(date_str)

                if daily_invoices:
                    all_invoices.extend(daily_invoices)
                    logger.info(f"[OK] {len(daily_invoices)} facturas obtenidas para {date_str}. Total acumulado: {len(all_invoices)}")
                else:
                    logger.info(f"  0 facturas para {date_str}")

            except Exception as e:
                logger.error(f"Error consultando facturas para {date_str}: {str(e)}")
                # Continuar con el siguiente día en caso de error

            # Avanzar al siguiente día
            current_date += timedelta(days=1)
            days_processed += 1

        logger.info(f"[OK] Consulta completa finalizada. {days_processed} días procesados. Total de facturas: {len(all_invoices)}")
        return all_invoices

    def get_monthly_sales_summary(
        self,
        start_date: str,
        end_date: str
    ) -> Dict:
        """
        Obtiene el resumen de ventas para un rango de fechas (mes)
        IMPORTANTE: Filtra facturas anuladas automáticamente

        Args:
            start_date: Fecha de inicio en formato YYYY-MM-DD
            end_date: Fecha de fin en formato YYYY-MM-DD

        Returns:
            Dict con resumen de ventas mensuales (sin facturas anuladas)
        """
        # Obtener todas las facturas del mes
        all_invoices = self.get_all_invoices_in_range(start_date, end_date)

        # Filtrar facturas anuladas ANTES de calcular totales
        filter_result = filter_voided_invoices(all_invoices)
        invoices = filter_result['active_invoices']
        voided_info = {
            'voided_count': filter_result['voided_count'],
            'total_voided_amount': filter_result['total_voided_amount'],
            'total_voided_amount_formatted': filter_result['total_voided_amount_formatted'],
            'voided_summary': filter_result['voided_summary']
        }

        # Log información sobre facturas anuladas
        if filter_result['voided_count'] > 0:
            logger.info(
                f"⚠️  Periodo {start_date} - {end_date}: "
                f"Se encontraron {filter_result['voided_count']} facturas anuladas "
                f"(Total: {filter_result['total_voided_amount_formatted']}) - "
                f"Estas NO se incluyen en los cálculos de venta"
            )

        # Calcular totales SOLO con facturas activas
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

        response = {
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
            "username_used": self.username,
            "invoices_summary": {
                "total_invoices": len(all_invoices),
                "active_invoices": len(invoices),
                "voided_invoices": filter_result['voided_count']
            }
        }

        # Agregar información de facturas anuladas si existen
        if voided_info['voided_count'] > 0:
            response['voided_invoices'] = voided_info

        return response

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

    def get_sales_comparison_year_over_year(self, current_date: str) -> Dict:
        """
        Obtiene comparación de ventas del día actual vs mismo día del año anterior

        Args:
            current_date: Fecha actual en formato YYYY-MM-DD

        Returns:
            Diccionario con ventas del día actual, año anterior, y comparación
        """
        from datetime import datetime, timedelta

        # Calcular fecha del año anterior (mismo día y mes)
        try:
            current_dt = datetime.strptime(current_date, '%Y-%m-%d')
            previous_year_dt = current_dt.replace(year=current_dt.year - 1)
            previous_year_date = previous_year_dt.strftime('%Y-%m-%d')
        except ValueError:
            # Caso especial: 29 de febrero en año bisiesto
            current_dt = datetime.strptime(current_date, '%Y-%m-%d')
            previous_year_dt = current_dt - timedelta(days=365)
            previous_year_date = previous_year_dt.strftime('%Y-%m-%d')

        logger.info(f"Obteniendo comparación: {current_date} vs {previous_year_date}")

        # Obtener ventas del día actual
        current_sales = self.get_sales_summary(current_date)

        # Obtener ventas del año anterior
        previous_sales = self.get_sales_summary(previous_year_date)

        # Extraer totales
        current_total = current_sales.get('total_sale', {}).get('total', 0)
        previous_total = previous_sales.get('total_sale', {}).get('total', 0)

        # Calcular diferencia y porcentaje
        difference = current_total - previous_total

        if previous_total > 0:
            percentage_change = ((current_total - previous_total) / previous_total) * 100
        else:
            # Si el año anterior fue 0, pero ahora hay ventas, es crecimiento infinito
            percentage_change = 100.0 if current_total > 0 else 0.0

        # Construir respuesta
        comparison = {
            'current': {
                'date': current_date,
                'total': current_total,
                'formatted': format_cop(current_total),
                'invoices_count': current_sales.get('invoices_summary', {}).get('active_invoices', 0)
            },
            'previous_year': {
                'date': previous_year_date,
                'total': previous_total,
                'formatted': format_cop(previous_total),
                'invoices_count': previous_sales.get('invoices_summary', {}).get('active_invoices', 0)
            },
            'comparison': {
                'difference': difference,
                'difference_formatted': format_cop(abs(difference)),
                'percentage_change': round(percentage_change, 2),
                'is_growth': difference >= 0,
                'growth_label': 'crecimiento' if difference >= 0 else 'decrecimiento'
            }
        }

        logger.info(
            f"Comparación YoY - Actual: {format_cop(current_total)}, "
            f"Anterior: {format_cop(previous_total)}, "
            f"Cambio: {percentage_change:.2f}%"
        )

        return comparison

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
