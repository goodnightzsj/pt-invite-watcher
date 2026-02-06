import types
import tempfile
import unittest
from contextlib import asynccontextmanager
from pathlib import Path
import logging

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
from pt_invite_watcher.kv_keys import SCAN_STATUS_KEY
from pt_invite_watcher.models import Site
from pt_invite_watcher.notify.manager import NotifierManager
from pt_invite_watcher.scanner_impl import Scanner
from pt_invite_watcher.scanner_run import PreparedRun
from pt_invite_watcher.storage.sqlite import SqliteStore


class ScannerRunTaskErrorsTest(unittest.IsolatedAsyncioTestCase):
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

    async def test_run_once_records_task_error(self) -> None:
        site = Site(id=1, name="Example", domain="example.com", url="https://example.com/")
        prepared = PreparedRun(
            sites=[site],
            cookie_mgr=object(),  # type: ignore[arg-type]
            mp_configured=False,
            mp_fields={
                "moviepilot_ok": False,
                "moviepilot_error": "",
                "moviepilot_source": "none",
                "moviepilot_cache_fetched_at": None,
                "moviepilot_cache_age_seconds": None,
                "moviepilot_cache_expired": False,
            },
            scan_lease_ttl_seconds=60,
            scan_lease_refresh_interval_seconds=20,
            scan_timeout=1,
            scan_user_agent=None,
            scan_trust_env=False,
            request_retry_delay_seconds=0,
        )

        @asynccontextmanager
        async def _fake_prepare_run_with_lease(
            self,
            started_at,
            *,
            ctx_reason: str = "scan_context",
            prefer_moviepilot_cache_if_fresh: bool = False,
        ):
            yield prepared

        @asynccontextmanager
        async def _dummy_http_client(self, *, timeout_seconds: int, trust_env: bool):
            yield object()

        async def _boom(self, client, site, now, cookie_mgr, default_user_agent, *, retry_delay_seconds: int) -> None:
            raise RuntimeError("boom")

        self._scanner._prepare_run_with_lease = types.MethodType(_fake_prepare_run_with_lease, self._scanner)  # type: ignore[assignment]
        self._scanner._new_http_client = types.MethodType(_dummy_http_client, self._scanner)  # type: ignore[assignment]
        self._scanner._check_one = types.MethodType(_boom, self._scanner)  # type: ignore[assignment]

        scan_logger = logging.getLogger("pt_invite_watcher.scanner")
        prev_level = scan_logger.level
        prev_propagate = scan_logger.propagate
        scan_logger.setLevel(logging.CRITICAL)
        scan_logger.propagate = False
        try:
            status = await self._scanner.run_once()
        finally:
            scan_logger.setLevel(prev_level)
            scan_logger.propagate = prev_propagate
        self.assertTrue(status.get("ok"))
        self.assertEqual(status.get("task_errors_count"), 1)
        self.assertIn("task_errors=", str(status.get("warning") or ""))

        events = await self._store.list_events(category="scan", limit=0)
        self.assertTrue(any(e.get("action") == "scan_task_error" for e in events))

        stored = await self._store.get_json(SCAN_STATUS_KEY, default=None)
        self.assertEqual((stored or {}).get("task_errors_count"), 1)


if __name__ == "__main__":
    unittest.main()
