from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Dict, Annotated

from fastapi import APIRouter, Body, Depends, HTTPException

from pt_invite_watcher.app_context import AppContext
from pt_invite_watcher.config_store import load_app_config, load_sites_config
from pt_invite_watcher.kv_keys import APP_CONFIG_KEY, NOTIFICATIONS_KEY, SCAN_STATUS_KEY, SITES_KEY
from pt_invite_watcher.routes.common import BACKUP_VERSION, SCAN_HINT_KEY, broadcast_dashboard_update, get_ctx, require_auth
from pt_invite_watcher.site_list_sync import sync_site_list_summary
from pt_invite_watcher.utils.parse import safe_dict


router = APIRouter()
logger = logging.getLogger("pt_invite_watcher.backup")


def _deep_merge(base: Any, update: Any) -> Any:
    if not isinstance(base, dict) or not isinstance(update, dict):
        return update
    merged = dict(base)
    for k, v in update.items():
        if k in merged:
            merged[k] = _deep_merge(merged[k], v)
        else:
            merged[k] = v
    return merged


def _redact_backup(data: Dict[str, Any]) -> Dict[str, Any]:
    cfg = safe_dict(data.get("app_config"))
    notif = safe_dict(data.get("notifications"))
    sites = safe_dict(data.get("sites"))

    cfg = _deep_merge({}, cfg)
    mp = safe_dict(cfg.get("moviepilot"))
    mp.pop("password", None)
    mp.pop("otp_password", None)
    if mp:
        cfg["moviepilot"] = mp
    cookie = safe_dict(cfg.get("cookie"))
    cc = safe_dict(safe_dict(cookie.get("cookiecloud")))
    cc.pop("password", None)
    if cc:
        cookie["cookiecloud"] = cc
    if cookie:
        cfg["cookie"] = cookie

    notif = _deep_merge({}, notif)
    telegram = safe_dict(notif.get("telegram"))
    telegram.pop("token", None)
    if telegram:
        notif["telegram"] = telegram
    wecom = safe_dict(notif.get("wecom"))
    wecom.pop("app_secret", None)
    if wecom:
        notif["wecom"] = wecom

    sites = _deep_merge({}, sites)
    entries = safe_dict(sites.get("entries"))
    redacted_entries: Dict[str, Any] = {}
    for domain, entry_any in entries.items():
        entry = safe_dict(entry_any)
        entry.pop("cookie", None)
        entry.pop("authorization", None)
        entry.pop("did", None)
        redacted_entries[str(domain)] = entry
    sites["entries"] = redacted_entries

    return {"app_config": cfg, "notifications": notif, "sites": sites}


@router.get("/api/backup/export", dependencies=[Depends(require_auth)])
async def api_backup_export(
    ctx: Annotated[AppContext, Depends(get_ctx)],
    include_secrets: int = 0,
) -> Dict[str, Any]:
    include = bool(int(include_secrets or 0))
    app_cfg = await load_app_config(ctx.store)
    notif_cfg = await ctx.store.get_json(NOTIFICATIONS_KEY, default={}) or {}
    sites_cfg = await load_sites_config(ctx.store)

    data = {"app_config": safe_dict(app_cfg), "notifications": safe_dict(notif_cfg), "sites": safe_dict(sites_cfg)}
    if not include:
        data = _redact_backup(data)

    await ctx.store.add_event(
        category="backup",
        level="info",
        action="backup_export",
        message="backup exported",
        detail={"include_secrets": include},
    )

    return {
        "version": BACKUP_VERSION,
        "exported_at": datetime.now(timezone.utc).isoformat(),
        "include_secrets": include,
        "data": data,
    }


@router.post("/api/backup/import", dependencies=[Depends(require_auth)])
async def api_backup_import(
    ctx: Annotated[AppContext, Depends(get_ctx)],
    payload: Dict[str, Any] = Body(default={}),
    mode: str = "merge",
) -> Dict[str, Any]:
    mode = (mode or "").strip().lower()
    if mode not in {"merge", "replace"}:
        raise HTTPException(status_code=400, detail="mode must be merge|replace")

    root = safe_dict(payload)
    data = safe_dict(root.get("data")) or root

    changed: list[str] = []

    if "app_config" in data:
        incoming = safe_dict(data.get("app_config"))
        if mode == "replace":
            await ctx.store.set_json(APP_CONFIG_KEY, incoming)
        else:
            current = await load_app_config(ctx.store)
            await ctx.store.set_json(APP_CONFIG_KEY, _deep_merge(current, incoming))
        try:
            ctx.runtime_config.invalidate()
        except Exception:
            pass
        changed.append("app_config")

    if "notifications" in data:
        incoming = safe_dict(data.get("notifications"))
        if mode == "replace":
            await ctx.store.set_json(NOTIFICATIONS_KEY, incoming)
        else:
            current = await ctx.store.get_json(NOTIFICATIONS_KEY, default={}) or {}
            await ctx.store.set_json(NOTIFICATIONS_KEY, _deep_merge(safe_dict(current), incoming))
        changed.append("notifications")

    if "sites" in data:
        incoming_sites = safe_dict(data.get("sites"))
        incoming_entries = safe_dict(incoming_sites.get("entries"))
        incoming = {"version": int(incoming_sites.get("version") or 1), "entries": incoming_entries}
        if mode == "replace":
            await ctx.store.set_json(SITES_KEY, incoming)
        else:
            current = await load_sites_config(ctx.store)
            current_entries = safe_dict(current.get("entries"))
            merged_entries = _deep_merge(current_entries, incoming_entries)
            await ctx.store.set_json(SITES_KEY, {"version": 1, "entries": merged_entries})
        changed.append("sites")

    if not changed:
        raise HTTPException(status_code=400, detail="no supported keys found in payload")

    if "sites" in changed:
        # Best-effort: keep effective site summary in sync after import.
        # Do not force a live MoviePilot call here.
        try:
            now = datetime.now(timezone.utc)
            eff = await ctx.effective_sites.load_for_sites(now=now, allow_live=False, force_live=False)
            await sync_site_list_summary(ctx.store, ctx.notifier, eff.sites, now, notify=True, reason="backup_import")
        except Exception:
            logger.exception("failed to sync site list summary (backup_import)")

    needs_scan_hint = any(k in changed for k in ("app_config", "sites"))
    if needs_scan_hint:
        await ctx.store.set_json(
            SCAN_HINT_KEY,
            {"reason": "import", "at": datetime.now(timezone.utc).isoformat(), "changed": list(changed)},
        )
        await ctx.store.set_json(SCAN_STATUS_KEY, None)

    await ctx.store.add_event(
        category="backup",
        level="info",
        action="backup_import",
        message="backup imported",
        detail={"mode": mode, "changed": list(changed), "needs_scan": needs_scan_hint},
    )

    try:
        await broadcast_dashboard_update()
    except Exception:
        pass

    return {"ok": True, "message": f"imported: {', '.join(changed)}", "changed": list(changed), "needs_scan": needs_scan_hint}
