import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from pt_invite_watcher.storage.sqlite import SqliteStore


class EventLogStoreLegacyDetailTest(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self._db_path = Path(self._tmp.name) / "test.db"
        self._store = SqliteStore(self._db_path)
        await self._store.init()

    async def asyncTearDown(self) -> None:
        await self._store.close()
        self._tmp.cleanup()

    async def test_list_events_parses_python_literal_detail_dict(self) -> None:
        ts = datetime.now(timezone.utc).isoformat()
        async with self._store.write_transaction() as conn:
            await conn.execute(
                """
                INSERT INTO event_log(ts, category, level, action, domain, message, detail)
                VALUES(?, ?, ?, ?, ?, ?, ?)
                """,
                (ts, "misc", "info", "a", "example.com", "m", "{'a': 1, 'b': [2, 3]}"),
            )

        items = await self._store.list_events(limit=1)
        self.assertEqual(len(items), 1)
        self.assertIsInstance(items[0].get("detail"), dict)
        self.assertEqual(items[0]["detail"]["a"], 1)
        self.assertEqual(items[0]["detail"]["b"], [2, 3])


if __name__ == "__main__":
    unittest.main()

