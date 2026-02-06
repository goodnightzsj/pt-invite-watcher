import tempfile
import unittest
from pathlib import Path

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
from pt_invite_watcher.notify.manager import NotifierManager
from pt_invite_watcher.scanner import Scanner
from pt_invite_watcher.storage.sqlite import SqliteStore


class ScannerRunOneNotFoundTest(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self._db_path = Path(self._tmp.name) / "test.db"
        self._store = SqliteStore(self._db_path)
        await self._store.init()

        # Make tests deterministic by disabling background flush.
        self._store._scan_log_flush_interval_seconds = 3600  # type: ignore[attr-defined]

        self._settings = Settings(
            moviepilot=MoviePilotSettings(base_url="", username="", password="", otp_password=None),
            cookie=CookieSettings(
                source="auto",
                cookiecloud=CookieCloudSettings(base_url="", uuid="", password="", refresh_interval_seconds=300),
            ),
            scan=ScanSettings(interval_seconds=600, timeout_seconds=2, concurrency=8, user_agent="", trust_env=False),
            db=DatabaseSettings(path=self._db_path),
            web=WebSettings(host="0.0.0.0", port=8080, basic_auth=BasicAuthSettings(enabled=False, username="", password="")),
            log_level="INFO",
        )
        self._notifier = NotifierManager(self._store, self._settings)
        self._scanner = Scanner(self._settings, self._store, self._notifier)

    async def asyncTearDown(self) -> None:
        await self._store.close()
        self._tmp.cleanup()

    async def test_run_one_not_found_does_not_crash(self) -> None:
        res = await self._scanner.run_one("example.com")
        self.assertFalse(res.get("ok"))
        self.assertEqual(res.get("site_count"), 0)
        self.assertIn("site not found", str(res.get("error") or ""))
        self.assertEqual(res.get("moviepilot_source"), "none")
        self.assertIn("last_run_at", res)

        events = await self._store.list_events(category="scan", limit=0)
        self.assertTrue(any(e.get("action") == "scan_one_not_found" for e in events))


if __name__ == "__main__":
    unittest.main()

