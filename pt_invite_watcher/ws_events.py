from __future__ import annotations

"""
WebSocket event type constants.

Wire protocol must remain stable; these values are the canonical strings used by
the WebUI and any external clients.
"""

WS_CONNECTED = "connected"
WS_PING = "ping"
WS_DASHBOARD_UPDATE = "dashboard_update"
WS_LOGS_UPDATE = "logs_update"
WS_LOGS_APPEND = "logs_append"
WS_SCAN_PROGRESS = "scan_progress"

__all__ = [
    "WS_CONNECTED",
    "WS_PING",
    "WS_DASHBOARD_UPDATE",
    "WS_LOGS_UPDATE",
    "WS_LOGS_APPEND",
    "WS_SCAN_PROGRESS",
]

