from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Optional

from pt_invite_watcher.kv_keys import SITE_LIST_SUMMARY_KEY
from pt_invite_watcher.models import Site
from pt_invite_watcher.providers.deps_status import (
    DEFAULT_RETRY_INTERVAL_SECONDS,
    DEPS_STATUS_KEY,
    best_effort_persist_deps_status,
    can_attempt,
    fingerprint_moviepilot,
    get_dep_status,
    load_deps_status,
    update_dep_fail,
    update_dep_ok,
)
from pt_invite_watcher.providers.moviepilot_api import MoviePilotClient
from pt_invite_watcher.providers.moviepilot_sites_cache import MP_SITES_CACHE_KEY, build_cache, cache_expired, parse_cache
from pt_invite_watcher.storage.sqlite import SqliteStore
from pt_invite_watcher.utils.parse import format_error_detail, normalize_domain, safe_dict, safe_str


logger = logging.getLogger("pt_invite_watcher.moviepilot.sites")


@dataclass(frozen=True)
class MoviePilotSitesResult:
    sites: list[Site]
    configured: bool
    attempted: bool
    ok: bool
    error: str
    source: str  # live|cache|state|summary|none
    cache_fetched_at: str
    cache_age_seconds: Optional[int]
    cache_expired: Optional[bool]
    deps_status: dict[str, Any]


class MoviePilotSitesService:
    def __init__(self, store: SqliteStore):
        self._store = store

    async def load_sites(
        self,
        *,
        now: datetime,
        base_url: str,
        cache_ttl_seconds: int,
        username: str = "",
        password: str = "",
        otp_password: Optional[str] = None,
        timeout_seconds: int = 15,
        request_retry_delay_seconds: int = 30,
        deps_retry_interval_seconds: int = DEFAULT_RETRY_INTERVAL_SECONDS,
        deps_status: Optional[dict[str, Any]] = None,
        allow_live: bool = True,
        throttle_live_seconds: int = 0,
        prefer_cache_if_fresh: bool = False,
        force_live: bool = False,
        require_credentials: bool = True,
    ) -> MoviePilotSitesResult:
        """
        Load MoviePilot site list.

        The default behavior matches scan/config endpoints:
        - When credentials are configured, it may fetch from MoviePilot (with deps_status gating).
        - On failure it falls back to KV cache (moviepilot_sites_cache) or local state snapshot (site_state).

        When `require_credentials=False`, cache/state fallback works even if credentials are missing.
        This is used by site-config APIs to sync site summary without requiring a live MoviePilot call.
        """

        mp_sites: list[Site] = []
        mp_error = ""
        mp_ok = False
        mp_source = "none"
        mp_cache_fetched_at = ""
        mp_cache_age_seconds: Optional[int] = None
        mp_cache_expired: Optional[bool] = None

        has_creds = bool(base_url and username and password)
        mp_configured = has_creds
        mp_attempted = False
        allow_fallback = (not require_credentials) or has_creds

        cache = None
        cache_loaded = False
        should_try_read_cache_early = (
            bool(allow_live)
            and has_creds
            and (int(throttle_live_seconds or 0) > 0 or bool(prefer_cache_if_fresh))
            and (not bool(force_live))
        )
        if should_try_read_cache_early:
            try:
                cache = parse_cache(await self._store.get_json(MP_SITES_CACHE_KEY, default=None))
            except Exception:
                logger.exception("failed to load MoviePilot sites cache")
                cache = None
            cache_loaded = True

        if deps_status is None:
            deps_status = load_deps_status(await self._store.get_json(DEPS_STATUS_KEY, default=None))
        else:
            deps_status = load_deps_status(deps_status)

        allow_live_final = bool(allow_live)
        if allow_live_final and has_creds and (not bool(force_live)):
            cooldown_seconds = max(0, int(throttle_live_seconds or 0))
            if cooldown_seconds > 0 and cache and cache.base_url and base_url and cache.base_url.rstrip("/") == base_url.rstrip("/"):
                if cache.age_seconds(now) < cooldown_seconds:
                    allow_live_final = False

            if allow_live_final and bool(prefer_cache_if_fresh):
                if cache and cache.base_url and base_url and cache.base_url.rstrip("/") == base_url.rstrip("/"):
                    ttl = int(cache_ttl_seconds or 0)
                    if ttl > 0 and not cache_expired(cache, now, ttl, base_url=base_url):
                        allow_live_final = False

        if allow_live_final and has_creds:
            mp_fp = fingerprint_moviepilot(base_url)
            mp_dep = get_dep_status(deps_status, "moviepilot")
            if not can_attempt(mp_dep, now, mp_fp):
                mp_error = mp_dep.error
            else:
                mp_client = MoviePilotClient(
                    base_url=base_url,
                    username=username,
                    password=password,
                    otp_password=otp_password or None,
                    timeout_seconds=timeout_seconds,
                    retry_delay_seconds=request_retry_delay_seconds,
                )
                try:
                    mp_attempted = True
                    mp_sites = await mp_client.list_sites(only_active=True)
                    mp_ok = True
                    mp_source = "live"
                    mp_cache_fetched_at = now.isoformat()
                    mp_cache_age_seconds = 0
                    mp_cache_expired = False
                    try:
                        await self._store.set_json(MP_SITES_CACHE_KEY, build_cache(base_url, mp_sites, fetched_at=now))
                    except Exception:
                        logger.exception("failed to persist MoviePilot sites cache")

                    deps_status = update_dep_ok(deps_status, "moviepilot", now, mp_fp)
                    await best_effort_persist_deps_status(self._store, deps_status, reason="moviepilot_sites_ok")
                except Exception as e:
                    logger.exception("failed to load sites from MoviePilot")
                    mp_error = format_error_detail(e)
                    deps_status = update_dep_fail(
                        deps_status,
                        "moviepilot",
                        now,
                        mp_fp,
                        mp_error,
                        retry_interval_seconds=deps_retry_interval_seconds,
                    )
                    await best_effort_persist_deps_status(self._store, deps_status, reason="moviepilot_sites_fail")

        if allow_fallback and not mp_sites:
            try:
                if not cache_loaded:
                    cache = parse_cache(await self._store.get_json(MP_SITES_CACHE_KEY, default=None))
                    cache_loaded = True
                if cache:
                    mp_cache_fetched_at = cache.fetched_at_iso
                    mp_cache_age_seconds = cache.age_seconds(now)
                    mp_cache_expired = cache_expired(cache, now, cache_ttl_seconds, base_url=base_url)
                    if not mp_cache_expired:
                        mp_sites = cache.sites
                        mp_source = "cache"
            except Exception:
                logger.exception("failed to load MoviePilot sites cache")

            if not mp_sites:
                try:
                    snap_at, snap_sites = await self._store.load_sites_snapshot()
                    if snap_sites and snap_at:
                        age = int(max(0, (now - snap_at).total_seconds()))
                        mp_cache_fetched_at = snap_at.isoformat()
                        mp_cache_age_seconds = age
                        if age <= int(cache_ttl_seconds or 0):
                            mp_cache_expired = False
                            mp_sites = snap_sites
                            mp_source = "state"
                            try:
                                await self._store.set_json(MP_SITES_CACHE_KEY, build_cache(base_url, mp_sites, fetched_at=snap_at))
                            except Exception:
                                logger.exception("failed to persist MoviePilot sites cache (seeded)")
                        else:
                            mp_cache_expired = True
                except Exception:
                    logger.exception("failed to load sites snapshot from local state")

            if not mp_sites:
                try:
                    summary = safe_dict(await self._store.get_json(SITE_LIST_SUMMARY_KEY, default=None))
                    items = safe_dict(summary.get("items"))
                    for raw_domain, item_any in items.items():
                        item = safe_dict(item_any)
                        if safe_str(item.get("source")).lower() != "moviepilot":
                            continue
                        url = safe_str(item.get("url"))
                        if not url:
                            continue
                        dom = normalize_domain(str(raw_domain)) or normalize_domain(safe_str(item.get("domain")))
                        if not dom:
                            continue
                        mp_sites.append(
                            Site(
                                id=0,
                                name=safe_str(item.get("name")) or dom,
                                domain=dom,
                                url=url,
                                ua=None,
                                cookie=None,
                                cookie_override=None,
                                authorization=None,
                                did=None,
                                is_active=True,
                                template=safe_str(item.get("template")) or None,
                                registration_path=safe_str(item.get("registration_path")) or None,
                                invite_path=safe_str(item.get("invite_path")) or None,
                            )
                        )
                    if mp_sites:
                        mp_source = "summary"
                        fetched_at = safe_str(summary.get("updated_at"))
                        if fetched_at:
                            mp_cache_fetched_at = fetched_at
                            try:
                                snap_at = datetime.fromisoformat(fetched_at)
                                mp_cache_age_seconds = int(max(0, (now - snap_at).total_seconds()))
                                if cache_ttl_seconds:
                                    mp_cache_expired = mp_cache_age_seconds > int(cache_ttl_seconds or 0)
                            except Exception:
                                pass
                except Exception:
                    logger.exception("failed to load MoviePilot sites from summary")

        return MoviePilotSitesResult(
            sites=mp_sites,
            configured=mp_configured,
            attempted=mp_attempted,
            ok=mp_ok,
            error=mp_error,
            source=mp_source,
            cache_fetched_at=mp_cache_fetched_at,
            cache_age_seconds=mp_cache_age_seconds,
            cache_expired=mp_cache_expired,
            deps_status=deps_status,
        )
