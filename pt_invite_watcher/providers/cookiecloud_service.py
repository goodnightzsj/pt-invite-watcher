from __future__ import annotations

import asyncio
import logging
from contextlib import suppress
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Optional

from pt_invite_watcher.config import Settings
from pt_invite_watcher.providers.cookiecloud import CookieCloudClient, CookieManager
from pt_invite_watcher.providers.deps_status import (
    best_effort_persist_deps_status,
    can_attempt,
    fingerprint_cookiecloud,
    get_dep_status,
    load_deps_status,
    update_dep_fail,
    update_dep_ok,
)
from pt_invite_watcher.runtime_config_cache import RuntimeConfigCache
from pt_invite_watcher.runtime_config_loader import get_runtime_config
from pt_invite_watcher.utils.parse import format_error_detail


logger = logging.getLogger("pt_invite_watcher.cookiecloud_service")


@dataclass(frozen=True)
class CookieCloudAccessResult:
    attempted: bool
    ok: Optional[bool]
    error: str
    client: Optional[CookieCloudClient]
    cookies: Optional[list[dict[str, Any]]]
    prefetched_at: Optional[datetime]
    deps_status: dict[str, Any]


class CookieCloudService:
    """
    CookieCloud access helper.

    Goal:
    - Centralize deps_status gating for CookieCloud.
    - Share in-process cookie prefetch cache across probe + scan within one process.
    - Keep behavior compatible with existing scan/probe semantics.
    """

    def __init__(self, settings: Settings, store: Any, *, runtime_config: RuntimeConfigCache | None = None):
        self._settings = settings
        self._store = store
        self._runtime_config = runtime_config

        self._lock = asyncio.Lock()
        self._fetch_task: Optional[asyncio.Task[list[dict[str, Any]]]] = None
        self._fetch_fp = ""

        self._cache_fp = ""
        self._cache_at: Optional[datetime] = None
        self._cache: Optional[list[dict[str, Any]]] = None

    async def close(self) -> None:
        task: Optional[asyncio.Task[list[dict[str, Any]]]] = None
        async with self._lock:
            task = self._fetch_task
            self._fetch_task = None
            self._fetch_fp = ""
        if task is None:
            return
        if not task.done():
            task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            if task.cancelled():
                return
            raise
        except Exception:
            logger.exception("cookiecloud fetch task failed on close")

    async def _load_runtime_config(self) -> Any:
        return await get_runtime_config(self._settings, self._store, runtime_config=self._runtime_config)

    async def _snapshot_cache(
        self,
        *,
        now: datetime,
        fp: str,
        refresh_interval_seconds: int,
    ) -> tuple[Optional[list[dict[str, Any]]], Optional[datetime], Optional[list[dict[str, Any]]], Optional[datetime]]:
        async with self._lock:
            if self._cache is None or self._cache_at is None or self._cache_fp != fp:
                return None, None, None, None

            age = (now - self._cache_at).total_seconds()
            if age < max(0, int(refresh_interval_seconds or 0)):
                return self._cache, self._cache_at, None, None
            return None, None, self._cache, self._cache_at

    async def _fetch_cookie_items_single_flight(
        self,
        client: CookieCloudClient,
        *,
        fp: str,
    ) -> tuple[list[dict[str, Any]], datetime]:
        async def _finalize_fetch_task(task: asyncio.Task[list[dict[str, Any]]]) -> None:
            try:
                async with self._lock:
                    if self._fetch_task is not task:
                        return
                    self._fetch_task = None
                    self._fetch_fp = ""
                    if task.cancelled():
                        return
                    try:
                        cookies = task.result()
                    except Exception:
                        return
                    fetched_at = datetime.now(timezone.utc)
                    self._cache_fp = fp
                    self._cache_at = fetched_at
                    self._cache = cookies
            except Exception:
                return

        async with self._lock:
            if self._fetch_task is None or self._fetch_fp != fp:
                self._fetch_fp = fp
                task = asyncio.create_task(
                    client.fetch_cookie_items(),
                    name="cookiecloud_fetch_cookie_items",
                )
                def _on_fetch_done(t: asyncio.Task[list[dict[str, Any]]]) -> None:
                    try:
                        t.exception()
                    except asyncio.CancelledError:
                        pass
                    try:
                        asyncio.create_task(_finalize_fetch_task(t), name="cookiecloud_finalize_fetch")
                    except RuntimeError:
                        # Event loop is closing; nothing meaningful to do.
                        return

                task.add_done_callback(_on_fetch_done)
                self._fetch_task = task
            task = self._fetch_task

        try:
            cookies = await asyncio.shield(task)
            fetched_at = datetime.now(timezone.utc)
        except asyncio.CancelledError:
            # Don't let a cancelled waiter kill the shared in-flight fetch.
            # If the shared task itself was cancelled, clear it so future calls can retry.
            if task.cancelled():
                async with self._lock:
                    if self._fetch_task is task:
                        self._fetch_task = None
                        self._fetch_fp = ""
            raise
        except Exception:
            async with self._lock:
                if self._fetch_task is task:
                    self._fetch_task = None
                    self._fetch_fp = ""
            raise

        async with self._lock:
            if self._fetch_task is task:
                self._fetch_task = None
                self._fetch_fp = ""
                self._cache_fp = fp
                self._cache_at = fetched_at
                self._cache = cookies
            else:
                # Another coroutine already finalized the fetch; still ensure cache is consistent.
                self._cache_fp = fp
                self._cache_at = fetched_at
                self._cache = cookies

        return cookies, fetched_at

    async def access(
        self,
        *,
        now: datetime,
        deps_status: dict[str, Any] | None,
        require_enabled: bool,
        force_fetch: bool,
    ) -> CookieCloudAccessResult:
        """
        Access CookieCloud with deps_status gating and in-process caching.

        - require_enabled=True: only access when cookie_source is auto/cookiecloud.
        - force_fetch=True: always attempt a network call when allowed (even if cache is fresh),
          and keep cached cookies as fallback if the network call fails.
        """
        rc = await self._load_runtime_config()

        cookie_source = str(getattr(rc.cookie, "source", "") or "auto").strip().lower() or "auto"
        enabled = cookie_source in {"auto", "cookiecloud"}

        cc_base_url = rc.cookie.cookiecloud.base_url
        cc_uuid = rc.cookie.cookiecloud.uuid
        cc_password = rc.cookie.cookiecloud.password
        cc_refresh = int(rc.cookie.cookiecloud.refresh_interval_seconds or 300)

        deps_retry_interval = int(rc.connectivity.retry_interval_seconds or 3600)
        request_retry_delay_seconds = int(rc.connectivity.request_retry_delay_seconds or 30)
        scan_timeout = int(rc.scan.timeout_seconds or 15)

        has_creds = bool(cc_base_url and cc_uuid and cc_password)
        if not has_creds or (require_enabled and not enabled):
            return CookieCloudAccessResult(
                attempted=False,
                ok=None,
                error="",
                client=None,
                cookies=None,
                prefetched_at=None,
                deps_status=load_deps_status(deps_status),
            )

        deps_status_obj = load_deps_status(deps_status)
        fp = fingerprint_cookiecloud(cc_base_url, cc_uuid)
        dep = get_dep_status(deps_status_obj, "cookiecloud")
        allowed = can_attempt(dep, now, fp)

        cached, cached_at, fallback, fallback_at = await self._snapshot_cache(
            now=now,
            fp=fp,
            refresh_interval_seconds=cc_refresh,
        )

        if not allowed:
            # Respect deps_status backoff; still allow using cached cookies (no network).
            return CookieCloudAccessResult(
                attempted=False,
                ok=bool(dep.ok),
                error=str(dep.error or ""),
                client=None,
                cookies=cached,
                prefetched_at=cached_at,
                deps_status=deps_status_obj,
            )

        client = CookieCloudClient(
            base_url=cc_base_url,
            uuid=cc_uuid,
            password=cc_password,
            timeout_seconds=scan_timeout,
            retry_delay_seconds=request_retry_delay_seconds,
        )

        should_fetch = bool(force_fetch or cached is None)
        attempted = bool(should_fetch)
        cookies = cached
        prefetched_at = cached_at
        ok: Optional[bool] = None
        error = ""

        try:
            if should_fetch:
                cookies, prefetched_at = await self._fetch_cookie_items_single_flight(client, fp=fp)
            ok = True
            deps_status_obj = update_dep_ok(deps_status_obj, "cookiecloud", now, fp)
        except asyncio.CancelledError:
            raise
        except Exception as e:
            ok = False
            error = format_error_detail(e)
            deps_status_obj = update_dep_fail(
                deps_status_obj,
                "cookiecloud",
                now,
                fp,
                error,
                retry_interval_seconds=deps_retry_interval,
            )
            client = None
            if cookies is None and fallback is not None:
                cookies = fallback
                prefetched_at = fallback_at

        await best_effort_persist_deps_status(self._store, deps_status_obj, reason="cookiecloud")

        return CookieCloudAccessResult(
            attempted=attempted,
            ok=ok,
            error=error,
            client=client,
            cookies=cookies,
            prefetched_at=prefetched_at,
            deps_status=deps_status_obj,
        )

    async def build_cookie_manager_for_scan(
        self,
        *,
        now: datetime,
        deps_status: dict[str, Any] | None,
    ) -> tuple[CookieManager, dict[str, Any]]:
        """
        Build a CookieManager suitable for scanning, using cached cookies when available.
        """
        rc = await self._load_runtime_config()
        res = await self.access(now=now, deps_status=deps_status, require_enabled=True, force_fetch=False)
        mgr = CookieManager(
            cookie_source=rc.cookie.source,
            cookiecloud=res.client,
            refresh_interval_seconds=int(rc.cookie.cookiecloud.refresh_interval_seconds or 300),
            prefetched_cookies=res.cookies,
            prefetched_at=res.prefetched_at,
        )
        return mgr, res.deps_status


__all__ = ["CookieCloudAccessResult", "CookieCloudService"]
