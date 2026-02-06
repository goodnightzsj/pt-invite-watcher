from __future__ import annotations

import logging
import unittest

from pt_invite_watcher.storage.event_hooks import dispatch_event_hooks


class EventHookDispatchHelperTest(unittest.TestCase):
    def test_fallback_hooks_ignore_exceptions(self) -> None:
        logger = logging.getLogger("pt_invite_watcher.storage.event_hooks")
        prev_level = logger.level
        prev_propagate = logger.propagate
        logger.setLevel(logging.CRITICAL)
        logger.propagate = False

        try:
            seen: list[dict] = []

            def bad_hook(evt: dict) -> None:
                raise RuntimeError("boom")

            def good_hook(evt: dict) -> None:
                seen.append(evt)

            store = type("LegacyStore", (), {})()
            store._event_hooks = [bad_hook, good_hook]

            dispatch_event_hooks(store, {"id": 1})
            self.assertEqual(seen, [{"id": 1}])
        finally:
            logger.setLevel(prev_level)
            logger.propagate = prev_propagate

    def test_prefers_store_dispatch_method(self) -> None:
        seen: list[dict] = []

        def bad_hook(evt: dict) -> None:
            raise RuntimeError("should not be called")

        class Store:
            def __init__(self) -> None:
                self._event_hooks = [bad_hook]

            def dispatch_event_hooks(self, evt: dict) -> None:
                seen.append(evt)

        store = Store()
        dispatch_event_hooks(store, {"id": 2})
        self.assertEqual(seen, [{"id": 2}])


if __name__ == "__main__":
    unittest.main()

