import logging
import unittest

from pt_invite_watcher.scheduler_lease import SchedulerLeaseManager


class _DummyStore:
    def __init__(self, results: list[object]):
        self.calls: list[tuple[str, str, str, int]] = []
        self.events: list[dict] = []
        self._results = list(results)

    async def try_acquire_lease(self, key: str, *, owner: str, ttl_seconds: int) -> bool:
        self.calls.append((key, owner, "try_acquire_lease", int(ttl_seconds)))
        if not self._results:
            raise AssertionError("no more results configured")
        res = self._results.pop(0)
        if isinstance(res, BaseException):
            raise res
        return bool(res)

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


class SchedulerLeaseManagerTest(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self._logger = logging.getLogger("pt_invite_watcher.scheduler_lease")
        self._prev_level = self._logger.level
        self._prev_propagate = self._logger.propagate
        self._logger.setLevel(logging.CRITICAL)
        self._logger.propagate = False

    async def asyncTearDown(self) -> None:
        self._logger.setLevel(self._prev_level)
        self._logger.propagate = self._prev_propagate

    async def test_disabled_by_env_returns_leader_without_calls(self) -> None:
        store = _DummyStore([])
        lease = SchedulerLeaseManager(store, owner="owner", enabled=False)
        ok = await lease.ensure_leader(ttl_seconds=10)
        self.assertTrue(ok)
        self.assertEqual(store.calls, [])
        self.assertEqual(store.events, [])

    async def test_exception_disables_lock_and_stops_future_checks(self) -> None:
        store = _DummyStore([False, True, RuntimeError("boom"), False])
        lease = SchedulerLeaseManager(store, owner="owner", enabled=True)

        ok1 = await lease.ensure_leader(ttl_seconds=10)
        self.assertFalse(ok1)

        ok2 = await lease.ensure_leader(ttl_seconds=10)
        self.assertTrue(ok2)

        ok3 = await lease.ensure_leader(ttl_seconds=10)
        self.assertTrue(ok3)

        ok4 = await lease.ensure_leader(ttl_seconds=10)
        self.assertTrue(ok4)

        actions = [e.get("action") for e in store.events]
        self.assertIn("scheduler_leader_acquired", actions)
        self.assertIn("scheduler_lease_disabled_exception", actions)
        self.assertEqual(store.calls.count(("scheduler_lease", "owner", "try_acquire_lease", 10)), 3)


if __name__ == "__main__":
    unittest.main()

