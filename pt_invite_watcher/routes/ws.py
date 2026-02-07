from __future__ import annotations

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from pt_invite_watcher.routes.common import ws_broadcaster
from pt_invite_watcher.ws_events import WS_CONNECTED, WS_PING


router = APIRouter()


@router.websocket("/ws/events")
async def websocket_endpoint(websocket: WebSocket):
    await ws_broadcaster.connect(websocket)
    try:
        await websocket.send_json({"type": WS_CONNECTED})
        while True:
            msg = await websocket.receive_text()
            if str(msg or "").strip().lower() == "ping":
                await websocket.send_json({"type": WS_PING})
    except WebSocketDisconnect:
        pass
    finally:
        await ws_broadcaster.disconnect(websocket)
