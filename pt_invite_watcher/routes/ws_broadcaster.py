from __future__ import annotations

import asyncio
import logging
from contextlib import suppress
from typing import Optional

from fastapi import WebSocket

from pt_invite_watcher.utils.asyncio_tasks import create_task_logged
from pt_invite_watcher.ws_events import WS_LOGS_APPEND, WS_LOGS_UPDATE

logger = logging.getLogger("pt_invite_watcher")


class WebSocketBroadcaster:
    def __init__(self, *, queue_size: int = 200):
        self._clients: list[WebSocket] = []
        self._queue_size = max(1, int(queue_size or 0))
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._clients_lock: Optional[asyncio.Lock] = None
        self._broadcast_lock: Optional[asyncio.Lock] = None
        self._queue: Optional[asyncio.Queue[dict]] = None
        self._pump_task: Optional[asyncio.Task[None]] = None
        self._logs_update_enqueued = False
        self._stopped = False

    def _ensure_inited(self) -> None:
        if self._queue is not None and self._clients_lock is not None and self._broadcast_lock is not None:
            return

        # Python 3.9 asyncio primitives are bound to the event loop at creation time.
        # Create them lazily inside the *running* loop to avoid "attached to a different loop".
        loop = asyncio.get_running_loop()
        self._loop = loop
        self._clients_lock = asyncio.Lock()
        self._broadcast_lock = asyncio.Lock()
        self._queue = asyncio.Queue(maxsize=self._queue_size)

    async def connect(self, websocket: WebSocket):
        self._ensure_inited()
        await websocket.accept()
        async with self._clients_lock:  # type: ignore[union-attr]
            if websocket not in self._clients:
                self._clients.append(websocket)

    async def disconnect(self, websocket: WebSocket):
        self._ensure_inited()
        async with self._clients_lock:  # type: ignore[union-attr]
            if websocket in self._clients:
                self._clients.remove(websocket)

    async def start(self) -> None:
        self._stopped = False
        self._ensure_inited()
        self._ensure_pump()

    async def stop(self) -> None:
        self._stopped = True
        if self._pump_task is not None:
            self._pump_task.cancel()
            try:
                await self._pump_task
            except asyncio.CancelledError:
                pass
            except Exception:
                logger.exception("ws pump task failed on stop")
            self._pump_task = None

        q = self._queue
        if q is not None:
            while not q.empty():
                with suppress(asyncio.QueueEmpty, RuntimeError):
                    q.get_nowait()
                    q.task_done()
        self._logs_update_enqueued = False
        if self._clients_lock is not None:
            async with self._clients_lock:
                self._clients.clear()
        self._clients_lock = None
        self._broadcast_lock = None
        self._queue = None
        self._loop = None

    def publish(self, message: dict) -> None:
        """
        Best-effort enqueue for high-volume events (e.g., logs stream).

        This avoids creating an asyncio.Task per event. If the queue is full, we drop
        the message and (for logs) ask clients to resync via a single `logs_update`.
        """
        if self._stopped:
            return
        if not self._clients:
            return
        if message.get("type") == WS_LOGS_UPDATE and self._logs_update_enqueued:
            return
        try:
            self._ensure_inited()
            self._ensure_pump()
            q = self._queue
            if q is None:
                return
            q.put_nowait(message)
            if message.get("type") == WS_LOGS_UPDATE:
                self._logs_update_enqueued = True
        except RuntimeError:
            # Event loop is closing / no running loop. Best-effort: drop.
            return
        except asyncio.QueueFull:
            msg_type = message.get("type")
            if msg_type not in {WS_LOGS_APPEND, WS_LOGS_UPDATE}:
                return
            if self._logs_update_enqueued:
                return
            # Drop backlog and ask clients to resync once.
            q = self._queue
            if q is None:
                return
            while not q.empty():
                with suppress(asyncio.QueueEmpty, RuntimeError):
                    q.get_nowait()
                    q.task_done()
            with suppress(asyncio.QueueFull, RuntimeError):
                if msg_type == WS_LOGS_UPDATE:
                    q.put_nowait(message)
                else:
                    q.put_nowait({"type": WS_LOGS_UPDATE, "data": {"reason": "ws_queue_full"}})
                self._logs_update_enqueued = True

    def _ensure_pump(self) -> None:
        if self._pump_task is not None and not self._pump_task.done():
            return
        self._pump_task = create_task_logged(
            self._pump(),
            logger=logger,
            name="ws_broadcaster_pump",
            label="ws broadcaster pump",
        )

    async def _pump(self) -> None:
        q = self._queue
        if q is None:
            return
        while True:
            msg = await q.get()
            try:
                try:
                    await self.broadcast(msg)
                except asyncio.CancelledError:
                    raise
                except Exception:
                    logger.exception("ws broadcast failed (type=%s)", msg.get("type"))
            finally:
                if msg.get("type") == WS_LOGS_UPDATE:
                    self._logs_update_enqueued = False
                q.task_done()

    async def broadcast(self, message: dict):
        self._ensure_inited()
        async with self._broadcast_lock:  # type: ignore[union-attr]
            async with self._clients_lock:  # type: ignore[union-attr]
                clients = list(self._clients)
            if not clients:
                return

            async def _send_one(ws: WebSocket) -> None:
                await asyncio.wait_for(ws.send_json(message), timeout=2)

            results = await asyncio.gather(*[_send_one(c) for c in clients], return_exceptions=True)
            failed: list[WebSocket] = [ws for ws, res in zip(clients, results) if isinstance(res, Exception)]
            if not failed:
                return

            async with self._clients_lock:
                for ws in failed:
                    if ws in self._clients:
                        self._clients.remove(ws)


ws_broadcaster = WebSocketBroadcaster()


__all__ = ["WebSocketBroadcaster", "ws_broadcaster"]
