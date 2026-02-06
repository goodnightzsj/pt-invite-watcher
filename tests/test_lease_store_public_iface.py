from __future__ import annotations

import unittest
from contextlib import asynccontextmanager

import aiosqlite

from pt_invite_watcher.storage.lease_store import release_lease, try_acquire_lease


class _FakeStore:
    def __init__(self, conn: aiosqlite.Connection):
        self._conn = conn

    @asynccontextmanager
    async def lease_operation(self):
        yield self._conn


class LeaseStorePublicIfaceTest(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self._conn = await aiosqlite.connect(":memory:")
        self._conn.row_factory = aiosqlite.Row
        await self._conn.execute(
            """
            CREATE TABLE kv (
              key TEXT PRIMARY KEY,
              value TEXT NOT NULL,
              updated_at TEXT NOT NULL
            );
            """
        )
        await self._conn.commit()
        self._store = _FakeStore(self._conn)

    async def asyncTearDown(self) -> None:
        await self._conn.close()

    async def test_lease_helpers_use_public_lease_operation(self) -> None:
        key = "test_lease"
        ttl = 1000

        self.assertTrue(await try_acquire_lease(self._store, key, owner="a", ttl_seconds=ttl))
        self.assertFalse(await try_acquire_lease(self._store, key, owner="b", ttl_seconds=ttl))
        self.assertTrue(await try_acquire_lease(self._store, key, owner="a", ttl_seconds=ttl))

        await release_lease(self._store, key, owner="b")
        self.assertFalse(await try_acquire_lease(self._store, key, owner="b", ttl_seconds=ttl))

        await release_lease(self._store, key, owner="a")
        self.assertTrue(await try_acquire_lease(self._store, key, owner="b", ttl_seconds=ttl))


if __name__ == "__main__":
    unittest.main()

