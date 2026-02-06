from __future__ import annotations

import os
from typing import Annotated, Any, Dict, Optional

from fastapi import Depends, HTTPException, Request
from fastapi.security import HTTPBasic, HTTPBasicCredentials

from pt_invite_watcher.app_context import AppContext
from pt_invite_watcher.config import Settings
from pt_invite_watcher.config_store import load_app_config as _load_app_config, load_sites_config as _load_sites_config
from pt_invite_watcher.runtime_config import RuntimeConfig
from pt_invite_watcher.runtime_config_loader import load_runtime_config_from_store
from pt_invite_watcher.utils.parse import cfg_bool


basic_security = HTTPBasic(auto_error=False)


async def get_ctx(request: Request) -> AppContext:
    ctx: Optional[AppContext] = getattr(request.app.state, "ctx", None)
    if ctx is None:
        raise HTTPException(status_code=503, detail="App not ready")
    return ctx


def _maybe_require_auth(credentials: Optional[HTTPBasicCredentials], settings: Settings) -> None:
    if cfg_bool(os.getenv("PTIW_DISABLE_AUTH"), default=False):
        return
    if not settings.web.basic_auth.enabled:
        return
    if not credentials or not credentials.username or not credentials.password:
        raise HTTPException(status_code=401, headers={"WWW-Authenticate": "Basic"})
    if credentials.username != settings.web.basic_auth.username or credentials.password != settings.web.basic_auth.password:
        raise HTTPException(status_code=401, detail="Unauthorized", headers={"WWW-Authenticate": "Basic"})


async def require_auth(
    credentials: Annotated[Optional[HTTPBasicCredentials], Depends(basic_security)],
    ctx: Annotated[AppContext, Depends(get_ctx)],
) -> None:
    _maybe_require_auth(credentials, ctx.settings)


async def load_app_config(ctx: AppContext) -> Dict[str, Any]:
    return await _load_app_config(ctx.store)


async def load_sites_config(ctx: AppContext) -> Dict[str, Any]:
    return await _load_sites_config(ctx.store)


async def get_runtime_config(ctx: AppContext) -> RuntimeConfig:
    try:
        return await ctx.runtime_config.get()
    except Exception:
        return await load_runtime_config_from_store(ctx.settings, ctx.store)


__all__ = [
    "basic_security",
    "get_ctx",
    "get_runtime_config",
    "load_app_config",
    "load_sites_config",
    "require_auth",
]

