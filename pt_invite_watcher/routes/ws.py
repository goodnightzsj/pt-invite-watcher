from __future__ import annotations

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from pt_invite_watcher.routes.common import ws_broadcaster
from pt_invite_watcher.ws_events import WS_CONNECTED


router = APIRouter()


@router.websocket("/ws/events")
async def websocket_endpoint(websocket: WebSocket):
    await ws_broadcaster.connect(websocket)
    try:
        await websocket.send_json({"type": WS_CONNECTED})
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        pass
    finally:
        await ws_broadcaster.disconnect(websocket)
