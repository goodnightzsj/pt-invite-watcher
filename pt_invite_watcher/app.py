from __future__ import annotations

import asyncio
import logging
from typing import Annotated, Optional
from urllib.parse import quote

from fastapi import Depends, FastAPI, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.security import HTTPBasic, HTTPBasicCredentials

from pt_invite_watcher.app_context import AppContext, build_context
from pt_invite_watcher.config import Settings, load_settings


logger = logging.getLogger("pt_invite_watcher")

app = FastAPI(title="PT Invite Watcher", version="0.1.0")
templates = Jinja2Templates(directory="pt_invite_watcher/web/templates")
app.mount("/static", StaticFiles(directory="pt_invite_watcher/web/static"), name="static")

basic_security = HTTPBasic(auto_error=False)


def _cfg_str(value: Optional[str]) -> str:
    return (value or "").strip()


def _cfg_int(value: Optional[str], default: int, min_value: int, max_value: int) -> int:
    if value is None or value == "":
        return default
    try:
        parsed = int(str(value).strip())
    except ValueError:
        return default
    return max(min_value, min(max_value, parsed))


def _cfg_bool(value: object, default: bool) -> bool:
    if value is None or value == "":
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, int):
        return value != 0
    return str(value).strip().lower() in {"1", "true", "yes", "y", "on"}


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
async def health() -> dict:
    return {"ok": True}


@app.get("/", response_class=HTMLResponse, dependencies=[Depends(require_auth)])
async def index(request: Request, ctx: Annotated[AppContext, Depends(get_ctx)]) -> HTMLResponse:
    rows = await ctx.store.list_site_states()
    scan_status = await ctx.store.get_json("scan_status", default=None)
    return templates.TemplateResponse(
        request=request,
        name="index.html",
        context={
            "title": "站点状态",
            "rows": rows,
            "scan_status": scan_status,
            "flash": request.query_params.get("flash"),
        },
    )


@app.post("/scan/run", dependencies=[Depends(require_auth)])
async def scan_run(ctx: Annotated[AppContext, Depends(get_ctx)]) -> RedirectResponse:
    status = await ctx.scanner.run_once()
    if status.get("ok"):
        msg = f"scan ok: {status.get('site_count', 0)} sites"
    else:
        msg = f"scan failed: {status.get('error') or 'unknown error'}"
    return RedirectResponse(url=f"/?flash={quote(msg)}", status_code=303)


@app.get("/notifications", response_class=HTMLResponse, dependencies=[Depends(require_auth)])
async def notifications(request: Request, ctx: Annotated[AppContext, Depends(get_ctx)]) -> HTMLResponse:
    cfg = await ctx.store.get_json("notifications", default={})
    telegram = cfg.get("telegram") or {}
    wecom = cfg.get("wecom") or {}

    telegram_view = {
        "enabled": bool(telegram.get("enabled")),
        "configured": bool(telegram.get("token") and telegram.get("chat_id")),
    }
    wecom_view = {
        "enabled": bool(wecom.get("enabled")),
        "configured": bool(wecom.get("corpid") and wecom.get("app_secret") and wecom.get("agent_id")),
        "to_user": wecom.get("to_user") or "@all",
        "to_party": wecom.get("to_party") or "",
        "to_tag": wecom.get("to_tag") or "",
    }

    return templates.TemplateResponse(
        request=request,
        name="notifications.html",
        context={
            "title": "通知设置",
            "telegram": telegram_view,
            "wecom": wecom_view,
            "flash": request.query_params.get("flash"),
        },
    )


@app.get("/config", response_class=HTMLResponse, dependencies=[Depends(require_auth)])
async def config_page(request: Request, ctx: Annotated[AppContext, Depends(get_ctx)]) -> HTMLResponse:
    cfg = await ctx.store.get_json("app_config", default={})
    if not isinstance(cfg, dict):
        cfg = {}
    mp_cfg = cfg.get("moviepilot") or {}
    if not isinstance(mp_cfg, dict):
        mp_cfg = {}
    cookie_cfg = cfg.get("cookie") or {}
    if not isinstance(cookie_cfg, dict):
        cookie_cfg = {}
    cc_cfg = cookie_cfg.get("cookiecloud") or {}
    if not isinstance(cc_cfg, dict):
        cc_cfg = {}
    scan_cfg = cfg.get("scan") or {}
    if not isinstance(scan_cfg, dict):
        scan_cfg = {}

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
                str(cc_cfg.get("refresh_interval_seconds")) if cc_cfg.get("refresh_interval_seconds") is not None else None,
                ctx.settings.cookie.cookiecloud.refresh_interval_seconds,
                30,
                24 * 3600,
            ),
        },
    }
    scan = {
        "interval_seconds": _cfg_int(
            str(scan_cfg.get("interval_seconds")) if scan_cfg.get("interval_seconds") is not None else None,
            ctx.settings.scan.interval_seconds,
            30,
            24 * 3600,
        ),
        "timeout_seconds": _cfg_int(
            str(scan_cfg.get("timeout_seconds")) if scan_cfg.get("timeout_seconds") is not None else None,
            ctx.settings.scan.timeout_seconds,
            5,
            180,
        ),
        "concurrency": _cfg_int(
            str(scan_cfg.get("concurrency")) if scan_cfg.get("concurrency") is not None else None,
            ctx.settings.scan.concurrency,
            1,
            64,
        ),
        "user_agent": _cfg_str(scan_cfg.get("user_agent")) or ctx.settings.scan.user_agent,
        "trust_env": _cfg_bool(scan_cfg.get("trust_env"), default=ctx.settings.scan.trust_env),
    }

    return templates.TemplateResponse(
        request=request,
        name="config.html",
        context={
            "title": "服务配置",
            "moviepilot": moviepilot,
            "cookie": cookie,
            "scan": scan,
            "flash": request.query_params.get("flash"),
        },
    )


@app.post("/config/save", dependencies=[Depends(require_auth)])
async def config_save(
    ctx: Annotated[AppContext, Depends(get_ctx)],
    moviepilot_base_url: Annotated[Optional[str], Form()] = None,
    moviepilot_username: Annotated[Optional[str], Form()] = None,
    moviepilot_password: Annotated[Optional[str], Form()] = None,
    moviepilot_otp_password: Annotated[Optional[str], Form()] = None,
    cookie_source: Annotated[Optional[str], Form()] = None,
    cookiecloud_base_url: Annotated[Optional[str], Form()] = None,
    cookiecloud_uuid: Annotated[Optional[str], Form()] = None,
    cookiecloud_password: Annotated[Optional[str], Form()] = None,
    cookiecloud_refresh_interval_seconds: Annotated[Optional[str], Form()] = None,
    scan_interval_seconds: Annotated[Optional[str], Form()] = None,
    scan_timeout_seconds: Annotated[Optional[str], Form()] = None,
    scan_concurrency: Annotated[Optional[str], Form()] = None,
    scan_user_agent: Annotated[Optional[str], Form()] = None,
    scan_trust_env: Annotated[Optional[str], Form()] = None,
) -> RedirectResponse:
    cfg = await ctx.store.get_json("app_config", default={}) or {}
    if not isinstance(cfg, dict):
        cfg = {}

    mp = cfg.get("moviepilot")
    if not isinstance(mp, dict):
        mp = {}
    mp_base = _cfg_str(moviepilot_base_url)
    mp_user = _cfg_str(moviepilot_username)
    mp_pass = _cfg_str(moviepilot_password)
    mp_otp = _cfg_str(moviepilot_otp_password)
    if mp_base:
        mp["base_url"] = mp_base
    if mp_user:
        mp["username"] = mp_user
    if mp_pass:
        mp["password"] = mp_pass
    if mp_otp:
        mp["otp_password"] = mp_otp
    cfg["moviepilot"] = mp

    cookie = cfg.get("cookie")
    if not isinstance(cookie, dict):
        cookie = {}
    src = _cfg_str(cookie_source).lower()
    if src in {"auto", "cookiecloud", "moviepilot"}:
        cookie["source"] = src

    cc = cookie.get("cookiecloud")
    if not isinstance(cc, dict):
        cc = {}
    cc_base = _cfg_str(cookiecloud_base_url)
    cc_uuid = _cfg_str(cookiecloud_uuid)
    cc_pass = _cfg_str(cookiecloud_password)
    if cc_base:
        cc["base_url"] = cc_base
    if cc_uuid:
        cc["uuid"] = cc_uuid
    if cc_pass:
        cc["password"] = cc_pass
    cc_refresh_default = int(cc.get("refresh_interval_seconds") or ctx.settings.cookie.cookiecloud.refresh_interval_seconds)
    cc["refresh_interval_seconds"] = _cfg_int(cookiecloud_refresh_interval_seconds, cc_refresh_default, 30, 24 * 3600)
    cookie["cookiecloud"] = cc
    cfg["cookie"] = cookie

    scan = cfg.get("scan")
    if not isinstance(scan, dict):
        scan = {}
    scan_interval_default = int(scan.get("interval_seconds") or ctx.settings.scan.interval_seconds)
    scan_timeout_default = int(scan.get("timeout_seconds") or ctx.settings.scan.timeout_seconds)
    scan_concurrency_default = int(scan.get("concurrency") or ctx.settings.scan.concurrency)
    scan["interval_seconds"] = _cfg_int(scan_interval_seconds, scan_interval_default, 30, 24 * 3600)
    scan["timeout_seconds"] = _cfg_int(scan_timeout_seconds, scan_timeout_default, 5, 180)
    scan["concurrency"] = _cfg_int(scan_concurrency, scan_concurrency_default, 1, 64)
    ua = (scan_user_agent or "").strip()
    if ua != "":
        scan["user_agent"] = ua
    scan["trust_env"] = scan_trust_env == "1"
    cfg["scan"] = scan

    await ctx.store.set_json("app_config", cfg)
    return RedirectResponse(url="/config?flash=saved", status_code=303)


@app.post("/config/reset", dependencies=[Depends(require_auth)])
async def config_reset(ctx: Annotated[AppContext, Depends(get_ctx)]) -> RedirectResponse:
    await ctx.store.set_json("app_config", {})
    return RedirectResponse(url="/config?flash=reset", status_code=303)


@app.post("/notifications/save", dependencies=[Depends(require_auth)])
async def notifications_save(
    ctx: Annotated[AppContext, Depends(get_ctx)],
    telegram_enabled: Annotated[Optional[str], Form()] = None,
    telegram_token: Annotated[Optional[str], Form()] = None,
    telegram_chat_id: Annotated[Optional[str], Form()] = None,
    wecom_enabled: Annotated[Optional[str], Form()] = None,
    wecom_corpid: Annotated[Optional[str], Form()] = None,
    wecom_app_secret: Annotated[Optional[str], Form()] = None,
    wecom_agent_id: Annotated[Optional[str], Form()] = None,
    wecom_to_user: Annotated[Optional[str], Form()] = None,
    wecom_to_party: Annotated[Optional[str], Form()] = None,
    wecom_to_tag: Annotated[Optional[str], Form()] = None,
) -> RedirectResponse:
    cfg = await ctx.store.get_json("notifications", default={})
    telegram = cfg.get("telegram") or {}
    wecom = cfg.get("wecom") or {}

    telegram["enabled"] = telegram_enabled == "1"
    if telegram_token:
        telegram["token"] = telegram_token.strip()
    if telegram_chat_id:
        telegram["chat_id"] = telegram_chat_id.strip()

    wecom["enabled"] = wecom_enabled == "1"
    if wecom_corpid:
        wecom["corpid"] = wecom_corpid.strip()
    if wecom_app_secret:
        wecom["app_secret"] = wecom_app_secret.strip()
    if wecom_agent_id:
        wecom["agent_id"] = wecom_agent_id.strip()
    if wecom_to_user is not None:
        wecom["to_user"] = (wecom_to_user or "@all").strip()
    if wecom_to_party is not None:
        wecom["to_party"] = (wecom_to_party or "").strip()
    if wecom_to_tag is not None:
        wecom["to_tag"] = (wecom_to_tag or "").strip()

    await ctx.store.set_json("notifications", {"telegram": telegram, "wecom": wecom})
    return RedirectResponse(url="/notifications?flash=saved", status_code=303)


@app.post("/notifications/test/telegram", dependencies=[Depends(require_auth)])
async def notifications_test_telegram(ctx: Annotated[AppContext, Depends(get_ctx)]) -> RedirectResponse:
    ok, msg = await ctx.notifier.test("telegram")
    return RedirectResponse(url=f"/notifications?flash={'ok' if ok else 'fail'}%3A{msg}", status_code=303)


@app.post("/notifications/test/wecom", dependencies=[Depends(require_auth)])
async def notifications_test_wecom(ctx: Annotated[AppContext, Depends(get_ctx)]) -> RedirectResponse:
    ok, msg = await ctx.notifier.test("wecom")
    return RedirectResponse(url=f"/notifications?flash={'ok' if ok else 'fail'}%3A{msg}", status_code=303)
