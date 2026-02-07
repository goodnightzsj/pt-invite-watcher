from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from typing import Any, Dict, Annotated

from fastapi import APIRouter, Body, Depends, HTTPException

from pt_invite_watcher.app_context import AppContext
from pt_invite_watcher.kv_keys import SITES_KEY
from pt_invite_watcher.routes.common import (
    broadcast_dashboard_update,
    cfg_str,
    domain_from_url,
    get_ctx,
    load_sites_config_payload,
    normalize_domain,
    relative_path_from_page_url,
    require_auth,
    site_entry_view,
)
from pt_invite_watcher.routes.site_helpers import derive_site_page_urls
from pt_invite_watcher.scanner import AlreadyScanningError
from pt_invite_watcher.site_list_sync import sync_site_list_summary
from pt_invite_watcher.site_templates import SITE_TEMPLATES, default_paths_for_template, infer_template, normalize_template, validate_template_for_domain
from pt_invite_watcher.utils.asyncio_tasks import create_task_logged
from pt_invite_watcher.utils.parse import safe_dict


logger = logging.getLogger("pt_invite_watcher.sites")

router = APIRouter()


async def _sync_site_list_summary_after_sites_write(
    ctx: AppContext,
    *,
    reason: str,
) -> None:
    """
    Best-effort: keep effective site summary in sync after site-config changes.
    This runs without forcing a live MoviePilot call (uses cache/state fallback).
    """
    try:
        now = datetime.now(timezone.utc)
        eff = await ctx.effective_sites.load_for_sites(now=now, allow_live=False, force_live=False)
        await sync_site_list_summary(ctx.store, ctx.notifier, eff.sites, now, notify=True, reason=reason)
    except Exception:
        logger.exception("failed to sync site list summary (%s)", reason)


@router.get("/api/sites", dependencies=[Depends(require_auth)])
async def api_sites_get(
    ctx: Annotated[AppContext, Depends(get_ctx)],
    live: int = 1,
    force: int = 0,
) -> Dict[str, Any]:
    now = datetime.now(timezone.utc)
    allow_live = bool(int(live or 0))
    force_live = bool(int(force or 0))

    items: list[Dict[str, Any]] = []
    eff = await ctx.effective_sites.load_for_sites(now=now, allow_live=allow_live, force_live=force_live)

    mp_result = eff.moviepilot
    mp_error = mp_result.error
    mp_ok = mp_result.ok
    mp_source = mp_result.source
    mp_cache_fetched_at = mp_result.cache_fetched_at
    mp_cache_age_seconds = mp_result.cache_age_seconds
    mp_cache_expired = mp_result.cache_expired

    entries = eff.entries
    for site in eff.sites:
        domain = normalize_domain(site.domain)
        if not domain:
            continue

        entry = safe_dict(entries.get(domain))
        if entry and (cfg_str(entry.get("mode")) or "").lower() not in {"override", "manual"}:
            entry = {}

        source = "moviepilot" if getattr(site, "id", None) is not None else "manual"
        default_tpl = "nexusphp" if source == "moviepilot" else "custom"
        template_value = infer_template(domain, getattr(site, "template", None) or entry.get("template"), default=default_tpl)
        view = site_entry_view(entry, site.url)
        urls = derive_site_page_urls(
            base_url=site.url,
            template=template_value,
            registration_path=getattr(site, "registration_path", None),
            invite_path=getattr(site, "invite_path", None),
        )
        registration_url = urls["registration_url"]
        invite_url = urls["invite_url"]

        items.append(
            {
                "domain": domain,
                "name": site.name,
                "url": site.url,
                "source": source,
                "template": template_value,
                "has_local_config": bool(entry) if source == "moviepilot" else True,
                "cookie_configured": bool(view.get("cookie_configured")),
                "authorization_configured": bool(view.get("authorization_configured")),
                "did_configured": bool(view.get("did_configured")),
                "registration_url": registration_url,
                "invite_url": invite_url,
            }
        )

    try:
        extras_map = await ctx.store.get_sites_extras([normalize_domain(x.get("domain") or "") for x in items])
        for x in items:
            dom = normalize_domain(x.get("domain") or "")
            if not dom:
                continue
            extra = extras_map.get(dom) or {}
            x["reachability_state"] = extra.get("reachability_state", "unknown")
            if x.get("template") == "nexusphp":
                invite_uid = extra.get("invite_uid")
                if invite_uid:
                    x["invite_url"] = derive_site_page_urls(
                        base_url=x.get("url", ""),
                        template="nexusphp",
                        invite_uid=str(invite_uid),
                    )["invite_url"]
    except Exception:
        logger.exception("failed to load site extras for sites list")

    items.sort(
        key=lambda x: (
            (x.get("reachability_state") == "down"),
            (x.get("source") != "moviepilot"),
            x.get("name") or x.get("domain") or "",
        )
    )
    if mp_error and mp_source in {"cache", "state", "summary"} and mp_cache_age_seconds is not None:
        mp_error = f"{mp_error} (fallback={mp_source} age={mp_cache_age_seconds}s)"
    return {
        "items": items,
        "moviepilot_ok": bool(mp_ok),
        "moviepilot_error": mp_error,
        "moviepilot_source": mp_source,
        "moviepilot_cache_fetched_at": mp_cache_fetched_at,
        "moviepilot_cache_age_seconds": mp_cache_age_seconds,
        "moviepilot_cache_expired": mp_cache_expired,
    }


@router.put("/api/sites", dependencies=[Depends(require_auth)])
async def api_sites_put(
    ctx: Annotated[AppContext, Depends(get_ctx)],
    payload: Dict[str, Any] = Body(default={}),
) -> Dict[str, Any]:
    payload = safe_dict(payload)
    mode = (cfg_str(payload.get("mode")) or "manual").lower()
    if mode not in {"manual", "override"}:
        raise HTTPException(status_code=400, detail="mode must be manual|override")

    url = cfg_str(payload.get("url"))
    domain = normalize_domain(cfg_str(payload.get("domain")) or domain_from_url(url))
    if not domain:
        raise HTTPException(status_code=400, detail="domain is required (or provide url)")

    name = cfg_str(payload.get("name"))
    template_raw = cfg_str(payload.get("template")) or "nexusphp"
    template = normalize_template(template_raw)
    if not template:
        supported = "|".join(sorted(SITE_TEMPLATES.keys()))
        raise HTTPException(status_code=400, detail=f"template must be {supported}")
    if not validate_template_for_domain(template, domain):
        raise HTTPException(status_code=400, detail=f"{template} template not supported for domain {domain}")

    cookie = payload.get("cookie")
    clear_cookie = bool(payload.get("clear_cookie"))

    authorization = payload.get("authorization")
    clear_authorization = bool(payload.get("clear_authorization"))
    did = payload.get("did")
    clear_did = bool(payload.get("clear_did"))

    registration_url = cfg_str(payload.get("registration_url"))
    invite_url = cfg_str(payload.get("invite_url"))

    sites_cfg = await load_sites_config_payload(ctx)
    entries = safe_dict(sites_cfg.get("entries"))
    existed = domain in entries
    entry = safe_dict(entries.get(domain))
    entry["mode"] = mode

    if name != "":
        entry["name"] = name
    elif "name" in payload and "name" in entry:
        entry.pop("name", None)

    if mode == "manual":
        if not url:
            raise HTTPException(status_code=400, detail="url is required for manual site")
        entry["url"] = url
    else:
        if url:
            entry["url"] = url

    entry["template"] = template

    if clear_cookie:
        entry.pop("cookie", None)
    elif cookie is not None and cfg_str(cookie):
        entry["cookie"] = cfg_str(cookie)

    if clear_authorization:
        entry.pop("authorization", None)
    elif authorization is not None and cfg_str(authorization):
        entry["authorization"] = cfg_str(authorization)

    if clear_did:
        entry.pop("did", None)
    elif did is not None and cfg_str(did):
        entry["did"] = cfg_str(did)

    if template == "custom":
        if not registration_url or not invite_url:
            raise HTTPException(status_code=400, detail="registration_url and invite_url are required for custom template")
        base_for_validate = url or registration_url
        entry["registration_path"] = relative_path_from_page_url(registration_url, base_for_validate, label="registration_url")
        entry["invite_path"] = relative_path_from_page_url(invite_url, base_for_validate, label="invite_url")
    else:
        entry.pop("registration_path", None)
        entry.pop("invite_path", None)
        if template == "mteam":
            reg_default, inv_default = default_paths_for_template(template)
            entry["registration_path"] = reg_default
            entry["invite_path"] = inv_default

    entries[domain] = entry
    await ctx.store.set_json(SITES_KEY, {"version": 1, "entries": entries})

    await ctx.store.add_event(
        category="site",
        level="info",
        action="site_upsert",
        message="site added" if not existed else "site updated",
        domain=domain,
        detail={"mode": mode, "template": template},
    )

    await _sync_site_list_summary_after_sites_write(ctx, reason="sites_put")
    try:
        await broadcast_dashboard_update()
    except Exception:
        pass

    scan_triggered = False
    scan_reason = ""
    try:
        inflight = set(ctx.scanner.in_flight_domains() or [])
    except Exception:
        inflight = set()
    if domain in inflight:
        scan_triggered = False
        scan_reason = "already_scanning"
    else:
        scan_triggered = True

        async def _kick() -> None:
            run_task = asyncio.create_task(ctx.scanner.run_one(domain), name=f"scan_one_{domain}")
            await asyncio.sleep(0)
            try:
                await broadcast_dashboard_update()
            except Exception:
                pass
            try:
                await run_task
            except AlreadyScanningError:
                return
            except Exception:
                logger.exception("auto scan after sites upsert failed: %s", domain)
            finally:
                try:
                    await broadcast_dashboard_update()
                except Exception:
                    pass

        create_task_logged(
            _kick(),
            logger=logger,
            name=f"sites_auto_scan_{domain}",
            label="sites auto scan",
        )

    return {"ok": True, "scan_triggered": scan_triggered, "scan_reason": scan_reason}


@router.delete("/api/sites/{domain}", dependencies=[Depends(require_auth)])
async def api_sites_delete(domain: str, ctx: Annotated[AppContext, Depends(get_ctx)]) -> Dict[str, Any]:
    dom = normalize_domain(domain)
    sites_cfg = await load_sites_config_payload(ctx)
    entries = safe_dict(sites_cfg.get("entries"))
    existed = dom in entries
    existed_mode = cfg_str(safe_dict(entries.get(dom)).get("mode")).lower() if existed else ""
    if existed:
        entries.pop(dom, None)
        await ctx.store.set_json(SITES_KEY, {"version": 1, "entries": entries})
        await ctx.store.add_event(
            category="site",
            level="info",
            action="site_delete" if existed_mode == "manual" else "site_override_clear",
            message="site deleted" if existed_mode == "manual" else "site override cleared",
            domain=dom,
        )

        await _sync_site_list_summary_after_sites_write(ctx, reason="sites_delete")
        try:
            await broadcast_dashboard_update()
        except Exception:
            pass
    return {"ok": True}
