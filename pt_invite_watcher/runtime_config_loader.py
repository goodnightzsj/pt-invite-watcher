from __future__ import annotations

from typing import Any

from pt_invite_watcher.config import Settings
from pt_invite_watcher.config_store import load_app_config
from pt_invite_watcher.runtime_config import RuntimeConfig, load_runtime_config


async def load_runtime_config_from_store(settings: Settings, store: Any) -> RuntimeConfig:
    """
    Convenience helper: load KV-backed app_config from store and merge with file/env Settings.
    """
    cfg = await load_app_config(store)
    return load_runtime_config(settings, cfg)


async def get_runtime_config(settings: Settings, store: Any, *, runtime_config: Any | None = None) -> RuntimeConfig:
    """
    Unified runtime config access.

    Prefer a provided runtime_config cache (duck-typed, requires an async `.get()`),
    otherwise load and merge from store directly.
    """
    if runtime_config is not None:
        getter = getattr(runtime_config, "get", None)
        if callable(getter):
            return await getter()
    return await load_runtime_config_from_store(settings, store)


__all__ = ["get_runtime_config", "load_runtime_config_from_store"]
