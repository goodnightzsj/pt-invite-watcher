from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional
from urllib.parse import urlparse
import os

import yaml


def _env(name: str, default: Optional[str] = None) -> Optional[str]:
    value = os.getenv(name)
    if value is None or value == "":
        return default
    return value


def _env_int(name: str, default: int) -> int:
    value = _env(name)
    if value is None:
        return default
    try:
        return int(value)
    except ValueError:
        return default


def _env_bool(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None or value == "":
        return default
    return _as_bool(value)


def _as_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return False
    if isinstance(value, int):
        return value != 0
    return str(value).strip().lower() in {"1", "true", "yes", "y", "on"}


def _clean_base_url(base_url: str) -> str:
    base_url = (base_url or "").strip()
    if not base_url:
        return ""
    # Users often paste Swagger docs url like ".../docs" or an api prefix like ".../api/v1".
    # Keep any reverse-proxy prefix path, only strip these well-known suffixes.
    while True:
        original = base_url
        for suffix in ("/docs", "/docs/", "/api/v1", "/api/v1/"):
            if base_url.endswith(suffix):
                base_url = base_url[: -len(suffix)]
                break
        if base_url == original:
            break
    return base_url.rstrip("/")


@dataclass(frozen=True)
class BasicAuthSettings:
    enabled: bool
    username: str
    password: str


@dataclass(frozen=True)
class WebSettings:
    host: str
    port: int
    basic_auth: BasicAuthSettings


@dataclass(frozen=True)
class DatabaseSettings:
    path: Path


@dataclass(frozen=True)
class ScanSettings:
    interval_seconds: int
    timeout_seconds: int
    concurrency: int
    user_agent: str
    trust_env: bool


@dataclass(frozen=True)
class CookieCloudSettings:
    base_url: str
    uuid: str
    password: str
    refresh_interval_seconds: int


@dataclass(frozen=True)
class CookieSettings:
    source: str  # auto|cookiecloud|moviepilot
    cookiecloud: CookieCloudSettings


@dataclass(frozen=True)
class MoviePilotSettings:
    base_url: str
    username: str
    password: str
    otp_password: Optional[str]


@dataclass(frozen=True)
class Settings:
    moviepilot: MoviePilotSettings
    cookie: CookieSettings
    scan: ScanSettings
    db: DatabaseSettings
    web: WebSettings
    log_level: str


def _load_yaml_config(config_path: Optional[str]) -> dict[str, Any]:
    candidates: list[Path] = []
    if config_path:
        candidates.append(Path(config_path))
    env_path = _env("PTIW_CONFIG")
    if env_path:
        candidates.append(Path(env_path))
    candidates.extend([Path("./config/config.yaml"), Path("./config.yaml")])

    for path in candidates:
        if path.exists() and path.is_file():
            data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
            if not isinstance(data, dict):
                return {}
            return data
    return {}


def _deep_get(obj: dict[str, Any], keys: list[str], default: Any = None) -> Any:
    cur: Any = obj
    for key in keys:
        if not isinstance(cur, dict) or key not in cur:
            return default
        cur = cur[key]
    return cur


def load_settings(config_path: Optional[str] = None) -> Settings:
    cfg = _load_yaml_config(config_path)

    mp_base_url = _clean_base_url(_env("MP_BASE_URL", _deep_get(cfg, ["moviepilot", "base_url"], "")) or "")
    mp_username = _env("MP_USERNAME", _deep_get(cfg, ["moviepilot", "username"], "")) or ""
    mp_password = _env("MP_PASSWORD", _deep_get(cfg, ["moviepilot", "password"], "")) or ""
    mp_otp_password = _env("MP_OTP_PASSWORD", _deep_get(cfg, ["moviepilot", "otp_password"], None))

    cookie_source = (_env("COOKIE_SOURCE", _deep_get(cfg, ["cookie", "source"], "auto")) or "auto").strip().lower()
    cc_base_url = _clean_base_url(_env("COOKIECLOUD_BASE_URL", _deep_get(cfg, ["cookie", "cookiecloud", "base_url"], "")) or "")
    cc_uuid = _env("COOKIECLOUD_UUID", _deep_get(cfg, ["cookie", "cookiecloud", "uuid"], "")) or ""
    cc_password = _env("COOKIECLOUD_PASSWORD", _deep_get(cfg, ["cookie", "cookiecloud", "password"], "")) or ""
    cc_refresh = _env_int("COOKIECLOUD_REFRESH_INTERVAL_SECONDS",
                          int(_deep_get(cfg, ["cookie", "cookiecloud", "refresh_interval_seconds"], 300) or 300))

    scan_interval = _env_int("PTIW_SCAN_INTERVAL_SECONDS", int(_deep_get(cfg, ["scan", "interval_seconds"], 600) or 600))
    scan_timeout = _env_int("PTIW_SCAN_TIMEOUT_SECONDS", int(_deep_get(cfg, ["scan", "timeout_seconds"], 20) or 20))
    scan_concurrency = _env_int("PTIW_SCAN_CONCURRENCY", int(_deep_get(cfg, ["scan", "concurrency"], 8) or 8))
    scan_user_agent = _env("PTIW_USER_AGENT", _deep_get(cfg, ["scan", "user_agent"], "")) or ""
    scan_trust_env = _env_bool("PTIW_SCAN_TRUST_ENV", _as_bool(_deep_get(cfg, ["scan", "trust_env"], False)))

    db_path = Path(_env("PTIW_DB_PATH", _deep_get(cfg, ["db", "path"], "./data/ptiw.db")) or "./data/ptiw.db")

    web_host = _env("PTIW_WEB_HOST", _deep_get(cfg, ["web", "host"], "0.0.0.0")) or "0.0.0.0"
    web_port = _env_int("PTIW_WEB_PORT", int(_deep_get(cfg, ["web", "port"], 8080) or 8080))

    web_auth_username = _env("PTIW_WEB_AUTH_USERNAME", _deep_get(cfg, ["web", "basic_auth", "username"], "")) or ""
    web_auth_password = _env("PTIW_WEB_AUTH_PASSWORD", _deep_get(cfg, ["web", "basic_auth", "password"], "")) or ""
    web_auth_enabled = bool(web_auth_username and web_auth_password)

    log_level = (_env("PTIW_LOG_LEVEL", "INFO") or "INFO").strip().upper()

    if mp_base_url:
        parsed = urlparse(mp_base_url)
        if not parsed.scheme or not parsed.netloc:
            raise ValueError(f"Invalid MP_BASE_URL: {mp_base_url}")

    return Settings(
        moviepilot=MoviePilotSettings(
            base_url=mp_base_url,
            username=mp_username,
            password=mp_password,
            otp_password=mp_otp_password,
        ),
        cookie=CookieSettings(
            source=cookie_source,
            cookiecloud=CookieCloudSettings(
                base_url=cc_base_url,
                uuid=cc_uuid,
                password=cc_password,
                refresh_interval_seconds=cc_refresh,
            ),
        ),
        scan=ScanSettings(
            interval_seconds=scan_interval,
            timeout_seconds=scan_timeout,
            concurrency=scan_concurrency,
            user_agent=scan_user_agent,
            trust_env=scan_trust_env,
        ),
        db=DatabaseSettings(path=db_path),
        web=WebSettings(
            host=web_host,
            port=web_port,
            basic_auth=BasicAuthSettings(
                enabled=web_auth_enabled,
                username=web_auth_username,
                password=web_auth_password,
            ),
        ),
        log_level=log_level,
    )
