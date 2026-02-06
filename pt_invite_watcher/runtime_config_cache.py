from __future__ import annotations

import asyncio
import time
from typing import Any, Optional

from pt_invite_watcher.config import Settings
from pt_invite_watcher.runtime_config import RuntimeConfig
from pt_invite_watcher.runtime_config_loader import load_runtime_config_from_store


class RuntimeConfigCache:
    """
    Small in-process cache for RuntimeConfig loaded from KV store.

    This is intentionally simple:
    - Reduces repeated KV reads across one request / one scan tick.
    - Uses a short TTL to avoid long-lived staleness if config is changed externally.
    - Can be explicitly invalidated after config writes.
    """

    def __init__(self, settings: Settings, store: Any, *, ttl_seconds: int = 2):
        self._settings = settings
        self._store = store
        self._ttl_seconds = max(0, int(ttl_seconds or 0))
        self._lock = asyncio.Lock()
        self._cached: Optional[RuntimeConfig] = None
        self._cached_at: Optional[float] = None

    def invalidate(self) -> None:
        self._cached = None
        self._cached_at = None

    def _is_fresh(self) -> bool:
        if self._cached is None or self._cached_at is None:
            return False
        if self._ttl_seconds <= 0:
            return False
        return (time.monotonic() - self._cached_at) <= self._ttl_seconds

    async def get(self) -> RuntimeConfig:
        if self._is_fresh():
            assert self._cached is not None
            return self._cached

        async with self._lock:
            if self._is_fresh():
                assert self._cached is not None
                return self._cached

            rc = await load_runtime_config_from_store(self._settings, self._store)
            self._cached = rc
            self._cached_at = time.monotonic()
            return rc

