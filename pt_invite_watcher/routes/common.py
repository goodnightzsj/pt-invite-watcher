from __future__ import annotations

from pathlib import Path

from pt_invite_watcher.kv_keys import SCAN_HINT_KEY
from pt_invite_watcher.routes.deps import (
    basic_security,
    get_ctx,
    get_runtime_config,
    load_app_config,
    load_sites_config,
    require_auth,
)
from pt_invite_watcher.routes.site_helpers import domain_from_url, relative_path_from_page_url, site_entry_view
from pt_invite_watcher.routes.ws_broadcaster import WebSocketBroadcaster, ws_broadcaster
from pt_invite_watcher.utils.parse import cfg_bool, cfg_int, cfg_str, normalize_domain, safe_dict
from pt_invite_watcher.ws_events import WS_DASHBOARD_UPDATE


DIST_DIR = Path(__file__).resolve().parent.parent / "webui_dist"
ASSETS_DIR = DIST_DIR / "assets"

BACKUP_VERSION = 1


async def broadcast_dashboard_update() -> None:
    await ws_broadcaster.broadcast({"type": WS_DASHBOARD_UPDATE})


# Explicit aliases to reduce confusion with similarly named store-level helpers.
get_runtime_config_dep = get_runtime_config
load_app_config_payload = load_app_config
load_sites_config_payload = load_sites_config

__all__ = [
    "ASSETS_DIR",
    "BACKUP_VERSION",
    "DIST_DIR",
    "SCAN_HINT_KEY",
    "WebSocketBroadcaster",
    "basic_security",
    "broadcast_dashboard_update",
    "cfg_bool",
    "cfg_int",
    "cfg_str",
    "domain_from_url",
    "get_ctx",
    "get_runtime_config",
    "get_runtime_config_dep",
    "load_app_config",
    "load_app_config_payload",
    "load_sites_config",
    "load_sites_config_payload",
    "normalize_domain",
    "relative_path_from_page_url",
    "require_auth",
    "safe_dict",
    "site_entry_view",
    "ws_broadcaster",
]
