import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from unittest.mock import patch

from pt_invite_watcher.config import (
    BasicAuthSettings,
    CookieCloudSettings,
    CookieSettings,
    DatabaseSettings,
    MoviePilotSettings,
    ScanSettings,
    Settings,
    WebSettings,
)
from pt_invite_watcher.effective_sites import EffectiveSitesService
from pt_invite_watcher.models import Site
from pt_invite_watcher.providers.moviepilot_sites_cache import MP_SITES_CACHE_KEY, build_cache
from pt_invite_watcher.providers.deps_status import fingerprint_moviepilot
from pt_invite_watcher.providers.deps_status import load_deps_status
from pt_invite_watcher.runtime_config_cache import RuntimeConfigCache


class _FakeStore:
    def __init__(self):
        self.kv: dict[str, Any] = {}

    async def get_json(self, key: str, default: Any) -> Any:
        return self.kv.get(key, default)

    async def set_json(self, key: str, value: Any) -> None:
        self.kv[key] = value

    async def load_sites_snapshot(self):
        return None, []


def _settings() -> Settings:
    return Settings(
        moviepilot=MoviePilotSettings(base_url="http://mp", username="u", password="p", otp_password=None),
        cookie=CookieSettings(
            source="auto",
            cookiecloud=CookieCloudSettings(base_url="", uuid="", password="", refresh_interval_seconds=300),
        ),
        scan=ScanSettings(interval_seconds=600, timeout_seconds=20, concurrency=8, user_agent="", trust_env=False),
        db=DatabaseSettings(path=Path("./data/ptiw.db")),
        web=WebSettings(host="0.0.0.0", port=8080, basic_auth=BasicAuthSettings(enabled=False, username="", password="")),
        log_level="INFO",
    )


class EffectiveSitesScanPreferCacheTest(unittest.IsolatedAsyncioTestCase):
    async def test_prefer_cache_uses_cache_when_fresh(self) -> None:
        store = _FakeStore()
        settings = _settings()
        rc_cache = RuntimeConfigCache(settings, store)
        svc = EffectiveSitesService(settings, store, runtime_config=rc_cache)

        now = datetime.now(timezone.utc)
        cached_sites = [Site(id=1, name="A", domain="a.example.com", url="https://a.example.com")]
        store.kv[MP_SITES_CACHE_KEY] = build_cache("http://mp", cached_sites, fetched_at=now)

        class _FakeClient:
            calls = 0

            def __init__(self, **kwargs: Any):
                pass

            async def list_sites(self, only_active: bool = True):
                _FakeClient.calls += 1
                return []

        with patch("pt_invite_watcher.providers.moviepilot_sites.MoviePilotClient", _FakeClient):
            res = await svc.load_for_scan(now=now, deps_status={"version": 1}, prefer_moviepilot_cache_if_fresh=True)
            self.assertEqual(res.moviepilot.source, "cache")

        self.assertEqual(_FakeClient.calls, 0)

    async def test_prefer_cache_allows_live_when_cache_expired(self) -> None:
        store = _FakeStore()
        settings = _settings()
        rc_cache = RuntimeConfigCache(settings, store)
        svc = EffectiveSitesService(settings, store, runtime_config=rc_cache)

        now = datetime.now(timezone.utc)
        stale_at = now - timedelta(days=2)
        store.kv[MP_SITES_CACHE_KEY] = build_cache("http://mp", [Site(id=1, name="Old", domain="old.example.com", url="https://old.example.com")], fetched_at=stale_at)

        live_sites = [Site(id=2, name="B", domain="b.example.com", url="https://b.example.com")]

        class _FakeClient:
            calls = 0

            def __init__(self, **kwargs: Any):
                pass

            async def list_sites(self, only_active: bool = True):
                _FakeClient.calls += 1
                return list(live_sites)

        with patch("pt_invite_watcher.providers.moviepilot_sites.MoviePilotClient", _FakeClient):
            res = await svc.load_for_scan(now=now, deps_status={"version": 1}, prefer_moviepilot_cache_if_fresh=True)
            self.assertEqual(res.moviepilot.source, "live")

        self.assertEqual(_FakeClient.calls, 1)

    async def test_prefer_cache_does_not_override_deps_backoff(self) -> None:
        store = _FakeStore()
        settings = _settings()
        rc_cache = RuntimeConfigCache(settings, store)
        svc = EffectiveSitesService(settings, store, runtime_config=rc_cache)

        now = datetime.now(timezone.utc)
        stale_at = now - timedelta(days=2)
        store.kv[MP_SITES_CACHE_KEY] = build_cache("http://mp", [Site(id=1, name="Old", domain="old.example.com", url="https://old.example.com")], fetched_at=stale_at)

        fp = fingerprint_moviepilot("http://mp")
        deps_status = load_deps_status(
            {
                "version": 1,
                "moviepilot": {
                    "ok": False,
                    "checked_at": now.isoformat(),
                    "next_retry_at": (now + timedelta(hours=1)).isoformat(),
                    "error": "fail",
                    "fingerprint": fp,
                },
            }
        )

        class _FakeClient:
            calls = 0

            def __init__(self, **kwargs: Any):
                pass

            async def list_sites(self, only_active: bool = True):
                _FakeClient.calls += 1
                return []

        with patch("pt_invite_watcher.providers.moviepilot_sites.MoviePilotClient", _FakeClient):
            res = await svc.load_for_scan(now=now, deps_status=deps_status, prefer_moviepilot_cache_if_fresh=True)
            self.assertNotEqual(res.moviepilot.source, "live")

        self.assertEqual(_FakeClient.calls, 0)


if __name__ == "__main__":
    unittest.main()
