from __future__ import annotations

import asyncio
import logging
import time
from datetime import datetime, timezone
from typing import Any, Dict, Optional, Tuple, Annotated

import httpx
from fastapi import APIRouter, Body, Depends, HTTPException
from fastapi.responses import Response

from pt_invite_watcher.app_context import AppContext
from pt_invite_watcher.engines.redirect_guard import guarded_get
from pt_invite_watcher.engines.site_registry import (
    find_by_domain as _registry_find_by_domain,
    friendly_peers_for,
    list_all as _registry_list_all,
)
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


_FAVICON_MAX_BYTES = 256 * 1024  # 256 KB — a favicon should never exceed this
_FAVICON_TIMEOUT_SECONDS = 6
_FAVICON_BROWSER_HEADERS = {
    # Browser-ish headers so anti-bot layers don't serve us an HTML error page.
    "Accept": "image/avif,image/webp,image/apng,image/*,*/*;q=0.8",
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
}

# Probe order: start with the historical default, then fall through to modern
# locations. Many recent PT sites only ship PNG / apple-touch-icon and answer
# /favicon.ico with 404, so skipping the fallbacks misses icons we could have
# served. Stops at the first valid image — doesn't keep pounding on a site.
_FAVICON_PATHS: tuple[str, ...] = (
    "/favicon.ico",
    "/favicon.png",
    "/apple-touch-icon.png",
    "/apple-touch-icon-precomposed.png",
)

# Shared outbound client: creating a fresh AsyncClient per request pays a full
# TCP+TLS handshake every time, which adds ~50-200ms per icon on a cold pool.
# The singleton keeps keep-alive sockets warm across requests.
_ICON_CLIENT_LIMITS = httpx.Limits(max_connections=16, max_keepalive_connections=8)
_ICON_CLIENT: Optional[httpx.AsyncClient] = None
_ICON_CLIENT_LOCK = asyncio.Lock()

# Server-side icon cache. Without this, N browsers pointed at the same server
# each trigger an upstream fetch to every PT site every 12h — multiplying a
# per-user load by the number of dashboards open. Status is stored so negative
# results (hijacked/unreachable) don't retry on every request.
# entry: (expires_at_monotonic, status_code, body, content_type)
_ICON_CACHE_TTL_OK = 12 * 3600          # 12h — matches the client-side Cache-Control
_ICON_CACHE_TTL_FAIL = 60 * 60          # 1h  — faster recovery when a hijack gets fixed
_ICON_CACHE_MAX = 2048
_icon_cache: Dict[str, Tuple[float, int, bytes, str]] = {}


async def _get_icon_client() -> httpx.AsyncClient:
    global _ICON_CLIENT
    if _ICON_CLIENT is not None:
        return _ICON_CLIENT
    async with _ICON_CLIENT_LOCK:
        if _ICON_CLIENT is None:
            _ICON_CLIENT = httpx.AsyncClient(
                timeout=_FAVICON_TIMEOUT_SECONDS,
                http2=True,
                limits=_ICON_CLIENT_LIMITS,
            )
    return _ICON_CLIENT


async def close_icon_client() -> None:
    """Called from the app lifespan on shutdown — cleanly drains the pool."""
    global _ICON_CLIENT
    if _ICON_CLIENT is None:
        return
    client = _ICON_CLIENT
    _ICON_CLIENT = None
    try:
        await client.aclose()
    except Exception:
        logger.exception("icon proxy client close failed")


def _icon_cache_get(dom: str) -> Optional[Tuple[int, bytes, str]]:
    entry = _icon_cache.get(dom)
    if entry is None:
        return None
    expires_at, status, body, ct = entry
    if expires_at < time.monotonic():
        _icon_cache.pop(dom, None)
        return None
    return status, body, ct


def _icon_cache_put(dom: str, status: int, body: bytes, ct: str) -> None:
    if len(_icon_cache) >= _ICON_CACHE_MAX:
        # Evict the 10% closest-to-expiry entries so a single pathological run
        # can't unbounded-grow the cache. Cheap (O(n log n)) since n is bounded.
        drop = sorted(_icon_cache.items(), key=lambda kv: kv[1][0])[: max(1, _ICON_CACHE_MAX // 10)]
        for k, _ in drop:
            _icon_cache.pop(k, None)
    ttl = _ICON_CACHE_TTL_OK if status == 200 else _ICON_CACHE_TTL_FAIL
    _icon_cache[dom] = (time.monotonic() + ttl, status, body, ct)


@router.get("/api/sites/icon", dependencies=[Depends(require_auth)])
async def api_site_icon(domain: str) -> Response:
    """Server-side favicon proxy with redirect-guard protection.

    The browser's ``<img>`` element silently follows cross-origin redirects, so if a
    site is hijacked (``xingyunge.org/favicon.ico`` → ``tmdi.pw/favicon.ico``) the
    frontend ends up caching the hijacker's icon as if it were genuine. Routing the
    fetch through ``guarded_get`` lets us detect the offsite hop and return 204 —
    the frontend then falls back to external icon services (DuckDuckGo / Google)
    which generally keep a record of the site's legitimate icon from its healthy
    days.

    A 204 (rather than 404) is deliberate: it signals "probed, no valid icon"
    without polluting the browser's error console.
    """
    dom = normalize_domain(domain)
    if not dom:
        raise HTTPException(status_code=400, detail="domain required")

    cached = _icon_cache_get(dom)
    if cached is not None:
        status, body, ct = cached
        if status == 204:
            return Response(status_code=204)
        return Response(
            content=body,
            media_type=ct or "image/x-icon",
            headers={"Cache-Control": "public, max-age=43200"},
        )

    friendly = friendly_peers_for(dom)

    def _remember_fail() -> Response:
        _icon_cache_put(dom, 204, b"", "")
        return Response(status_code=204)

    try:
        client = await _get_icon_client()
    except Exception:
        logger.exception("favicon proxy failed to obtain client for %s", dom)
        return _remember_fail()

    # Try each candidate path in order. An offsite-redirect verdict from any
    # probe is decisive — once guarded_get says "this origin is redirecting you
    # elsewhere" we short-circuit rather than keep probing (they'd all redirect
    # the same way and we'd just pile up 204s).
    for path in _FAVICON_PATHS:
        url = f"https://{dom}{path}"
        try:
            gr = await guarded_get(
                client,
                url,
                expected_host=dom,
                friendly_hosts=friendly,
                headers=_FAVICON_BROWSER_HEADERS,
                attempts=1,
                delay_seconds=0,
            )
        except Exception:
            logger.exception("favicon proxy failed for %s (path=%s)", dom, path)
            # Transient error on one path shouldn't doom the rest; try the next.
            continue

        if gr.off_site_reason:
            # Hijack / parked redirect — give up on this domain entirely.
            if gr.response is not None:
                try:
                    await gr.response.aclose()
                except Exception:
                    pass
            return _remember_fail()

        if gr.response is None or gr.error is not None:
            if gr.response is not None:
                try:
                    await gr.response.aclose()
                except Exception:
                    pass
            continue

        resp = gr.response
        try:
            if resp.status_code >= 400:
                continue
            content_type = (resp.headers.get("Content-Type") or "").split(";")[0].strip().lower()
            # Some sites serve an HTML 404 page with a 200 status when the
            # favicon is missing. Treat only real image types as valid.
            if not (content_type.startswith("image/") or content_type in {"application/octet-stream", "application/x-ico"}):
                continue
            body = resp.content
            if not body or len(body) < 32 or len(body) > _FAVICON_MAX_BYTES:
                continue
            media_type = content_type or "image/x-icon"
            _icon_cache_put(dom, 200, body, media_type)
            return Response(
                content=body,
                media_type=media_type,
                headers={
                    # 12h browser cache is enough to let users see icon refreshes on
                    # the same day, while cutting origin hits by ~99%.
                    "Cache-Control": "public, max-age=43200",
                },
            )
        finally:
            try:
                await resp.aclose()
            except Exception:
                pass

    # Exhausted all candidate paths without a valid icon.
    return _remember_fail()


@router.get("/api/sites/registry", dependencies=[Depends(require_auth)])
async def api_sites_registry() -> Dict[str, Any]:
    """Return the curated list of known PT sites.

    The WebUI uses this to power the "pick a known site" dropdown when adding a
    new manual site — users don't have to remember URLs, canonical names, or
    which engine schema each site runs. Client-side filters keep this fast even
    as the registry grows.
    """
    items = [
        {
            "id": sd.id,
            "name": sd.name,
            "aliases": list(sd.aliases),
            "domains": list(sd.domains),
            "primary_domain": sd.primary_domain,
            "primary_url": sd.primary_url,
            "schema": sd.schema,
            "tags": list(sd.tags),
            "registration_path": sd.registration_path,
            "invite_path": sd.invite_path,
            "notes": sd.notes,
        }
        for sd in _registry_list_all()
    ]
    return {"items": items, "total": len(items)}


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
