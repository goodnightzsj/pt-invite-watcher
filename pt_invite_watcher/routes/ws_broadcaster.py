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
        self._clients_lock = asyncio.Lock()
        self._broadcast_lock = asyncio.Lock()
        self._queue: asyncio.Queue[dict] = asyncio.Queue(maxsize=max(1, int(queue_size or 0)))
        self._pump_task: Optional[asyncio.Task[None]] = None
        self._logs_update_enqueued = False
        self._stopped = False

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        async with self._clients_lock:
            if websocket not in self._clients:
                self._clients.append(websocket)

    async def disconnect(self, websocket: WebSocket):
        async with self._clients_lock:
            if websocket in self._clients:
                self._clients.remove(websocket)

    async def start(self) -> None:
        self._stopped = False
        self._ensure_pump()

    async def stop(self) -> None:
        self._stopped = True
        if self._pump_task is not None:
            self._pump_task.cancel()
            with suppress(asyncio.CancelledError):
                await self._pump_task
            self._pump_task = None

        while not self._queue.empty():
            with suppress(asyncio.QueueEmpty):
                self._queue.get_nowait()
                self._queue.task_done()
        self._logs_update_enqueued = False
        async with self._clients_lock:
            self._clients.clear()

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
        self._ensure_pump()
        try:
            self._queue.put_nowait(message)
            if message.get("type") == WS_LOGS_UPDATE:
                self._logs_update_enqueued = True
        except asyncio.QueueFull:
            msg_type = message.get("type")
            if msg_type not in {WS_LOGS_APPEND, WS_LOGS_UPDATE}:
                return
            if self._logs_update_enqueued:
                return
            # Drop backlog and ask clients to resync once.
            while not self._queue.empty():
                with suppress(asyncio.QueueEmpty):
                    self._queue.get_nowait()
                    self._queue.task_done()
            with suppress(asyncio.QueueFull):
                if msg_type == WS_LOGS_UPDATE:
                    self._queue.put_nowait(message)
                else:
                    self._queue.put_nowait({"type": WS_LOGS_UPDATE, "data": {"reason": "ws_queue_full"}})
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
        while True:
            msg = await self._queue.get()
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
                self._queue.task_done()

    async def broadcast(self, message: dict):
        async with self._broadcast_lock:
            async with self._clients_lock:
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
