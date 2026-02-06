from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from pt_invite_watcher.config import Settings
from pt_invite_watcher.providers.deps_status import (
    DEFAULT_RETRY_INTERVAL_SECONDS,
    MAX_RETRY_INTERVAL_SECONDS,
    MIN_RETRY_INTERVAL_SECONDS,
)
from pt_invite_watcher.providers.moviepilot_sites_cache import (
    MP_SITES_CACHE_DEFAULT_TTL_SECONDS,
    MP_SITES_CACHE_MAX_TTL_SECONDS,
    MP_SITES_CACHE_MIN_TTL_SECONDS,
)
from pt_invite_watcher.utils.parse import cfg_bool, cfg_int, cfg_str, safe_dict


@dataclass(frozen=True)
class MoviePilotRuntimeConfig:
    base_url: str
    username: str
    password: str
    otp_password: str
    sites_cache_ttl_seconds: int


@dataclass(frozen=True)
class ConnectivityRuntimeConfig:
    retry_interval_seconds: int
    request_retry_delay_seconds: int


@dataclass(frozen=True)
class CookieCloudRuntimeConfig:
    base_url: str
    uuid: str
    password: str
    refresh_interval_seconds: int


@dataclass(frozen=True)
class CookieRuntimeConfig:
    source: str
    cookiecloud: CookieCloudRuntimeConfig


@dataclass(frozen=True)
class ScanRuntimeConfig:
    interval_seconds: int
    timeout_seconds: int
    concurrency: int
    user_agent: str
    trust_env: bool


@dataclass(frozen=True)
class UIRuntimeConfig:
    allow_state_reset: bool


@dataclass(frozen=True)
class RuntimeConfig:
    moviepilot: MoviePilotRuntimeConfig
    connectivity: ConnectivityRuntimeConfig
    cookie: CookieRuntimeConfig
    scan: ScanRuntimeConfig
    ui: UIRuntimeConfig


def load_runtime_config(settings: Settings, app_config_payload: Any) -> RuntimeConfig:
    cfg = safe_dict(app_config_payload)

    mp_cfg = safe_dict(cfg.get("moviepilot"))
    connectivity_cfg = safe_dict(cfg.get("connectivity"))
    cookie_cfg = safe_dict(cfg.get("cookie"))
    cc_cfg = safe_dict(cookie_cfg.get("cookiecloud"))
    scan_cfg = safe_dict(cfg.get("scan"))
    ui_cfg = safe_dict(cfg.get("ui"))

    mp_base_url = cfg_str(mp_cfg.get("base_url")) or settings.moviepilot.base_url
    mp_username = cfg_str(mp_cfg.get("username")) or settings.moviepilot.username
    mp_password = cfg_str(mp_cfg.get("password")) or settings.moviepilot.password
    mp_otp_password = cfg_str(mp_cfg.get("otp_password")) or (settings.moviepilot.otp_password or "")
    mp_sites_cache_ttl = cfg_int(
        mp_cfg.get("sites_cache_ttl_seconds"),
        MP_SITES_CACHE_DEFAULT_TTL_SECONDS,
        MP_SITES_CACHE_MIN_TTL_SECONDS,
        MP_SITES_CACHE_MAX_TTL_SECONDS,
    )

    deps_retry_interval = cfg_int(
        connectivity_cfg.get("retry_interval_seconds"),
        DEFAULT_RETRY_INTERVAL_SECONDS,
        MIN_RETRY_INTERVAL_SECONDS,
        MAX_RETRY_INTERVAL_SECONDS,
    )
    request_retry_delay_seconds = cfg_int(
        connectivity_cfg.get("request_retry_delay_seconds"),
        30,
        5,
        24 * 3600,
    )

    source = (cfg_str(cookie_cfg.get("source")) or settings.cookie.source or "auto").strip().lower() or "auto"
    if source not in {"auto", "cookiecloud", "moviepilot"}:
        source = (settings.cookie.source or "auto").strip().lower() or "auto"

    cc_base_url = cfg_str(cc_cfg.get("base_url")) or settings.cookie.cookiecloud.base_url
    cc_uuid = cfg_str(cc_cfg.get("uuid")) or settings.cookie.cookiecloud.uuid
    cc_password = cfg_str(cc_cfg.get("password")) or settings.cookie.cookiecloud.password
    cc_refresh = cfg_int(
        cc_cfg.get("refresh_interval_seconds"),
        int(settings.cookie.cookiecloud.refresh_interval_seconds),
        30,
        24 * 3600,
    )

    scan_interval = cfg_int(
        scan_cfg.get("interval_seconds"),
        settings.scan.interval_seconds,
        30,
        24 * 3600,
    )
    scan_timeout = cfg_int(
        scan_cfg.get("timeout_seconds"),
        settings.scan.timeout_seconds,
        5,
        180,
    )
    scan_concurrency = cfg_int(
        scan_cfg.get("concurrency"),
        settings.scan.concurrency,
        1,
        64,
    )
    scan_user_agent = cfg_str(scan_cfg.get("user_agent")) or settings.scan.user_agent
    scan_trust_env = cfg_bool(scan_cfg.get("trust_env"), default=settings.scan.trust_env)

    ui_allow_state_reset = cfg_bool(ui_cfg.get("allow_state_reset"), default=True)

    return RuntimeConfig(
        moviepilot=MoviePilotRuntimeConfig(
            base_url=mp_base_url,
            username=mp_username,
            password=mp_password,
            otp_password=mp_otp_password,
            sites_cache_ttl_seconds=mp_sites_cache_ttl,
        ),
        connectivity=ConnectivityRuntimeConfig(
            retry_interval_seconds=deps_retry_interval,
            request_retry_delay_seconds=request_retry_delay_seconds,
        ),
        cookie=CookieRuntimeConfig(
            source=source,
            cookiecloud=CookieCloudRuntimeConfig(
                base_url=cc_base_url,
                uuid=cc_uuid,
                password=cc_password,
                refresh_interval_seconds=cc_refresh,
            ),
        ),
        scan=ScanRuntimeConfig(
            interval_seconds=scan_interval,
            timeout_seconds=scan_timeout,
            concurrency=scan_concurrency,
            user_agent=scan_user_agent,
            trust_env=scan_trust_env,
        ),
        ui=UIRuntimeConfig(allow_state_reset=ui_allow_state_reset),
    )
