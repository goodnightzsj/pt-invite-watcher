from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from typing import Any, Dict, Optional

import httpx
import re
from urllib.parse import urljoin, urlparse

from pt_invite_watcher.config import Settings
from pt_invite_watcher.engines.mteam import MTeamDetector
from pt_invite_watcher.engines.nexusphp import NexusPhpDetector
from pt_invite_watcher.models import AspectResult, Evidence, ReachabilityResult, Site, SiteCheckResult
from pt_invite_watcher.notify.manager import NotifierManager
from pt_invite_watcher.providers.cookiecloud import CookieCloudClient, CookieManager
from pt_invite_watcher.providers.deps_status import (
    DEFAULT_RETRY_INTERVAL_SECONDS,
    DEPS_STATUS_KEY,
    MAX_RETRY_INTERVAL_SECONDS,
    MIN_RETRY_INTERVAL_SECONDS,
    can_attempt,
    fingerprint_cookiecloud,
    fingerprint_moviepilot,
    get_dep_status,
    load_deps_status,
    update_dep_fail,
    update_dep_ok,
)
from pt_invite_watcher.providers.moviepilot_api import MoviePilotClient
from pt_invite_watcher.providers.moviepilot_sites_cache import (
    MP_SITES_CACHE_DEFAULT_TTL_SECONDS,
    MP_SITES_CACHE_KEY,
    MP_SITES_CACHE_MAX_TTL_SECONDS,
    MP_SITES_CACHE_MIN_TTL_SECONDS,
    build_cache,
    cache_expired,
    parse_cache,
)
from pt_invite_watcher.storage.sqlite import SqliteStore


logger = logging.getLogger("pt_invite_watcher.scanner")

_MAX_ERROR_DETAIL_LEN = 240
_DOWN_HTTP_STATUSES = set(range(520, 530))


def _format_error_detail(exc: Exception) -> str:
    msg = str(exc or "").strip()
    if not msg:
        msg = getattr(getattr(exc, "__cause__", None), "args", None) and str(exc.__cause__).strip() or ""
    if not msg:
        msg = type(exc).__name__
    msg = re.sub(r"\s+", " ", msg)
    if len(msg) > _MAX_ERROR_DETAIL_LEN:
        msg = msg[: _MAX_ERROR_DETAIL_LEN - 1] + "…"
    return msg


def _hosts_related(host_a: str, host_b: str) -> bool:
    a = (host_a or "").lower().strip(".")
    b = (host_b or "").lower().strip(".")
    if not a or not b:
        return True
    return a == b or a.endswith("." + b) or b.endswith("." + a)


def _engine_hint_from_html(html: str) -> Optional[str]:
    h = (html or "").lower()
    if not h:
        return None
    if "nexusphp" in h:
        return "nexusphp"
    if any(token in h for token in ("torrents.php", "userdetails.php", "takesignup.php", "takeinvite.php", "login.php")):
        return "nexusphp"
    return None


def _safe_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _cfg_str(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _cfg_int(value: Any, default: int, min_value: int, max_value: int) -> int:
    if value is None or value == "":
        return default
    try:
        parsed = int(str(value).strip())
    except ValueError:
        return default
    return max(min_value, min(max_value, parsed))


def _cfg_bool(value: Any, default: bool) -> bool:
    if value is None or value == "":
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, int):
        return value != 0
    return str(value).strip().lower() in {"1", "true", "yes", "y", "on"}


def _normalize_domain(domain: str) -> str:
    return (domain or "").strip().lower()


class Scanner:
    def __init__(self, settings: Settings, store: SqliteStore, notifier: NotifierManager):
        self._settings = settings
        self._store = store
        self._notifier = notifier

        self._lock = asyncio.Lock()
        self._sem = asyncio.Semaphore(max(1, settings.scan.concurrency))
        self._detector = NexusPhpDetector()
        self._mteam = MTeamDetector()

    async def _load_app_config(self) -> dict[str, Any]:
        try:
            data = await self._store.get_json("app_config", default={})
            return _safe_dict(data)
        except Exception:
            return {}

    async def _load_sites_config(self) -> dict[str, Any]:
        try:
            data = await self._store.get_json("sites", default={"version": 1, "entries": {}})
            cfg = _safe_dict(data)
            entries = _safe_dict(cfg.get("entries"))
            return {"entries": entries}
        except Exception:
            return {"entries": {}}

    @staticmethod
    def _merge_sites(mp_sites: list[Site], site_entries: dict[str, Any]) -> list[Site]:
        entries = site_entries if isinstance(site_entries, dict) else {}

        merged: list[Site] = []
        mp_domains: set[str] = set()
        for s in mp_sites:
            domain = _normalize_domain(s.domain)
            if not domain:
                continue
            mp_domains.add(domain)

            entry = _safe_dict(entries.get(domain))
            mode = (_cfg_str(entry.get("mode")) or "override").lower()
            if mode not in {"override", "manual"}:
                entry = {}

            name = _cfg_str(entry.get("name")) or s.name
            cookie_override = _cfg_str(entry.get("cookie")) or None
            authorization = _cfg_str(entry.get("authorization")) or None
            did = _cfg_str(entry.get("did")) or None
            template = (_cfg_str(entry.get("template")) or "").lower()
            if template not in {"nexusphp", "custom", "mteam"}:
                template = ""
            reg_path = _cfg_str(entry.get("registration_path")) or None
            inv_path = _cfg_str(entry.get("invite_path")) or None
            if domain.endswith("m-team.cc"):
                template = template or "mteam"
                reg_path = reg_path or "signup"
                inv_path = inv_path or "invite"

            merged.append(
                Site(
                    id=s.id,
                    name=name,
                    domain=domain,
                    url=s.url,
                    ua=s.ua,
                    cookie=s.cookie,
                    cookie_override=cookie_override,
                    authorization=authorization,
                    did=did,
                    is_active=s.is_active,
                    template=template or None,
                    registration_path=reg_path,
                    invite_path=inv_path,
                )
            )

        # Manual sites (not in MoviePilot list)
        for raw_domain, raw in entries.items():
            domain = _normalize_domain(raw_domain)
            if not domain or domain in mp_domains:
                continue
            entry = _safe_dict(raw)
            mode = (_cfg_str(entry.get("mode")) or "manual").lower()
            if mode != "manual":
                continue
            url = _cfg_str(entry.get("url"))
            if not url:
                continue
            name = _cfg_str(entry.get("name")) or domain
            cookie_override = _cfg_str(entry.get("cookie")) or None
            authorization = _cfg_str(entry.get("authorization")) or None
            did = _cfg_str(entry.get("did")) or None
            template = (_cfg_str(entry.get("template")) or "custom").lower()
            if template not in {"nexusphp", "custom", "mteam"}:
                template = "custom"
            reg_path = _cfg_str(entry.get("registration_path")) or None
            inv_path = _cfg_str(entry.get("invite_path")) or None
            if domain.endswith("m-team.cc"):
                template = template or "mteam"
                reg_path = reg_path or "signup"
                inv_path = inv_path or "invite"

            merged.append(
                Site(
                    id=None,
                    name=name,
                    domain=domain,
                    url=url,
                    ua=None,
                    cookie=None,
                    cookie_override=cookie_override,
                    authorization=authorization,
                    did=did,
                    is_active=True,
                    template=template,
                    registration_path=reg_path,
                    invite_path=inv_path,
                )
            )

        # Deduplicate by domain (prefer later entries)
        by_domain: dict[str, Site] = {}
        for s in merged:
            dom = _normalize_domain(s.domain)
            if not dom:
                continue
            by_domain[dom] = s
        return list(by_domain.values())

    async def probe_dependencies(self) -> Dict[str, Any]:
        async with self._lock:
            now = datetime.now(timezone.utc)
            cfg = await self._load_app_config()

            mp_cfg = _safe_dict(cfg.get("moviepilot"))
            connectivity_cfg = _safe_dict(cfg.get("connectivity"))
            cookie_cfg = _safe_dict(cfg.get("cookie"))
            cc_cfg = _safe_dict(cookie_cfg.get("cookiecloud"))
            scan_cfg = _safe_dict(cfg.get("scan"))

            mp_base_url = _cfg_str(mp_cfg.get("base_url")) or self._settings.moviepilot.base_url
            mp_username = _cfg_str(mp_cfg.get("username")) or self._settings.moviepilot.username
            mp_password = _cfg_str(mp_cfg.get("password")) or self._settings.moviepilot.password
            mp_otp_password = _cfg_str(mp_cfg.get("otp_password")) or (self._settings.moviepilot.otp_password or "")
            deps_retry_interval = _cfg_int(
                connectivity_cfg.get("retry_interval_seconds"),
                default=DEFAULT_RETRY_INTERVAL_SECONDS,
                min_value=MIN_RETRY_INTERVAL_SECONDS,
                max_value=MAX_RETRY_INTERVAL_SECONDS,
            )
            scan_timeout = _cfg_int(
                scan_cfg.get("timeout_seconds"),
                default=int(self._settings.scan.timeout_seconds),
                min_value=5,
                max_value=180,
            )

            cc_base_url = _cfg_str(cc_cfg.get("base_url")) or self._settings.cookie.cookiecloud.base_url
            cc_uuid = _cfg_str(cc_cfg.get("uuid")) or self._settings.cookie.cookiecloud.uuid
            cc_password = _cfg_str(cc_cfg.get("password")) or self._settings.cookie.cookiecloud.password

            deps_status = load_deps_status(await self._store.get_json(DEPS_STATUS_KEY, default=None))

            mp_attempted = False
            mp_ok: Optional[bool] = None
            mp_error = ""
            if mp_base_url and mp_username and mp_password:
                mp_fp = fingerprint_moviepilot(mp_base_url)
                mp_dep = get_dep_status(deps_status, "moviepilot")
                if can_attempt(mp_dep, now, mp_fp):
                    mp_attempted = True
                    mp_client = MoviePilotClient(
                        base_url=mp_base_url,
                        username=mp_username,
                        password=mp_password,
                        otp_password=mp_otp_password or None,
                        timeout_seconds=scan_timeout,
                    )
                    try:
                        mp_sites = await mp_client.list_sites(only_active=True)
                        mp_ok = True
                        deps_status = update_dep_ok(deps_status, "moviepilot", now, mp_fp)
                        try:
                            await self._store.set_json(MP_SITES_CACHE_KEY, build_cache(mp_base_url, mp_sites, fetched_at=now))
                        except Exception:
                            logger.exception("failed to persist MoviePilot sites cache (probe)")
                    except Exception as e:
                        mp_ok = False
                        mp_error = _format_error_detail(e)
                        deps_status = update_dep_fail(
                            deps_status,
                            "moviepilot",
                            now,
                            mp_fp,
                            mp_error,
                            retry_interval_seconds=deps_retry_interval,
                        )
                else:
                    mp_ok = bool(mp_dep.ok)
                    mp_error = mp_dep.error

            cc_attempted = False
            cc_ok: Optional[bool] = None
            cc_error = ""
            if cc_base_url and cc_uuid and cc_password:
                cc_fp = fingerprint_cookiecloud(cc_base_url, cc_uuid)
                cc_dep = get_dep_status(deps_status, "cookiecloud")
                if can_attempt(cc_dep, now, cc_fp):
                    cc_attempted = True
                    cc_client = CookieCloudClient(
                        base_url=cc_base_url,
                        uuid=cc_uuid,
                        password=cc_password,
                        timeout_seconds=scan_timeout,
                    )
                    try:
                        await cc_client.fetch_cookie_items()
                        cc_ok = True
                        deps_status = update_dep_ok(deps_status, "cookiecloud", now, cc_fp)
                    except Exception as e:
                        cc_ok = False
                        cc_error = _format_error_detail(e)
                        deps_status = update_dep_fail(
                            deps_status,
                            "cookiecloud",
                            now,
                            cc_fp,
                            cc_error,
                            retry_interval_seconds=deps_retry_interval,
                        )
                else:
                    cc_ok = bool(cc_dep.ok)
                    cc_error = cc_dep.error

            try:
                await self._store.set_json(DEPS_STATUS_KEY, deps_status)
            except Exception:
                logger.exception("failed to persist deps status (probe)")

            status: Dict[str, Any] = {
                "ok": True,
                "checked_at": now.isoformat(),
                "moviepilot_attempted": mp_attempted,
                "moviepilot_ok": mp_ok,
                "moviepilot_error": mp_error,
                "cookiecloud_attempted": cc_attempted,
                "cookiecloud_ok": cc_ok,
                "cookiecloud_error": cc_error,
            }
            return status

    async def run_once(self) -> Dict[str, Any]:
        async with self._lock:
            started_at = datetime.now(timezone.utc)
            cfg = await self._load_app_config()
            sites_cfg = await self._load_sites_config()

            mp_cfg = _safe_dict(cfg.get("moviepilot"))
            connectivity_cfg = _safe_dict(cfg.get("connectivity"))
            cookie_cfg = _safe_dict(cfg.get("cookie"))
            cc_cfg = _safe_dict(cookie_cfg.get("cookiecloud"))
            scan_cfg = _safe_dict(cfg.get("scan"))

            mp_base_url = _cfg_str(mp_cfg.get("base_url")) or self._settings.moviepilot.base_url
            mp_username = _cfg_str(mp_cfg.get("username")) or self._settings.moviepilot.username
            mp_password = _cfg_str(mp_cfg.get("password")) or self._settings.moviepilot.password
            mp_otp_password = _cfg_str(mp_cfg.get("otp_password")) or (self._settings.moviepilot.otp_password or "")
            mp_sites_cache_ttl = _cfg_int(
                mp_cfg.get("sites_cache_ttl_seconds"),
                default=MP_SITES_CACHE_DEFAULT_TTL_SECONDS,
                min_value=MP_SITES_CACHE_MIN_TTL_SECONDS,
                max_value=MP_SITES_CACHE_MAX_TTL_SECONDS,
            )
            deps_retry_interval = _cfg_int(
                connectivity_cfg.get("retry_interval_seconds"),
                default=DEFAULT_RETRY_INTERVAL_SECONDS,
                min_value=MIN_RETRY_INTERVAL_SECONDS,
                max_value=MAX_RETRY_INTERVAL_SECONDS,
            )

            cookie_source = (_cfg_str(cookie_cfg.get("source")) or self._settings.cookie.source or "auto").strip().lower()
            cc_base_url = _cfg_str(cc_cfg.get("base_url")) or self._settings.cookie.cookiecloud.base_url
            cc_uuid = _cfg_str(cc_cfg.get("uuid")) or self._settings.cookie.cookiecloud.uuid
            cc_password = _cfg_str(cc_cfg.get("password")) or self._settings.cookie.cookiecloud.password
            cc_refresh = _cfg_int(
                cc_cfg.get("refresh_interval_seconds"),
                default=int(self._settings.cookie.cookiecloud.refresh_interval_seconds),
                min_value=30,
                max_value=24 * 3600,
            )

            scan_timeout = _cfg_int(
                scan_cfg.get("timeout_seconds"),
                default=int(self._settings.scan.timeout_seconds),
                min_value=5,
                max_value=180,
            )
            scan_concurrency = _cfg_int(
                scan_cfg.get("concurrency"),
                default=int(self._settings.scan.concurrency),
                min_value=1,
                max_value=64,
            )
            scan_user_agent = _cfg_str(scan_cfg.get("user_agent")) or self._settings.scan.user_agent or ""
            scan_trust_env = _cfg_bool(scan_cfg.get("trust_env"), default=bool(self._settings.scan.trust_env))

            self._sem = asyncio.Semaphore(max(1, scan_concurrency))

            deps_status = load_deps_status(await self._store.get_json(DEPS_STATUS_KEY, default=None))

            mp_attempted = bool(mp_base_url and mp_username and mp_password)
            mp_sites: list[Site] = []
            mp_error = ""
            mp_ok = False
            mp_source = "none"  # live|cache|none
            mp_cache_fetched_at = ""
            mp_cache_age_seconds: Optional[int] = None
            mp_cache_expired: Optional[bool] = None
            if mp_attempted:
                mp_fp = fingerprint_moviepilot(mp_base_url)
                mp_dep = get_dep_status(deps_status, "moviepilot")
                mp_allowed = can_attempt(mp_dep, started_at, mp_fp)
                if not mp_allowed:
                    mp_error = mp_dep.error
                else:
                    mp_client = MoviePilotClient(
                        base_url=mp_base_url,
                        username=mp_username,
                        password=mp_password,
                        otp_password=mp_otp_password or None,
                        timeout_seconds=scan_timeout,
                    )
                    try:
                        mp_sites = await mp_client.list_sites(only_active=True)
                        mp_ok = True
                        mp_source = "live"
                        mp_cache_fetched_at = started_at.isoformat()
                        mp_cache_age_seconds = 0
                        mp_cache_expired = False
                        try:
                            await self._store.set_json(MP_SITES_CACHE_KEY, build_cache(mp_base_url, mp_sites, fetched_at=started_at))
                        except Exception:
                            logger.exception("failed to persist MoviePilot sites cache")

                        deps_status = update_dep_ok(deps_status, "moviepilot", started_at, mp_fp)
                        try:
                            await self._store.set_json(DEPS_STATUS_KEY, deps_status)
                        except Exception:
                            logger.exception("failed to persist deps status")
                    except Exception as e:
                        logger.exception("failed to load sites from MoviePilot")
                        mp_error = _format_error_detail(e)
                        deps_status = update_dep_fail(
                            deps_status,
                            "moviepilot",
                            started_at,
                            mp_fp,
                            mp_error,
                            retry_interval_seconds=deps_retry_interval,
                        )
                        try:
                            await self._store.set_json(DEPS_STATUS_KEY, deps_status)
                        except Exception:
                            logger.exception("failed to persist deps status")

                if mp_sites:
                    pass
                else:
                    # Try cache / snapshot.
                    try:
                        cache = parse_cache(await self._store.get_json(MP_SITES_CACHE_KEY, default=None))
                        if cache:
                            mp_cache_fetched_at = cache.fetched_at_iso
                            mp_cache_age_seconds = cache.age_seconds(started_at)
                            mp_cache_expired = cache_expired(cache, started_at, mp_sites_cache_ttl, base_url=mp_base_url)
                            if not mp_cache_expired:
                                mp_sites = cache.sites
                                mp_source = "cache"
                    except Exception:
                        logger.exception("failed to load MoviePilot sites cache")
                    if not mp_sites:
                        try:
                            snap_at, snap_sites = await self._store.load_sites_snapshot()
                            if snap_sites and snap_at:
                                age = int(max(0, (started_at - snap_at).total_seconds()))
                                mp_cache_fetched_at = snap_at.isoformat()
                                mp_cache_age_seconds = age
                                if age <= mp_sites_cache_ttl:
                                    mp_cache_expired = False
                                    mp_sites = snap_sites
                                    mp_source = "state"
                                    try:
                                        await self._store.set_json(MP_SITES_CACHE_KEY, build_cache(mp_base_url, mp_sites, fetched_at=snap_at))
                                    except Exception:
                                        logger.exception("failed to persist MoviePilot sites cache (seeded)")
                                else:
                                    mp_cache_expired = True
                        except Exception:
                            logger.exception("failed to load sites snapshot from local state")

            cc_should_attempt = bool(cc_base_url and cc_uuid and cc_password and cookie_source in {"auto", "cookiecloud"})
            cc_cookies: Optional[list[dict[str, Any]]] = None
            cc_client = None
            if cc_should_attempt:
                cc_fp = fingerprint_cookiecloud(cc_base_url, cc_uuid)
                cc_dep = get_dep_status(deps_status, "cookiecloud")
                cc_allowed = can_attempt(cc_dep, started_at, cc_fp)
                if cc_allowed:
                    cc_client = CookieCloudClient(
                        base_url=cc_base_url,
                        uuid=cc_uuid,
                        password=cc_password,
                        timeout_seconds=scan_timeout,
                    )
                    try:
                        cc_cookies = await cc_client.fetch_cookie_items()
                        deps_status = update_dep_ok(deps_status, "cookiecloud", started_at, cc_fp)
                        await self._store.set_json(DEPS_STATUS_KEY, deps_status)
                    except Exception as e:
                        cc_error = _format_error_detail(e)
                        deps_status = update_dep_fail(
                            deps_status,
                            "cookiecloud",
                            started_at,
                            cc_fp,
                            cc_error,
                            retry_interval_seconds=deps_retry_interval,
                        )
                        try:
                            await self._store.set_json(DEPS_STATUS_KEY, deps_status)
                        except Exception:
                            logger.exception("failed to persist deps status")
                        cc_client = None
            cookie_mgr = CookieManager(
                cookie_source=cookie_source,
                cookiecloud=cc_client,
                refresh_interval_seconds=cc_refresh,
                prefetched_cookies=cc_cookies,
                prefetched_at=started_at if cc_cookies is not None else None,
            )
            sites = self._merge_sites(mp_sites, _safe_dict(sites_cfg.get("entries")))
            if not sites:
                error = mp_error if mp_error else "no sites configured"
                status = {
                    "ok": False,
                    "site_count": 0,
                    "error": error,
                    "moviepilot_ok": mp_ok,
                    "moviepilot_error": mp_error,
                    "moviepilot_source": mp_source,
                    "moviepilot_cache_fetched_at": mp_cache_fetched_at,
                    "moviepilot_cache_age_seconds": mp_cache_age_seconds,
                    "moviepilot_cache_expired": mp_cache_expired,
                    "last_run_at": started_at.isoformat(),
                }
                await self._store.set_json("scan_status", status)
                return status

            manual_count = sum(1 for s in sites if s.id is None)
            logger.info("scan start: %d sites (moviepilot=%d manual=%d)", len(sites), len(sites) - manual_count, manual_count)

            timeout = httpx.Timeout(scan_timeout)
            async with httpx.AsyncClient(
                timeout=timeout,
                follow_redirects=True,
                trust_env=scan_trust_env,
            ) as client:
                tasks = [self._check_one(client, site, started_at, cookie_mgr, scan_user_agent or None) for site in sites]
                results = await asyncio.gather(*tasks, return_exceptions=True)
                errors = [r for r in results if isinstance(r, Exception)]
                if errors:
                    logger.warning("scan completed with %d task errors", len(errors))

            logger.info("scan done")
            warning = ""
            if mp_attempted and mp_error:
                if mp_source in {"cache", "state"} and mp_cache_age_seconds is not None:
                    warning = f"moviepilot_failed: {mp_error} (fallback={mp_source} age={mp_cache_age_seconds}s)"
                else:
                    warning = f"moviepilot_failed: {mp_error}"
            status = {
                "ok": True,
                "site_count": len(sites),
                "error": "",
                "warning": warning,
                "moviepilot_ok": mp_ok,
                "moviepilot_error": mp_error,
                "moviepilot_source": mp_source,
                "moviepilot_cache_fetched_at": mp_cache_fetched_at,
                "moviepilot_cache_age_seconds": mp_cache_age_seconds,
                "moviepilot_cache_expired": mp_cache_expired,
                "last_run_at": datetime.now(timezone.utc).isoformat(),
            }
            await self._store.set_json("scan_status", status)
            return status

    async def run_one(self, domain: str) -> Dict[str, Any]:
        async with self._lock:
            started_at = datetime.now(timezone.utc)
            target = _normalize_domain(domain)
            if not target:
                status = {
                    "ok": False,
                    "site_count": 0,
                    "error": "domain is required",
                    "last_run_at": started_at.isoformat(),
                }
                return status

            cfg = await self._load_app_config()
            sites_cfg = await self._load_sites_config()

            mp_cfg = _safe_dict(cfg.get("moviepilot"))
            connectivity_cfg = _safe_dict(cfg.get("connectivity"))
            cookie_cfg = _safe_dict(cfg.get("cookie"))
            cc_cfg = _safe_dict(cookie_cfg.get("cookiecloud"))
            scan_cfg = _safe_dict(cfg.get("scan"))

            mp_base_url = _cfg_str(mp_cfg.get("base_url")) or self._settings.moviepilot.base_url
            mp_username = _cfg_str(mp_cfg.get("username")) or self._settings.moviepilot.username
            mp_password = _cfg_str(mp_cfg.get("password")) or self._settings.moviepilot.password
            mp_otp_password = _cfg_str(mp_cfg.get("otp_password")) or (self._settings.moviepilot.otp_password or "")
            mp_sites_cache_ttl = _cfg_int(
                mp_cfg.get("sites_cache_ttl_seconds"),
                default=MP_SITES_CACHE_DEFAULT_TTL_SECONDS,
                min_value=MP_SITES_CACHE_MIN_TTL_SECONDS,
                max_value=MP_SITES_CACHE_MAX_TTL_SECONDS,
            )
            deps_retry_interval = _cfg_int(
                connectivity_cfg.get("retry_interval_seconds"),
                default=DEFAULT_RETRY_INTERVAL_SECONDS,
                min_value=MIN_RETRY_INTERVAL_SECONDS,
                max_value=MAX_RETRY_INTERVAL_SECONDS,
            )
            mp_sites_cache_ttl = _cfg_int(
                mp_cfg.get("sites_cache_ttl_seconds"),
                default=MP_SITES_CACHE_DEFAULT_TTL_SECONDS,
                min_value=MP_SITES_CACHE_MIN_TTL_SECONDS,
                max_value=MP_SITES_CACHE_MAX_TTL_SECONDS,
            )

            cookie_source = (_cfg_str(cookie_cfg.get("source")) or self._settings.cookie.source or "auto").strip().lower()
            cc_base_url = _cfg_str(cc_cfg.get("base_url")) or self._settings.cookie.cookiecloud.base_url
            cc_uuid = _cfg_str(cc_cfg.get("uuid")) or self._settings.cookie.cookiecloud.uuid
            cc_password = _cfg_str(cc_cfg.get("password")) or self._settings.cookie.cookiecloud.password
            cc_refresh = _cfg_int(
                cc_cfg.get("refresh_interval_seconds"),
                default=int(self._settings.cookie.cookiecloud.refresh_interval_seconds),
                min_value=30,
                max_value=24 * 3600,
            )

            scan_timeout = _cfg_int(
                scan_cfg.get("timeout_seconds"),
                default=int(self._settings.scan.timeout_seconds),
                min_value=5,
                max_value=180,
            )
            scan_concurrency = _cfg_int(
                scan_cfg.get("concurrency"),
                default=int(self._settings.scan.concurrency),
                min_value=1,
                max_value=64,
            )
            scan_user_agent = _cfg_str(scan_cfg.get("user_agent")) or self._settings.scan.user_agent or ""
            scan_trust_env = _cfg_bool(scan_cfg.get("trust_env"), default=bool(self._settings.scan.trust_env))

            self._sem = asyncio.Semaphore(max(1, scan_concurrency))

            deps_status = load_deps_status(await self._store.get_json(DEPS_STATUS_KEY, default=None))

            mp_attempted = bool(mp_base_url and mp_username and mp_password)
            mp_sites: list[Site] = []
            mp_error = ""
            mp_ok = False
            mp_source = "none"
            mp_cache_fetched_at = ""
            mp_cache_age_seconds: Optional[int] = None
            mp_cache_expired: Optional[bool] = None
            if mp_attempted:
                mp_fp = fingerprint_moviepilot(mp_base_url)
                mp_dep = get_dep_status(deps_status, "moviepilot")
                mp_allowed = can_attempt(mp_dep, started_at, mp_fp)
                if not mp_allowed:
                    mp_error = mp_dep.error
                else:
                    mp_client = MoviePilotClient(
                        base_url=mp_base_url,
                        username=mp_username,
                        password=mp_password,
                        otp_password=mp_otp_password or None,
                        timeout_seconds=scan_timeout,
                    )
                    try:
                        mp_sites = await mp_client.list_sites(only_active=True)
                        mp_ok = True
                        mp_source = "live"
                        mp_cache_fetched_at = started_at.isoformat()
                        mp_cache_age_seconds = 0
                        mp_cache_expired = False
                        try:
                            await self._store.set_json(MP_SITES_CACHE_KEY, build_cache(mp_base_url, mp_sites, fetched_at=started_at))
                        except Exception:
                            logger.exception("failed to persist MoviePilot sites cache")

                        deps_status = update_dep_ok(deps_status, "moviepilot", started_at, mp_fp)
                        try:
                            await self._store.set_json(DEPS_STATUS_KEY, deps_status)
                        except Exception:
                            logger.exception("failed to persist deps status")
                    except Exception as e:
                        logger.exception("failed to load sites from MoviePilot")
                        mp_error = _format_error_detail(e)
                        deps_status = update_dep_fail(
                            deps_status,
                            "moviepilot",
                            started_at,
                            mp_fp,
                            mp_error,
                            retry_interval_seconds=deps_retry_interval,
                        )
                        try:
                            await self._store.set_json(DEPS_STATUS_KEY, deps_status)
                        except Exception:
                            logger.exception("failed to persist deps status")

                if mp_sites:
                    pass
                else:
                    try:
                        cache = parse_cache(await self._store.get_json(MP_SITES_CACHE_KEY, default=None))
                        if cache:
                            mp_cache_fetched_at = cache.fetched_at_iso
                            mp_cache_age_seconds = cache.age_seconds(started_at)
                            mp_cache_expired = cache_expired(cache, started_at, mp_sites_cache_ttl, base_url=mp_base_url)
                            if not mp_cache_expired:
                                mp_sites = cache.sites
                                mp_source = "cache"
                    except Exception:
                        logger.exception("failed to load MoviePilot sites cache")
                    if not mp_sites:
                        try:
                            snap_at, snap_sites = await self._store.load_sites_snapshot()
                            if snap_sites and snap_at:
                                age = int(max(0, (started_at - snap_at).total_seconds()))
                                mp_cache_fetched_at = snap_at.isoformat()
                                mp_cache_age_seconds = age
                                if age <= mp_sites_cache_ttl:
                                    mp_cache_expired = False
                                    mp_sites = snap_sites
                                    mp_source = "state"
                                    try:
                                        await self._store.set_json(MP_SITES_CACHE_KEY, build_cache(mp_base_url, mp_sites, fetched_at=snap_at))
                                    except Exception:
                                        logger.exception("failed to persist MoviePilot sites cache (seeded)")
                                else:
                                    mp_cache_expired = True
                        except Exception:
                            logger.exception("failed to load sites snapshot from local state")

            cc_client = None
            cc_should_attempt = bool(cc_base_url and cc_uuid and cc_password and cookie_source in {"auto", "cookiecloud"})
            cc_cookies: Optional[list[dict[str, Any]]] = None
            if cc_should_attempt:
                cc_fp = fingerprint_cookiecloud(cc_base_url, cc_uuid)
                cc_dep = get_dep_status(deps_status, "cookiecloud")
                cc_allowed = can_attempt(cc_dep, started_at, cc_fp)
                if cc_allowed:
                    cc_client = CookieCloudClient(
                        base_url=cc_base_url,
                        uuid=cc_uuid,
                        password=cc_password,
                        timeout_seconds=scan_timeout,
                    )
                    try:
                        cc_cookies = await cc_client.fetch_cookie_items()
                        deps_status = update_dep_ok(deps_status, "cookiecloud", started_at, cc_fp)
                        await self._store.set_json(DEPS_STATUS_KEY, deps_status)
                    except Exception as e:
                        cc_error = _format_error_detail(e)
                        deps_status = update_dep_fail(
                            deps_status,
                            "cookiecloud",
                            started_at,
                            cc_fp,
                            cc_error,
                            retry_interval_seconds=deps_retry_interval,
                        )
                        try:
                            await self._store.set_json(DEPS_STATUS_KEY, deps_status)
                        except Exception:
                            logger.exception("failed to persist deps status")
                        cc_client = None
            cookie_mgr = CookieManager(
                cookie_source=cookie_source,
                cookiecloud=cc_client,
                refresh_interval_seconds=cc_refresh,
                prefetched_cookies=cc_cookies,
                prefetched_at=started_at if cc_cookies is not None else None,
            )

            sites = self._merge_sites(mp_sites, _safe_dict(sites_cfg.get("entries")))
            site = next((s for s in sites if _normalize_domain(s.domain) == target), None)
            if not site:
                hint = ""
                if mp_attempted and mp_error:
                    hint = " (MoviePilot unavailable and no local manual site)"
                status = {
                    "ok": False,
                    "site_count": 0,
                    "error": f"site not found: {target}{hint}",
                    "moviepilot_ok": mp_ok,
                    "moviepilot_error": mp_error,
                    "moviepilot_source": mp_source,
                    "moviepilot_cache_fetched_at": mp_cache_fetched_at,
                    "moviepilot_cache_age_seconds": mp_cache_age_seconds,
                    "moviepilot_cache_expired": mp_cache_expired,
                    "last_run_at": started_at.isoformat(),
                }
                return status

            logger.info("single scan start: %s", target)
            timeout = httpx.Timeout(scan_timeout)
            try:
                async with httpx.AsyncClient(
                    timeout=timeout,
                    follow_redirects=True,
                    trust_env=scan_trust_env,
                ) as client:
                    await self._check_one(client, site, started_at, cookie_mgr, scan_user_agent or None)
            except Exception as e:
                logger.exception("single scan failed: %s", target)
                status = {
                    "ok": False,
                    "site_count": 1,
                    "domain": target,
                    "error": _format_error_detail(e),
                    "moviepilot_ok": mp_ok,
                    "moviepilot_error": mp_error,
                    "moviepilot_source": mp_source,
                    "moviepilot_cache_fetched_at": mp_cache_fetched_at,
                    "moviepilot_cache_age_seconds": mp_cache_age_seconds,
                    "moviepilot_cache_expired": mp_cache_expired,
                    "last_run_at": datetime.now(timezone.utc).isoformat(),
                }
                return status

            logger.info("single scan done: %s", target)
            warning = ""
            if mp_attempted and mp_error:
                if mp_source in {"cache", "state"} and mp_cache_age_seconds is not None:
                    warning = f"moviepilot_failed: {mp_error} (fallback={mp_source} age={mp_cache_age_seconds}s)"
                else:
                    warning = f"moviepilot_failed: {mp_error}"
            status = {
                "ok": True,
                "site_count": 1,
                "domain": target,
                "error": "",
                "warning": warning,
                "moviepilot_ok": mp_ok,
                "moviepilot_error": mp_error,
                "moviepilot_source": mp_source,
                "moviepilot_cache_fetched_at": mp_cache_fetched_at,
                "moviepilot_cache_age_seconds": mp_cache_age_seconds,
                "moviepilot_cache_expired": mp_cache_expired,
                "last_run_at": datetime.now(timezone.utc).isoformat(),
            }
            return status

    async def _check_one(
        self,
        client: httpx.AsyncClient,
        site,
        now: datetime,
        cookie_mgr: CookieManager,
        default_user_agent: Optional[str],
    ) -> None:
        async with self._sem:
            ua = site.ua or default_user_agent or None
            reachability, engine_hint = await self._probe_reachability(client, site.url, ua)
            engine = engine_hint or "unknown"
            is_mteam = (site.domain or "").lower().endswith("m-team.cc")
            if is_mteam:
                engine = "mteam"

            reg_path = (getattr(site, "registration_path", None) or "").strip() or "signup.php"
            inv_path = (getattr(site, "invite_path", None) or "").strip() or "invite.php"

            if reachability.state != "up":
                registration = AspectResult(
                    state="unknown",
                    evidence=Evidence(
                        url=urljoin(site.url.rstrip("/") + "/", reg_path),
                        http_status=None,
                        reason="site_unreachable",
                        detail=reachability.evidence.detail or reachability.evidence.reason,
                    ),
                )
                invites = AspectResult(
                    state="unknown",
                    evidence=Evidence(
                        url=urljoin(site.url.rstrip("/") + "/", inv_path),
                        http_status=None,
                        reason="site_unreachable",
                        detail=reachability.evidence.detail or reachability.evidence.reason,
                    ),
                )
                result = SiteCheckResult(
                    site=site,
                    engine=engine,
                    reachability=reachability,
                    registration=registration,
                    invites=invites,
                    checked_at=now,
                )
                await self._persist_and_notify(site, result, now)
                return

            try:
                registration = await self._detector.check_registration(client, site, ua)
            except Exception as e:
                logger.exception("registration check failed: %s", site.domain)
                registration = AspectResult(
                    state="unknown",
                    evidence=Evidence(
                        url=urljoin(site.url.rstrip("/") + "/", reg_path),
                        http_status=None,
                        reason=f"registration_error:{type(e).__name__}",
                        detail=_format_error_detail(e),
                    ),
                )

            def _get_cookie_override() -> str:
                return (getattr(site, "cookie_override", None) or "").strip()

            try:
                if is_mteam:
                    api_key = (getattr(site, "did", None) or "").strip()
                    if api_key:
                        invites = await self._mteam.check_invites(client, site, ua)
                        if invites.state == "unknown":
                            cookie_header = None
                            try:
                                cookie_override = _get_cookie_override()
                                if cookie_override:
                                    cookie_header = cookie_override
                                else:
                                    cookie_header = await cookie_mgr.cookie_header_for(site.url, fallback_cookie=getattr(site, "cookie", None))
                            except Exception:
                                logger.exception("cookie build failed: %s", site.domain)
                            if cookie_header:
                                invites = await self._detector.check_invites(client, site, ua, cookie_header)
                    else:
                        cookie_header = None
                        try:
                            cookie_override = _get_cookie_override()
                            if cookie_override:
                                cookie_header = cookie_override
                            else:
                                cookie_header = await cookie_mgr.cookie_header_for(site.url, fallback_cookie=getattr(site, "cookie", None))
                        except Exception:
                            logger.exception("cookie build failed: %s", site.domain)
                        if cookie_header:
                            invites = await self._detector.check_invites(client, site, ua, cookie_header)
                        else:
                            invites = AspectResult(
                                state="unknown",
                                evidence=Evidence(
                                    url="https://api.m-team.cc/api/member/profile",
                                    http_status=None,
                                    reason="missing_auth",
                                    detail="api-key (did) not configured",
                                ),
                            )
                else:
                    cookie_header = None
                    try:
                        cookie_override = _get_cookie_override()
                        if cookie_override:
                            cookie_header = cookie_override
                        else:
                            cookie_header = await cookie_mgr.cookie_header_for(site.url, fallback_cookie=getattr(site, "cookie", None))
                    except Exception:
                        logger.exception("cookie build failed: %s", site.domain)
                    invites = await self._detector.check_invites(client, site, ua, cookie_header)
            except Exception as e:
                logger.exception("invites check failed: %s", site.domain)
                invites = AspectResult(
                    state="unknown",
                    evidence=Evidence(
                        url=urljoin(site.url.rstrip("/") + "/", inv_path),
                        http_status=None,
                        reason=f"invites_error:{type(e).__name__}",
                        detail=_format_error_detail(e),
                    ),
                )

            result = SiteCheckResult(
                site=site,
                engine=engine,
                reachability=reachability,
                registration=registration,
                invites=invites,
                checked_at=now,
            )
            await self._persist_and_notify(site, result, now)

    async def _probe_reachability(
        self,
        client: httpx.AsyncClient,
        site_url: str,
        user_agent: Optional[str],
    ) -> tuple[ReachabilityResult, Optional[str]]:
        ua = user_agent or None
        orig_host = urlparse(site_url).hostname or ""

        engine_hint: Optional[str] = None
        last: tuple[ReachabilityResult, Optional[str]] = (
            ReachabilityResult(state="unknown", evidence=Evidence(url=site_url, http_status=None, reason="probe_not_run")),
            None,
        )

        attempts = 3
        for attempt in range(attempts):
            try:
                resp = await client.get(site_url, headers={"User-Agent": ua} if ua else None)
                status = resp.status_code
                engine_hint = engine_hint or _engine_hint_from_html(resp.text)

                final_host = resp.url.host if resp.url else ""
                if orig_host and final_host and not _hosts_related(orig_host, final_host):
                    last = (
                        ReachabilityResult(
                            state="down",
                            evidence=Evidence(
                                url=str(resp.url),
                                http_status=status,
                                reason="probe_redirect",
                                detail=f"redirected_to:{final_host}",
                            ),
                        ),
                        engine_hint,
                    )
                elif status >= 500 or status in _DOWN_HTTP_STATUSES:
                    last = (
                        ReachabilityResult(
                            state="down",
                            evidence=Evidence(url=str(resp.url), http_status=status, reason=f"probe_http_{status}"),
                        ),
                        engine_hint,
                    )
                else:
                    return (
                        ReachabilityResult(
                            state="up",
                            evidence=Evidence(url=str(resp.url), http_status=status, reason="probe_ok"),
                        ),
                        engine_hint,
                    )
            except httpx.RequestError as e:
                last = (
                    ReachabilityResult(
                        state="down",
                        evidence=Evidence(
                            url=site_url,
                            http_status=None,
                            reason=f"probe_error:{type(e).__name__}",
                            detail=_format_error_detail(e),
                        ),
                    ),
                    engine_hint,
                )
            except Exception as e:
                last = (
                    ReachabilityResult(
                        state="unknown",
                        evidence=Evidence(
                            url=site_url,
                            http_status=None,
                            reason=f"probe_error:{type(e).__name__}",
                            detail=_format_error_detail(e),
                        ),
                    ),
                    engine_hint,
                )

            if attempt < attempts - 1:
                await asyncio.sleep(0.3 * (attempt + 1))

        # Mark that we retried before concluding it's down/unknown.
        result, hint = last
        ev = result.evidence
        if ev.detail:
            detail = f"{ev.detail} (retries={attempts})"
        else:
            detail = f"retries={attempts}"
        return (
            ReachabilityResult(
                state=result.state,
                evidence=Evidence(url=ev.url, http_status=ev.http_status, reason=ev.reason, matched=ev.matched, detail=detail),
            ),
            hint,
        )

    async def _persist_and_notify(self, site, result: SiteCheckResult, now: datetime) -> None:
        try:
            prev = await self._store.get_site_state(site.domain)
            changes = self._diff(prev, result)
            changed_at = now.isoformat() if changes else None
            await self._store.save_site_result(result, changed_at=changed_at)
        except Exception:
            logger.exception("failed to persist site result: %s", site.domain)
            return

        if not changes:
            return

        invite_display = "-"
        if result.invites.permanent is not None:
            invite_display = f"{int(result.invites.permanent)}({int(result.invites.temporary or 0)})"
        elif result.invites.available is not None:
            invite_display = str(int(result.invites.available))

        title = "PT Invite Watcher: 状态变化"
        text = "\n".join(
            [
                f"站点：{site.name} ({site.domain})",
                f"URL：{site.url}",
                *changes,
                f"注册：{result.registration.state} ({result.registration.evidence.reason})",
                f"邀请：{result.invites.state} {invite_display}",
            ]
        )
        try:
            await self._notifier.send(title=title, text=text)
        except Exception:
            logger.exception("notify failed: %s", site.domain)

    @staticmethod
    def _diff(prev, cur: SiteCheckResult) -> list[str]:
        if prev is None:
            return []

        changes: list[str] = []

        if cur.registration.state == "open" and prev.registration_state != "open":
            changes.append("开放注册：open")
        elif cur.registration.state == "closed" and prev.registration_state == "open":
            changes.append("开放注册：closed")

        if cur.invites.available is not None:
            prev_count = prev.invites_available
            cur_count = cur.invites.available
            if cur_count > 0 and (prev_count is None or prev_count <= 0):
                changes.append(f"可用邀请数：{prev_count or 0} -> {cur_count}")
            elif cur_count <= 0 and (prev_count is not None and prev_count > 0):
                changes.append(f"可用邀请数：{prev_count} -> {cur_count}")

        return changes
