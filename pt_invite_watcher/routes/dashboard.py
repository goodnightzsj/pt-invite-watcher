from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Dict, Annotated

from fastapi import APIRouter, Depends, HTTPException

from pt_invite_watcher.app_context import AppContext
from pt_invite_watcher.dashboard_state_view import derive_state_view
from pt_invite_watcher.engines.engine_selector import engine_for_site
from pt_invite_watcher.kv_keys import SCAN_STATUS_KEY
from pt_invite_watcher.routes.common import (
    SCAN_HINT_KEY,
    broadcast_dashboard_update,
    cfg_str,
    get_ctx,
    get_runtime_config_dep,
    normalize_domain,
    require_auth,
    ws_broadcaster,
)
from pt_invite_watcher.routes.site_helpers import derive_site_page_urls


logger = logging.getLogger("pt_invite_watcher.dashboard")

router = APIRouter()

@router.get("/api/dashboard", dependencies=[Depends(require_auth)])
async def api_dashboard(ctx: Annotated[AppContext, Depends(get_ctx)]) -> Dict[str, Any]:
    now = datetime.now(timezone.utc)

    rc = await get_runtime_config_dep(ctx)

    eff = await ctx.effective_sites.load_for_dashboard(now=now)
    sites = eff.sites
    current_domains = [normalize_domain(s.domain) for s in sites if normalize_domain(s.domain)]

    states = await ctx.store.list_site_states()
    state_map = {normalize_domain(r.get("domain") or ""): r for r in states if normalize_domain(r.get("domain") or "")}

    extras_map: Dict[str, Dict[str, Any]] = {}
    try:
        extras_map = await ctx.store.get_sites_extras(current_domains)
    except Exception:
        extras_map = {}

    rows: list[dict[str, Any]] = []
    for site in sites:
        domain = normalize_domain(site.domain)
        if not domain:
            continue
        state_row = dict(state_map.get(domain) or {})
        derived = derive_state_view(state_row) if state_row else {}
        row = dict(state_row)
        row.pop("last_evidence", None)

        template = cfg_str(getattr(site, "template", None)).lower()
        engine = cfg_str(row.get("engine")) or engine_for_site(site)
        row["domain"] = domain
        row["name"] = cfg_str(getattr(site, "name", None)) or row.get("name") or domain
        row["url"] = cfg_str(getattr(site, "url", None)) or row.get("url") or ""
        row["engine"] = engine

        if "reachability_state" not in row:
            row["reachability_state"] = derived.get("reachability_state") or "unknown"
        if "reachability_note" not in row:
            row["reachability_note"] = derived.get("reachability_note") or ""
        if "registration_state" not in row:
            row["registration_state"] = "unknown"
        if "registration_note" not in row:
            row["registration_note"] = derived.get("registration_note") or ""
        if "invites_state" not in row:
            row["invites_state"] = "unknown"
        if "invites_available" not in row:
            row["invites_available"] = None
        if "invites_display" not in row:
            row["invites_display"] = derived.get("invites_display") or ""
        if "last_checked_at" not in row:
            row["last_checked_at"] = ""
        if "last_changed_at" not in row:
            row["last_changed_at"] = None
        if "errors" not in row:
            row["errors"] = derived.get("errors") or []

        base_url = row["url"]

        invite_uid = cfg_str((extras_map.get(domain) or {}).get("invite_uid")) if template in {"", "nexusphp"} else ""
        urls = derive_site_page_urls(
            base_url=base_url,
            template=template,
            registration_path=getattr(site, "registration_path", None),
            invite_path=getattr(site, "invite_path", None),
            invite_uid=invite_uid,
        )
        row["registration_url"] = urls["registration_url"]
        row["invite_url"] = urls["invite_url"]

        rows.append(row)

    inflight = set()
    try:
        inflight = set(ctx.scanner.in_flight_domains() or [])
    except Exception:
        inflight = set()
    if inflight:
        for r in rows:
            r["scanning"] = normalize_domain(r.get("domain") or "") in inflight
    else:
        for r in rows:
            r["scanning"] = False
    scan_status = await ctx.store.get_json(SCAN_STATUS_KEY, default=None)
    scan_hint = await ctx.store.get_json(SCAN_HINT_KEY, default=None)
    ui = {"allow_state_reset": rc.ui.allow_state_reset}
    return {"rows": rows, "scan_status": scan_status, "scan_hint": scan_hint, "ui": ui}


@router.post("/api/state/reset", dependencies=[Depends(require_auth)])
async def api_state_reset(ctx: Annotated[AppContext, Depends(get_ctx)]) -> Dict[str, Any]:
    rc = await get_runtime_config_dep(ctx)
    allowed = rc.ui.allow_state_reset
    if not allowed:
        raise HTTPException(status_code=403, detail="state reset disabled")

    await ctx.store.reset_site_states()
    await ctx.store.set_json(SCAN_STATUS_KEY, None)
    await ctx.store.set_json(SCAN_HINT_KEY, None)
    await ctx.store.add_event(category="config", level="info", action="state_reset", message="site state reset")
    await broadcast_dashboard_update()
    return {"ok": True}
