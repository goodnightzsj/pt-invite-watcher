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
from pt_invite_watcher.kv_keys import APP_CONFIG_KEY, SITES_KEY
from pt_invite_watcher.models import Site
from pt_invite_watcher.providers.deps_status import DEPS_STATUS_KEY
from pt_invite_watcher.routes.sites import _sync_site_list_summary_after_sites_write
from pt_invite_watcher.site_list import SITE_LIST_SUMMARY_KEY


class _FakeNotifier:
    def __init__(self) -> None:
        self.sent: list[tuple[str, str]] = []

    async def send(self, title: str, text: str) -> None:
        self.sent.append((title, text))


class _FakeStore:
    def __init__(self) -> None:
        self.kv: dict[str, Any] = {}
        self.events: list[dict[str, Any]] = []
        self.snapshot_at: Optional[datetime] = None
        self.snapshot_sites: list[Site] = []

    async def get_json(self, key: str, default: Any) -> Any:
        return self.kv.get(key, default)

    async def set_json(self, key: str, value: Any) -> None:
        self.kv[key] = value

    async def add_event(self, **kwargs: Any) -> None:
        self.events.append(dict(kwargs))

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


class SitesSummarySyncTest(unittest.IsolatedAsyncioTestCase):
    async def test_sync_after_sites_write_uses_effective_sites_fallback(self) -> None:
        store = _FakeStore()
        store.kv[APP_CONFIG_KEY] = {}
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
                },
            },
        }

        svc = EffectiveSitesService(_settings(), store)  # type: ignore[arg-type]
        notifier = _FakeNotifier()

        class _Ctx:
            pass

        ctx = _Ctx()
        ctx.store = store
        ctx.notifier = notifier
        ctx.effective_sites = svc

        await _sync_site_list_summary_after_sites_write(ctx, reason="test")  # type: ignore[arg-type]

        summary = store.kv.get(SITE_LIST_SUMMARY_KEY) or {}
        items = (summary.get("items") or {}) if isinstance(summary, dict) else {}
        self.assertIn("mp.example", items)
        self.assertIn("manual.example", items)
        self.assertTrue(notifier.sent)
        self.assertTrue(any(e.get("action") == "site_list_changed" for e in store.events))


if __name__ == "__main__":
    unittest.main()

