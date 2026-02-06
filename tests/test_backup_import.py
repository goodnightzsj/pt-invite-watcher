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
from pt_invite_watcher.kv_keys import APP_CONFIG_KEY, SCAN_HINT_KEY, SCAN_STATUS_KEY, SITES_KEY
from pt_invite_watcher.models import Site
from pt_invite_watcher.providers.deps_status import DEPS_STATUS_KEY
from pt_invite_watcher.routes.backup import api_backup_import
from pt_invite_watcher.runtime_config_cache import RuntimeConfigCache
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


class BackupImportTest(unittest.IsolatedAsyncioTestCase):
    async def test_import_invalidates_runtime_config_cache(self) -> None:
        store = _FakeStore()
        store.kv[APP_CONFIG_KEY] = {"scan": {"interval_seconds": 600}}

        settings = _settings()
        cache = RuntimeConfigCache(settings, store, ttl_seconds=60)  # type: ignore[arg-type]

        rc1 = await cache.get()
        self.assertEqual(rc1.scan.interval_seconds, 600)

        class _Ctx:
            pass

        ctx = _Ctx()
        ctx.store = store
        ctx.runtime_config = cache

        await api_backup_import(ctx, payload={"data": {"app_config": {"scan": {"interval_seconds": 120}}}}, mode="replace")  # type: ignore[arg-type]

        rc2 = await cache.get()
        self.assertEqual(rc2.scan.interval_seconds, 120)
        self.assertIn(SCAN_HINT_KEY, store.kv)
        self.assertIn(SCAN_STATUS_KEY, store.kv)

    async def test_import_sites_syncs_effective_site_summary(self) -> None:
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

        svc = EffectiveSitesService(_settings(), store)  # type: ignore[arg-type]
        notifier = _FakeNotifier()

        class _Ctx:
            pass

        ctx = _Ctx()
        ctx.store = store
        ctx.effective_sites = svc
        ctx.notifier = notifier

        await api_backup_import(
            ctx,  # type: ignore[arg-type]
            payload={
                "data": {
                    "sites": {
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
                }
            },
            mode="replace",
        )

        summary = store.kv.get(SITE_LIST_SUMMARY_KEY) or {}
        items = (summary.get("items") or {}) if isinstance(summary, dict) else {}
        self.assertIn("mp.example", items)
        self.assertIn("manual.example", items)
        self.assertTrue(store.kv.get(SITES_KEY))
        self.assertTrue(notifier.sent)
        self.assertTrue(any(e.get("action") == "site_list_changed" for e in store.events))


if __name__ == "__main__":
    unittest.main()

