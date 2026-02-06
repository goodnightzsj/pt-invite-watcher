import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from pt_invite_watcher.models import AspectResult, Evidence, ReachabilityResult, Site, SiteCheckResult
from pt_invite_watcher.storage.sqlite import SqliteStore


class SqliteStoreSiteStateTest(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self._db_path = Path(self._tmp.name) / "test.db"
        self._store = SqliteStore(self._db_path)
        await self._store.init()

    async def asyncTearDown(self) -> None:
        await self._store.close()
        self._tmp.cleanup()

    async def test_site_state_roundtrip_and_helpers(self) -> None:
        site = Site(
            id=123,
            name="Example",
            domain="example.com",
            url="https://example.com",
            ua="UA",
            cookie="cookie",
            is_active=True,
        )
        now = datetime(2026, 1, 1, tzinfo=timezone.utc)
        result = SiteCheckResult(
            site=site,
            engine="nexusphp",
            reachability=ReachabilityResult(
                state="up",
                evidence=Evidence(url=site.url, http_status=200, reason="probe_ok"),
            ),
            registration=AspectResult(
                state="unknown",
                evidence=Evidence(url=f"{site.url}/signup.php", http_status=404, reason="registration_unknown"),
            ),
            invites=AspectResult(
                state="open",
                available=2,
                permanent=None,
                temporary=None,
                evidence=Evidence(url=f"{site.url}/invite.php?id=42", http_status=200, reason="invites_ok"),
            ),
            checked_at=now,
        )
        await self._store.save_site_result(result, changed_at=None)

        state = await self._store.get_site_state("example.com")
        self.assertIsNotNone(state)
        assert state is not None
        self.assertEqual(state.domain, "example.com")
        self.assertEqual(state.reachability_state, "up")
        self.assertEqual(state.registration_state, "unknown")
        self.assertEqual(state.invites_state, "open")
        self.assertEqual(state.invites_available, 2)
        self.assertEqual(state.last_changed_at, None)

        reach = await self._store.get_reachability_states(["example.com", "missing.com"])
        self.assertEqual(reach, {"example.com": "up"})

        extras = await self._store.get_sites_extras(["example.com"])
        self.assertEqual(extras, {"example.com": {"reachability_state": "up", "invite_uid": "42"}})

        snap_at, sites = await self._store.load_sites_snapshot()
        self.assertEqual(snap_at, now)
        self.assertEqual(len(sites), 1)
        self.assertEqual(sites[0].domain, "example.com")
        self.assertEqual(sites[0].id, 123)
        self.assertEqual(sites[0].ua, "UA")
        self.assertEqual(sites[0].cookie, "cookie")
        self.assertTrue(sites[0].is_active)

        await self._store.reset_site_states()
        states = await self._store.list_site_states()
        self.assertEqual(states, [])


if __name__ == "__main__":
    unittest.main()

