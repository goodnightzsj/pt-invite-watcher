from __future__ import annotations

import logging
from typing import Any, Dict, Annotated

from fastapi import APIRouter, Body, Depends

from pt_invite_watcher.app_context import AppContext
from pt_invite_watcher.config_store import load_app_config
from pt_invite_watcher.kv_keys import APP_CONFIG_KEY
from pt_invite_watcher.providers.deps_status import (
    MAX_RETRY_INTERVAL_SECONDS,
    MIN_RETRY_INTERVAL_SECONDS,
)
from pt_invite_watcher.providers.moviepilot_sites_cache import (
    MP_SITES_CACHE_MAX_TTL_SECONDS,
    MP_SITES_CACHE_MIN_TTL_SECONDS,
)
from pt_invite_watcher.runtime_config import load_runtime_config
from pt_invite_watcher.routes.common import broadcast_dashboard_update, cfg_bool, cfg_int, cfg_str, get_ctx, require_auth
from pt_invite_watcher.utils.parse import safe_dict


router = APIRouter()
logger = logging.getLogger("pt_invite_watcher.routes.config_api")


@router.get("/api/config", dependencies=[Depends(require_auth)])
async def api_config_get(ctx: Annotated[AppContext, Depends(get_ctx)]) -> Dict[str, Any]:
    cfg = await load_app_config(ctx.store)
    rc = load_runtime_config(ctx.settings, cfg)

    moviepilot = {
        "base_url": rc.moviepilot.base_url,
        "username": rc.moviepilot.username,
        "password_configured": bool(rc.moviepilot.password),
        "otp_configured": bool(rc.moviepilot.otp_password),
        "sites_cache_ttl_seconds": rc.moviepilot.sites_cache_ttl_seconds,
    }
    cookie = {
        "source": rc.cookie.source,
        "cookiecloud": {
            "base_url": rc.cookie.cookiecloud.base_url,
            "uuid": rc.cookie.cookiecloud.uuid,
            "password_configured": bool(rc.cookie.cookiecloud.password),
            "refresh_interval_seconds": rc.cookie.cookiecloud.refresh_interval_seconds,
        },
    }
    scan = {
        "interval_seconds": rc.scan.interval_seconds,
        "timeout_seconds": rc.scan.timeout_seconds,
        "concurrency": rc.scan.concurrency,
        "user_agent": rc.scan.user_agent,
        "trust_env": rc.scan.trust_env,
    }

    connectivity = {
        "retry_interval_seconds": rc.connectivity.retry_interval_seconds,
        "request_retry_delay_seconds": rc.connectivity.request_retry_delay_seconds,
    }

    ui = {"allow_state_reset": rc.ui.allow_state_reset}

    return {"moviepilot": moviepilot, "connectivity": connectivity, "cookie": cookie, "scan": scan, "ui": ui}


@router.put("/api/config", dependencies=[Depends(require_auth)])
async def api_config_put(
    ctx: Annotated[AppContext, Depends(get_ctx)],
    payload: Dict[str, Any] = Body(default={}),
) -> Dict[str, Any]:
    cfg = await load_app_config(ctx.store)
    baseline = load_runtime_config(ctx.settings, cfg)

    payload = safe_dict(payload)

    mp_in = safe_dict(payload.get("moviepilot"))
    connectivity_in = safe_dict(payload.get("connectivity"))
    cookie_in = safe_dict(payload.get("cookie"))
    cc_in = safe_dict(cookie_in.get("cookiecloud"))
    scan_in = safe_dict(payload.get("scan"))
    ui_in = safe_dict(payload.get("ui"))

    mp = safe_dict(cfg.get("moviepilot"))
    mp_base = cfg_str(mp_in.get("base_url"))
    mp_user = cfg_str(mp_in.get("username"))
    mp_pass = cfg_str(mp_in.get("password"))
    mp_otp = cfg_str(mp_in.get("otp_password"))
    mp_clear_base = cfg_bool(mp_in.get("clear_base_url"), default=False)
    mp_clear_user = cfg_bool(mp_in.get("clear_username"), default=False)
    mp_clear_pass = cfg_bool(mp_in.get("clear_password"), default=False)
    mp_clear_otp = cfg_bool(mp_in.get("clear_otp_password"), default=False)

    if mp_clear_base:
        mp.pop("base_url", None)
    if mp_base:
        mp["base_url"] = mp_base
    if mp_clear_user:
        mp.pop("username", None)
    if mp_user:
        mp["username"] = mp_user
    if mp_clear_pass:
        mp.pop("password", None)
    if mp_pass:
        mp["password"] = mp_pass
    if mp_clear_otp:
        mp.pop("otp_password", None)
    if mp_otp:
        mp["otp_password"] = mp_otp
    mp["sites_cache_ttl_seconds"] = cfg_int(
        mp_in.get("sites_cache_ttl_seconds"),
        baseline.moviepilot.sites_cache_ttl_seconds,
        MP_SITES_CACHE_MIN_TTL_SECONDS,
        MP_SITES_CACHE_MAX_TTL_SECONDS,
    )
    cfg["moviepilot"] = mp

    connectivity = safe_dict(cfg.get("connectivity"))
    connectivity["retry_interval_seconds"] = cfg_int(
        connectivity_in.get("retry_interval_seconds"),
        baseline.connectivity.retry_interval_seconds,
        MIN_RETRY_INTERVAL_SECONDS,
        MAX_RETRY_INTERVAL_SECONDS,
    )
    connectivity["request_retry_delay_seconds"] = cfg_int(
        connectivity_in.get("request_retry_delay_seconds"),
        baseline.connectivity.request_retry_delay_seconds,
        5,
        24 * 3600,
    )
    cfg["connectivity"] = connectivity

    cookie = safe_dict(cfg.get("cookie"))
    src = cfg_str(cookie_in.get("source")).lower()
    if src in {"auto", "cookiecloud", "moviepilot"}:
        cookie["source"] = src

    cc = safe_dict(cookie.get("cookiecloud"))
    cc_base = cfg_str(cc_in.get("base_url"))
    cc_uuid = cfg_str(cc_in.get("uuid"))
    cc_pass = cfg_str(cc_in.get("password"))
    cc_clear_base = cfg_bool(cc_in.get("clear_base_url"), default=False)
    cc_clear_uuid = cfg_bool(cc_in.get("clear_uuid"), default=False)
    cc_clear_pass = cfg_bool(cc_in.get("clear_password"), default=False)

    if cc_clear_base:
        cc.pop("base_url", None)
    if cc_base:
        cc["base_url"] = cc_base
    if cc_clear_uuid:
        cc.pop("uuid", None)
    if cc_uuid:
        cc["uuid"] = cc_uuid
    if cc_clear_pass:
        cc.pop("password", None)
    if cc_pass:
        cc["password"] = cc_pass
    cc["refresh_interval_seconds"] = cfg_int(
        cc_in.get("refresh_interval_seconds"),
        baseline.cookie.cookiecloud.refresh_interval_seconds,
        30,
        24 * 3600,
    )
    cookie["cookiecloud"] = cc
    cfg["cookie"] = cookie

    scan = safe_dict(cfg.get("scan"))
    scan["interval_seconds"] = cfg_int(scan_in.get("interval_seconds"), baseline.scan.interval_seconds, 30, 24 * 3600)
    scan["timeout_seconds"] = cfg_int(scan_in.get("timeout_seconds"), baseline.scan.timeout_seconds, 5, 180)
    scan["concurrency"] = cfg_int(scan_in.get("concurrency"), baseline.scan.concurrency, 1, 64)

    if "user_agent" in scan_in:
        ua_in = scan_in.get("user_agent")
        ua = ("" if ua_in is None else str(ua_in)).strip()
        if ua != "":
            scan["user_agent"] = ua
        elif "user_agent" in scan:
            scan.pop("user_agent", None)

    if "trust_env" in scan_in:
        scan["trust_env"] = cfg_bool(scan_in.get("trust_env"), default=baseline.scan.trust_env)

    cfg["scan"] = scan

    ui = safe_dict(cfg.get("ui"))
    if "allow_state_reset" in ui_in:
        ui["allow_state_reset"] = cfg_bool(ui_in.get("allow_state_reset"), default=baseline.ui.allow_state_reset)
    cfg["ui"] = ui

    await ctx.store.set_json(APP_CONFIG_KEY, cfg)
    try:
        ctx.runtime_config.invalidate()
    except Exception:
        # Cache invalidation is best-effort, but we log it: silently swallowing means a stale
        # config can keep driving the scheduler indefinitely without operator visibility.
        logger.exception("runtime_config.invalidate() failed after config update")
    await ctx.store.add_event(
        category="config",
        level="info",
        action="config_update",
        message="app config updated",
        detail={"keys": list(payload.keys())},
    )
    try:
        await broadcast_dashboard_update()
    except Exception:
        logger.exception("broadcast_dashboard_update() failed after config update")
    return {"ok": True}


@router.post("/api/config/reset", dependencies=[Depends(require_auth)])
async def api_config_reset(ctx: Annotated[AppContext, Depends(get_ctx)]) -> Dict[str, Any]:
    await ctx.store.set_json(APP_CONFIG_KEY, {})
    try:
        ctx.runtime_config.invalidate()
    except Exception:
        pass
    await ctx.store.add_event(category="config", level="info", action="config_reset", message="app config reset")
    try:
        await broadcast_dashboard_update()
    except Exception:
        pass
    return {"ok": True}
