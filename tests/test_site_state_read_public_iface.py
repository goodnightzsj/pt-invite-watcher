from __future__ import annotations

import json
import unittest
from dataclasses import dataclass
from datetime import datetime, timezone

import aiosqlite

from pt_invite_watcher.storage.site_state_read import (
    get_reachability_states,
    get_site_state,
    get_sites_extras,
    list_site_states,
    load_sites_snapshot,
)


@dataclass(frozen=True)
class _State:
    domain: str
    reachability_state: str
    registration_state: str
    invites_state: str
    invites_available: int | None
    last_checked_at: str
    last_changed_at: str | None


class _FakeStore:
    def __init__(self, conn: aiosqlite.Connection):
        self._conn = conn

    def require_conn(self) -> aiosqlite.Connection:
        return self._conn


class SiteStateReadPublicIfaceTest(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self._conn = await aiosqlite.connect(":memory:")
        self._conn.row_factory = aiosqlite.Row
        await self._conn.execute(
            """
            CREATE TABLE site_state (
              domain TEXT PRIMARY KEY,
              name TEXT,
              url TEXT,
              engine TEXT,
              registration_state TEXT NOT NULL,
              invites_state TEXT NOT NULL,
              invites_available INTEGER,
              last_checked_at TEXT NOT NULL,
              last_changed_at TEXT,
              last_evidence TEXT NOT NULL
            );
            """
        )

        evidence = {
            "reachability": {"state": "up"},
            "invites": {"evidence": {"url": "https://example.com/invite.php?id=123"}},
            "site": {"id": 1, "ua": "UA", "cookie": "cookie=1", "is_active": True},
        }
        now = datetime(2026, 1, 1, 0, 0, 0, tzinfo=timezone.utc)
        await self._conn.execute(
            """
            INSERT INTO site_state(
              domain, name, url, engine,
              registration_state, invites_state, invites_available,
              last_checked_at, last_changed_at, last_evidence
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "example.com",
                "Example",
                "https://example.com/",
                "nexusphp",
                "open",
                "open",
                3,
                now.isoformat(),
                None,
                json.dumps(evidence),
            ),
        )
        await self._conn.commit()
        self._store = _FakeStore(self._conn)

    async def asyncTearDown(self) -> None:
        await self._conn.close()

    async def test_site_state_read_helpers_use_public_require_conn(self) -> None:
        state = await get_site_state(self._store, "example.com", state_cls=_State)
        self.assertIsNotNone(state)
        assert state is not None
        self.assertEqual(state.domain, "example.com")
        self.assertEqual(state.reachability_state, "up")

        rows = await list_site_states(self._store)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["domain"], "example.com")

        reach = await get_reachability_states(self._store, ["example.com", "missing.com"])
        self.assertEqual(reach.get("example.com"), "up")
        self.assertNotIn("missing.com", reach)

        extras = await get_sites_extras(self._store, ["example.com"])
        self.assertEqual(extras["example.com"]["reachability_state"], "up")
        self.assertEqual(extras["example.com"]["invite_uid"], "123")

        snap_at, sites = await load_sites_snapshot(self._store)
        self.assertIsNotNone(snap_at)
        self.assertEqual(len(sites), 1)
        self.assertEqual(sites[0].domain, "example.com")
        self.assertEqual(sites[0].ua, "UA")


if __name__ == "__main__":
    unittest.main()
