from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from typing import Any, Dict, Optional

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from contextlib import asynccontextmanager

from pt_invite_watcher.app_context import build_context
from pt_invite_watcher.config import load_settings
from pt_invite_watcher import __version__
from pt_invite_watcher.scheduler import start_scheduler, stop_scheduler
from pt_invite_watcher.routes import ASSETS_DIR, router, ws_broadcaster
from pt_invite_watcher.routes.common import broadcast_dashboard_update, broadcast_scan_progress
from pt_invite_watcher.ws_events import WS_LOGS_APPEND, WS_LOGS_UPDATE


logger = logging.getLogger("pt_invite_watcher")

def _warn_if_webui_dist_stale() -> None:
    """
    Best-effort guardrail for development checkouts.

    The backend serves `pt_invite_watcher/webui_dist` (built by Vite). If `webui/src`
    changes without rebuilding, users may see stale UI behavior.
    """
    try:
        repo_root = Path(__file__).resolve().parent.parent
        webui_src = repo_root / "webui" / "src"
        dist_index = Path(__file__).resolve().parent / "webui_dist" / "index.html"
        if not webui_src.exists() or not dist_index.exists():
            return

        src_latest = max((p.stat().st_mtime for p in webui_src.rglob("*") if p.is_file()), default=0.0)
        dist_mtime = dist_index.stat().st_mtime
        if src_latest > (dist_mtime + 1):
            logger.warning(
                "Web UI build may be stale: %s contains newer files than %s; run `npm --prefix webui run build`",
                webui_src.as_posix(),
                dist_index.as_posix(),
            )
    except Exception:
        logger.exception("failed to check webui build staleness")


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = load_settings()
    logging.basicConfig(level=getattr(logging, settings.log_level, logging.INFO))
    _warn_if_webui_dist_stale()
    ctx = await build_context(settings)
    app.state.ctx = ctx
    await ws_broadcaster.start()

    # Wire up logs to WebSocket
    def _on_log_event(event: Dict[str, Any]) -> None:
        ws_broadcaster.publish({"type": WS_LOGS_APPEND, "data": event})

    ctx.store.on_event(_on_log_event)
    on_logs_resync = getattr(ctx.store, "on_logs_resync", None)
    if callable(on_logs_resync):
        # Ask clients to resync logs when the store detects log buffering issues.
        def _on_logs_resync(reason: str) -> None:
            ws_broadcaster.publish({"type": WS_LOGS_UPDATE, "data": {"reason": reason}})

        on_logs_resync(_on_logs_resync)

    # Stream per-site scan progress to WebSocket clients.
    scanner_set_progress = getattr(ctx.scanner, "set_progress_broadcast", None)
    if callable(scanner_set_progress):
        scanner_set_progress(broadcast_scan_progress)

    scan_task = await start_scheduler(ctx, broadcast_dashboard_update=broadcast_dashboard_update)
    yield
    await stop_scheduler(scan_task)
    await ws_broadcaster.stop()
    await ctx.cookiecloud.close()
    await ctx.store.close()


app = FastAPI(title="PT Invite Watcher", version=__version__, lifespan=lifespan)

# Serve Vite build assets. We intentionally don't require auth here; the SPA entry and APIs are protected.
app.mount("/assets", StaticFiles(directory=ASSETS_DIR.as_posix(), check_dir=False), name="assets")
app.include_router(router)
