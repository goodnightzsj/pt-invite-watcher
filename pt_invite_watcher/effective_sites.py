from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from pt_invite_watcher.config import Settings
from pt_invite_watcher.config_store import load_sites_config
from pt_invite_watcher.models import Site
from pt_invite_watcher.providers.moviepilot_sites import MoviePilotSitesResult, MoviePilotSitesService
from pt_invite_watcher.runtime_config_cache import RuntimeConfigCache
from pt_invite_watcher.runtime_config_loader import get_runtime_config
from pt_invite_watcher.site_templates import default_paths_for_template, infer_template, infer_template_optional
from pt_invite_watcher.utils.parse import cfg_str, normalize_domain, safe_dict


def merge_sites(mp_sites: list[Site], site_entries: dict[str, Any]) -> list[Site]:
    """
    Merge MoviePilot sites and local site entries into the effective site list.

    Local entries can:
    - override MP sites (mode=override)
    - define manual sites not present in MP (mode=manual)
    """
    entries = site_entries if isinstance(site_entries, dict) else {}

    merged: list[Site] = []
    mp_domains: set[str] = set()
    for site in mp_sites:
        domain = normalize_domain(site.domain)
        if not domain:
            continue
        mp_domains.add(domain)

        entry = safe_dict(entries.get(domain))
        mode = (cfg_str(entry.get("mode")) or "override").lower()
        if mode not in {"override", "manual"}:
            entry = {}

        name = cfg_str(entry.get("name")) or site.name
        cookie_override = cfg_str(entry.get("cookie")) or None
        authorization = cfg_str(entry.get("authorization")) or None
        did = cfg_str(entry.get("did")) or None
        template = infer_template_optional(domain, entry.get("template"))
        reg_path = cfg_str(entry.get("registration_path")) or None
        inv_path = cfg_str(entry.get("invite_path")) or None
        if template == "mteam":
            reg_default, inv_default = default_paths_for_template(template)
            reg_path = reg_path or reg_default
            inv_path = inv_path or inv_default

        merged.append(
            Site(
                id=site.id,
                name=name,
                domain=domain,
                url=site.url,
                ua=site.ua,
                cookie=site.cookie,
                cookie_override=cookie_override,
                authorization=authorization,
                did=did,
                is_active=site.is_active,
                template=template,
                registration_path=reg_path,
                invite_path=inv_path,
            )
        )

    # Manual sites (not in MoviePilot list)
    for raw_domain, raw in entries.items():
        domain = normalize_domain(raw_domain)
        if not domain or domain in mp_domains:
            continue
        entry = safe_dict(raw)
        mode = (cfg_str(entry.get("mode")) or "manual").lower()
        if mode != "manual":
            continue
        url = cfg_str(entry.get("url"))
        if not url:
            continue
        name = cfg_str(entry.get("name")) or domain
        cookie_override = cfg_str(entry.get("cookie")) or None
        authorization = cfg_str(entry.get("authorization")) or None
        did = cfg_str(entry.get("did")) or None
        template = infer_template(domain, entry.get("template"), default="custom")
        reg_path = cfg_str(entry.get("registration_path")) or None
        inv_path = cfg_str(entry.get("invite_path")) or None
        if template == "mteam":
            reg_default, inv_default = default_paths_for_template(template)
            reg_path = reg_path or reg_default
            inv_path = inv_path or inv_default

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
    for site in merged:
        dom = normalize_domain(site.domain)
        if not dom:
            continue
        by_domain[dom] = site
    return list(by_domain.values())


@dataclass(frozen=True)
class EffectiveSitesResult:
    sites: list[Site]
    entries: dict[str, Any]
    moviepilot: MoviePilotSitesResult


class EffectiveSitesService:
    def __init__(
        self,
        settings: Settings,
        store: Any,
        *,
        runtime_config: RuntimeConfigCache | None = None,
        mp_live_throttle_seconds: int = 15,
    ):
        self._settings = settings
        self._store = store
        self._runtime_config = runtime_config
        self._mp_live_throttle_seconds = max(0, int(mp_live_throttle_seconds or 0))

    async def load_for_scan(
        self,
        *,
        now: datetime,
        deps_status: dict[str, Any] | None = None,
        prefer_moviepilot_cache_if_fresh: bool = False,
    ) -> EffectiveSitesResult:
        """
        Scan mode: allow live MoviePilot fetch; require credentials; deps_status is threaded through.
        """
        return await self._load(
            now=now,
            allow_live=True,
            require_credentials=True,
            deps_status=deps_status,
            prefer_moviepilot_cache_if_fresh=bool(prefer_moviepilot_cache_if_fresh),
        )

    async def load_for_dashboard(self, *, now: datetime) -> EffectiveSitesResult:
        """
        Dashboard mode: never force a live MoviePilot call; allow fallback even without credentials.
        """
        return await self._load(now=now, allow_live=False, require_credentials=False, deps_status=None)

    async def load_for_sites(self, *, now: datetime, allow_live: bool, force_live: bool) -> EffectiveSitesResult:
        """
        Sites page: allow live MoviePilot call optionally (with throttling), and allow
        cache/state/summary fallback even when credentials are missing.
        """
        return await self._load(
            now=now,
            allow_live=bool(allow_live),
            require_credentials=False,
            deps_status=None,
            throttle_live=True,
            force_live=bool(force_live),
        )

    async def _load_runtime_config(self) -> Any:
        return await get_runtime_config(self._settings, self._store, runtime_config=self._runtime_config)

    async def _load_entries(self) -> dict[str, Any]:
        sites_cfg = await load_sites_config(self._store)
        return safe_dict(sites_cfg.get("entries"))

    async def _load(
        self,
        *,
        now: datetime,
        allow_live: bool,
        require_credentials: bool,
        deps_status: dict[str, Any] | None,
        throttle_live: bool = False,
        force_live: bool = False,
        prefer_moviepilot_cache_if_fresh: bool = False,
    ) -> EffectiveSitesResult:
        rc = await self._load_runtime_config()

        mp_base_url = rc.moviepilot.base_url
        mp_username = rc.moviepilot.username
        mp_password = rc.moviepilot.password
        mp_otp_password = rc.moviepilot.otp_password
        mp_sites_cache_ttl = rc.moviepilot.sites_cache_ttl_seconds

        deps_retry_interval = rc.connectivity.retry_interval_seconds
        request_retry_delay_seconds = rc.connectivity.request_retry_delay_seconds
        scan_timeout = rc.scan.timeout_seconds

        throttle_seconds = self._mp_live_throttle_seconds if throttle_live else 0

        mp_service = MoviePilotSitesService(self._store)
        mp_result = await mp_service.load_sites(
            now=now,
            base_url=mp_base_url,
            cache_ttl_seconds=mp_sites_cache_ttl,
            username=mp_username,
            password=mp_password,
            otp_password=mp_otp_password or None,
            timeout_seconds=scan_timeout,
            request_retry_delay_seconds=request_retry_delay_seconds,
            deps_retry_interval_seconds=deps_retry_interval,
            deps_status=deps_status,
            allow_live=bool(allow_live),
            throttle_live_seconds=int(throttle_seconds or 0),
            prefer_cache_if_fresh=bool(prefer_moviepilot_cache_if_fresh),
            force_live=bool(force_live),
            require_credentials=require_credentials,
        )

        entries = await self._load_entries()
        sites = merge_sites(mp_result.sites, entries)
        return EffectiveSitesResult(sites=sites, entries=entries, moviepilot=mp_result)
