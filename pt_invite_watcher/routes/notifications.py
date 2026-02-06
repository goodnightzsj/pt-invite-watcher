from __future__ import annotations

from typing import Any, Dict, Annotated

from fastapi import APIRouter, Body, Depends, HTTPException

from pt_invite_watcher.app_context import AppContext
from pt_invite_watcher.kv_keys import NOTIFICATIONS_KEY
from pt_invite_watcher.routes.common import cfg_str, get_ctx, require_auth
from pt_invite_watcher.utils.parse import safe_dict


router = APIRouter()


@router.get("/api/notifications", dependencies=[Depends(require_auth)])
async def api_notifications_get(ctx: Annotated[AppContext, Depends(get_ctx)]) -> Dict[str, Any]:
    cfg = await ctx.store.get_json(NOTIFICATIONS_KEY, default={}) or {}
    cfg = safe_dict(cfg)
    telegram = safe_dict(cfg.get("telegram"))
    wecom = safe_dict(cfg.get("wecom"))

    telegram_view = {
        "enabled": bool(telegram.get("enabled")),
        "configured": bool(telegram.get("token") and telegram.get("chat_id")),
        "chat_id": cfg_str(telegram.get("chat_id")),
    }
    wecom_view = {
        "enabled": bool(wecom.get("enabled")),
        "configured": bool(wecom.get("corpid") and wecom.get("app_secret") and wecom.get("agent_id")),
        "corpid": cfg_str(wecom.get("corpid")),
        "agent_id": cfg_str(wecom.get("agent_id")),
        "to_user": cfg_str(wecom.get("to_user")) or "@all",
        "to_party": cfg_str(wecom.get("to_party")),
        "to_tag": cfg_str(wecom.get("to_tag")),
    }

    return {"telegram": telegram_view, "wecom": wecom_view}


@router.put("/api/notifications", dependencies=[Depends(require_auth)])
async def api_notifications_put(
    ctx: Annotated[AppContext, Depends(get_ctx)],
    payload: Dict[str, Any] = Body(default={}),
) -> Dict[str, Any]:
    cfg = await ctx.store.get_json(NOTIFICATIONS_KEY, default={}) or {}
    cfg = safe_dict(cfg)

    payload = safe_dict(payload)
    tg_in = safe_dict(payload.get("telegram"))
    wc_in = safe_dict(payload.get("wecom"))

    telegram = safe_dict(cfg.get("telegram"))
    wecom = safe_dict(cfg.get("wecom"))

    if "enabled" in tg_in:
        telegram["enabled"] = bool(tg_in.get("enabled"))
    token = cfg_str(tg_in.get("token"))
    if token:
        telegram["token"] = token
    chat_id = cfg_str(tg_in.get("chat_id"))
    if chat_id:
        telegram["chat_id"] = chat_id

    if "enabled" in wc_in:
        wecom["enabled"] = bool(wc_in.get("enabled"))
    corpid = cfg_str(wc_in.get("corpid"))
    if corpid:
        wecom["corpid"] = corpid
    app_secret = cfg_str(wc_in.get("app_secret"))
    if app_secret:
        wecom["app_secret"] = app_secret
    agent_id = cfg_str(wc_in.get("agent_id"))
    if agent_id:
        wecom["agent_id"] = agent_id

    if "to_user" in wc_in:
        wecom["to_user"] = (cfg_str(wc_in.get("to_user")) or "@all").strip()
    if "to_party" in wc_in:
        wecom["to_party"] = cfg_str(wc_in.get("to_party"))
    if "to_tag" in wc_in:
        wecom["to_tag"] = cfg_str(wc_in.get("to_tag"))

    await ctx.store.set_json(NOTIFICATIONS_KEY, {"telegram": telegram, "wecom": wecom})
    await ctx.store.add_event(
        category="notify",
        level="info",
        action="notifications_update",
        message="notifications updated",
        detail={
            "telegram_enabled": bool(telegram.get("enabled")),
            "telegram_configured": bool(telegram.get("token") and telegram.get("chat_id")),
            "wecom_enabled": bool(wecom.get("enabled")),
            "wecom_configured": bool(wecom.get("corpid") and wecom.get("app_secret") and wecom.get("agent_id")),
        },
    )
    return {"ok": True}


@router.post("/api/notifications/test/{channel}", dependencies=[Depends(require_auth)])
async def api_notifications_test(channel: str, ctx: Annotated[AppContext, Depends(get_ctx)]) -> Dict[str, Any]:
    if channel not in {"telegram", "wecom"}:
        raise HTTPException(status_code=404, detail="unknown channel")
    ok, msg = await ctx.notifier.test(channel)
    await ctx.store.add_event(
        category="notify",
        level="info" if ok else "error",
        action="notifications_test",
        message=f"{channel} test: {'ok' if ok else 'fail'}",
        detail={"channel": channel, "ok": ok, "message": msg},
    )
    return {"ok": bool(ok), "message": str(msg or "")}
