from __future__ import annotations

import unittest

import aiosqlite

from pt_invite_watcher.storage.kv_store import get_json, set_json


class _FakeStore:
    def __init__(self, conn: aiosqlite.Connection):
        self._conn = conn

    def require_conn(self) -> aiosqlite.Connection:
        return self._conn


class KVStorePublicIfaceTest(unittest.IsolatedAsyncioTestCase):
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

    async def test_kv_helpers_use_public_require_conn(self) -> None:
        await set_json(self._store, "k1", {"a": 1})
        self.assertEqual(await get_json(self._store, "k1", default=None), {"a": 1})
        self.assertEqual(await get_json(self._store, "missing", default={"d": 1}), {"d": 1})


if __name__ == "__main__":
    unittest.main()

