from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Awaitable, Callable, Optional

import httpx

from pt_invite_watcher.kv_keys import SCAN_STATUS_KEY
from pt_invite_watcher.models import Site
from pt_invite_watcher.scanner_moviepilot import moviepilot_warning as _moviepilot_warning


logger = logging.getLogger("pt_invite_watcher.scanner")


@dataclass(frozen=True)
class PreparedRun:
    sites: list[Site]
    cookie_mgr: Any
    mp_configured: bool
    mp_fields: dict[str, Any]
    scan_lease_ttl_seconds: int
    scan_lease_refresh_interval_seconds: int
    scan_timeout: int
    scan_user_agent: Optional[str]
    scan_trust_env: bool
    request_retry_delay_seconds: int


@dataclass(frozen=True)
class ScanRunResult:
    status: dict[str, Any]
    clear_hint: bool


async def run_once_locked(
    *,
    store: Any,
    prepared: PreparedRun,
    started_at: datetime,
    in_flight: dict[str, asyncio.Task[Any]],
    new_http_client: Callable[[int, bool], httpx.AsyncClient],
    check_one: Callable[..., Awaitable[None]],
    format_error_detail: Callable[[Exception], str],
    normalize_domain: Callable[[str], str],
) -> ScanRunResult:
    sites = prepared.sites
    cookie_mgr = prepared.cookie_mgr
    mp_configured = prepared.mp_configured
    mp_fields = prepared.mp_fields
    scan_user_agent = prepared.scan_user_agent
    request_retry_delay_seconds = prepared.request_retry_delay_seconds

    if not sites:
        error = mp_fields["moviepilot_error"] if mp_fields["moviepilot_error"] else "no sites configured"
        status = {
            "ok": False,
            "site_count": 0,
            "error": error,
            **mp_fields,
            "last_run_at": started_at.isoformat(),
        }
        await store.set_json(SCAN_STATUS_KEY, status)
        await store.add_event(category="scan", level="error", action="scan_failed", message=error)
        return ScanRunResult(status=status, clear_hint=False)

    to_scan: list[Site] = []
    skipped_in_flight = 0
    for site in sites:
        dom = normalize_domain(site.domain)
        if not dom:
            continue
        if dom in in_flight:
            skipped_in_flight += 1
            continue
        to_scan.append(site)

    if not to_scan:
        status = {
            "ok": True,
            "site_count": len(sites),
            "scanned_count": 0,
            "skipped_in_flight": skipped_in_flight,
            "error": "",
            "warning": "all_sites_scanning",
            **mp_fields,
            "last_run_at": started_at.isoformat(),
        }
        await store.add_event(
            category="scan",
            level="info",
            action="scan_skipped",
            message="所有站点正在扫描中",
            detail={"skipped_in_flight": skipped_in_flight, "site_count": len(sites)},
        )
        return ScanRunResult(status=status, clear_hint=False)

    manual_count = sum(1 for s in sites if getattr(s, "id", None) is None)
    tasks: list[asyncio.Task[Any]] = []
    task_errors_count = 0
    async with new_http_client(prepared.scan_timeout, prepared.scan_trust_env) as client:
        for site in to_scan:
            dom = normalize_domain(site.domain)
            if not dom:
                continue
            if dom in in_flight:
                skipped_in_flight += 1
                continue

            async def _runner(site=site, dom=dom):
                try:
                    await check_one(
                        client,
                        site,
                        started_at,
                        cookie_mgr,
                        scan_user_agent,
                        retry_delay_seconds=request_retry_delay_seconds,
                    )
                except asyncio.CancelledError:
                    raise
                except Exception as e:
                    nonlocal task_errors_count
                    task_errors_count += 1
                    err_detail = format_error_detail(e)
                    logger.warning("scan task failed: %s (%s)", dom, err_detail)
                    try:
                        await store.add_event(
                            category="scan",
                            level="error",
                            action="scan_task_error",
                            message="扫描任务异常",
                            domain=dom,
                            detail={"error": err_detail, "type": type(e).__name__},
                        )
                    except Exception:
                        logger.exception("failed to record scan_task_error event")
                finally:
                    if in_flight.get(dom) is asyncio.current_task():
                        in_flight.pop(dom, None)

            task = asyncio.create_task(_runner(), name=f"scan_{dom}")
            in_flight[dom] = task
            tasks.append(task)

        if not tasks:
            return ScanRunResult(
                status={
                    "ok": True,
                    "site_count": len(sites),
                    "scanned_count": 0,
                    "skipped_in_flight": skipped_in_flight,
                    "error": "",
                    "warning": "all_sites_scanning",
                    **mp_fields,
                    "last_run_at": started_at.isoformat(),
                },
                clear_hint=False,
            )

        logger.info(
            "scan start: %d sites (moviepilot=%d manual=%d skipped_in_flight=%d)",
            len(tasks),
            len(sites) - manual_count,
            manual_count,
            skipped_in_flight,
        )
        await store.add_event(
            category="scan",
            level="info",
            action="scan_start",
            message="开始扫描",
            detail={
                "site_count": len(sites),
                "scanned_count": len(tasks),
                "manual_count": manual_count,
                "skipped_in_flight": skipped_in_flight,
                "moviepilot_source": mp_fields["moviepilot_source"],
            },
        )

        await asyncio.gather(*tasks)
        if task_errors_count:
            logger.warning("scan completed with %d task errors", task_errors_count)

    logger.info("scan done")

    warning = _moviepilot_warning(mp_configured=mp_configured, mp_fields=mp_fields)
    if task_errors_count:
        suffix = f"task_errors={task_errors_count}"
        warning = f"{warning}; {suffix}" if warning else suffix

    status = {
        "ok": True,
        "site_count": len(sites),
        "scanned_count": len(tasks),
        "skipped_in_flight": skipped_in_flight,
        "task_errors_count": task_errors_count,
        "error": "",
        "warning": warning,
        **mp_fields,
        "last_run_at": datetime.now(timezone.utc).isoformat(),
    }
    await store.set_json(SCAN_STATUS_KEY, status)
    await store.add_event(
        category="scan",
        level="info",
        action="scan_done",
        message="扫描完成",
        detail={
            "site_count": len(sites),
            "scanned_count": len(tasks),
            "skipped_in_flight": skipped_in_flight,
            "task_errors_count": task_errors_count,
            "warning": warning,
        },
    )
    return ScanRunResult(status=status, clear_hint=True)


__all__ = ["PreparedRun", "ScanRunResult", "run_once_locked"]
