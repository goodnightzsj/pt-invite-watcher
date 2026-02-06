import asyncio
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from pt_invite_watcher.storage.sqlite import SqliteStore


class ScanLogResyncTest(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self._db_path = Path(self._tmp.name) / "test.db"
        self._store = SqliteStore(self._db_path)
        await self._store.init()

        # Make tests deterministic by disabling background flush.
        self._store._scan_log_flush_interval_seconds = 3600  # type: ignore[attr-defined]

    async def asyncTearDown(self) -> None:
        await self._store.close()
        self._tmp.cleanup()

    async def test_buffer_full_triggers_sync_flush_instead_of_drop(self) -> None:
        self._store._scan_log_buffer_max = 2  # type: ignore[attr-defined]

        await self._store.add_event(category="scan", level="info", action="a", message="m1")
        await self._store.add_event(category="scan", level="info", action="a", message="m2")
        before = getattr(self._store, "_scan_log_flush_count", 0)

        # Third enqueue should apply backpressure and flush existing buffered logs.
        await self._store.add_event(category="scan", level="info", action="a", message="m3")
        after = getattr(self._store, "_scan_log_flush_count", 0)
        self.assertGreater(after, before)

        await self._store.flush_scan_logs(max_items=1000)
        rows = await self._store.list_events(category="scan", limit=0)
        self.assertGreaterEqual(len(rows), 3)

    async def test_flush_failure_requests_logs_resync(self) -> None:
        reasons: list[str] = []

        def _hook(reason: str) -> None:
            reasons.append(reason)

        self._store.on_logs_resync(_hook)  # type: ignore[attr-defined]
        self._store._logs_resync_throttle_seconds = 0  # type: ignore[attr-defined]
        self._store._scan_log_buffer_max = 2  # type: ignore[attr-defined]
        self._store._scan_log_enqueue_max_wait_seconds = 0.01  # type: ignore[attr-defined]
        self._store._scan_log_enqueue_retry_sleep_seconds = 0  # type: ignore[attr-defined]

        await self._store.add_event(category="scan", level="info", action="a", message="m1")
        await self._store.add_event(category="scan", level="info", action="a", message="m2")

        with patch.object(self._store, "_require_write_conn", side_effect=RuntimeError("boom")):
            await self._store.add_event(category="scan", level="info", action="a", message="m3")

        # Ensure hook is called (either due to flush failure, or buffer overflow, or both).
        self.assertTrue(reasons)


if __name__ == "__main__":
    unittest.main()

