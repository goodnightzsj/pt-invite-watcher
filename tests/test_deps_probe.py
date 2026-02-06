import unittest
from datetime import datetime, timezone
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
from pt_invite_watcher.providers.deps_probe import probe_dependencies
from pt_invite_watcher.providers.deps_status import DEPS_STATUS_KEY


class _FakeStore:
    def __init__(self):
        self.kv: dict[str, Any] = {}

    async def get_json(self, key: str, default: Any) -> Any:
        return self.kv.get(key, default)

    async def set_json(self, key: str, value: Any) -> None:
        self.kv[key] = value


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


class DepsProbeTest(unittest.IsolatedAsyncioTestCase):
    async def test_probe_without_credentials(self) -> None:
        store = _FakeStore()
        now = datetime.now(timezone.utc)

        res = await probe_dependencies(store, _settings(), now=now)  # type: ignore[arg-type]
        self.assertTrue(res.get("ok"))
        self.assertFalse(res.get("moviepilot_attempted"))
        self.assertFalse(res.get("cookiecloud_attempted"))
        self.assertIn(DEPS_STATUS_KEY, store.kv)


if __name__ == "__main__":
    unittest.main()

