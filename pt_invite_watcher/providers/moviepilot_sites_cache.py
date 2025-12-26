from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import Any, Optional

from pt_invite_watcher.models import Site


MP_SITES_CACHE_KEY = "moviepilot_sites_cache"
MP_SITES_CACHE_VERSION = 1

MP_SITES_CACHE_DEFAULT_TTL_SECONDS = 24 * 3600
MP_SITES_CACHE_MIN_TTL_SECONDS = 60
MP_SITES_CACHE_MAX_TTL_SECONDS = 7 * 24 * 3600


def _safe_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _safe_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _safe_str(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _norm_base_url(value: Any) -> str:
    return _safe_str(value).rstrip("/")


def _safe_int(value: Any) -> Optional[int]:
    if value is None or value == "":
        return None
    try:
        return int(value)
    except Exception:
        return None


def _parse_dt(value: Any) -> Optional[datetime]:
    s = _safe_str(value)
    if not s:
        return None
    try:
        dt = datetime.fromisoformat(s)
    except Exception:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


@dataclass(frozen=True)
class MoviePilotSitesCache:
    base_url: str
    fetched_at: datetime
    sites: list[Site]

    @property
    def fetched_at_iso(self) -> str:
        return self.fetched_at.isoformat()

    def age_seconds(self, now: datetime) -> int:
        try:
            seconds = int((now - self.fetched_at).total_seconds())
        except Exception:
            return 0
        return max(0, seconds)


def build_cache(base_url: str, sites: list[Site], fetched_at: Optional[datetime] = None) -> dict[str, Any]:
    ts = fetched_at or datetime.now(timezone.utc)
    return {
        "version": MP_SITES_CACHE_VERSION,
        "base_url": _norm_base_url(base_url),
        "fetched_at": ts.isoformat(),
        "sites": [asdict(s) for s in sites],
    }


def parse_cache(payload: Any) -> Optional[MoviePilotSitesCache]:
    data = _safe_dict(payload)
    if int(data.get("version") or 0) != MP_SITES_CACHE_VERSION:
        return None
    fetched_at = _parse_dt(data.get("fetched_at"))
    if not fetched_at:
        return None
    base_url = _safe_str(data.get("base_url"))

    sites: list[Site] = []
    for raw in _safe_list(data.get("sites")):
        item = _safe_dict(raw)
        domain = _safe_str(item.get("domain")).lower()
        url = _safe_str(item.get("url"))
        if not domain or not url:
            continue
        sites.append(
            Site(
                id=_safe_int(item.get("id")),
                name=_safe_str(item.get("name")) or domain,
                domain=domain,
                url=url,
                ua=_safe_str(item.get("ua")) or None,
                cookie=_safe_str(item.get("cookie")) or None,
                cookie_override=None,
                authorization=None,
                did=None,
                is_active=bool(item.get("is_active", True)),
                template=None,
                registration_path=None,
                invite_path=None,
            )
        )
    return MoviePilotSitesCache(base_url=base_url, fetched_at=fetched_at, sites=sites)


def cache_expired(cache: MoviePilotSitesCache, now: datetime, ttl_seconds: int, *, base_url: str) -> bool:
    if _norm_base_url(base_url) and cache.base_url and _norm_base_url(base_url) != _norm_base_url(cache.base_url):
        return True
    if ttl_seconds <= 0:
        return True
    return cache.age_seconds(now) > ttl_seconds
