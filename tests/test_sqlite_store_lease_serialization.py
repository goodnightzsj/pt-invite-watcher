import asyncio
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from pt_invite_watcher.storage.sqlite import SqliteStore


class SqliteStoreLeaseSerializationTest(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self._db_path = Path(self._tmp.name) / "test.db"
        self._store = SqliteStore(self._db_path)
        await self._store.init()

    async def asyncTearDown(self) -> None:
        await self._store.close()
        self._tmp.cleanup()

    async def test_lease_operation_serialized_with_write_transaction(self) -> None:
        lease_conn = self._store.require_lease_conn()
        cur = await lease_conn.execute("PRAGMA busy_timeout=1;")
        await cur.close()

        txn_started = asyncio.Event()
        release_txn = asyncio.Event()

        async def _hold_write() -> None:
            async with self._store.write_transaction() as conn:
                now = datetime.now(timezone.utc).isoformat()
                cur2 = await conn.execute(
                    """
                    INSERT INTO kv(key, value, updated_at) VALUES(?, ?, ?)
                    ON CONFLICT(key) DO UPDATE SET value=excluded.value, updated_at=excluded.updated_at
                    """,
                    ("_hold_write_lock", "{}", now),
                )
                await cur2.close()
                txn_started.set()
                await release_txn.wait()

        writer = asyncio.create_task(_hold_write())
        await asyncio.wait_for(txn_started.wait(), timeout=2)

        lease_task = asyncio.create_task(
            self._store.try_acquire_lease("lease_key", owner="owner-a", ttl_seconds=60),
        )
        done, pending = await asyncio.wait({lease_task}, timeout=0.2)
        self.assertIn(lease_task, pending, "lease should wait for write_transaction instead of failing fast")

        release_txn.set()
        ok = await asyncio.wait_for(lease_task, timeout=2)
        await asyncio.wait_for(writer, timeout=2)
        self.assertTrue(ok)


if __name__ == "__main__":
    unittest.main()

