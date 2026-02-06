from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Optional

from pt_invite_watcher.config import Settings
from pt_invite_watcher.effective_sites import EffectiveSitesService
from pt_invite_watcher.models import Site
from pt_invite_watcher.providers.cookiecloud import CookieManager
from pt_invite_watcher.providers.cookiecloud_service import CookieCloudService
from pt_invite_watcher.providers.deps_status import DEPS_STATUS_KEY, load_deps_status
from pt_invite_watcher.runtime_config_loader import get_runtime_config
from pt_invite_watcher.runtime_config_cache import RuntimeConfigCache
from pt_invite_watcher.storage.sqlite import SqliteStore


logger = logging.getLogger("pt_invite_watcher.scan_context")


@dataclass(frozen=True)
class PreparedScanContext:
    sites: list[Site]
    cookie_mgr: CookieManager

    scan_timeout_seconds: int
    scan_concurrency: int
    scan_user_agent: str
    scan_trust_env: bool
    request_retry_delay_seconds: int

    moviepilot_configured: bool
    moviepilot_attempted: bool
    moviepilot_ok: bool
    moviepilot_error: str
    moviepilot_source: str
    moviepilot_cache_fetched_at: str
    moviepilot_cache_age_seconds: Optional[int]
    moviepilot_cache_expired: Optional[bool]

    def moviepilot_status_fields(self) -> dict[str, Any]:
        return {
            "moviepilot_ok": bool(self.moviepilot_ok),
            "moviepilot_error": str(self.moviepilot_error or ""),
            "moviepilot_source": str(self.moviepilot_source or "none"),
            "moviepilot_cache_fetched_at": str(self.moviepilot_cache_fetched_at or ""),
            "moviepilot_cache_age_seconds": self.moviepilot_cache_age_seconds,
            "moviepilot_cache_expired": self.moviepilot_cache_expired,
        }


class ScanContextBuilder:
    def __init__(
        self,
        settings: Settings,
        store: SqliteStore,
        *,
        runtime_config: RuntimeConfigCache | None = None,
        effective_sites: EffectiveSitesService | None = None,
        cookiecloud: CookieCloudService | None = None,
    ):
        self._settings = settings
        self._store = store
        self._runtime_config = runtime_config
        self._sites = effective_sites or EffectiveSitesService(settings, store, runtime_config=runtime_config)
        self._cookiecloud = cookiecloud

    async def prepare(
        self,
        started_at: datetime,
        *,
        prefer_moviepilot_cache_if_fresh: bool = False,
    ) -> PreparedScanContext:
        rc = await get_runtime_config(self._settings, self._store, runtime_config=self._runtime_config)

        request_retry_delay_seconds = rc.connectivity.request_retry_delay_seconds

        cookie_source = rc.cookie.source

        scan_timeout = rc.scan.timeout_seconds
        scan_concurrency = rc.scan.concurrency
        scan_user_agent = rc.scan.user_agent or ""
        scan_trust_env = bool(rc.scan.trust_env)

        deps_status = load_deps_status(await self._store.get_json(DEPS_STATUS_KEY, default=None))
        eff = await self._sites.load_for_scan(
            now=started_at,
            deps_status=deps_status,
            prefer_moviepilot_cache_if_fresh=bool(prefer_moviepilot_cache_if_fresh),
        )
        mp_result = eff.moviepilot
        deps_status = mp_result.deps_status

        cookie_mgr: CookieManager
        if self._cookiecloud is not None:
            cookie_mgr, deps_status = await self._cookiecloud.build_cookie_manager_for_scan(now=started_at, deps_status=deps_status)
        else:
            cookie_mgr = CookieManager(cookie_source=cookie_source, cookiecloud=None, refresh_interval_seconds=300)

        sites = eff.sites
        return PreparedScanContext(
            sites=sites,
            cookie_mgr=cookie_mgr,
            scan_timeout_seconds=scan_timeout,
            scan_concurrency=scan_concurrency,
            scan_user_agent=scan_user_agent,
            scan_trust_env=scan_trust_env,
            request_retry_delay_seconds=request_retry_delay_seconds,
            moviepilot_configured=bool(mp_result.configured),
            moviepilot_attempted=mp_result.attempted,
            moviepilot_ok=mp_result.ok,
            moviepilot_error=mp_result.error,
            moviepilot_source=mp_result.source,
            moviepilot_cache_fetched_at=mp_result.cache_fetched_at,
            moviepilot_cache_age_seconds=mp_result.cache_age_seconds,
            moviepilot_cache_expired=mp_result.cache_expired,
        )
