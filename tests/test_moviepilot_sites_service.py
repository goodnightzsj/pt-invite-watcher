import unittest
from dataclasses import asdict
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from pt_invite_watcher.models import Site
from pt_invite_watcher.providers.deps_status import DEPS_STATUS_KEY
from pt_invite_watcher.providers.moviepilot_sites import MoviePilotSitesService
from pt_invite_watcher.providers.moviepilot_sites_cache import MP_SITES_CACHE_KEY, build_cache
from pt_invite_watcher.site_list import SITE_LIST_SUMMARY_KEY


class _FakeStore:
    def __init__(self):
        self.kv: dict[str, Any] = {}
        self.snapshot_at: Optional[datetime] = None
        self.snapshot_sites: list[Site] = []

    async def get_json(self, key: str, default: Any) -> Any:
        return self.kv.get(key, default)

    async def set_json(self, key: str, value: Any) -> None:
        self.kv[key] = value

    async def load_sites_snapshot(self):
        return self.snapshot_at, list(self.snapshot_sites)


class MoviePilotSitesServiceTest(unittest.IsolatedAsyncioTestCase):
    async def test_fallback_cache(self) -> None:
        store = _FakeStore()
        store.kv[DEPS_STATUS_KEY] = {"version": 1}

        now = datetime.now(timezone.utc)
        sites = [
            Site(
                id=1,
                name="S",
                domain="example.com",
                url="https://example.com",
                ua=None,
                cookie=None,
                cookie_override=None,
                authorization=None,
                did=None,
                is_active=True,
            )
        ]
        store.kv[MP_SITES_CACHE_KEY] = build_cache("http://moviepilot", sites, fetched_at=now - timedelta(seconds=10))

        svc = MoviePilotSitesService(store)  # type: ignore[arg-type]
        res = await svc.load_sites(
            now=now,
            base_url="http://moviepilot",
            cache_ttl_seconds=60,
            allow_live=False,
            require_credentials=False,
        )
        self.assertEqual(res.source, "cache")
        self.assertFalse(res.attempted)
        self.assertEqual([asdict(s) for s in res.sites], [asdict(s) for s in sites])
        self.assertEqual(res.cache_expired, False)

    async def test_fallback_state_snapshot_when_cache_expired(self) -> None:
        store = _FakeStore()
        store.kv[DEPS_STATUS_KEY] = {"version": 1}

        now = datetime.now(timezone.utc)
        old_sites = [
            Site(
                id=1,
                name="Old",
                domain="old.example",
                url="https://old.example",
                ua=None,
                cookie=None,
                cookie_override=None,
                authorization=None,
                did=None,
                is_active=True,
            )
        ]
        store.kv[MP_SITES_CACHE_KEY] = build_cache("http://moviepilot", old_sites, fetched_at=now - timedelta(seconds=999))

        snap_at = now - timedelta(seconds=10)
        snap_sites = [
            Site(
                id=2,
                name="Snap",
                domain="snap.example",
                url="https://snap.example",
                ua=None,
                cookie=None,
                cookie_override=None,
                authorization=None,
                did=None,
                is_active=True,
            )
        ]
        store.snapshot_at = snap_at
        store.snapshot_sites = snap_sites

        svc = MoviePilotSitesService(store)  # type: ignore[arg-type]
        res = await svc.load_sites(
            now=now,
            base_url="http://moviepilot",
            cache_ttl_seconds=60,
            allow_live=False,
            require_credentials=False,
        )
        self.assertEqual(res.source, "state")
        self.assertEqual([asdict(s) for s in res.sites], [asdict(s) for s in snap_sites])
        self.assertEqual(res.cache_expired, False)

    async def test_fallback_summary(self) -> None:
        store = _FakeStore()
        store.kv[DEPS_STATUS_KEY] = {"version": 1}

        now = datetime.now(timezone.utc)
        store.kv[SITE_LIST_SUMMARY_KEY] = {
            "version": 1,
            "updated_at": (now - timedelta(seconds=10)).isoformat(),
            "items": {
                "mp.example": {
                    "domain": "mp.example",
                    "name": "MP",
                    "url": "https://mp.example",
                    "template": "nexusphp",
                    "registration_path": "signup.php",
                    "invite_path": "invite.php",
                    "source": "moviepilot",
                },
                "manual.example": {
                    "domain": "manual.example",
                    "name": "Manual",
                    "url": "https://manual.example",
                    "template": "custom",
                    "registration_path": "signup",
                    "invite_path": "invite",
                    "source": "manual",
                },
            },
        }

        svc = MoviePilotSitesService(store)  # type: ignore[arg-type]
        res = await svc.load_sites(
            now=now,
            base_url="",
            cache_ttl_seconds=60,
            allow_live=False,
            require_credentials=False,
        )
        self.assertEqual(res.source, "summary")
        domains = {s.domain for s in res.sites}
        self.assertIn("mp.example", domains)
        self.assertNotIn("manual.example", domains)


if __name__ == "__main__":
    unittest.main()
