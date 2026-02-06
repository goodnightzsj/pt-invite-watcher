from __future__ import annotations

import time
from typing import Any, Optional

from pt_invite_watcher.lease_events import best_effort_lease_event, build_lease_detail
from pt_invite_watcher.storage.types import SupportsAddEvent


class LeaseEventEmitter:
    """
    Helper to emit lease-related events with optional throttling and one-shot behavior.

    This keeps the "event detail" schema consistent across scheduler leadership and scan locking.
    """

    def __init__(self, store: SupportsAddEvent, *, kind: str, key: str, owner: str):
        self._store = store
        self._kind = str(kind or "").strip() or "unknown"
        self._key = str(key or "").strip()
        self._owner = str(owner or "").strip()
        self._last_sent: dict[str, float] = {}
        self._once: set[str] = set()

    def clear_once(self, *keys: str) -> None:
        if not keys:
            self._once.clear()
            return
        for key in keys:
            k = str(key or "").strip()
            if k:
                self._once.discard(k)

    async def emit(
        self,
        *,
        level: str,
        action: str,
        message: str,
        ttl_seconds: Optional[int] = None,
        error: str = "",
        extra: Optional[dict[str, Any]] = None,
        throttle_seconds: float | None = None,
        throttle_key: str | None = None,
        once: bool = False,
        once_key: str | None = None,
    ) -> None:
        act = str(action or "").strip() or "-"

        if once:
            k = str(once_key or act).strip()
            if k and k in self._once:
                return

        if throttle_seconds is not None:
            t = float(throttle_seconds or 0.0)
            if t > 0:
                k = str(throttle_key or act).strip() or act
                last = float(self._last_sent.get(k, 0.0) or 0.0)
                now = time.monotonic()
                if (now - last) < t:
                    return
                self._last_sent[k] = now

        if once:
            k = str(once_key or act).strip()
            if k:
                self._once.add(k)

        await best_effort_lease_event(
            self._store,
            level=level,
            action=act,
            message=message,
            detail=build_lease_detail(
                kind=self._kind,
                key=self._key,
                owner=self._owner,
                ttl_seconds=ttl_seconds,
                error=error,
                extra=extra,
            ),
        )


__all__ = ["LeaseEventEmitter"]
