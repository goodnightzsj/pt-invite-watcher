from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from typing import Annotated, Any, Dict, Optional

from fastapi import Body, Depends, FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.security import HTTPBasic, HTTPBasicCredentials

from pt_invite_watcher.app_context import AppContext, build_context
from pt_invite_watcher.config import Settings, load_settings


logger = logging.getLogger("pt_invite_watcher")

app = FastAPI(title="PT Invite Watcher", version="0.1.0")

basic_security = HTTPBasic(auto_error=False)

_DIST_DIR = Path(__file__).resolve().parent / "webui_dist"
_ASSETS_DIR = _DIST_DIR / "assets"

# Serve Vite build assets. We intentionally don't require auth here; the SPA entry and APIs are protected.
app.mount("/assets", StaticFiles(directory=_ASSETS_DIR.as_posix(), check_dir=False), name="assets")


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
    rows = await ctx.store.list_site_states()
    scan_status = await ctx.store.get_json("scan_status", default=None)
    return {"rows": rows, "scan_status": scan_status}


@app.post("/api/scan/run", dependencies=[Depends(require_auth)])
async def api_scan_run(ctx: Annotated[AppContext, Depends(get_ctx)]) -> Dict[str, Any]:
    status = await ctx.scanner.run_once()
    return status


@app.get("/api/config", dependencies=[Depends(require_auth)])
async def api_config_get(ctx: Annotated[AppContext, Depends(get_ctx)]) -> Dict[str, Any]:
    cfg = await ctx.store.get_json("app_config", default={})
    cfg = _safe_dict(cfg)
    mp_cfg = _safe_dict(cfg.get("moviepilot"))
    cookie_cfg = _safe_dict(cfg.get("cookie"))
    cc_cfg = _safe_dict(cookie_cfg.get("cookiecloud"))
    scan_cfg = _safe_dict(cfg.get("scan"))

    moviepilot = {
        "base_url": _cfg_str(mp_cfg.get("base_url")) or ctx.settings.moviepilot.base_url,
        "username": _cfg_str(mp_cfg.get("username")) or ctx.settings.moviepilot.username,
        "password_configured": bool(_cfg_str(mp_cfg.get("password")) or ctx.settings.moviepilot.password),
        "otp_configured": bool(_cfg_str(mp_cfg.get("otp_password")) or (ctx.settings.moviepilot.otp_password or "")),
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

    return {"moviepilot": moviepilot, "cookie": cookie, "scan": scan}


@app.put("/api/config", dependencies=[Depends(require_auth)])
async def api_config_put(
    ctx: Annotated[AppContext, Depends(get_ctx)],
    payload: Dict[str, Any] = Body(default={}),
) -> Dict[str, Any]:
    cfg = await ctx.store.get_json("app_config", default={}) or {}
    cfg = _safe_dict(cfg)

    payload = _safe_dict(payload)

    mp_in = _safe_dict(payload.get("moviepilot"))
    cookie_in = _safe_dict(payload.get("cookie"))
    cc_in = _safe_dict(cookie_in.get("cookiecloud"))
    scan_in = _safe_dict(payload.get("scan"))

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
    cfg["moviepilot"] = mp

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

    await ctx.store.set_json("app_config", cfg)
    return {"ok": True}


@app.post("/api/config/reset", dependencies=[Depends(require_auth)])
async def api_config_reset(ctx: Annotated[AppContext, Depends(get_ctx)]) -> Dict[str, Any]:
    await ctx.store.set_json("app_config", {})
    return {"ok": True}


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
    return {"ok": True}


@app.post("/api/notifications/test/{channel}", dependencies=[Depends(require_auth)])
async def api_notifications_test(channel: str, ctx: Annotated[AppContext, Depends(get_ctx)]) -> Dict[str, Any]:
    if channel not in {"telegram", "wecom"}:
        raise HTTPException(status_code=404, detail="unknown channel")
    ok, msg = await ctx.notifier.test(channel)
    return {"ok": bool(ok), "message": str(msg or "")}


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
