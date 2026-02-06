from __future__ import annotations

from typing import Any

from pt_invite_watcher.kv_keys import APP_CONFIG_KEY, SITES_KEY
from pt_invite_watcher.utils.parse import safe_dict


SITES_CONFIG_VERSION = 1
DEFAULT_SITES_CONFIG: dict[str, Any] = {"version": SITES_CONFIG_VERSION, "entries": {}}


async def load_app_config(store: Any) -> dict[str, Any]:
    """
    Load the persisted app config payload from KV.

    The return value is always a dict (possibly empty).
    """
    cfg = await store.get_json(APP_CONFIG_KEY, default={}) or {}
    return safe_dict(cfg)


async def load_sites_config(store: Any) -> dict[str, Any]:
    """
    Load the persisted sites config payload from KV.

    Normalizes to: {"version": int, "entries": dict}.
    """
    cfg = await store.get_json(SITES_KEY, default=DEFAULT_SITES_CONFIG) or DEFAULT_SITES_CONFIG
    cfg = safe_dict(cfg)
    entries = safe_dict(cfg.get("entries"))
    return {"version": int(cfg.get("version") or SITES_CONFIG_VERSION), "entries": entries}
