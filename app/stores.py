"""
Multi-tienda: registro de tiendas KOAJ y resolución de la tienda activa por
request.

Las tiendas son INDEPENDIENTES en datos (cierres, cuentas, recompras,
empleadas, notas/tareas, ventas/inventario de Alegra) pero comparten la misma
plataforma, usuarios y Códigos KOAJ. Cada tienda tiene su propia cuenta de
Alegra.

Cómo se elige la tienda de un request:
  - El frontend manda el header `X-Store: <código>` (ej. 'primavera').
  - Sin header (o sin request, ej. al arrancar) se usa DEFAULT_STORE
    ('carreno'), así cualquier cliente que todavía no conozca el multi-tienda
    (frontend viejo en caché, workflow de GitHub Actions) sigue operando sobre
    Carreño exactamente como antes.
  - El permiso del usuario sobre esa tienda se valida en token_required
    (app/middlewares/auth.py), que es donde ya se conoce al usuario.

Credenciales de Alegra por tienda (variables de entorno):
  ALEGRA_USER_<SUFIJO> / ALEGRA_PASS_<SUFIJO>, ej. ALEGRA_USER_PRIMAVERA.
  Carreño cae a ALEGRA_USER / ALEGRA_PASS si no tiene las suyas propias, para
  no tener que tocar las variables que ya existen en Render.

Base de caja por tienda: BASE_OBJETIVO_<SUFIJO>, con respaldo a BASE_OBJETIVO
(450.000 por defecto).
"""
import os

from flask import g, has_request_context, request

from app.config import Config

DEFAULT_STORE = 'carreno'

# Orden = orden en que se muestran en el selector del frontend.
STORES = {
    'carreno': {
        'code': 'carreno',
        'name': 'KOAJ Puerto Carreño',
        'short_name': 'Carreño',
        'env_suffix': 'CARRENO',
    },
    'primavera': {
        'code': 'primavera',
        'name': 'KOAJ Primavera',
        'short_name': 'Primavera',
        'env_suffix': 'PRIMAVERA',
    },
}

STORE_HEADER = 'X-Store'


class InvalidStoreError(ValueError):
    """El código de tienda recibido no existe en STORES."""


def is_valid_store(code):
    return code in STORES


def normalize_store_code(code):
    """'Primavera ' -> 'primavera'. No valida que exista."""
    return (code or '').strip().lower()


def get_store_info(code):
    """Datos públicos de la tienda (sin credenciales), aptos para el frontend."""
    store = STORES[code]
    return {
        'code': store['code'],
        'name': store['name'],
        'short_name': store['short_name'],
        'base_objetivo': get_base_objetivo(code),
        'alegra_configured': all(get_alegra_credentials(code)),
    }


def list_stores():
    return [get_store_info(code) for code in STORES]


def _store_env(code, name):
    return os.getenv(f"{name}_{STORES[code]['env_suffix']}", '')


def get_alegra_credentials(code):
    """(usuario, token) de Alegra de la tienda. Pueden venir vacíos si no está configurada."""
    user = _store_env(code, 'ALEGRA_USER')
    password = _store_env(code, 'ALEGRA_PASS')
    if code == DEFAULT_STORE and not (user and password):
        # Compatibilidad: Carreño usa las variables de siempre si no tiene las suyas.
        user, password = Config.ALEGRA_USER, Config.ALEGRA_PASS
    return user, password


def get_base_objetivo(code):
    value = _store_env(code, 'BASE_OBJETIVO')
    if value:
        try:
            return int(value)
        except ValueError:
            pass
    return Config.BASE_OBJETIVO


def resolve_request_store():
    """
    Lee la tienda pedida por el request (header X-Store; query param ?store=
    como respaldo para descargas por URL). Sin valor -> DEFAULT_STORE.
    Lanza InvalidStoreError si el código no existe.
    """
    raw = request.headers.get(STORE_HEADER) or request.args.get('store')
    code = normalize_store_code(raw) or DEFAULT_STORE
    if not is_valid_store(code):
        raise InvalidStoreError(f"Tienda desconocida: '{raw}'")
    return code


def stores_for_user(user):
    """
    Códigos de las tiendas que puede operar el usuario (dict de g.current_user).
    Por ahora: el admin opera todas; el resto, solo la tienda por defecto.
    """
    if user and user.get('role') == 'admin':
        return list(STORES)
    return [DEFAULT_STORE]


def user_can_access_store(user, code):
    return code in stores_for_user(user)


def get_current_store():
    """Código de la tienda activa del request en curso (DEFAULT_STORE fuera de un request)."""
    if has_request_context():
        return getattr(g, 'store_code', None) or DEFAULT_STORE
    return DEFAULT_STORE


def store_setting_key(key, code=None):
    """
    Clave de app_settings propia de una tienda. Carreño conserva las claves de
    siempre (sin sufijo) para no tener que migrar los valores ya guardados en
    producción; las demás tiendas usan '<clave>:<tienda>'.
    """
    code = code or get_current_store()
    return key if code == DEFAULT_STORE else f"{key}:{code}"


def get_alegra_client(code=None):
    """Cliente de Alegra de la tienda (por defecto, la del request en curso)."""
    from app.services.alegra_client import AlegraClient
    from app.exceptions import ConfigurationError

    code = code or get_current_store()
    user, password = get_alegra_credentials(code)
    if not user or not password:
        raise ConfigurationError(
            f"La cuenta de Alegra de {STORES[code]['name']} todavía no está configurada"
        )
    return AlegraClient(user, password, Config.ALEGRA_API_BASE_URL, Config.ALEGRA_TIMEOUT)


def get_alegra_direct_client(code=None):
    """Cliente de las APIs directas de Alegra de la tienda (por defecto, la del request)."""
    from app.services.alegra_direct_client import AlegraDirectClient
    from app.exceptions import ConfigurationError

    code = code or get_current_store()
    user, password = get_alegra_credentials(code)
    if not user or not password:
        raise ConfigurationError(
            f"La cuenta de Alegra de {STORES[code]['name']} todavía no está configurada"
        )
    return AlegraDirectClient(user, password, Config.ALEGRA_API_BASE_URL, Config.ALEGRA_TIMEOUT)
