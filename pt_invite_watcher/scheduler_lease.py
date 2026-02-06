from __future__ import annotations

import logging

from pt_invite_watcher.lease_emitter import LeaseEventEmitter
from pt_invite_watcher.kv_keys import SCHEDULER_LEASE_KEY
from pt_invite_watcher.storage.types import SupportsLeaseStoreWithEvents
from pt_invite_watcher.utils.parse import format_error_detail


logger = logging.getLogger("pt_invite_watcher.scheduler_lease")


class SchedulerLeaseManager:
    """
    Encapsulate scheduler leadership (leader lock) handling.

    The scheduler loop can focus on scanning cadence, while this manager
    centralizes leader election transitions + lease-disabled fallback behavior.
    """

    def __init__(self, store: SupportsLeaseStoreWithEvents, *, owner: str, enabled: bool):
        self._store = store
        self._owner = str(owner or "").strip()
        self._enabled = bool(enabled)
        self._was_leader = False
        self._events = LeaseEventEmitter(store, kind="scheduler", key=SCHEDULER_LEASE_KEY, owner=self._owner)

    async def ensure_leader(self, *, ttl_seconds: int) -> bool:
        """
        Return True if this process should run scans; False if it should pause.
        """
        if not self._enabled:
            return True

        ttl = int(ttl_seconds or 0)
        try:
            is_leader = await self._store.try_acquire_lease(SCHEDULER_LEASE_KEY, owner=self._owner, ttl_seconds=ttl)
        except Exception as e:
            logger.exception("scheduler lease check failed; disabling leader lock for this process")
            await self._events.emit(
                level="warn",
                action="scheduler_lease_disabled_exception",
                message="scheduler lease check failed; leader lock disabled for this process",
                ttl_seconds=ttl,
                error=format_error_detail(e),
                extra={"disabled_reason": "exception"},
            )
            self._enabled = False
            is_leader = True

        if not is_leader:
            if self._was_leader:
                logger.warning("scheduler lease lost; pausing scan loop")
                await self._events.emit(
                    level="warn",
                    action="scheduler_leader_lost",
                    message="scheduler lease lost; pausing scan loop",
                    ttl_seconds=ttl,
                )
            self._was_leader = False
            return False

        if not self._was_leader:
            logger.info("scheduler lease acquired (owner=%s)", self._owner)
            await self._events.emit(
                level="info",
                action="scheduler_leader_acquired",
                message="scheduler lease acquired",
                ttl_seconds=ttl,
            )
        self._was_leader = True
        return True


__all__ = ["SchedulerLeaseManager"]
