import unittest
from pathlib import Path
from typing import Any

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
from pt_invite_watcher.runtime_config_loader import get_runtime_config
from pt_invite_watcher.runtime_config import load_runtime_config


def _settings() -> Settings:
    return Settings(
        moviepilot=MoviePilotSettings(base_url="http://moviepilot", username="u", password="p", otp_password=None),
        cookie=CookieSettings(
            source="auto",
            cookiecloud=CookieCloudSettings(base_url="http://cookiecloud", uuid="uuid", password="ccp", refresh_interval_seconds=300),
        ),
        scan=ScanSettings(interval_seconds=600, timeout_seconds=20, concurrency=8, user_agent="", trust_env=False),
        db=DatabaseSettings(path=Path("./data/ptiw.db")),
        web=WebSettings(
            host="0.0.0.0",
            port=8080,
            basic_auth=BasicAuthSettings(enabled=False, username="", password=""),
        ),
        log_level="INFO",
    )


class RuntimeConfigLoaderTest(unittest.IsolatedAsyncioTestCase):
    async def test_prefers_runtime_config_cache(self) -> None:
        settings = _settings()
        sentinel = load_runtime_config(settings, {"scan": {"interval_seconds": 123}})

        class _BadStore:
            async def get_json(self, key: str, default: Any) -> Any:
                raise AssertionError("store.get_json should not be called when runtime_config is provided")

        class _Cache:
            async def get(self):
                return sentinel

        rc = await get_runtime_config(settings, _BadStore(), runtime_config=_Cache())
        self.assertIs(rc, sentinel)

    async def test_falls_back_to_store_when_no_cache(self) -> None:
        settings = _settings()

        class _Store:
            def __init__(self):
                self.kv: dict[str, Any] = {}

            async def get_json(self, key: str, default: Any) -> Any:
                return self.kv.get(key, default)

        store = _Store()
        rc = await get_runtime_config(settings, store, runtime_config=None)
        self.assertEqual(rc.scan.interval_seconds, settings.scan.interval_seconds)
        self.assertEqual(rc.moviepilot.base_url, settings.moviepilot.base_url)


if __name__ == "__main__":
    unittest.main()

