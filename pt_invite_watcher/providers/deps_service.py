from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from typing import Any, Optional

from pt_invite_watcher.config import Settings
from pt_invite_watcher.providers.cookiecloud_service import CookieCloudService
from pt_invite_watcher.providers.deps_status import (
    DEPS_STATUS_KEY,
    best_effort_persist_deps_status,
    can_attempt,
    fingerprint_moviepilot,
    get_dep_status,
    load_deps_status,
    update_dep_fail,
)
from pt_invite_watcher.providers.moviepilot_sites import MoviePilotSitesService
from pt_invite_watcher.runtime_config_cache import RuntimeConfigCache
from pt_invite_watcher.runtime_config_loader import get_runtime_config
from pt_invite_watcher.utils.parse import format_error_detail


logger = logging.getLogger("pt_invite_watcher.deps_service")


class DepsService:
    """
    Dependency probe shared by scheduler startup and scan pipeline.

    Goal:
    - Use the same deps_status gating and cache update behaviors as scanning.
    - Keep the returned payload backward-compatible for existing logs/tests.
    """

    def __init__(
        self,
        settings: Settings,
        store: Any,
        *,
        runtime_config: RuntimeConfigCache | None = None,
        cookiecloud: CookieCloudService | None = None,
    ):
        self._settings = settings
        self._store = store
        self._runtime_config = runtime_config
        self._cookiecloud = cookiecloud or CookieCloudService(settings, store, runtime_config=runtime_config)

    async def probe(self, *, now: Optional[datetime] = None) -> dict[str, Any]:
        checked_at = now or datetime.now(timezone.utc)
        rc = await get_runtime_config(self._settings, self._store, runtime_config=self._runtime_config)

        mp_base_url = rc.moviepilot.base_url
        mp_username = rc.moviepilot.username
        mp_password = rc.moviepilot.password
        mp_otp_password = rc.moviepilot.otp_password
        mp_sites_cache_ttl = rc.moviepilot.sites_cache_ttl_seconds

        deps_retry_interval = rc.connectivity.retry_interval_seconds
        request_retry_delay_seconds = rc.connectivity.request_retry_delay_seconds
        scan_timeout = rc.scan.timeout_seconds

        cc_base_url = rc.cookie.cookiecloud.base_url
        cc_uuid = rc.cookie.cookiecloud.uuid
        cc_password = rc.cookie.cookiecloud.password

        deps_status_raw = await self._store.get_json(DEPS_STATUS_KEY, default=None)
        deps_status = load_deps_status(deps_status_raw)
        deps_status_dirty = False
        deps_status_persisted = False

        mp_attempted = False
        mp_ok: Optional[bool] = None
        mp_error = ""
        if mp_base_url and mp_username and mp_password:
            mp_fp = fingerprint_moviepilot(mp_base_url)
            mp_dep = get_dep_status(deps_status, "moviepilot")
            if can_attempt(mp_dep, checked_at, mp_fp):
                mp_attempted = True
                try:
                    svc = MoviePilotSitesService(self._store)
                    res = await svc.load_sites(
                        now=checked_at,
                        base_url=mp_base_url,
                        cache_ttl_seconds=mp_sites_cache_ttl,
                        username=mp_username,
                        password=mp_password,
                        otp_password=mp_otp_password or None,
                        timeout_seconds=scan_timeout,
                        request_retry_delay_seconds=request_retry_delay_seconds,
                        deps_retry_interval_seconds=deps_retry_interval,
                        deps_status=deps_status,
                        allow_live=True,
                        require_credentials=True,
                    )
                    deps_status = res.deps_status
                    deps_status_persisted = deps_status_persisted or bool(res.attempted)
                    mp_ok = bool(res.ok)
                    mp_error = str(res.error or "")
                except asyncio.CancelledError:
                    raise
                except Exception as e:
                    mp_ok = False
                    mp_error = format_error_detail(e)
                    deps_status = update_dep_fail(
                        deps_status,
                        "moviepilot",
                        checked_at,
                        mp_fp,
                        mp_error,
                        retry_interval_seconds=deps_retry_interval,
                    )
                    deps_status_dirty = True
            else:
                mp_ok = bool(mp_dep.ok)
                mp_error = mp_dep.error

        cc_attempted = False
        cc_ok: Optional[bool] = None
        cc_error = ""
        if cc_base_url and cc_uuid and cc_password:
            try:
                cc_res = await self._cookiecloud.access(
                    now=checked_at,
                    deps_status=deps_status,
                    require_enabled=False,
                    force_fetch=True,
                )
                deps_status = cc_res.deps_status
                cc_attempted = bool(cc_res.attempted)
                cc_ok = cc_res.ok
                cc_error = str(cc_res.error or "")
                deps_status_persisted = True
            except asyncio.CancelledError:
                raise
            except Exception as e:
                # Extremely defensive: deps probe should never crash scheduler.
                cc_attempted = False
                cc_ok = False
                cc_error = format_error_detail(e)

        if (deps_status_raw is None or deps_status_dirty) and not deps_status_persisted:
            await best_effort_persist_deps_status(self._store, deps_status, reason="probe")

        return {
            "ok": True,
            "checked_at": checked_at.isoformat(),
            "moviepilot_attempted": mp_attempted,
            "moviepilot_ok": mp_ok,
            "moviepilot_error": mp_error,
            "cookiecloud_attempted": cc_attempted,
            "cookiecloud_ok": cc_ok,
            "cookiecloud_error": cc_error,
        }


__all__ = ["DepsService"]
