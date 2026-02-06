from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass

from pt_invite_watcher.lease_emitter import LeaseEventEmitter
from pt_invite_watcher.kv_keys import SCAN_LEASE_KEY
from pt_invite_watcher.lease_policy import scan_lease_ttl_seconds
from pt_invite_watcher.storage.types import SupportsLeaseStoreWithEvents
from pt_invite_watcher.utils.parse import format_error_detail


logger = logging.getLogger("pt_invite_watcher.scanner_lease")


@dataclass(frozen=True)
class ScanLeasePolicy:
    ttl_seconds: int
    refresh_interval_seconds: int


def compute_policy(*, base_ttl_seconds: int, scan_timeout_seconds: int) -> ScanLeasePolicy:
    ttl = max(
        int(base_ttl_seconds or 0),
        scan_lease_ttl_seconds(timeout_seconds=int(scan_timeout_seconds or 0)),
    )
    refresh = max(10, ttl // 3)
    return ScanLeasePolicy(ttl_seconds=ttl, refresh_interval_seconds=refresh)


class ScanLeaseManager:
    def __init__(self, store: SupportsLeaseStoreWithEvents, *, owner: str):
        self._store = store
        self._owner = str(owner or "").strip()
        self._events = LeaseEventEmitter(store, kind="scan", key=SCAN_LEASE_KEY, owner=self._owner)
        self._busy_throttle_seconds = 60.0
        self._disabled_throttle_seconds = 300.0

    async def acquire(self, *, ttl_seconds: int) -> bool:
        # Each scan run should report refresh failures/exceptions once.
        self._events.clear_once("scan_lease_refresh_failed", "scan_lease_refresh_exception")
        try:
            ok = await self._store.try_acquire_lease(SCAN_LEASE_KEY, owner=self._owner, ttl_seconds=ttl_seconds)
        except asyncio.CancelledError:
            raise
        except Exception as e:
            logger.exception("scan lease check failed; running without lease")
            await self._events.emit(
                level="warn",
                action="scan_lease_disabled",
                message="scan lease check failed; running without lease",
                ttl_seconds=ttl_seconds,
                error=format_error_detail(e),
                extra={"disabled_reason": "exception"},
                throttle_seconds=self._disabled_throttle_seconds,
            )
            return True
        if not ok:
            await self._events.emit(
                level="info",
                action="scan_lease_busy",
                message="scan lease is held by another owner; skipping scan",
                ttl_seconds=ttl_seconds,
                throttle_seconds=self._busy_throttle_seconds,
            )
        return bool(ok)

    async def extend(self, *, ttl_seconds: int) -> None:
        try:
            ok = await self._store.try_acquire_lease(SCAN_LEASE_KEY, owner=self._owner, ttl_seconds=ttl_seconds)
            if not ok:
                logger.warning("scan lease refresh failed; another process may scan concurrently")
                await self._events.emit(
                    level="warn",
                    action="scan_lease_refresh_failed",
                    message="scan lease refresh failed; another process may scan concurrently",
                    ttl_seconds=ttl_seconds,
                    once=True,
                )
        except asyncio.CancelledError:
            raise
        except Exception as e:
            logger.exception("scan lease refresh failed; continuing without lease")
            await self._events.emit(
                level="warn",
                action="scan_lease_refresh_exception",
                message="scan lease refresh exception; continuing without lease",
                ttl_seconds=ttl_seconds,
                error=format_error_detail(e),
                extra={"disabled_reason": "exception"},
                once=True,
            )

    async def release(self) -> None:
        try:
            await self._store.release_lease(SCAN_LEASE_KEY, owner=self._owner)
        except asyncio.CancelledError:
            raise
        except Exception as e:
            logger.exception("scan lease release failed")
            await self._events.emit(
                level="warn",
                action="scan_lease_release_failed",
                message="scan lease release failed",
                ttl_seconds=0,
                error=format_error_detail(e),
            )

    async def refresh_loop(self, *, ttl_seconds: int, refresh_interval_seconds: int | None = None) -> None:
        ttl = max(1, int(ttl_seconds or 0))
        refresh = int(refresh_interval_seconds or 0)
        if refresh <= 0:
            refresh = max(10, ttl // 3)
        while True:
            await asyncio.sleep(refresh)
            await self.extend(ttl_seconds=ttl)


__all__ = ["ScanLeaseManager", "ScanLeasePolicy", "compute_policy"]
