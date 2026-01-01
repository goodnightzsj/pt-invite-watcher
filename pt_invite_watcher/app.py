from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Annotated, Any, Dict, Optional
from urllib.parse import urljoin, urlparse

from fastapi import Body, Depends, FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.security import HTTPBasic, HTTPBasicCredentials
import json

from pt_invite_watcher.app_context import AppContext, build_context
from pt_invite_watcher.config import Settings, load_settings
from pt_invite_watcher.providers.moviepilot_api import MoviePilotClient
from pt_invite_watcher.scanner import AlreadyScanningError
from pt_invite_watcher.providers.moviepilot_sites_cache import (
    MP_SITES_CACHE_DEFAULT_TTL_SECONDS,
    MP_SITES_CACHE_KEY,
    MP_SITES_CACHE_MAX_TTL_SECONDS,
    MP_SITES_CACHE_MIN_TTL_SECONDS,
    build_cache,
    cache_expired,
    parse_cache,
)
from pt_invite_watcher.providers.deps_status import (
    DEFAULT_RETRY_INTERVAL_SECONDS,
    DEPS_STATUS_KEY,
    MAX_RETRY_INTERVAL_SECONDS,
    MIN_RETRY_INTERVAL_SECONDS,
    can_attempt,
    fingerprint_moviepilot,
    get_dep_status,
    load_deps_status,
    update_dep_fail,
    update_dep_ok,
)
from pt_invite_watcher.models import Site
from pt_invite_watcher.site_list import SITE_LIST_SUMMARY_KEY


logger = logging.getLogger("pt_invite_watcher")

app = FastAPI(title="PT Invite Watcher", version="0.1.0")

basic_security = HTTPBasic(auto_error=False)

_DIST_DIR = Path(__file__).resolve().parent / "webui_dist"
_ASSETS_DIR = _DIST_DIR / "assets"
_BACKUP_VERSION = 1
_SCAN_HINT_KEY = "scan_hint"

# Serve Vite build assets. We intentionally don't require auth here; the SPA entry and APIs are protected.
app.mount("/assets", StaticFiles(directory=_ASSETS_DIR.as_posix(), check_dir=False), name="assets")

_MAX_ERROR_DETAIL_LEN = 240
_DEFAULT_REQUEST_RETRY_DELAY_SECONDS = 30


# SSE Broadcaster for real-time updates
class SSEBroadcaster:
    def __init__(self):
        self._clients: list[asyncio.Queue] = []
    
    async def subscribe(self) -> asyncio.Queue:
        queue: asyncio.Queue = asyncio.Queue()
        self._clients.append(queue)
        return queue
    
    def unsubscribe(self, queue: asyncio.Queue):
        if queue in self._clients:
            self._clients.remove(queue)
    
    async def broadcast(self, event_type: str, data: Any = None):
        msg = {"type": event_type, "data": data}
        for queue in self._clients:
            try:
                queue.put_nowait(msg)
            except asyncio.QueueFull:
                pass  # Drop message if queue is full

sse_broadcaster = SSEBroadcaster()


def _cfg_str(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _cfg_int(value: Any, default: int, min_value: int, max_value: int) -> int:
    if value is None or value == "":
        return default
    try:
        parsed = int(str(value).strip())
    except ValueError:
        return default
    return max(min_value, min(max_value, parsed))


def _cfg_bool(value: Any, default: bool) -> bool:
    if value is None or value == "":
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, int):
        return value != 0
    return str(value).strip().lower() in {"1", "true", "yes", "y", "on"}


def _safe_dict(value: Any) -> Dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _format_error_detail(exc: Exception) -> str:
    msg = str(exc or "").strip()
    if not msg:
        cause = getattr(exc, "__cause__", None)
        if cause is not None:
            msg = str(cause).strip()
    if not msg:
        msg = type(exc).__name__
    msg = " ".join(msg.split())
    if len(msg) > _MAX_ERROR_DETAIL_LEN:
        msg = msg[: _MAX_ERROR_DETAIL_LEN - 1] + "…"
    return msg


def _normalize_domain(domain: str) -> str:
    return (domain or "").strip().lower()


def _domain_from_url(url: str) -> str:
    try:
        host = urlparse(url).hostname
        return _normalize_domain(host or "")
    except Exception:
        return ""


def _hosts_related(host_a: str, host_b: str) -> bool:
    a = (host_a or "").lower().strip(".")
    b = (host_b or "").lower().strip(".")
    if not a or not b:
        return True
    return a == b or a.endswith("." + b) or b.endswith("." + a)


def _relative_path_from_page_url(page_url: str, site_url: str, *, label: str) -> str:
    try:
        p = urlparse(page_url)
        site_host = urlparse(site_url).hostname or ""
        page_host = p.hostname or ""
        if site_host and page_host and not _hosts_related(site_host, page_host):
            raise ValueError(f"{label} host mismatch: {page_host} (site={site_host})")
        rel = (p.path or "").strip()
        if rel in {"", "/"}:
            raise ValueError(f"{label} path missing")
        rel = rel.lstrip("/")
        if p.query:
            rel = f"{rel}?{p.query}"
        return rel
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


async def _load_app_config(ctx: AppContext) -> Dict[str, Any]:
    cfg = await ctx.store.get_json("app_config", default={}) or {}
    return _safe_dict(cfg)


async def _load_sites_config(ctx: AppContext) -> Dict[str, Any]:
    cfg = await ctx.store.get_json("sites", default={"version": 1, "entries": {}}) or {"version": 1, "entries": {}}
    cfg = _safe_dict(cfg)
    entries = _safe_dict(cfg.get("entries"))
    return {"version": int(cfg.get("version") or 1), "entries": entries}


def _site_entry_view(entry: Dict[str, Any], base_url: str) -> Dict[str, Any]:
    template = (_cfg_str(entry.get("template")) or "nexusphp").lower()
    reg_path = _cfg_str(entry.get("registration_path"))
    inv_path = _cfg_str(entry.get("invite_path"))
    return {
        "mode": _cfg_str(entry.get("mode")) or "manual",
        "template": template if template in {"nexusphp", "custom", "mteam"} else "nexusphp",
        "cookie_configured": bool(_cfg_str(entry.get("cookie"))),
        "authorization_configured": bool(_cfg_str(entry.get("authorization"))),
        "did_configured": bool(_cfg_str(entry.get("did"))),
        "registration_url": urljoin(base_url.rstrip("/") + "/", reg_path) if reg_path else "",
        "invite_url": urljoin(base_url.rstrip("/") + "/", inv_path) if inv_path else "",
    }


async def get_ctx() -> AppContext:
    ctx: Optional[AppContext] = getattr(app.state, "ctx", None)
    if ctx is None:
        raise HTTPException(status_code=503, detail="App not ready")
    return ctx


def _maybe_require_auth(
    request: Request,
    credentials: Optional[HTTPBasicCredentials],
    settings: Settings,
) -> None:
    if not settings.web.basic_auth.enabled:
        return
    if not credentials or not credentials.username or not credentials.password:
        raise HTTPException(status_code=401, headers={"WWW-Authenticate": "Basic"})
    if credentials.username != settings.web.basic_auth.username or credentials.password != settings.web.basic_auth.password:
        raise HTTPException(status_code=401, detail="Unauthorized", headers={"WWW-Authenticate": "Basic"})


async def require_auth(
    request: Request,
    credentials: Annotated[Optional[HTTPBasicCredentials], Depends(basic_security)],
    ctx: Annotated[AppContext, Depends(get_ctx)],
) -> None:
    _maybe_require_auth(request, credentials, ctx.settings)


@app.on_event("startup")
async def _startup() -> None:
    settings = load_settings()
    logging.basicConfig(level=getattr(logging, settings.log_level, logging.INFO))
    app.state.ctx = await build_context(settings)

    async def _loop() -> None:
        try:
            probe_status = await app.state.ctx.scanner.probe_dependencies()
            logger.info("deps probe: %s", probe_status)
        except Exception:
            logger.exception("deps probe failed")

        while True:
            try:
                status = await app.state.ctx.scanner.run_once()
                logger.info("scan status: %s", status)
            except Exception:
                logger.exception("scan cycle failed")

            interval = app.state.ctx.settings.scan.interval_seconds
            try:
                cfg = await app.state.ctx.store.get_json("app_config", default={}) or {}
                scan_cfg = cfg.get("scan") if isinstance(cfg, dict) else None
                if isinstance(scan_cfg, dict) and scan_cfg.get("interval_seconds") is not None:
                    interval = int(scan_cfg.get("interval_seconds") or interval)
            except Exception:
                pass
            await asyncio.sleep(max(30, int(interval or 600)))

    app.state.scan_task = asyncio.create_task(_loop())


@app.on_event("shutdown")
async def _shutdown() -> None:
    task: Optional[asyncio.Task] = getattr(app.state, "scan_task", None)
    if task:
        task.cancel()
    ctx: Optional[AppContext] = getattr(app.state, "ctx", None)
    if ctx:
        await ctx.store.close()


@app.get("/health")
async def health() -> Dict[str, Any]:
    return {"ok": True}


@app.get("/api/dashboard", dependencies=[Depends(require_auth)])
async def api_dashboard(ctx: Annotated[AppContext, Depends(get_ctx)]) -> Dict[str, Any]:
    now = datetime.now(timezone.utc)

    cfg = await _load_app_config(ctx)
    mp_cfg = _safe_dict(cfg.get("moviepilot"))
    ui_cfg = _safe_dict(cfg.get("ui"))
    mp_base_url = _cfg_str(mp_cfg.get("base_url")) or ctx.settings.moviepilot.base_url
    mp_sites_cache_ttl = _cfg_int(
        mp_cfg.get("sites_cache_ttl_seconds"),
        MP_SITES_CACHE_DEFAULT_TTL_SECONDS,
        MP_SITES_CACHE_MIN_TTL_SECONDS,
        MP_SITES_CACHE_MAX_TTL_SECONDS,
    )

    mp_sites = []
    try:
        cache = parse_cache(await ctx.store.get_json(MP_SITES_CACHE_KEY, default=None))
        if cache and not cache_expired(cache, now, mp_sites_cache_ttl, base_url=mp_base_url):
            mp_sites = cache.sites
    except Exception:
        mp_sites = []
    if not mp_sites:
        try:
            snap_at, snap_sites = await ctx.store.load_sites_snapshot()
            if snap_sites and snap_at and int((now - snap_at).total_seconds()) <= mp_sites_cache_ttl:
                mp_sites = snap_sites
        except Exception:
            mp_sites = []

    sites_cfg = await _load_sites_config(ctx)
    sites = ctx.scanner._merge_sites(mp_sites, _safe_dict(sites_cfg.get("entries")))
    current_domains = [_normalize_domain(s.domain) for s in sites if _normalize_domain(s.domain)]

    states = await ctx.store.list_site_states()
    state_map = {_normalize_domain(r.get("domain") or ""): r for r in states if _normalize_domain(r.get("domain") or "")}

    extras_map: Dict[str, Dict[str, Any]] = {}
    try:
        extras_map = await ctx.store.get_sites_extras(current_domains)
    except Exception:
        extras_map = {}

    def _infer_engine(domain: str, template: str) -> str:
        t = (template or "").strip().lower()
        if not t:
            if domain.endswith("m-team.cc"):
                return "mteam"
            return "nexusphp"
        return t

    def _default_paths_for_template(template: str) -> tuple[str, str]:
        t = (template or "").strip().lower()
        if t == "mteam":
            return "signup", "invite"
        return "signup.php", "invite.php"

    rows: list[dict[str, Any]] = []
    for site in sites:
        domain = _normalize_domain(site.domain)
        if not domain:
            continue
        row = dict(state_map.get(domain) or {})

        template = _cfg_str(getattr(site, "template", None)).lower()
        engine = _cfg_str(row.get("engine")) or _infer_engine(domain, template)
        row["domain"] = domain
        row["name"] = _cfg_str(getattr(site, "name", None)) or row.get("name") or domain
        row["url"] = _cfg_str(getattr(site, "url", None)) or row.get("url") or ""
        row["engine"] = engine

        if "reachability_state" not in row:
            row["reachability_state"] = "unknown"
        if "reachability_note" not in row:
            row["reachability_note"] = ""
        if "registration_state" not in row:
            row["registration_state"] = "unknown"
        if "registration_note" not in row:
            row["registration_note"] = ""
        if "invites_state" not in row:
            row["invites_state"] = "unknown"
        if "invites_available" not in row:
            row["invites_available"] = None
        if "invites_display" not in row:
            row["invites_display"] = ""
        if "last_checked_at" not in row:
            row["last_checked_at"] = ""
        if "last_changed_at" not in row:
            row["last_changed_at"] = None
        if "errors" not in row:
            row["errors"] = []

        base_url = row["url"]
        reg_default, inv_default = _default_paths_for_template(template)
        reg_path = _cfg_str(getattr(site, "registration_path", None)) or (reg_default if template in {"", "nexusphp", "mteam"} else "")
        inv_path = _cfg_str(getattr(site, "invite_path", None)) or (inv_default if template in {"", "nexusphp", "mteam"} else "")

        invite_uid = _cfg_str((extras_map.get(domain) or {}).get("invite_uid")) if template in {"", "nexusphp"} else ""
        if invite_uid:
            inv_path = f"invite.php?id={invite_uid}"

        row["registration_url"] = urljoin(base_url.rstrip("/") + "/", reg_path) if base_url and reg_path else ""
        row["invite_url"] = urljoin(base_url.rstrip("/") + "/", inv_path) if base_url and inv_path else ""

        rows.append(row)

    inflight = set()
    try:
        inflight = set(getattr(ctx.scanner, "in_flight_domains")() or [])
    except Exception:
        inflight = set()
    if inflight:
        for r in rows:
            r["scanning"] = _normalize_domain(r.get("domain") or "") in inflight
    else:
        for r in rows:
            r["scanning"] = False
    scan_status = await ctx.store.get_json("scan_status", default=None)
    scan_hint = await ctx.store.get_json(_SCAN_HINT_KEY, default=None)
    ui = {"allow_state_reset": _cfg_bool(ui_cfg.get("allow_state_reset"), default=True)}
    return {"rows": rows, "scan_status": scan_status, "scan_hint": scan_hint, "ui": ui}


@app.post("/api/scan/run", dependencies=[Depends(require_auth)])
async def api_scan_run(ctx: Annotated[AppContext, Depends(get_ctx)]) -> Dict[str, Any]:
    status = await ctx.scanner.run_once()
    await sse_broadcaster.broadcast("dashboard_update")
    await sse_broadcaster.broadcast("logs_update")
    return status


@app.post("/api/scan/run/{domain}", dependencies=[Depends(require_auth)])
async def api_scan_run_one(domain: str, ctx: Annotated[AppContext, Depends(get_ctx)]) -> Dict[str, Any]:
    try:
        status = await ctx.scanner.run_one(domain)
        await sse_broadcaster.broadcast("dashboard_update")
        await sse_broadcaster.broadcast("logs_update")
        return status
    except AlreadyScanningError as e:
        raise HTTPException(status_code=409, detail=str(e))


@app.post("/api/state/reset", dependencies=[Depends(require_auth)])
async def api_state_reset(ctx: Annotated[AppContext, Depends(get_ctx)]) -> Dict[str, Any]:
    cfg = await _load_app_config(ctx)
    ui_cfg = _safe_dict(cfg.get("ui"))
    allowed = _cfg_bool(ui_cfg.get("allow_state_reset"), default=True)
    if not allowed:
        raise HTTPException(status_code=403, detail="state reset disabled")

    await ctx.store.reset_site_states()
    await ctx.store.set_json("scan_status", None)
    await ctx.store.set_json(_SCAN_HINT_KEY, None)
    try:
        await ctx.store.add_event(category="config", level="info", action="state_reset", message="site state reset")
    except Exception:
        pass
    await sse_broadcaster.broadcast("dashboard_update")
    await sse_broadcaster.broadcast("logs_update")
    return {"ok": True}


@app.get("/api/logs", dependencies=[Depends(require_auth)])
async def api_logs(
    ctx: Annotated[AppContext, Depends(get_ctx)],
    category: str = "all",
    keyword: str = "",
    limit: int = 200,
) -> Dict[str, Any]:
    items = await ctx.store.list_events(category=category, keyword=keyword, limit=limit)
    return {"items": items}


@app.post("/api/logs/clear", dependencies=[Depends(require_auth)])
async def api_logs_clear(ctx: Annotated[AppContext, Depends(get_ctx)]) -> Dict[str, Any]:
    await ctx.store.clear_events()
    await sse_broadcaster.broadcast("logs_update")
    return {"ok": True}


@app.get("/api/events")
async def api_sse_events():
    """SSE endpoint for real-time updates"""
    async def event_generator():
        queue = await sse_broadcaster.subscribe()
        try:
            # Send initial ping
            yield f"data: {json.dumps({'type': 'connected'})}\n\n"
            while True:
                try:
                    msg = await asyncio.wait_for(queue.get(), timeout=30.0)
                    yield f"data: {json.dumps(msg)}\n\n"
                except asyncio.TimeoutError:
                    # Send keepalive ping
                    yield f"data: {json.dumps({'type': 'ping'})}\n\n"
        except asyncio.CancelledError:
            pass
        finally:
            sse_broadcaster.unsubscribe(queue)
    
    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        }
    )


@app.get("/api/config", dependencies=[Depends(require_auth)])
async def api_config_get(ctx: Annotated[AppContext, Depends(get_ctx)]) -> Dict[str, Any]:
    cfg = await ctx.store.get_json("app_config", default={})
    cfg = _safe_dict(cfg)
    mp_cfg = _safe_dict(cfg.get("moviepilot"))
    connectivity_cfg = _safe_dict(cfg.get("connectivity"))
    cookie_cfg = _safe_dict(cfg.get("cookie"))
    cc_cfg = _safe_dict(cookie_cfg.get("cookiecloud"))
    scan_cfg = _safe_dict(cfg.get("scan"))
    ui_cfg = _safe_dict(cfg.get("ui"))

    moviepilot = {
        "base_url": _cfg_str(mp_cfg.get("base_url")) or ctx.settings.moviepilot.base_url,
        "username": _cfg_str(mp_cfg.get("username")) or ctx.settings.moviepilot.username,
        "password_configured": bool(_cfg_str(mp_cfg.get("password")) or ctx.settings.moviepilot.password),
        "otp_configured": bool(_cfg_str(mp_cfg.get("otp_password")) or (ctx.settings.moviepilot.otp_password or "")),
        "sites_cache_ttl_seconds": _cfg_int(
            mp_cfg.get("sites_cache_ttl_seconds"),
            MP_SITES_CACHE_DEFAULT_TTL_SECONDS,
            MP_SITES_CACHE_MIN_TTL_SECONDS,
            MP_SITES_CACHE_MAX_TTL_SECONDS,
        ),
    }
    cookie = {
        "source": (_cfg_str(cookie_cfg.get("source")) if isinstance(cookie_cfg, dict) else "") or ctx.settings.cookie.source,
        "cookiecloud": {
            "base_url": _cfg_str(cc_cfg.get("base_url")) or ctx.settings.cookie.cookiecloud.base_url,
            "uuid": _cfg_str(cc_cfg.get("uuid")) or ctx.settings.cookie.cookiecloud.uuid,
            "password_configured": bool(_cfg_str(cc_cfg.get("password")) or ctx.settings.cookie.cookiecloud.password),
            "refresh_interval_seconds": _cfg_int(
                cc_cfg.get("refresh_interval_seconds"),
                ctx.settings.cookie.cookiecloud.refresh_interval_seconds,
                30,
                24 * 3600,
            ),
        },
    }
    scan = {
        "interval_seconds": _cfg_int(
            scan_cfg.get("interval_seconds"),
            ctx.settings.scan.interval_seconds,
            30,
            24 * 3600,
        ),
        "timeout_seconds": _cfg_int(
            scan_cfg.get("timeout_seconds"),
            ctx.settings.scan.timeout_seconds,
            5,
            180,
        ),
        "concurrency": _cfg_int(
            scan_cfg.get("concurrency"),
            ctx.settings.scan.concurrency,
            1,
            64,
        ),
        "user_agent": _cfg_str(scan_cfg.get("user_agent")) or ctx.settings.scan.user_agent,
        "trust_env": _cfg_bool(scan_cfg.get("trust_env"), default=ctx.settings.scan.trust_env),
    }

    connectivity = {
        "retry_interval_seconds": _cfg_int(
            connectivity_cfg.get("retry_interval_seconds"),
            DEFAULT_RETRY_INTERVAL_SECONDS,
            MIN_RETRY_INTERVAL_SECONDS,
            MAX_RETRY_INTERVAL_SECONDS,
        ),
        "request_retry_delay_seconds": _cfg_int(
            connectivity_cfg.get("request_retry_delay_seconds"),
            _DEFAULT_REQUEST_RETRY_DELAY_SECONDS,
            5,
            24 * 3600,
        ),
    }

    ui = {"allow_state_reset": _cfg_bool(ui_cfg.get("allow_state_reset"), default=True)}

    return {"moviepilot": moviepilot, "connectivity": connectivity, "cookie": cookie, "scan": scan, "ui": ui}


@app.put("/api/config", dependencies=[Depends(require_auth)])
async def api_config_put(
    ctx: Annotated[AppContext, Depends(get_ctx)],
    payload: Dict[str, Any] = Body(default={}),
) -> Dict[str, Any]:
    cfg = await ctx.store.get_json("app_config", default={}) or {}
    cfg = _safe_dict(cfg)

    payload = _safe_dict(payload)

    mp_in = _safe_dict(payload.get("moviepilot"))
    connectivity_in = _safe_dict(payload.get("connectivity"))
    cookie_in = _safe_dict(payload.get("cookie"))
    cc_in = _safe_dict(cookie_in.get("cookiecloud"))
    scan_in = _safe_dict(payload.get("scan"))
    ui_in = _safe_dict(payload.get("ui"))

    mp = _safe_dict(cfg.get("moviepilot"))
    mp_base = _cfg_str(mp_in.get("base_url"))
    mp_user = _cfg_str(mp_in.get("username"))
    mp_pass = _cfg_str(mp_in.get("password"))
    mp_otp = _cfg_str(mp_in.get("otp_password"))
    if mp_base:
        mp["base_url"] = mp_base
    if mp_user:
        mp["username"] = mp_user
    if mp_pass:
        mp["password"] = mp_pass
    if mp_otp:
        mp["otp_password"] = mp_otp
    ttl_default = int(mp.get("sites_cache_ttl_seconds") or MP_SITES_CACHE_DEFAULT_TTL_SECONDS)
    mp["sites_cache_ttl_seconds"] = _cfg_int(
        mp_in.get("sites_cache_ttl_seconds"),
        ttl_default,
        MP_SITES_CACHE_MIN_TTL_SECONDS,
        MP_SITES_CACHE_MAX_TTL_SECONDS,
    )
    cfg["moviepilot"] = mp

    connectivity = _safe_dict(cfg.get("connectivity"))
    retry_default = int(connectivity.get("retry_interval_seconds") or DEFAULT_RETRY_INTERVAL_SECONDS)
    connectivity["retry_interval_seconds"] = _cfg_int(
        connectivity_in.get("retry_interval_seconds"),
        retry_default,
        MIN_RETRY_INTERVAL_SECONDS,
        MAX_RETRY_INTERVAL_SECONDS,
    )
    request_retry_delay_default = int(connectivity.get("request_retry_delay_seconds") or _DEFAULT_REQUEST_RETRY_DELAY_SECONDS)
    connectivity["request_retry_delay_seconds"] = _cfg_int(
        connectivity_in.get("request_retry_delay_seconds"),
        request_retry_delay_default,
        5,
        24 * 3600,
    )
    cfg["connectivity"] = connectivity

    cookie = _safe_dict(cfg.get("cookie"))
    src = _cfg_str(cookie_in.get("source")).lower()
    if src in {"auto", "cookiecloud", "moviepilot"}:
        cookie["source"] = src

    cc = _safe_dict(cookie.get("cookiecloud"))
    cc_base = _cfg_str(cc_in.get("base_url"))
    cc_uuid = _cfg_str(cc_in.get("uuid"))
    cc_pass = _cfg_str(cc_in.get("password"))
    if cc_base:
        cc["base_url"] = cc_base
    if cc_uuid:
        cc["uuid"] = cc_uuid
    if cc_pass:
        cc["password"] = cc_pass
    cc_refresh_default = int(cc.get("refresh_interval_seconds") or ctx.settings.cookie.cookiecloud.refresh_interval_seconds)
    cc["refresh_interval_seconds"] = _cfg_int(cc_in.get("refresh_interval_seconds"), cc_refresh_default, 30, 24 * 3600)
    cookie["cookiecloud"] = cc
    cfg["cookie"] = cookie

    scan = _safe_dict(cfg.get("scan"))
    scan_interval_default = int(scan.get("interval_seconds") or ctx.settings.scan.interval_seconds)
    scan_timeout_default = int(scan.get("timeout_seconds") or ctx.settings.scan.timeout_seconds)
    scan_concurrency_default = int(scan.get("concurrency") or ctx.settings.scan.concurrency)
    scan["interval_seconds"] = _cfg_int(scan_in.get("interval_seconds"), scan_interval_default, 30, 24 * 3600)
    scan["timeout_seconds"] = _cfg_int(scan_in.get("timeout_seconds"), scan_timeout_default, 5, 180)
    scan["concurrency"] = _cfg_int(scan_in.get("concurrency"), scan_concurrency_default, 1, 64)

    if "user_agent" in scan_in:
        ua_in = scan_in.get("user_agent")
        ua = ("" if ua_in is None else str(ua_in)).strip()
        if ua != "":
            scan["user_agent"] = ua
        elif "user_agent" in scan:
            scan.pop("user_agent", None)

    if "trust_env" in scan_in:
        scan["trust_env"] = _cfg_bool(scan_in.get("trust_env"), default=ctx.settings.scan.trust_env)

    cfg["scan"] = scan

    ui = _safe_dict(cfg.get("ui"))
    if "allow_state_reset" in ui_in:
        ui["allow_state_reset"] = _cfg_bool(ui_in.get("allow_state_reset"), default=True)
    cfg["ui"] = ui

    await ctx.store.set_json("app_config", cfg)
    try:
        await ctx.store.add_event(
            category="config",
            level="info",
            action="config_update",
            message="app config updated",
            detail={"keys": list(payload.keys())},
        )
    except Exception:
        pass
    return {"ok": True}


@app.post("/api/config/reset", dependencies=[Depends(require_auth)])
async def api_config_reset(ctx: Annotated[AppContext, Depends(get_ctx)]) -> Dict[str, Any]:
    await ctx.store.set_json("app_config", {})
    try:
        await ctx.store.add_event(category="config", level="info", action="config_reset", message="app config reset")
    except Exception:
        pass
    return {"ok": True}

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
    cfg = _safe_dict(data.get("app_config"))
    notif = _safe_dict(data.get("notifications"))
    sites = _safe_dict(data.get("sites"))

    cfg = _deep_merge({}, cfg)
    mp = _safe_dict(cfg.get("moviepilot"))
    mp.pop("password", None)
    mp.pop("otp_password", None)
    if mp:
        cfg["moviepilot"] = mp
    cookie = _safe_dict(cfg.get("cookie"))
    cc = _safe_dict(_safe_dict(cookie.get("cookiecloud")))
    cc.pop("password", None)
    if cc:
        cookie["cookiecloud"] = cc
    if cookie:
        cfg["cookie"] = cookie

    notif = _deep_merge({}, notif)
    telegram = _safe_dict(notif.get("telegram"))
    telegram.pop("token", None)
    if telegram:
        notif["telegram"] = telegram
    wecom = _safe_dict(notif.get("wecom"))
    wecom.pop("app_secret", None)
    if wecom:
        notif["wecom"] = wecom

    sites = _deep_merge({}, sites)
    entries = _safe_dict(sites.get("entries"))
    redacted_entries: Dict[str, Any] = {}
    for domain, entry_any in entries.items():
        entry = _safe_dict(entry_any)
        entry.pop("cookie", None)
        entry.pop("authorization", None)
        entry.pop("did", None)
        redacted_entries[str(domain)] = entry
    sites["entries"] = redacted_entries

    return {"app_config": cfg, "notifications": notif, "sites": sites}


@app.get("/api/backup/export", dependencies=[Depends(require_auth)])
async def api_backup_export(
    ctx: Annotated[AppContext, Depends(get_ctx)],
    include_secrets: int = 1,
) -> Dict[str, Any]:
    include = bool(int(include_secrets or 0))
    app_cfg = await ctx.store.get_json("app_config", default={}) or {}
    notif_cfg = await ctx.store.get_json("notifications", default={}) or {}
    sites_cfg = await ctx.store.get_json("sites", default={"version": 1, "entries": {}}) or {"version": 1, "entries": {}}

    data = {"app_config": _safe_dict(app_cfg), "notifications": _safe_dict(notif_cfg), "sites": _safe_dict(sites_cfg)}
    if not include:
        data = _redact_backup(data)

    try:
        await ctx.store.add_event(
            category="backup",
            level="info",
            action="backup_export",
            message="backup exported",
            detail={"include_secrets": include},
        )
    except Exception:
        pass

    return {
        "version": _BACKUP_VERSION,
        "exported_at": datetime.now(timezone.utc).isoformat(),
        "include_secrets": include,
        "data": data,
    }


@app.post("/api/backup/import", dependencies=[Depends(require_auth)])
async def api_backup_import(
    ctx: Annotated[AppContext, Depends(get_ctx)],
    payload: Dict[str, Any] = Body(default={}),
    mode: str = "merge",
) -> Dict[str, Any]:
    mode = (mode or "").strip().lower()
    if mode not in {"merge", "replace"}:
        raise HTTPException(status_code=400, detail="mode must be merge|replace")

    root = _safe_dict(payload)
    data = _safe_dict(root.get("data")) or root

    changed: list[str] = []

    if "app_config" in data:
        incoming = _safe_dict(data.get("app_config"))
        if mode == "replace":
            await ctx.store.set_json("app_config", incoming)
        else:
            current = await ctx.store.get_json("app_config", default={}) or {}
            await ctx.store.set_json("app_config", _deep_merge(_safe_dict(current), incoming))
        changed.append("app_config")

    if "notifications" in data:
        incoming = _safe_dict(data.get("notifications"))
        if mode == "replace":
            await ctx.store.set_json("notifications", incoming)
        else:
            current = await ctx.store.get_json("notifications", default={}) or {}
            await ctx.store.set_json("notifications", _deep_merge(_safe_dict(current), incoming))
        changed.append("notifications")

    if "sites" in data:
        incoming_sites = _safe_dict(data.get("sites"))
        incoming_entries = _safe_dict(incoming_sites.get("entries"))
        incoming = {"version": int(incoming_sites.get("version") or 1), "entries": incoming_entries}
        if mode == "replace":
            await ctx.store.set_json("sites", incoming)
        else:
            current = await ctx.store.get_json("sites", default={"version": 1, "entries": {}}) or {"version": 1, "entries": {}}
            current_entries = _safe_dict(_safe_dict(current).get("entries"))
            merged_entries = _deep_merge(current_entries, incoming_entries)
            await ctx.store.set_json("sites", {"version": 1, "entries": merged_entries})
        changed.append("sites")

    if not changed:
        raise HTTPException(status_code=400, detail="no supported keys found in payload")

    # After importing site/app configuration, old scan status may no longer be valid.
    # Also, importing sites does NOT import scan results; user should run a scan to populate the dashboard.
    needs_scan_hint = any(k in changed for k in ("app_config", "sites"))
    if needs_scan_hint:
        await ctx.store.set_json(
            _SCAN_HINT_KEY,
            {"reason": "import", "at": datetime.now(timezone.utc).isoformat(), "changed": list(changed)},
        )
        await ctx.store.set_json("scan_status", None)

    try:
        await ctx.store.add_event(
            category="backup",
            level="info",
            action="backup_import",
            message="backup imported",
            detail={"mode": mode, "changed": list(changed), "needs_scan": needs_scan_hint},
        )
    except Exception:
        pass

    return {"ok": True, "message": f"imported: {', '.join(changed)}", "changed": list(changed), "needs_scan": needs_scan_hint}


@app.get("/api/notifications", dependencies=[Depends(require_auth)])
async def api_notifications_get(ctx: Annotated[AppContext, Depends(get_ctx)]) -> Dict[str, Any]:
    cfg = await ctx.store.get_json("notifications", default={}) or {}
    cfg = _safe_dict(cfg)
    telegram = _safe_dict(cfg.get("telegram"))
    wecom = _safe_dict(cfg.get("wecom"))

    telegram_view = {
        "enabled": bool(telegram.get("enabled")),
        "configured": bool(telegram.get("token") and telegram.get("chat_id")),
        "chat_id": _cfg_str(telegram.get("chat_id")),
    }
    wecom_view = {
        "enabled": bool(wecom.get("enabled")),
        "configured": bool(wecom.get("corpid") and wecom.get("app_secret") and wecom.get("agent_id")),
        "corpid": _cfg_str(wecom.get("corpid")),
        "agent_id": _cfg_str(wecom.get("agent_id")),
        "to_user": _cfg_str(wecom.get("to_user")) or "@all",
        "to_party": _cfg_str(wecom.get("to_party")),
        "to_tag": _cfg_str(wecom.get("to_tag")),
    }

    return {"telegram": telegram_view, "wecom": wecom_view}


@app.put("/api/notifications", dependencies=[Depends(require_auth)])
async def api_notifications_put(
    ctx: Annotated[AppContext, Depends(get_ctx)],
    payload: Dict[str, Any] = Body(default={}),
) -> Dict[str, Any]:
    cfg = await ctx.store.get_json("notifications", default={}) or {}
    cfg = _safe_dict(cfg)

    payload = _safe_dict(payload)
    tg_in = _safe_dict(payload.get("telegram"))
    wc_in = _safe_dict(payload.get("wecom"))

    telegram = _safe_dict(cfg.get("telegram"))
    wecom = _safe_dict(cfg.get("wecom"))

    if "enabled" in tg_in:
        telegram["enabled"] = bool(tg_in.get("enabled"))
    token = _cfg_str(tg_in.get("token"))
    if token:
        telegram["token"] = token
    chat_id = _cfg_str(tg_in.get("chat_id"))
    if chat_id:
        telegram["chat_id"] = chat_id

    if "enabled" in wc_in:
        wecom["enabled"] = bool(wc_in.get("enabled"))
    corpid = _cfg_str(wc_in.get("corpid"))
    if corpid:
        wecom["corpid"] = corpid
    app_secret = _cfg_str(wc_in.get("app_secret"))
    if app_secret:
        wecom["app_secret"] = app_secret
    agent_id = _cfg_str(wc_in.get("agent_id"))
    if agent_id:
        wecom["agent_id"] = agent_id

    if "to_user" in wc_in:
        wecom["to_user"] = (_cfg_str(wc_in.get("to_user")) or "@all").strip()
    if "to_party" in wc_in:
        wecom["to_party"] = _cfg_str(wc_in.get("to_party"))
    if "to_tag" in wc_in:
        wecom["to_tag"] = _cfg_str(wc_in.get("to_tag"))

    await ctx.store.set_json("notifications", {"telegram": telegram, "wecom": wecom})
    try:
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
    except Exception:
        pass
    return {"ok": True}


@app.post("/api/notifications/test/{channel}", dependencies=[Depends(require_auth)])
async def api_notifications_test(channel: str, ctx: Annotated[AppContext, Depends(get_ctx)]) -> Dict[str, Any]:
    if channel not in {"telegram", "wecom"}:
        raise HTTPException(status_code=404, detail="unknown channel")
    ok, msg = await ctx.notifier.test(channel)
    try:
        await ctx.store.add_event(
            category="notify",
            level="info" if ok else "error",
            action="notifications_test",
            message=f"{channel} test: {'ok' if ok else 'fail'}",
            detail={"channel": channel, "ok": ok, "message": msg},
        )
    except Exception:
        pass
    return {"ok": bool(ok), "message": str(msg or "")}


@app.get("/api/sites", dependencies=[Depends(require_auth)])
async def api_sites_get(ctx: Annotated[AppContext, Depends(get_ctx)]) -> Dict[str, Any]:
    app_cfg = await _load_app_config(ctx)
    mp_cfg = _safe_dict(app_cfg.get("moviepilot"))
    connectivity_cfg = _safe_dict(app_cfg.get("connectivity"))
    scan_cfg = _safe_dict(app_cfg.get("scan"))

    mp_base_url = _cfg_str(mp_cfg.get("base_url")) or ctx.settings.moviepilot.base_url
    mp_username = _cfg_str(mp_cfg.get("username")) or ctx.settings.moviepilot.username
    mp_password = _cfg_str(mp_cfg.get("password")) or ctx.settings.moviepilot.password
    mp_otp_password = _cfg_str(mp_cfg.get("otp_password")) or (ctx.settings.moviepilot.otp_password or "")
    mp_sites_cache_ttl = _cfg_int(
        mp_cfg.get("sites_cache_ttl_seconds"),
        MP_SITES_CACHE_DEFAULT_TTL_SECONDS,
        MP_SITES_CACHE_MIN_TTL_SECONDS,
        MP_SITES_CACHE_MAX_TTL_SECONDS,
    )
    deps_retry_interval = _cfg_int(
        connectivity_cfg.get("retry_interval_seconds"),
        DEFAULT_RETRY_INTERVAL_SECONDS,
        MIN_RETRY_INTERVAL_SECONDS,
        MAX_RETRY_INTERVAL_SECONDS,
    )
    request_retry_delay_seconds = _cfg_int(
        connectivity_cfg.get("request_retry_delay_seconds"),
        _DEFAULT_REQUEST_RETRY_DELAY_SECONDS,
        5,
        24 * 3600,
    )
    scan_timeout = _cfg_int(
        scan_cfg.get("timeout_seconds"),
        ctx.settings.scan.timeout_seconds,
        5,
        180,
    )

    mp_sites = []
    mp_error = ""
    mp_ok = False
    mp_source = "none"  # live|cache|none
    mp_cache_fetched_at = ""
    mp_cache_age_seconds: Optional[int] = None
    mp_cache_expired: Optional[bool] = None
    now = datetime.now(timezone.utc)
    deps_status = load_deps_status(await ctx.store.get_json(DEPS_STATUS_KEY, default=None))

    mp_attempted = bool(mp_base_url and mp_username and mp_password)
    if mp_attempted:
        mp_fp = fingerprint_moviepilot(mp_base_url)
        mp_dep = get_dep_status(deps_status, "moviepilot")
        mp_allowed = can_attempt(mp_dep, now, mp_fp)
        if not mp_allowed:
            mp_error = mp_dep.error
        else:
            try:
                mp_client = MoviePilotClient(
                    base_url=mp_base_url,
                    username=mp_username,
                    password=mp_password,
                    otp_password=mp_otp_password or None,
                    timeout_seconds=scan_timeout,
                    retry_delay_seconds=request_retry_delay_seconds,
                )
                mp_sites = await mp_client.list_sites(only_active=True)
                mp_ok = True
                mp_source = "live"
                mp_cache_fetched_at = now.isoformat()
                mp_cache_age_seconds = 0
                mp_cache_expired = False
                try:
                    await ctx.store.set_json(MP_SITES_CACHE_KEY, build_cache(mp_base_url, mp_sites, fetched_at=now))
                except Exception:
                    logger.exception("failed to persist MoviePilot sites cache")

                deps_status = update_dep_ok(deps_status, "moviepilot", now, mp_fp)
                try:
                    await ctx.store.set_json(DEPS_STATUS_KEY, deps_status)
                except Exception:
                    logger.exception("failed to persist deps status")
            except Exception as e:
                mp_error = _format_error_detail(e)
                deps_status = update_dep_fail(
                    deps_status,
                    "moviepilot",
                    now,
                    mp_fp,
                    mp_error,
                    retry_interval_seconds=deps_retry_interval,
                )
                try:
                    await ctx.store.set_json(DEPS_STATUS_KEY, deps_status)
                except Exception:
                    logger.exception("failed to persist deps status")

        if mp_sites:
            pass
        else:
            try:
                cache = parse_cache(await ctx.store.get_json(MP_SITES_CACHE_KEY, default=None))
                if cache:
                    mp_cache_fetched_at = cache.fetched_at_iso
                    mp_cache_age_seconds = cache.age_seconds(now)
                    mp_cache_expired = cache_expired(cache, now, mp_sites_cache_ttl, base_url=mp_base_url)
                    if not mp_cache_expired:
                        mp_sites = cache.sites
                        mp_source = "cache"
            except Exception:
                logger.exception("failed to load MoviePilot sites cache")
            if not mp_sites:
                try:
                    snap_at, snap_sites = await ctx.store.load_sites_snapshot()
                    if snap_sites and snap_at:
                        age = int(max(0, (now - snap_at).total_seconds()))
                        mp_cache_fetched_at = snap_at.isoformat()
                        mp_cache_age_seconds = age
                        if age <= mp_sites_cache_ttl:
                            mp_cache_expired = False
                            mp_sites = snap_sites
                            mp_source = "state"
                            try:
                                await ctx.store.set_json(MP_SITES_CACHE_KEY, build_cache(mp_base_url, mp_sites, fetched_at=snap_at))
                            except Exception:
                                logger.exception("failed to persist MoviePilot sites cache (seeded)")
                        else:
                            mp_cache_expired = True
                except Exception:
                    logger.exception("failed to load sites snapshot from local state")

    sites_cfg = await _load_sites_config(ctx)
    entries = _safe_dict(sites_cfg.get("entries"))

    items: list[Dict[str, Any]] = []
    mp_domains = set()
    for s in mp_sites:
        domain = _normalize_domain(s.domain)
        mp_domains.add(domain)
        entry = _safe_dict(entries.get(domain))
        if entry and (_cfg_str(entry.get("mode")) or "").lower() not in {"override", "manual"}:
            entry = {}

        effective_name = _cfg_str(entry.get("name")) or s.name
        raw_template = (_cfg_str(entry.get("template")) or "").lower()
        if raw_template in {"nexusphp", "custom", "mteam"}:
            template = raw_template
        elif domain.endswith("m-team.cc"):
            template = "mteam"
        else:
            template = "nexusphp"

        view = _site_entry_view(entry, s.url)
        if template == "mteam":
            reg_default = "signup"
            inv_default = "invite"
        else:
            reg_default = "signup.php"
            inv_default = "invite.php"
        items.append(
            {
                "domain": domain,
                "name": effective_name,
                "url": s.url,
                "source": "moviepilot",
                "template": template,
                "has_local_config": bool(entry),
                "cookie_configured": bool(view.get("cookie_configured")),
                "authorization_configured": bool(view.get("authorization_configured")),
                "did_configured": bool(view.get("did_configured")),
                "registration_url": view.get("registration_url") or urljoin(s.url.rstrip("/") + "/", reg_default),
                "invite_url": view.get("invite_url") or urljoin(s.url.rstrip("/") + "/", inv_default),
            }
        )

    # Manual sites
    for domain, raw in entries.items():
        dom = _normalize_domain(domain)
        entry = _safe_dict(raw)
        mode = (_cfg_str(entry.get("mode")) or "manual").lower()
        if mode != "manual":
            continue
        if dom in mp_domains:
            # If it collides with MP domain, treat it as an override record.
            continue

        url = _cfg_str(entry.get("url"))
        if not url:
            continue
        name = _cfg_str(entry.get("name")) or dom
        template = (_cfg_str(entry.get("template")) or "custom").lower()
        if template not in {"nexusphp", "custom", "mteam"}:
            template = "mteam" if dom.endswith("m-team.cc") else "custom"
        view = _site_entry_view(entry, url)
        if template == "mteam":
            reg_default = "signup"
            inv_default = "invite"
        else:
            reg_default = "signup.php"
            inv_default = "invite.php"
        items.append(
            {
                "domain": dom,
                "name": name,
                "url": url,
                "source": "manual",
                "template": template,
                "has_local_config": True,
                "cookie_configured": bool(view.get("cookie_configured")),
                "authorization_configured": bool(view.get("authorization_configured")),
                "did_configured": bool(view.get("did_configured")),
                "registration_url": view.get("registration_url")
                or (urljoin(url.rstrip("/") + "/", reg_default) if template in {"nexusphp", "mteam"} else ""),
                "invite_url": view.get("invite_url") or (urljoin(url.rstrip("/") + "/", inv_default) if template in {"nexusphp", "mteam"} else ""),
            }
        )

    try:
        extras_map = await ctx.store.get_sites_extras([_normalize_domain(x.get("domain") or "") for x in items])
        for x in items:
            dom = _normalize_domain(x.get("domain") or "")
            if not dom:
                continue
            extra = extras_map.get(dom) or {}
            x["reachability_state"] = extra.get("reachability_state", "unknown")
            if x.get("template") == "nexusphp":
                invite_uid = extra.get("invite_uid")
                if invite_uid:
                    x["invite_url"] = urljoin(x.get("url", "").rstrip("/") + "/", f"invite.php?id={invite_uid}")
    except Exception:
        logger.exception("failed to load site extras for sites list")

    items.sort(
        key=lambda x: (
            (x.get("reachability_state") == "down"),
            (x.get("source") != "moviepilot"),
            x.get("name") or x.get("domain") or "",
        )
    )
    if mp_error and mp_source in {"cache", "state"} and mp_cache_age_seconds is not None:
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


@app.put("/api/sites", dependencies=[Depends(require_auth)])
async def api_sites_put(
    ctx: Annotated[AppContext, Depends(get_ctx)],
    payload: Dict[str, Any] = Body(default={}),
) -> Dict[str, Any]:
    payload = _safe_dict(payload)
    mode = (_cfg_str(payload.get("mode")) or "manual").lower()
    if mode not in {"manual", "override"}:
        raise HTTPException(status_code=400, detail="mode must be manual|override")

    url = _cfg_str(payload.get("url"))
    domain = _normalize_domain(_cfg_str(payload.get("domain")) or _domain_from_url(url))
    if not domain:
        raise HTTPException(status_code=400, detail="domain is required (or provide url)")

    name = _cfg_str(payload.get("name"))
    template = (_cfg_str(payload.get("template")) or "nexusphp").lower()
    if template not in {"nexusphp", "custom", "mteam"}:
        raise HTTPException(status_code=400, detail="template must be nexusphp|custom|mteam")
    if template == "mteam" and not domain.endswith("m-team.cc"):
        raise HTTPException(status_code=400, detail="mteam template requires domain *.m-team.cc")

    cookie = payload.get("cookie")
    clear_cookie = bool(payload.get("clear_cookie"))

    authorization = payload.get("authorization")
    clear_authorization = bool(payload.get("clear_authorization"))
    did = payload.get("did")
    clear_did = bool(payload.get("clear_did"))

    registration_url = _cfg_str(payload.get("registration_url"))
    invite_url = _cfg_str(payload.get("invite_url"))

    sites_cfg = await _load_sites_config(ctx)
    entries = _safe_dict(sites_cfg.get("entries"))
    existed = domain in entries
    entry = _safe_dict(entries.get(domain))
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
        # override: don't require url, but keep it if user explicitly provides it (used for validation)
        if url:
            entry["url"] = url

    entry["template"] = template

    if clear_cookie:
        entry.pop("cookie", None)
    elif cookie is not None and _cfg_str(cookie):
        entry["cookie"] = _cfg_str(cookie)

    if clear_authorization:
        entry.pop("authorization", None)
    elif authorization is not None and _cfg_str(authorization):
        entry["authorization"] = _cfg_str(authorization)

    if clear_did:
        entry.pop("did", None)
    elif did is not None and _cfg_str(did):
        entry["did"] = _cfg_str(did)

    if template == "custom":
        if not registration_url or not invite_url:
            raise HTTPException(status_code=400, detail="registration_url and invite_url are required for custom template")
        base_for_validate = url or registration_url
        entry["registration_path"] = _relative_path_from_page_url(registration_url, base_for_validate, label="registration_url")
        entry["invite_path"] = _relative_path_from_page_url(invite_url, base_for_validate, label="invite_url")
    else:
        entry.pop("registration_path", None)
        entry.pop("invite_path", None)
        if template == "mteam":
            entry["registration_path"] = "signup"
            entry["invite_path"] = "invite"

    entries[domain] = entry
    await ctx.store.set_json("sites", {"version": 1, "entries": entries})

    try:
        await ctx.store.add_event(
            category="site",
            level="info",
            action="site_upsert",
            message="site added" if not existed else "site updated",
            domain=domain,
            detail={"mode": mode, "template": template},
        )
    except Exception:
        pass

    # Sync site list summary (and notify) using cached MP sites when available.
    try:
        now = datetime.now(timezone.utc)
        app_cfg = await _load_app_config(ctx)
        mp_cfg = _safe_dict(app_cfg.get("moviepilot"))
        mp_base_url = _cfg_str(mp_cfg.get("base_url")) or ctx.settings.moviepilot.base_url
        mp_sites_cache_ttl = _cfg_int(
            mp_cfg.get("sites_cache_ttl_seconds"),
            MP_SITES_CACHE_DEFAULT_TTL_SECONDS,
            MP_SITES_CACHE_MIN_TTL_SECONDS,
            MP_SITES_CACHE_MAX_TTL_SECONDS,
        )

        mp_sites: list[Site] = []
        cache = parse_cache(await ctx.store.get_json(MP_SITES_CACHE_KEY, default=None))
        if cache and not cache_expired(cache, now, mp_sites_cache_ttl, base_url=mp_base_url):
            mp_sites = cache.sites
        if not mp_sites:
            snap_at, snap_sites = await ctx.store.load_sites_snapshot()
            if snap_sites and snap_at and int((now - snap_at).total_seconds()) <= mp_sites_cache_ttl:
                mp_sites = snap_sites
        if not mp_sites:
            prev_summary = _safe_dict(await ctx.store.get_json(SITE_LIST_SUMMARY_KEY, default=None))
            prev_items = _safe_dict(prev_summary.get("items"))
            for dom, item_any in prev_items.items():
                item = _safe_dict(item_any)
                if _cfg_str(item.get("source")) != "moviepilot":
                    continue
                url = _cfg_str(item.get("url"))
                if not url:
                    continue
                mp_sites.append(
                    Site(
                        id=0,
                        name=_cfg_str(item.get("name")) or _normalize_domain(dom),
                        domain=_normalize_domain(dom),
                        url=url,
                        ua=None,
                        cookie=None,
                        cookie_override=None,
                        authorization=None,
                        did=None,
                        is_active=True,
                        template=_cfg_str(item.get("template")) or None,
                        registration_path=_cfg_str(item.get("registration_path")) or None,
                        invite_path=_cfg_str(item.get("invite_path")) or None,
                    )
                )

        sites_for_sync = ctx.scanner._merge_sites(mp_sites, entries)
        await ctx.scanner.sync_site_list_summary(sites_for_sync, now, notify=True, reason="sites_put")
    except Exception:
        logger.exception("failed to sync site list summary after sites put")

    scan_triggered = False
    scan_reason = ""
    try:
        inflight = set(getattr(ctx.scanner, "in_flight_domains")() or [])
    except Exception:
        inflight = set()
    if domain in inflight:
        scan_triggered = False
        scan_reason = "already_scanning"
    else:
        scan_triggered = True

        async def _kick() -> None:
            try:
                await ctx.scanner.run_one(domain)
            except AlreadyScanningError:
                return
            except Exception:
                logger.exception("auto scan after sites upsert failed: %s", domain)

        asyncio.create_task(_kick())

    return {"ok": True, "scan_triggered": scan_triggered, "scan_reason": scan_reason}


@app.delete("/api/sites/{domain}", dependencies=[Depends(require_auth)])
async def api_sites_delete(domain: str, ctx: Annotated[AppContext, Depends(get_ctx)]) -> Dict[str, Any]:
    dom = _normalize_domain(domain)
    sites_cfg = await _load_sites_config(ctx)
    entries = _safe_dict(sites_cfg.get("entries"))
    existed = dom in entries
    existed_mode = _cfg_str(_safe_dict(entries.get(dom)).get("mode")).lower() if existed else ""
    if existed:
        entries.pop(dom, None)
        await ctx.store.set_json("sites", {"version": 1, "entries": entries})
        try:
            await ctx.store.add_event(
                category="site",
                level="info",
                action="site_delete" if existed_mode == "manual" else "site_override_clear",
                message="site deleted" if existed_mode == "manual" else "site override cleared",
                domain=dom,
            )
        except Exception:
            pass
        try:
            now = datetime.now(timezone.utc)
            app_cfg = await _load_app_config(ctx)
            mp_cfg = _safe_dict(app_cfg.get("moviepilot"))
            mp_base_url = _cfg_str(mp_cfg.get("base_url")) or ctx.settings.moviepilot.base_url
            mp_sites_cache_ttl = _cfg_int(
                mp_cfg.get("sites_cache_ttl_seconds"),
                MP_SITES_CACHE_DEFAULT_TTL_SECONDS,
                MP_SITES_CACHE_MIN_TTL_SECONDS,
                MP_SITES_CACHE_MAX_TTL_SECONDS,
            )

            mp_sites: list[Site] = []
            cache = parse_cache(await ctx.store.get_json(MP_SITES_CACHE_KEY, default=None))
            if cache and not cache_expired(cache, now, mp_sites_cache_ttl, base_url=mp_base_url):
                mp_sites = cache.sites
            if not mp_sites:
                snap_at, snap_sites = await ctx.store.load_sites_snapshot()
                if snap_sites and snap_at and int((now - snap_at).total_seconds()) <= mp_sites_cache_ttl:
                    mp_sites = snap_sites
            if not mp_sites:
                prev_summary = _safe_dict(await ctx.store.get_json(SITE_LIST_SUMMARY_KEY, default=None))
                prev_items = _safe_dict(prev_summary.get("items"))
                for d, item_any in prev_items.items():
                    item = _safe_dict(item_any)
                    if _cfg_str(item.get("source")) != "moviepilot":
                        continue
                    url = _cfg_str(item.get("url"))
                    if not url:
                        continue
                    mp_sites.append(
                        Site(
                            id=0,
                            name=_cfg_str(item.get("name")) or _normalize_domain(d),
                            domain=_normalize_domain(d),
                            url=url,
                            ua=None,
                            cookie=None,
                            cookie_override=None,
                            authorization=None,
                            did=None,
                            is_active=True,
                            template=_cfg_str(item.get("template")) or None,
                            registration_path=_cfg_str(item.get("registration_path")) or None,
                            invite_path=_cfg_str(item.get("invite_path")) or None,
                        )
                    )

            sites_for_sync = ctx.scanner._merge_sites(mp_sites, entries)
            await ctx.scanner.sync_site_list_summary(sites_for_sync, now, notify=True, reason="sites_delete")
        except Exception:
            logger.exception("failed to sync site list summary after sites delete")
    return {"ok": True}


def _spa_file_response() -> HTMLResponse:
    index_path = _DIST_DIR / "index.html"
    if not index_path.exists():
        detail = (
            "<h1>Web UI not built</h1>"
            "<p>Run:</p>"
            "<pre>npm --prefix webui install\nnpm --prefix webui run build</pre>"
        )
        return HTMLResponse(detail, status_code=503)
    return HTMLResponse(index_path.read_text(encoding="utf-8"), status_code=200)


@app.get("/", response_class=HTMLResponse, dependencies=[Depends(require_auth)])
async def spa_root() -> HTMLResponse:
    return _spa_file_response()


@app.get("/{path:path}", response_class=HTMLResponse, dependencies=[Depends(require_auth)])
async def spa_routes(path: str) -> HTMLResponse:
    if path.startswith("api") or path.startswith("assets") or path in {"docs", "openapi.json", "redoc", "health"}:
        raise HTTPException(status_code=404)
    return _spa_file_response()
