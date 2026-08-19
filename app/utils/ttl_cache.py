"""
Caché en memoria con expiración (TTL) simple y thread-safe.
Pensado para respuestas de Alegra que no cambian una vez que el día ya pasó.
"""
import time
import threading
from typing import Any, Optional


class TTLCache:
    """Caché clave-valor en memoria con expiración por entrada."""

    def __init__(self):
        self._store = {}
        self._lock = threading.Lock()

    def get(self, key: str) -> Optional[Any]:
        with self._lock:
            entry = self._store.get(key)
            if entry is None:
                return None
            value, expires_at = entry
            if time.monotonic() >= expires_at:
                del self._store[key]
                return None
            return value

    def set(self, key: str, value: Any, ttl_seconds: float) -> None:
        with self._lock:
            self._store[key] = (value, time.monotonic() + ttl_seconds)

    def clear(self) -> None:
        with self._lock:
            self._store.clear()

    def __len__(self) -> int:
        with self._lock:
            return len(self._store)
