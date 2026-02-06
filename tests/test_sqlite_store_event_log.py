import tempfile
import unittest
from pathlib import Path

from pt_invite_watcher.storage.sqlite import SqliteStore


class SqliteStoreEventLogTest(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self._db_path = Path(self._tmp.name) / "test.db"
        self._store = SqliteStore(self._db_path)
        await self._store.init()

    async def asyncTearDown(self) -> None:
        await self._store.close()
        self._tmp.cleanup()

    async def test_list_events_enriches_page_from_detail_url(self) -> None:
        await self._store.add_event(
            category="scan",
            level="info",
            action="inv_check",
            message="check invite",
            domain="example.com",
            detail={"url": "https://example.com/invite.php"},
        )
        rows = await self._store.list_events(limit=1)
        self.assertEqual(len(rows), 1)
        detail = rows[0]["detail"]
        self.assertIsInstance(detail, dict)
        self.assertEqual(detail.get("page", {}).get("kind"), "invite")
        self.assertEqual(detail.get("page", {}).get("url"), "https://example.com/invite.php")

    async def test_list_events_enriches_page_from_action_when_url_missing(self) -> None:
        await self._store.add_event(
            category="scan",
            level="info",
            action="inv_usercp_probe",
            message="check usercp",
            domain="example.com",
            detail={"source": "usercp"},
        )
        rows = await self._store.list_events(limit=1)
        self.assertEqual(len(rows), 1)
        detail = rows[0]["detail"]
        self.assertIsInstance(detail, dict)
        self.assertEqual(detail.get("page", {}).get("kind"), "usercp")

    async def test_add_event_max_rows_cleanup_keeps_last_100(self) -> None:
        # keep = max(100, max_rows) => always at least 100.
        for i in range(110):
            await self._store.add_event(
                category="test",
                level="info",
                action="spam",
                message=f"row {i}",
                max_rows=1,
            )
        rows = await self._store.list_events(limit=0)
        self.assertEqual(len(rows), 100)

    async def test_list_events_parses_legacy_python_literal_detail(self) -> None:
        # Simulate a legacy/dirty row whose detail was stored as a Python literal.
        async with self._store.write_transaction() as conn:
            await conn.execute(
                """
                INSERT INTO event_log(ts, category, level, action, domain, message, detail)
                VALUES(?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    "2026-01-01T00:00:00+00:00",
                    "scan",
                    "info",
                    "legacy_detail",
                    "example.com",
                    "legacy detail row",
                    "  {'a': 1, 'b': [2, 3]}",
                ),
            )

        rows = await self._store.list_events(limit=1)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["action"], "legacy_detail")
        self.assertEqual(rows[0]["detail"], {"a": 1, "b": [2, 3]})


if __name__ == "__main__":
    unittest.main()
