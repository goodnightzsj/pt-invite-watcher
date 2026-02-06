import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from pt_invite_watcher.storage.sqlite import SqliteStore


class SqliteStoreLeaseTest(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self._db_path = Path(self._tmp.name) / "test.db"
        self._store = SqliteStore(self._db_path)
        await self._store.init()

    async def asyncTearDown(self) -> None:
        await self._store.close()
        self._tmp.cleanup()

    async def test_lease_acquire_and_block_other_owner(self) -> None:
        ok = await self._store.try_acquire_lease("lease_key", owner="owner-a", ttl_seconds=60)
        self.assertTrue(ok)

        ok2 = await self._store.try_acquire_lease("lease_key", owner="owner-b", ttl_seconds=60)
        self.assertFalse(ok2)

        ok3 = await self._store.try_acquire_lease("lease_key", owner="owner-a", ttl_seconds=60)
        self.assertTrue(ok3)

    async def test_lease_expired_allows_takeover(self) -> None:
        expired_at = (datetime.now(timezone.utc) - timedelta(seconds=10)).isoformat()
        await self._store.set_json("lease_key", {"owner": "owner-a", "expires_at": expired_at})

        ok = await self._store.try_acquire_lease("lease_key", owner="owner-b", ttl_seconds=60)
        self.assertTrue(ok)

    async def test_lease_release(self) -> None:
        ok = await self._store.try_acquire_lease("lease_key", owner="owner-a", ttl_seconds=60)
        self.assertTrue(ok)
        await self._store.release_lease("lease_key", owner="owner-a")

        ok2 = await self._store.try_acquire_lease("lease_key", owner="owner-b", ttl_seconds=60)
        self.assertTrue(ok2)

    async def test_add_event_detail_is_jsonable_for_hooks(self) -> None:
        seen: list[dict] = []

        def hook(evt: dict) -> None:
            seen.append(evt)

        self._store.on_event(hook)
        now = datetime(2026, 1, 1, 0, 0, 0, tzinfo=timezone.utc)
        await self._store.add_event(
            category="test",
            level="info",
            action="detail_jsonable",
            message="ok",
            detail={"when": now},
        )
        self.assertEqual(seen[0]["detail"]["when"], now.isoformat())


if __name__ == "__main__":
    unittest.main()
