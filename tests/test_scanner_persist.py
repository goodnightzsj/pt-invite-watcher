import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from pt_invite_watcher.models import AspectResult, Evidence, ReachabilityResult, Site, SiteCheckResult
from pt_invite_watcher.scanner_persist import persist_and_notify
from pt_invite_watcher.storage.sqlite import SqliteStore


class _FakeNotifier:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str]] = []

    async def send(self, *, title: str, text: str) -> None:
        self.calls.append((title, text))


class ScannerPersistTest(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self._db_path = Path(self._tmp.name) / "test.db"
        self._store = SqliteStore(self._db_path)
        await self._store.init()

    async def asyncTearDown(self) -> None:
        await self._store.close()
        self._tmp.cleanup()

    async def test_persist_and_notify_dispatches_event_hooks_after_write(self) -> None:
        events: list[dict] = []

        def _hook(evt: dict) -> None:
            events.append(evt)

        self._store.on_event(_hook)
        notifier = _FakeNotifier()

        site = Site(
            id=123,
            name="Example",
            domain="example.com",
            url="https://example.com",
            ua="UA",
            cookie="cookie",
            is_active=True,
        )

        prev_at = datetime(2026, 1, 1, tzinfo=timezone.utc)
        prev = SiteCheckResult(
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
                state="closed",
                available=0,
                permanent=None,
                temporary=None,
                evidence=Evidence(url=f"{site.url}/invite.php?id=42", http_status=200, reason="invites_none"),
            ),
            checked_at=prev_at,
        )
        await self._store.save_site_result(prev, changed_at=None)
        self.assertEqual(events, [])
        self.assertEqual(notifier.calls, [])

        cur_at = datetime(2026, 1, 2, tzinfo=timezone.utc)
        cur = SiteCheckResult(
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
            checked_at=cur_at,
        )

        await persist_and_notify(store=self._store, notifier=notifier, site=site, result=cur, now=cur_at)

        self.assertEqual(len(notifier.calls), 1)
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0].get("action"), "state_changed")
        self.assertEqual(events[0].get("domain"), "example.com")

        st = await self._store.get_site_state("example.com")
        self.assertIsNotNone(st)
        assert st is not None
        self.assertEqual(st.invites_available, 2)

        rows = await self._store.list_events(limit=10)
        self.assertGreaterEqual(len(rows), 1)


if __name__ == "__main__":
    unittest.main()

