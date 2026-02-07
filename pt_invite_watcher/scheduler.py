from __future__ import annotations

import asyncio
import logging
import os
import socket
from collections.abc import Awaitable, Callable
from typing import Any, Optional

from pt_invite_watcher.lease_events import best_effort_lease_event, build_lease_detail
from pt_invite_watcher.kv_keys import SCHEDULER_LEASE_KEY
from pt_invite_watcher.lease_policy import scheduler_lease_ttl_seconds
from pt_invite_watcher.scanner import AlreadyScanningError
from pt_invite_watcher.scheduler_lease import SchedulerLeaseManager
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
        logger.exception("scheduler task ended with error")


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
    try:
        while True:
            try:
                is_leader = await lease.ensure_leader(ttl_seconds=lease_ttl)
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("ensure_leader failed")
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

            try:
                status = await ctx.scanner.run_once_scheduled()
                logger.info("scan status: %s", status)
                try:
                    await broadcast_dashboard_update()
                except asyncio.CancelledError:
                    raise
                except Exception:
                    pass
            except asyncio.CancelledError:
                raise
            except AlreadyScanningError as e:
                logger.info("scan skipped: %s", str(e))
            except Exception:
                logger.exception("scan cycle failed")

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
