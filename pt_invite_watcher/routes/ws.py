from __future__ import annotations

import base64

from fastapi import APIRouter, WebSocket, WebSocketDisconnect, status

from pt_invite_watcher.routes.common import ws_broadcaster
from pt_invite_watcher.ws_events import WS_CONNECTED, WS_PING


router = APIRouter()


def _ws_is_authorized(websocket: WebSocket) -> bool:
    """
    Verify a WebSocket client against the same BasicAuth the HTTP endpoints use.

    Browsers can't attach custom headers to `new WebSocket(url)`, so clients
    running in a non-same-origin context (Capacitor iOS / Android, Tauri with
    a remote server) pass credentials as `?token=<base64 user:pass>` on the
    WS URL. Same-origin browser clients already ride the HTTP BasicAuth
    challenge the browser remembers from the initial page load and don't
    need the query param.

    Auth is treated as optional at the WS layer only when the server has no
    BasicAuth configured — matches the HTTP endpoint behavior so a
    credential-less deployment doesn't get harder to use via WS than HTTP.
    """
    settings = getattr(websocket.app.state, "ctx", None)
    if settings is None:
        return True
    ba = settings.settings.web.basic_auth
    if not getattr(ba, "enabled", False):
        return True  # no auth configured → no auth required

    # Accept either header (same-origin) or query-param (cross-origin).
    header_auth = websocket.headers.get("authorization") or ""
    token = ""
    if header_auth.lower().startswith("basic "):
        token = header_auth.split(" ", 1)[1].strip()
    if not token:
        token = websocket.query_params.get("token") or ""
    if not token:
        return False

    try:
        decoded = base64.b64decode(token).decode("utf-8", errors="strict")
    except Exception:
        return False
    if ":" not in decoded:
        return False
    user, _, pw = decoded.partition(":")
    return user == ba.username and pw == ba.password


@router.websocket("/ws/events")
async def websocket_endpoint(websocket: WebSocket):
    if not _ws_is_authorized(websocket):
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return
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
