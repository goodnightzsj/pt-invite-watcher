from __future__ import annotations

import asyncio
import logging
import os
import socket
from collections.abc import Awaitable, Callable
from typing import Any, Optional

from datetime import datetime, timedelta, timezone

from pt_invite_watcher.lease_events import best_effort_lease_event, build_lease_detail
from pt_invite_watcher.kv_keys import SCHEDULER_LEASE_KEY
from pt_invite_watcher.lease_policy import scheduler_lease_ttl_seconds
from pt_invite_watcher.scanner import AlreadyScanningError
from pt_invite_watcher.scheduler_lease import SchedulerLeaseManager
from pt_invite_watcher.storage.event_log_store import prune_events_older_than
from pt_invite_watcher.utils.asyncio_tasks import create_task_logged
from pt_invite_watcher.utils.parse import cfg_bool


logger = logging.getLogger("pt_invite_watcher.scheduler")


async def start_scheduler(
    ctx: Any,
    *,
    broadcast_dashboard_update: Callable[[], Awaitable[None]],
) -> Optional[asyncio.Task[Any]]:
    scheduler_disabled = cfg_bool(os.getenv("PTIW_DISABLE_SCHEDULER"), default=False)
    if scheduler_disabled:
        logger.info("scheduler disabled (PTIW_DISABLE_SCHEDULER)")
        return None

    scheduler_owner = f"{socket.gethostname()}:{os.getpid()}"
    leader_lock_disabled = cfg_bool(os.getenv("PTIW_DISABLE_LEADER_LOCK"), default=False)
    if leader_lock_disabled:
        await best_effort_lease_event(
            ctx.store,
            level="info",
            action="scheduler_lease_disabled_env",
            message="scheduler leader lock disabled by env",
            detail=build_lease_detail(
                kind="scheduler",
                key=SCHEDULER_LEASE_KEY,
                owner=scheduler_owner,
                ttl_seconds=0,
                extra={"disabled_reason": "env"},
            ),
        )

    return create_task_logged(
        _scheduler_loop(
            ctx,
            broadcast_dashboard_update=broadcast_dashboard_update,
            owner=scheduler_owner,
            leader_lock_disabled=leader_lock_disabled,
        ),
        logger=logger,
        name="scheduler_loop",
        label="scheduler loop",
    )


async def stop_scheduler(task: Optional[asyncio.Task[Any]]) -> None:
    if task is None:
        return
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass
    except Exception:
        pass


async def _emit_scheduler_event(
    ctx: Any, *, level: str, action: str, message: str, detail: dict[str, Any] | None = None
) -> None:
    add_event = getattr(ctx.store, "add_event", None)
    if not callable(add_event):
        return
    try:
        await add_event(
            category="scan",
            level=level,
            action=action,
            message=message,
            detail=detail or {},
        )
    except asyncio.CancelledError:
        raise
    except Exception:
        logger.exception("failed to write scheduler event (action=%s)", action)


async def _scheduler_loop(
    ctx: Any,
    *,
    broadcast_dashboard_update: Callable[[], Awaitable[None]],
    owner: str,
    leader_lock_disabled: bool,
) -> None:
    probe_done = False
    lease = SchedulerLeaseManager(ctx.store, owner=owner, enabled=not leader_lock_disabled)
    interval = int(ctx.settings.scan.interval_seconds or 600)
    timeout = int(ctx.settings.scan.timeout_seconds or 20)
    try:
        rc = await ctx.runtime_config.get()
        interval = int(rc.scan.interval_seconds or interval)
        timeout = int(rc.scan.timeout_seconds or timeout)
    except asyncio.CancelledError:
        raise
    except Exception:
        pass
    lease_ttl = scheduler_lease_ttl_seconds(interval_seconds=interval, timeout_seconds=timeout)
    # Track consecutive failures so we can surface a louder alert (event log + WARNING) when
    # the loop has silently failed for several cycles in a row.
    # We alert at fixed milestones (3rd, 10th, 30th, 100th, …) instead of every cycle so the log
    # stays readable but operators still see ongoing problems escalate.
    consecutive_failures = 0
    consecutive_lease_failures = 0
    failure_alert_milestones = (3, 10, 30, 100, 300)
    # Retention sweep runs at most once per 24h (not on every scan tick).
    # `None` = "hasn't swept yet this process lifetime"; we lazy-run on first
    # leader tick + then every 24h.
    last_prune_at: Optional[datetime] = None
    try:
        while True:
            try:
                is_leader = await lease.ensure_leader(ttl_seconds=lease_ttl)
                consecutive_lease_failures = 0
            except asyncio.CancelledError:
                raise
            except Exception as e:
                consecutive_lease_failures += 1
                logger.exception("ensure_leader failed (consecutive=%d)", consecutive_lease_failures)
                if consecutive_lease_failures in failure_alert_milestones:
                    await _emit_scheduler_event(
                        ctx,
                        level="error",
                        action="scheduler_lease_alert",
                        message=f"scheduler leader-lock acquisition failed {consecutive_lease_failures} times in a row",
                        detail={"owner": owner, "error": str(e)[:500]},
                    )
                await asyncio.sleep(5)
                continue
            if not is_leader:
                await asyncio.sleep(5)
                continue

            if not probe_done:
                try:
                    probe_status = await ctx.deps.probe()
                    logger.info("deps probe: %s", probe_status)
                except asyncio.CancelledError:
                    raise
                except Exception:
                    logger.exception("deps probe failed")
                probe_done = True

            # Retention sweep — once per 24h, only from the leader, only if
            # configured to a positive number of days. Runs before the scan
            # so the newly-produced events aren't immediately eligible for
            # deletion. Failures log but don't abort the scan cycle; retention
            # is best-effort, the actual scan loop is the priority.
            retention_days = int(getattr(getattr(ctx.settings, "retention", None), "log_days", 0) or 0)
            if retention_days > 0:
                now_utc = datetime.now(timezone.utc)
                if last_prune_at is None or (now_utc - last_prune_at) >= timedelta(hours=24):
                    try:
                        cutoff = (now_utc - timedelta(days=retention_days)).isoformat()
                        removed = await prune_events_older_than(ctx.store, cutoff)
                        last_prune_at = now_utc
                        if removed > 0:
                            logger.info("retention: pruned %d event_log rows older than %dd", removed, retention_days)
                            await _emit_scheduler_event(
                                ctx,
                                level="info",
                                action="retention_prune",
                                message=f"retention: pruned {removed} event_log rows older than {retention_days}d",
                                detail={"removed": removed, "retention_days": retention_days},
                            )
                    except asyncio.CancelledError:
                        raise
                    except Exception:
                        logger.exception("retention sweep failed")

            try:
                status = await ctx.scanner.run_once_scheduled()
                logger.info("scan status: %s", status)
                if consecutive_failures >= failure_alert_milestones[0]:
                    # Recovered — note it so operators see the loop healed.
                    await _emit_scheduler_event(
                        ctx,
                        level="info",
                        action="scheduler_recovered",
                        message=f"scheduler recovered after {consecutive_failures} consecutive failures",
                        detail={"owner": owner},
                    )
                consecutive_failures = 0
                try:
                    await broadcast_dashboard_update()
                except asyncio.CancelledError:
                    raise
                except Exception:
                    logger.exception("broadcast_dashboard_update failed")
            except asyncio.CancelledError:
                raise
            except AlreadyScanningError as e:
                logger.info("scan skipped: %s", str(e))
            except Exception as e:
                consecutive_failures += 1
                logger.exception("scan cycle failed (consecutive=%d)", consecutive_failures)
                if consecutive_failures in failure_alert_milestones:
                    await _emit_scheduler_event(
                        ctx,
                        level="error",
                        action="scheduler_failure_alert",
                        message=f"scheduler scan failed {consecutive_failures} times in a row",
                        detail={"owner": owner, "error": str(e)[:500]},
                    )

            interval = int(ctx.settings.scan.interval_seconds or 600)
            timeout = int(ctx.settings.scan.timeout_seconds or timeout or 20)
            try:
                rc = await ctx.runtime_config.get()
                interval = int(rc.scan.interval_seconds or interval)
                timeout = int(rc.scan.timeout_seconds or timeout)
            except asyncio.CancelledError:
                raise
            except Exception:
                pass
            lease_ttl = scheduler_lease_ttl_seconds(interval_seconds=interval, timeout_seconds=timeout)
            await asyncio.sleep(max(30, interval))
    except asyncio.CancelledError:
        logger.info("scan loop cancelled")
        raise
