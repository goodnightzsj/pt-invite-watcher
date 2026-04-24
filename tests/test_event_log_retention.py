"""Tests for `prune_events_older_than`.

Pins the contract the scheduler relies on to keep `event_log` from growing
unbounded on long-lived installs: timestamp column is an ISO-8601 string
sortable lexicographically, and the DELETE scopes by `ts < cutoff`.
"""
from __future__ import annotations

import asyncio
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from pt_invite_watcher.storage.event_log_store import add_event, list_events, prune_events_older_than
from pt_invite_watcher.storage.sqlite import SqliteStore


class EventLogRetentionTest(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self._tmp.close()
        self.db_path = Path(self._tmp.name)

    def tearDown(self) -> None:
        try:
            self.db_path.unlink()
        except FileNotFoundError:
            pass

    def _run(self, coro):
        return asyncio.run(coro)

    def test_prune_deletes_rows_older_than_cutoff(self) -> None:
        async def body() -> None:
            store = SqliteStore(self.db_path)
            await store.init()
            try:
                # Seed three events, all identical except for `ts` which we
                # manually override via a direct insert to exercise the pruner
                # without clock-sleeping. add_event uses `now()` so all three
                # would otherwise share timestamps.
                conn = store._require_conn() if hasattr(store, "_require_conn") else None
                async with store.write_transaction() as conn:
                    await conn.execute(
                        "INSERT INTO event_log(ts, category, level, action, domain, message, detail) VALUES (?,?,?,?,?,?,?)",
                        ("2026-01-01T00:00:00+00:00", "scan", "info", "test_old", "a.example", "old", None),
                    )
                    await conn.execute(
                        "INSERT INTO event_log(ts, category, level, action, domain, message, detail) VALUES (?,?,?,?,?,?,?)",
                        ("2026-06-15T12:00:00+00:00", "scan", "info", "test_mid", "b.example", "mid", None),
                    )
                    await conn.execute(
                        "INSERT INTO event_log(ts, category, level, action, domain, message, detail) VALUES (?,?,?,?,?,?,?)",
                        ("2026-12-31T23:59:59+00:00", "scan", "info", "test_new", "c.example", "new", None),
                    )

                # Cutoff between old and mid: old should go, mid + new stay.
                removed = await prune_events_older_than(store, "2026-04-01T00:00:00+00:00")
                self.assertEqual(removed, 1)

                remaining = await list_events(store)
                actions = sorted(e["action"] for e in remaining)
                self.assertEqual(actions, ["test_mid", "test_new"])
            finally:
                await store.close()

        self._run(body())

    def test_prune_returns_zero_when_nothing_old(self) -> None:
        async def body() -> None:
            store = SqliteStore(self.db_path)
            await store.init()
            try:
                await add_event(store, category="scan", level="info", action="fresh", domain="a", message="m")
                # Cutoff in the distant past — every row is newer, so nothing pruned.
                cutoff = datetime(2020, 1, 1, tzinfo=timezone.utc).isoformat()
                removed = await prune_events_older_than(store, cutoff)
                self.assertEqual(removed, 0)
                self.assertEqual(len(await list_events(store)), 1)
            finally:
                await store.close()

        self._run(body())

    def test_prune_sweeps_all_when_cutoff_is_future(self) -> None:
        async def body() -> None:
            store = SqliteStore(self.db_path)
            await store.init()
            try:
                await add_event(store, category="scan", level="info", action="a", domain="x", message="m")
                await add_event(store, category="scan", level="info", action="b", domain="y", message="m")
                # Cutoff far in the future — all rows older than it.
                cutoff = (datetime.now(timezone.utc) + timedelta(days=365)).isoformat()
                removed = await prune_events_older_than(store, cutoff)
                self.assertEqual(removed, 2)
                self.assertEqual(len(await list_events(store)), 0)
            finally:
                await store.close()

        self._run(body())


if __name__ == "__main__":
    unittest.main()
