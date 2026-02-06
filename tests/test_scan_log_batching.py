import asyncio
import tempfile
import unittest
from pathlib import Path

from pt_invite_watcher.storage.sqlite import SqliteStore


class ScanLogBatchingTest(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self._db_path = Path(self._tmp.name) / "test.db"
        self._store = SqliteStore(self._db_path)
        await self._store.init()

    async def asyncTearDown(self) -> None:
        await self._store.close()
        self._tmp.cleanup()

    async def test_scan_info_logs_are_buffered_and_flushed_in_batch(self) -> None:
        hooks: list[dict] = []

        def _hook(evt: dict) -> None:
            hooks.append(evt)

        self._store.on_event(_hook)

        tasks = [
            asyncio.create_task(
                self._store.add_event(category="scan", level="info", action="step", message=f"m{i}", domain="example.com")
            )
            for i in range(50)
        ]
        await asyncio.gather(*tasks)

        self.assertEqual(getattr(self._store, "_scan_log_flush_count", 0), 0)
        self.assertEqual(hooks, [])

        await self._store.flush_scan_logs(max_items=1000)

        self.assertEqual(getattr(self._store, "_scan_log_flush_count", 0), 50)
        self.assertEqual(len(hooks), 50)

        rows = await self._store.list_events(category="scan", domain="example.com", limit=0)
        self.assertGreaterEqual(len(rows), 50)


if __name__ == "__main__":
    unittest.main()

