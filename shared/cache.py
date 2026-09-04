"""Small TTL cache with a Redis backend when one is configured.

The hot path reads tenant config and drift severity on every request. Both are
written rarely and read constantly, so both are cached. This module exists so
that neither caller has to know whether Redis is actually present: with no
``CUSTOS_REDIS_URL`` it degrades to an in-process dict, which is exactly right
for a single-node deployment and for tests.
"""

from __future__ import annotations

import json
import threading
import time
from typing import Any

from shared.config import defaults


class _InProcessCache:
    """Thread-safe dict with per-key expiry.

    Correct for a single gateway process. Multi-process deployments configure
    Redis so that a config change propagates to every worker at once instead of
    waiting out each process's independent TTL.
    """

    def __init__(self) -> None:
        self._data: dict[str, tuple[float, Any]] = {}
        self._lock = threading.Lock()

    def get(self, key: str) -> Any | None:
        with self._lock:
            entry = self._data.get(key)
            if entry is None:
                return None
            expires_at, value = entry
            if expires_at < time.monotonic():
                del self._data[key]
                return None
            return value

    def set(self, key: str, value: Any, ttl_s: int) -> None:
        with self._lock:
            self._data[key] = (time.monotonic() + ttl_s, value)

    def delete(self, key: str) -> None:
        with self._lock:
            self._data.pop(key, None)

    def clear(self) -> None:
        with self._lock:
            self._data.clear()


class _RedisCache:
    """Redis-backed cache. Values are JSON so they survive a process restart."""

    def __init__(self, url: str) -> None:
        import redis  # imported lazily: only a Redis deployment pays for the import

        self._client = redis.Redis.from_url(url, decode_responses=True)

    def get(self, key: str) -> Any | None:
        try:
            raw = self._client.get(key)
        except Exception:
            # A cache outage must not take down the hot path — miss and move on.
            return None
        return json.loads(raw) if raw is not None else None

    def set(self, key: str, value: Any, ttl_s: int) -> None:
        try:
            self._client.setex(key, ttl_s, json.dumps(value, default=str))
        except Exception:
            pass

    def delete(self, key: str) -> None:
        try:
            self._client.delete(key)
        except Exception:
            pass

    def clear(self) -> None:
        try:
            self._client.flushdb()
        except Exception:
            pass


_cache: _InProcessCache | _RedisCache | None = None


def get_cache() -> _InProcessCache | _RedisCache:
    global _cache
    if _cache is None:
        if defaults.REDIS_URL:
            try:
                _cache = _RedisCache(defaults.REDIS_URL)
            except Exception:
                _cache = _InProcessCache()
        else:
            _cache = _InProcessCache()
    return _cache


def reset_cache() -> None:
    """Drop everything. Used between tests and after a config write."""
    global _cache
    if _cache is not None:
        _cache.clear()
    _cache = None
