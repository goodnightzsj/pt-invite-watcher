from __future__ import annotations

import asyncio
import logging
import os
from pathlib import Path
from typing import Any, Dict, Optional

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
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


async def _startup_self_check(ctx) -> None:
    """Emit a one-shot startup banner covering the subsystems operators ask
    about first when something looks wrong: version, DB location, how many
    sites the registry sees, whether upstream providers are configured.

    Wrapped in broad try/except per probe so a single flaky dependency doesn't
    poison the overall startup; the lifespan itself is still free to fail on
    genuinely fatal errors elsewhere (e.g. malformed config).
    """
    try:
        from pt_invite_watcher.engines.site_registry import list_all as _registry_list_all
        registry_count = len(list(_registry_list_all()))
    except Exception:
        registry_count = -1

    try:
        from pt_invite_watcher.config import Settings as _Settings  # noqa: F401
        db_path = getattr(ctx.settings.db, "path", "?")
    except Exception:
        db_path = "?"

    mp_cfg = getattr(ctx.settings, "moviepilot", None)
    mp_configured = bool(getattr(mp_cfg, "base_url", "") if mp_cfg else False)

    cc_cfg = getattr(ctx.settings, "cookiecloud", None)
    cc_configured = bool(getattr(cc_cfg, "base_url", "") if cc_cfg else False)

    logger.info(
        "startup: version=%s db=%s registry_sites=%s moviepilot=%s cookiecloud=%s",
        __version__,
        db_path,
        registry_count,
        "configured" if mp_configured else "not-configured",
        "configured" if cc_configured else "not-configured",
    )

    if registry_count <= 0:
        logger.warning("startup: site registry is empty — preset picker will show no options")


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = load_settings()
    logging.basicConfig(level=getattr(logging, settings.log_level, logging.INFO))
    _warn_if_webui_dist_stale()
    ctx = await build_context(settings)
    app.state.ctx = ctx
    await _startup_self_check(ctx)
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
    from pt_invite_watcher.routes.sites import close_icon_client
    await close_icon_client()
    await ctx.cookiecloud.close()
    await ctx.store.close()


app = FastAPI(title="PT Invite Watcher", version=__version__, lifespan=lifespan)

# ============================================================================
# CORS — unlocks the mobile (Capacitor) shell
# ============================================================================
#
# The Vue bundle ships inside Capacitor iOS/Android via a WebView whose origin
# is `capacitor://localhost` (iOS) or `https://localhost` (Android). Every
# fetch to the user's remote FastAPI is cross-origin from those origins, and
# browsers block cross-origin requests without matching CORS headers. Without
# these entries the mobile app can't authenticate, can't list sites, can't
# subscribe to WebSocket updates — it's a blocking bug, not a nicety.
#
# The origins whitelisted below are device-local and device-specific; they
# are NOT internet-accessible, so allowing them doesn't expose the API to
# random websites. BasicAuth still gates every API endpoint as before.
#
# Operators who want to whitelist additional origins (e.g. their own Electron
# wrapper, a Homelab dashboard iframe) can list them in the
# `PTIW_CORS_EXTRA_ORIGINS` env var (comma-separated).
_EXTRA_ORIGINS = [
    o.strip()
    for o in (os.getenv("PTIW_CORS_EXTRA_ORIGINS") or "").split(",")
    if o.strip()
]
_ALLOWED_ORIGINS = [
    # Capacitor iOS custom scheme.
    "capacitor://localhost",
    # Capacitor Android (and some iOS builds with `iosScheme: https`).
    "https://localhost",
    # Legacy Ionic / Capacitor 1-3 scheme, still seen in the wild.
    "ionic://localhost",
    # Tauri webview runs from `tauri://localhost` on macOS/Linux and
    # `https://tauri.localhost` on Windows — same cross-origin concern
    # whenever apiBase points at a real domain.
    "tauri://localhost",
    "https://tauri.localhost",
    *_EXTRA_ORIGINS,
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=_ALLOWED_ORIGINS,
    allow_credentials=True,     # BasicAuth / cookies pass through CORS preflight
    allow_methods=["*"],
    allow_headers=["*"],
)

# Serve Vite build assets. We intentionally don't require auth here; the SPA entry and APIs are protected.
app.mount("/assets", StaticFiles(directory=ASSETS_DIR.as_posix(), check_dir=False), name="assets")
app.include_router(router)
