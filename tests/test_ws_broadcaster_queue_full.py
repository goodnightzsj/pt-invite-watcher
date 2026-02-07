import unittest
from unittest.mock import patch

from pt_invite_watcher.routes.ws_broadcaster import WebSocketBroadcaster
from pt_invite_watcher.ws_events import WS_LOGS_APPEND, WS_LOGS_UPDATE


class WebSocketBroadcasterQueueFullTest(unittest.IsolatedAsyncioTestCase):
    async def test_logs_update_not_dropped_on_queue_full(self) -> None:
        broadcaster = WebSocketBroadcaster(queue_size=1)

        # publish() short-circuits when there are no clients; we don't need a real WebSocket here.
        broadcaster._clients.append(object())  # type: ignore[attr-defined]

        # Prevent the background pump task from draining the queue and making the test flaky.
        with patch.object(broadcaster, "_ensure_pump", return_value=None):
            broadcaster.publish({"type": WS_LOGS_APPEND, "data": {"id": 1}})
            self.assertEqual(broadcaster._queue.qsize(), 1)  # type: ignore[attr-defined]

            # Force a QueueFull and ensure a logs_update gets enqueued (instead of being dropped).
            broadcaster.publish({"type": WS_LOGS_UPDATE, "data": {"reason": "test"}})
            self.assertEqual(broadcaster._queue.qsize(), 1)  # type: ignore[attr-defined]

            msg = broadcaster._queue.get_nowait()  # type: ignore[attr-defined]
            broadcaster._queue.task_done()  # type: ignore[attr-defined]
            self.assertEqual(msg.get("type"), WS_LOGS_UPDATE)
            self.assertEqual((msg.get("data") or {}).get("reason"), "test")

    async def test_publish_noop_after_stop(self) -> None:
        broadcaster = WebSocketBroadcaster(queue_size=1)
        await broadcaster.stop()

        # Even if a client list is present, stop() should prevent publish() from enqueuing.
        broadcaster._clients.append(object())  # type: ignore[attr-defined]

        with patch.object(broadcaster, "_ensure_pump", return_value=None) as ensure:
            broadcaster.publish({"type": WS_LOGS_APPEND, "data": {"id": 1}})
            ensure.assert_not_called()
            self.assertEqual(broadcaster._queue.qsize(), 0)  # type: ignore[attr-defined]


if __name__ == "__main__":
    unittest.main()
