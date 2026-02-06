from __future__ import annotations

import logging
import unittest
from unittest.mock import patch

from pt_invite_watcher.scanner_lease import ScanLeaseManager


class _DummyStore:
    def __init__(self, acquire_results: list[object], *, release_results: list[object] | None = None):
        self.calls: list[tuple[str, str, str, int]] = []
        self.events: list[dict] = []
        self._acquire_results = list(acquire_results)
        self._release_results = list(release_results or [])

    async def try_acquire_lease(self, key: str, *, owner: str, ttl_seconds: int) -> bool:
        self.calls.append((key, owner, "try_acquire_lease", int(ttl_seconds)))
        if not self._acquire_results:
            raise AssertionError("no more acquire results configured")
        res = self._acquire_results.pop(0)
        if isinstance(res, BaseException):
            raise res
        return bool(res)

    async def release_lease(self, key: str, *, owner: str) -> None:
        self.calls.append((key, owner, "release_lease", 0))
        if not self._release_results:
            return None
        res = self._release_results.pop(0)
        if isinstance(res, BaseException):
            raise res
        return None

    async def add_event(self, *, category: str, level: str, action: str, message: str, detail: dict) -> None:
        self.events.append(
            {
                "category": category,
                "level": level,
                "action": action,
                "message": message,
                "detail": detail,
            }
        )


class ScanLeaseManagerTest(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self._logger = logging.getLogger("pt_invite_watcher.scanner_lease")
        self._prev_level = self._logger.level
        self._prev_propagate = self._logger.propagate
        self._logger.setLevel(logging.CRITICAL)
        self._logger.propagate = False

    async def asyncTearDown(self) -> None:
        self._logger.setLevel(self._prev_level)
        self._logger.propagate = self._prev_propagate

    async def test_busy_event_is_throttled(self) -> None:
        store = _DummyStore([False, False])
        lease = ScanLeaseManager(store, owner="owner")

        with patch("pt_invite_watcher.lease_emitter.time.monotonic", side_effect=[1000.0, 1000.1]):
            ok1 = await lease.acquire(ttl_seconds=10)
            ok2 = await lease.acquire(ttl_seconds=10)

        self.assertFalse(ok1)
        self.assertFalse(ok2)

        actions = [e.get("action") for e in store.events]
        self.assertEqual(actions.count("scan_lease_busy"), 1)

    async def test_exception_event_is_throttled(self) -> None:
        store = _DummyStore([RuntimeError("boom"), RuntimeError("boom2")])
        lease = ScanLeaseManager(store, owner="owner")

        with patch("pt_invite_watcher.lease_emitter.time.monotonic", side_effect=[1000.0, 1000.1]):
            ok1 = await lease.acquire(ttl_seconds=10)
            ok2 = await lease.acquire(ttl_seconds=10)

        self.assertTrue(ok1)
        self.assertTrue(ok2)

        actions = [e.get("action") for e in store.events]
        self.assertEqual(actions.count("scan_lease_disabled"), 1)

    async def test_refresh_failed_is_once_per_run(self) -> None:
        store = _DummyStore([True, False, False, True, False])
        lease = ScanLeaseManager(store, owner="owner")

        ok1 = await lease.acquire(ttl_seconds=10)
        self.assertTrue(ok1)

        await lease.extend(ttl_seconds=10)
        await lease.extend(ttl_seconds=10)

        ok2 = await lease.acquire(ttl_seconds=10)
        self.assertTrue(ok2)

        await lease.extend(ttl_seconds=10)

        actions = [e.get("action") for e in store.events]
        self.assertEqual(actions.count("scan_lease_refresh_failed"), 2)

    async def test_refresh_exception_is_once_per_run(self) -> None:
        store = _DummyStore([True, RuntimeError("boom"), RuntimeError("boom2"), True, RuntimeError("boom3")])
        lease = ScanLeaseManager(store, owner="owner")

        ok1 = await lease.acquire(ttl_seconds=10)
        self.assertTrue(ok1)

        await lease.extend(ttl_seconds=10)
        await lease.extend(ttl_seconds=10)

        ok2 = await lease.acquire(ttl_seconds=10)
        self.assertTrue(ok2)

        await lease.extend(ttl_seconds=10)

        actions = [e.get("action") for e in store.events]
        self.assertEqual(actions.count("scan_lease_refresh_exception"), 2)

    async def test_release_failure_emits_every_time(self) -> None:
        store = _DummyStore([], release_results=[RuntimeError("boom"), RuntimeError("boom2")])
        lease = ScanLeaseManager(store, owner="owner")

        await lease.release()
        await lease.release()

        actions = [e.get("action") for e in store.events]
        self.assertEqual(actions, ["scan_lease_release_failed", "scan_lease_release_failed"])


if __name__ == "__main__":
    unittest.main()
