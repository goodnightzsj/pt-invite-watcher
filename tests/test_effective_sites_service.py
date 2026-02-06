import unittest
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

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
from pt_invite_watcher.providers.deps_status import DEPS_STATUS_KEY
from pt_invite_watcher.site_list import SITE_LIST_SUMMARY_KEY
from pt_invite_watcher.kv_keys import SITES_KEY


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


def _settings() -> Settings:
    return Settings(
        moviepilot=MoviePilotSettings(base_url="", username="", password="", otp_password=None),
        cookie=CookieSettings(
            source="auto",
            cookiecloud=CookieCloudSettings(base_url="", uuid="", password="", refresh_interval_seconds=300),
        ),
        scan=ScanSettings(interval_seconds=600, timeout_seconds=20, concurrency=8, user_agent="", trust_env=False),
        db=DatabaseSettings(path=Path("./data/ptiw.db")),
        web=WebSettings(host="0.0.0.0", port=8080, basic_auth=BasicAuthSettings(enabled=False, username="", password="")),
        log_level="INFO",
    )


class EffectiveSitesServiceTest(unittest.IsolatedAsyncioTestCase):
    async def test_dashboard_and_sites_fallback_summary_and_merge(self) -> None:
        store = _FakeStore()
        store.kv[DEPS_STATUS_KEY] = {"version": 1}

        now = datetime.now(timezone.utc)
        store.kv[SITE_LIST_SUMMARY_KEY] = {
            "version": 1,
            "updated_at": now.isoformat(),
            "items": {
                "mp.example": {
                    "domain": "mp.example",
                    "name": "MP",
                    "url": "https://mp.example",
                    "template": "nexusphp",
                    "registration_path": "signup.php",
                    "invite_path": "invite.php",
                    "source": "moviepilot",
                }
            },
        }
        store.kv[SITES_KEY] = {
            "version": 1,
            "entries": {
                "mp.example": {"mode": "override", "name": "Local", "template": "nexusphp"},
                "manual.example": {
                    "mode": "manual",
                    "name": "Manual",
                    "url": "https://manual.example",
                    "template": "custom",
                    "registration_path": "signup",
                    "invite_path": "invite",
                },
            },
        }

        svc = EffectiveSitesService(_settings(), store)  # type: ignore[arg-type]

        dash = await svc.load_for_dashboard(now=now)
        sites = await svc.load_for_sites(now=now, allow_live=True, force_live=False)

        for res in (dash, sites):
            self.assertEqual(res.moviepilot.source, "summary")
            by_domain = {s.domain: s for s in res.sites}
            self.assertIn("mp.example", by_domain)
            self.assertIn("manual.example", by_domain)
            self.assertEqual(by_domain["mp.example"].name, "Local")
            self.assertEqual(by_domain["manual.example"].template, "custom")

    async def test_scan_requires_credentials_for_fallback(self) -> None:
        store = _FakeStore()
        store.kv[DEPS_STATUS_KEY] = {"version": 1}

        now = datetime.now(timezone.utc)
        store.kv[SITE_LIST_SUMMARY_KEY] = {
            "version": 1,
            "updated_at": now.isoformat(),
            "items": {
                "mp.example": {
                    "domain": "mp.example",
                    "name": "MP",
                    "url": "https://mp.example",
                    "template": "nexusphp",
                    "registration_path": "signup.php",
                    "invite_path": "invite.php",
                    "source": "moviepilot",
                }
            },
        }
        store.kv[SITES_KEY] = {
            "version": 1,
            "entries": {
                "manual.example": {
                    "mode": "manual",
                    "name": "Manual",
                    "url": "https://manual.example",
                    "template": "custom",
                    "registration_path": "signup",
                    "invite_path": "invite",
                }
            },
        }

        svc = EffectiveSitesService(_settings(), store)  # type: ignore[arg-type]
        res = await svc.load_for_scan(now=now, deps_status={"version": 1})
        self.assertEqual(res.moviepilot.source, "none")
        self.assertFalse(res.moviepilot.attempted)

        by_domain = {s.domain: s for s in res.sites}
        self.assertIn("manual.example", by_domain)
        self.assertNotIn("mp.example", by_domain)


if __name__ == "__main__":
    unittest.main()

