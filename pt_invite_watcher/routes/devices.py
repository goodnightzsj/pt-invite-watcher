"""Device-token registration for native mobile push.

Endpoints:
  POST   /api/devices/register    — register or refresh a token
  DELETE /api/devices/{token}     — explicit unregister

These are called by the Capacitor shell when the user enables push
notifications in the app. Backend just stores the token — the actual
APN/FCM dispatch happens from `pt_invite_watcher.notify.mobile_push`
when a site's invite state transitions to "open".
"""
from __future__ import annotations

import logging
from typing import Annotated, Any, Dict

from fastapi import APIRouter, Body, Depends, HTTPException

from pt_invite_watcher.app_context import AppContext
from pt_invite_watcher.routes.common import cfg_str, get_ctx, require_auth, safe_dict
from pt_invite_watcher.storage.device_tokens_store import (
    list_device_tokens,
    remove_device_token,
    upsert_device_token,
)


logger = logging.getLogger("pt_invite_watcher.devices")

router = APIRouter()


@router.post("/api/devices/register", dependencies=[Depends(require_auth)])
async def api_devices_register(
    ctx: Annotated[AppContext, Depends(get_ctx)],
    payload: Dict[str, Any] = Body(default={}),
) -> Dict[str, Any]:
    """Register a device token for push delivery.

    Body shape:
      {"token": "<platform-issued>", "platform": "ios" | "android",
       "domain_filter": "a.example,b.example"}  # empty = all sites
    """
    payload = safe_dict(payload)
    token = cfg_str(payload.get("token"))
    platform = cfg_str(payload.get("platform")).lower()
    domain_filter = cfg_str(payload.get("domain_filter"))

    if not token:
        raise HTTPException(status_code=400, detail="token is required")
    if platform not in {"ios", "android"}:
        raise HTTPException(status_code=400, detail="platform must be ios|android")

    await upsert_device_token(
        ctx.store,
        token=token,
        platform=platform,
        domain_filter=domain_filter,
    )
    await ctx.store.add_event(
        category="notify",
        level="info",
        action="device_register",
        message=f"registered {platform} device",
        detail={"platform": platform, "has_filter": bool(domain_filter)},
    )
    return {"ok": True}


@router.delete("/api/devices/{token}", dependencies=[Depends(require_auth)])
async def api_devices_unregister(
    ctx: Annotated[AppContext, Depends(get_ctx)],
    token: str,
) -> Dict[str, Any]:
    removed = await remove_device_token(ctx.store, token)
    await ctx.store.add_event(
        category="notify",
        level="info",
        action="device_unregister",
        message="device unregistered" if removed else "device not found",
        detail={"removed": removed},
    )
    return {"ok": True, "removed": removed}


@router.get("/api/devices", dependencies=[Depends(require_auth)])
async def api_devices_list(ctx: Annotated[AppContext, Depends(get_ctx)]) -> Dict[str, Any]:
    """Lists registered devices — used by the Config page to show how many
    phones are subscribed, without exposing raw tokens (we truncate for PII)."""
    items = await list_device_tokens(ctx.store)
    safe = [
        {
            "id": x["id"],
            "platform": x["platform"],
            "token_preview": (x["token"][:8] + "…" if len(x["token"]) > 8 else x["token"]),
            "domain_filter": x["domain_filter"],
            "registered_at": x["registered_at"],
            "last_seen_at": x["last_seen_at"],
        }
        for x in items
    ]
    return {"items": safe, "total": len(safe)}
