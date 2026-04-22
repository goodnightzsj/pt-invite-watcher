from __future__ import annotations

# NOTE: This module contains the concrete Scanner implementation.
# Keep `pt_invite_watcher/scanner.py` as a small compatibility wrapper.

import asyncio
import logging
import os
import socket
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Any, Callable, Dict, Optional

import httpx

from pt_invite_watcher.config import Settings
from pt_invite_watcher.engines.mteam import MTeamDetector
from pt_invite_watcher.engines.nexusphp import NexusPhpDetector
from pt_invite_watcher.kv_keys import SCAN_HINT_KEY, SCAN_STATUS_KEY
from pt_invite_watcher.lease_policy import scan_lease_ttl_seconds
from pt_invite_watcher.models import AspectResult, Evidence, ReachabilityResult, Site, SiteCheckResult
from pt_invite_watcher.notify.manager import NotifierManager
from pt_invite_watcher.providers.cookiecloud import CookieManager
from pt_invite_watcher.providers.cookiecloud_service import CookieCloudService
from pt_invite_watcher.providers.deps_probe import probe_dependencies as _probe_dependencies
from pt_invite_watcher.providers.deps_service import DepsService
from pt_invite_watcher.effective_sites import EffectiveSitesService
from pt_invite_watcher.scan_context_builder import PreparedScanContext, ScanContextBuilder
from pt_invite_watcher.storage.sqlite import SqliteStore
from pt_invite_watcher.runtime_config_cache import RuntimeConfigCache
from pt_invite_watcher.scanner_diff import diff as _diff
from pt_invite_watcher.scanner_invites import check_invites_for_site as _check_invites_for_site
from pt_invite_watcher.scanner_lease import ScanLeaseManager, compute_policy as _compute_scan_lease_policy
from pt_invite_watcher.scanner_moviepilot import moviepilot_warning as _moviepilot_warning
from pt_invite_watcher.scanner_run import PreparedRun, run_once_locked as _run_once_locked_impl
from pt_invite_watcher.scanner_persist import persist_and_notify as _persist_and_notify_impl
from pt_invite_watcher.scanner_reachability import probe_reachability as _probe_reachability
from pt_invite_watcher.scanner_results import build_unreachable_result as _build_unreachable_result
from pt_invite_watcher.scanner_site_check import check_one_site as _check_one_site
from pt_invite_watcher.site_list_sync import sync_site_list_summary
from pt_invite_watcher.utils.asyncio_tasks import create_task_logged
from pt_invite_watcher.utils.parse import format_error_detail as _format_error_detail_util
from pt_invite_watcher.utils.parse import normalize_domain as _normalize_domain_util


logger = logging.getLogger("pt_invite_watcher.scanner")

_MAX_ERROR_DETAIL_LEN = 240


class AlreadyScanningError(RuntimeError):
    def __init__(self, domain: str):
        super().__init__(f"already scanning: {domain}")
        self.domain = domain


def _format_error_detail(exc: Exception) -> str:
    return _format_error_detail_util(exc, max_len=_MAX_ERROR_DETAIL_LEN)


def _normalize_domain(domain: str) -> str:
    return _normalize_domain_util(domain)


class Scanner:
    def __init__(
        self,
        settings: Settings,
        store: SqliteStore,
        notifier: NotifierManager,
        *,
        runtime_config: RuntimeConfigCache | None = None,
        effective_sites: EffectiveSitesService | None = None,
        deps: DepsService | None = None,
        cookiecloud: CookieCloudService | None = None,
    ):
        self._settings = settings
        self._store = store
        self._notifier = notifier
        self._runtime_config = runtime_config
        self._deps_service = deps

        self._deps_lock = asyncio.Lock()
        self._run_lock = asyncio.Lock()
        self._owner = f"{socket.gethostname()}:{os.getpid()}"
        self._lease = ScanLeaseManager(store, owner=self._owner)
        self._sem = asyncio.Semaphore(max(1, settings.scan.concurrency))
        self._detector = NexusPhpDetector()
        self._mteam = MTeamDetector()
        self._in_flight: dict[str, asyncio.Task[Any]] = {}
        # Optional callback for streaming "scanned N/M" progress to WebSocket clients.
        # Injected by the app layer so the scanner doesn't depend on routes/websocket modules.
        self._progress_broadcast: Optional[Callable[[dict], None]] = None
        self._ctx_builder = ScanContextBuilder(
            settings,
            store,
            runtime_config=runtime_config,
            effective_sites=effective_sites,
            cookiecloud=cookiecloud,
        )

    def in_flight_domains(self) -> set[str]:
        return set(self._in_flight.keys())

    def set_progress_broadcast(self, broadcast: Optional[Callable[[dict], None]]) -> None:
        """Install a callback invoked as sites finish scanning.

        Payload shape: ``{total, scanned, in_flight, domain, phase}``. Errors inside the callback
        are swallowed — progress is best-effort and must not break a scan.
        """
        self._progress_broadcast = broadcast

    async def probe_dependencies(self) -> Dict[str, Any]:
        async with self._deps_lock:
            if self._deps_service is not None:
                return await self._deps_service.probe()
            return await _probe_dependencies(self._store, self._settings, runtime_config=self._runtime_config)

    async def _prepare_scan_context(
        self,
        started_at: datetime,
        *,
        prefer_moviepilot_cache_if_fresh: bool,
    ) -> PreparedScanContext:
        ctx = await self._ctx_builder.prepare(started_at, prefer_moviepilot_cache_if_fresh=prefer_moviepilot_cache_if_fresh)
        if ctx.scan_concurrency > 0 and not self._in_flight:
            self._sem = asyncio.Semaphore(max(1, ctx.scan_concurrency))
        return ctx

    def _base_scan_lease_ttl_seconds(self) -> int:
        return scan_lease_ttl_seconds(timeout_seconds=int(self._settings.scan.timeout_seconds or 20))

    async def _prepare_run(
        self,
        started_at: datetime,
        *,
        base_ttl_seconds: int,
        ctx_reason: str = "scan_context",
        prefer_moviepilot_cache_if_fresh: bool = False,
    ) -> PreparedRun:
        async with self._deps_lock:
            scan_ctx = await self._prepare_scan_context(
                started_at,
                prefer_moviepilot_cache_if_fresh=prefer_moviepilot_cache_if_fresh,
            )

        lease_policy = _compute_scan_lease_policy(
            base_ttl_seconds=base_ttl_seconds,
            scan_timeout_seconds=int(scan_ctx.scan_timeout_seconds or 0),
        )
        await self._lease.extend(ttl_seconds=lease_policy.ttl_seconds)

        notify_site_list = True
        if (
            scan_ctx.moviepilot_configured
            and (not scan_ctx.moviepilot_ok)
            and scan_ctx.moviepilot_source == "none"
            and scan_ctx.moviepilot_error
        ):
            notify_site_list = False
        await sync_site_list_summary(
            self._store,
            self._notifier,
            scan_ctx.sites,
            started_at,
            notify=notify_site_list,
            reason=ctx_reason,
        )

        return PreparedRun(
            sites=scan_ctx.sites,
            cookie_mgr=scan_ctx.cookie_mgr,
            mp_configured=bool(scan_ctx.moviepilot_configured),
            mp_fields=scan_ctx.moviepilot_status_fields(),
            scan_lease_ttl_seconds=int(lease_policy.ttl_seconds),
            scan_lease_refresh_interval_seconds=int(lease_policy.refresh_interval_seconds),
            scan_timeout=int(scan_ctx.scan_timeout_seconds or int(self._settings.scan.timeout_seconds)),
            scan_user_agent=(str(scan_ctx.scan_user_agent or "") or None),
            scan_trust_env=bool(scan_ctx.scan_trust_env),
            request_retry_delay_seconds=int(scan_ctx.request_retry_delay_seconds or 30),
        )

    def _new_http_client(self, *, timeout_seconds: int, trust_env: bool) -> httpx.AsyncClient:
        timeout = httpx.Timeout(timeout_seconds)
        # http2=True lets httpx multiplex concurrent requests to the same site over a single
        # TCP+TLS connection. Per-scan the scanner fires registration + invites in parallel
        # via asyncio.gather, so with h2 they share one connection instead of needing two
        # handshakes. httpx auto-falls-back to HTTP/1.1 if a site doesn't negotiate h2.
        return httpx.AsyncClient(
            timeout=timeout,
            follow_redirects=True,
            trust_env=trust_env,
            http2=True,
        )

    async def _clear_scan_hint(self) -> None:
        try:
            await self._store.set_json(SCAN_HINT_KEY, None)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("failed to clear scan hint")

    async def run_once(self) -> Dict[str, Any]:
        async with self._run_lock:
            return await self._run_once_locked(ctx_reason="scan_context", prefer_moviepilot_cache_if_fresh=False)

    async def run_once_scheduled(self) -> Dict[str, Any]:
        async with self._run_lock:
            return await self._run_once_locked(ctx_reason="scheduler_scan", prefer_moviepilot_cache_if_fresh=True)

    @asynccontextmanager
    async def _prepare_run_with_lease(
        self,
        started_at: datetime,
        *,
        ctx_reason: str = "scan_context",
        prefer_moviepilot_cache_if_fresh: bool = False,
    ) -> Any:
        lease_acquired = False
        lease_refresh_task: asyncio.Task[None] | None = None
        try:
            base_ttl = self._base_scan_lease_ttl_seconds()
            lease_acquired = await self._lease.acquire(ttl_seconds=base_ttl)
            if not lease_acquired:
                raise AlreadyScanningError("global")

            prepared = await self._prepare_run(
                started_at,
                base_ttl_seconds=base_ttl,
                ctx_reason=ctx_reason,
                prefer_moviepilot_cache_if_fresh=prefer_moviepilot_cache_if_fresh,
            )
            lease_refresh_task_name = f"scan_lease_refresh_{ctx_reason}"
            lease_refresh_task = create_task_logged(
                self._lease.refresh_loop(
                    ttl_seconds=prepared.scan_lease_ttl_seconds,
                    refresh_interval_seconds=prepared.scan_lease_refresh_interval_seconds,
                ),
                logger=logger,
                name=lease_refresh_task_name,
                label="scan lease refresh",
            )
            yield prepared
        finally:
            if lease_refresh_task is not None:
                lease_refresh_task.cancel()
                await asyncio.gather(lease_refresh_task, return_exceptions=True)
            if lease_acquired:
                await self._lease.release()

    async def _run_once_locked(
        self,
        *,
        ctx_reason: str,
        prefer_moviepilot_cache_if_fresh: bool,
    ) -> Dict[str, Any]:
        started_at = datetime.now(timezone.utc)
        async with self._prepare_run_with_lease(
            started_at,
            ctx_reason=ctx_reason,
            prefer_moviepilot_cache_if_fresh=prefer_moviepilot_cache_if_fresh,
        ) as prepared:
            result = await _run_once_locked_impl(
                store=self._store,
                prepared=prepared,
                started_at=started_at,
                in_flight=self._in_flight,
                new_http_client=lambda timeout, trust_env: self._new_http_client(timeout_seconds=timeout, trust_env=trust_env),
                check_one=self._check_one,
                format_error_detail=_format_error_detail,
                normalize_domain=_normalize_domain,
                progress_broadcast=self._progress_broadcast,
            )
            if result.clear_hint:
                await self._clear_scan_hint()
            return result.status

    async def run_one(self, domain: str) -> Dict[str, Any]:
        async with self._run_lock:
            started_at = datetime.now(timezone.utc)
            target = _normalize_domain(domain)
            if not target:
                return {"ok": False, "site_count": 0, "error": "domain is required", "last_run_at": started_at.isoformat()}
            async with self._prepare_run_with_lease(started_at) as prepared:
                if target in self._in_flight:
                    raise AlreadyScanningError(target)
                sites = prepared.sites
                cookie_mgr = prepared.cookie_mgr
                mp_configured = prepared.mp_configured
                mp_fields = prepared.mp_fields
                scan_user_agent = prepared.scan_user_agent
                request_retry_delay_seconds = prepared.request_retry_delay_seconds

                site = next((s for s in sites if _normalize_domain(s.domain) == target), None)
                if not site:
                    hint = ""
                    if mp_configured and mp_fields.get("moviepilot_source") == "none" and mp_fields.get("moviepilot_error"):
                        hint = " (MoviePilot unavailable and no local manual site)"
                    await self._store.add_event(
                        category="scan",
                        level="error",
                        action="scan_one_not_found",
                        message=f"site not found: {target}{hint}",
                        domain=target,
                    )
                    return {
                        "ok": False,
                        "site_count": 0,
                        "error": f"site not found: {target}{hint}",
                        **mp_fields,
                        "last_run_at": started_at.isoformat(),
                    }

                logger.info("single scan start: %s", target)
                await self._store.add_event(
                    category="scan",
                    level="info",
                    action="scan_one_start",
                    message="开始单独扫描",
                    domain=target,
                )
                task = asyncio.current_task()
                if task is not None:
                    self._in_flight[target] = task
                try:
                    async with self._new_http_client(timeout_seconds=prepared.scan_timeout, trust_env=prepared.scan_trust_env) as client:
                        await self._check_one(
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
                    logger.exception("single scan failed: %s", target)
                    await self._store.add_event(
                        category="scan",
                        level="error",
                        action="scan_one_failed",
                        message=_format_error_detail(e),
                        domain=target,
                    )
                    return {
                        "ok": False,
                        "site_count": 1,
                        "domain": target,
                        "error": _format_error_detail(e),
                        **mp_fields,
                        "last_run_at": datetime.now(timezone.utc).isoformat(),
                    }
                finally:
                    if task is not None and self._in_flight.get(target) is task:
                        self._in_flight.pop(target, None)

                logger.info("single scan done: %s", target)
                warning = _moviepilot_warning(mp_configured=mp_configured, mp_fields=mp_fields)
                await self._store.add_event(
                    category="scan",
                    level="info",
                    action="scan_one_done",
                    message="单独扫描完成",
                    domain=target,
                    detail={"warning": warning},
                )

                status = {
                    "ok": True,
                    "site_count": 1,
                    "domain": target,
                    "error": "",
                    "warning": warning,
                    **mp_fields,
                    "last_run_at": datetime.now(timezone.utc).isoformat(),
                }
                await self._clear_scan_hint()
                return status

    async def _log_step(
        self,
        site: Site,
        page_kind: str,
        action: str,
        message: str,
    ) -> None:
        await self._store.add_event(
            category="scan",
            level="info",
            action=action,
            message=message,
            domain=_normalize_domain(site.domain),
            detail={"page": {"kind": page_kind}, "site_name": site.name},
            max_rows=5000,
        )

    async def _check_one(
        self,
        client: httpx.AsyncClient,
        site,
        now: datetime,
        cookie_mgr: CookieManager,
        default_user_agent: Optional[str],
        *,
        retry_delay_seconds: int,
    ) -> None:
        async with self._sem:
            await _check_one_site(
                client=client,
                site=site,
                now=now,
                cookie_mgr=cookie_mgr,
                default_user_agent=default_user_agent,
                detector=self._detector,
                mteam_detector=self._mteam,
                store=self._store,
                log_step=self._log_step,
                persist_and_notify=self._persist_and_notify,
                format_error_detail=_format_error_detail,
                normalize_domain=_normalize_domain,
                retry_delay_seconds=retry_delay_seconds,
            )

    async def _persist_and_notify(self, site, result: SiteCheckResult, now: datetime) -> None:
        await _persist_and_notify_impl(
            store=self._store,
            notifier=self._notifier,
            site=site,
            result=result,
            now=now,
        )

    @staticmethod
    def _diff(prev, cur: SiteCheckResult) -> list[str]:
        return _diff(prev, cur)
