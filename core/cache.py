"""
CacheManager — In-memory dict with TTL support.
Drop-in replacement for Redis when REDIS_URL is empty.
"""

import time
import threading
import logging
from typing import Any, Optional

logger = logging.getLogger(__name__)


class CacheManager:
    """Thread-safe in-memory cache with per-key TTL."""

    def __init__(self):
        self._store: dict[str, dict] = {}
        self._lock = threading.Lock()
        logger.info("CacheManager initialized (in-memory dict)")

    def set(self, key: str, value: Any, ttl: int = 60) -> None:
        """Store a value with TTL in seconds."""
        with self._lock:
            self._store[key] = {
                "value": value,
                "expires_at": time.time() + ttl,
                "set_at": time.time(),
            }

    def get(self, key: str) -> Optional[Any]:
        """Get value if not expired. Returns None if missing or expired."""
        with self._lock:
            entry = self._store.get(key)
            if entry is None:
                return None
            if time.time() > entry["expires_at"]:
                del self._store[key]
                return None
            return entry["value"]

    def get_or_default(self, key: str, default: Any = None) -> Any:
        """Get value or return default."""
        result = self.get(key)
        return result if result is not None else default

    def delete(self, key: str) -> None:
        with self._lock:
            self._store.pop(key, None)

    def exists(self, key: str) -> bool:
        return self.get(key) is not None

    def get_age(self, key: str) -> Optional[float]:
        """Seconds since key was last set. None if missing."""
        with self._lock:
            entry = self._store.get(key)
            if entry is None:
                return None
            return time.time() - entry["set_at"]

    def keys(self, prefix: str = "") -> list[str]:
        """List all non-expired keys with optional prefix filter."""
        now = time.time()
        with self._lock:
            return [
                k for k, v in self._store.items()
                if now <= v["expires_at"] and k.startswith(prefix)
            ]

    def cleanup(self) -> int:
        """Remove expired entries. Returns count removed."""
        now = time.time()
        with self._lock:
            expired = [k for k, v in self._store.items() if now > v["expires_at"]]
            for k in expired:
                del self._store[k]
            return len(expired)

    def status(self) -> dict:
        """Cache health status for /health endpoint."""
        now = time.time()
        with self._lock:
            total = len(self._store)
            active = sum(1 for v in self._store.values() if now <= v["expires_at"])
        return {"type": "in-memory", "total_keys": total, "active_keys": active}


# Singleton
cache = CacheManager()
