from __future__ import annotations

import logging
from datetime import datetime
from typing import Any, Awaitable, Callable, Optional
from urllib.parse import urljoin

import httpx

from pt_invite_watcher.engines.mteam import MTeamDetector
from pt_invite_watcher.engines.nexusphp import NexusPhpDetector
from pt_invite_watcher.engines.engine_selector import engine_for_site
from pt_invite_watcher.models import AspectResult, Evidence, Site, SiteCheckResult
from pt_invite_watcher.providers.cookiecloud import CookieManager
from pt_invite_watcher.scanner_invites import check_invites_for_site
from pt_invite_watcher.scanner_reachability import probe_reachability
from pt_invite_watcher.scanner_results import build_unreachable_result


logger = logging.getLogger("pt_invite_watcher.scanner.site")


async def check_one_site(
    *,
    client: httpx.AsyncClient,
    site: Site,
    now: datetime,
    cookie_mgr: CookieManager,
    default_user_agent: Optional[str],
    detector: NexusPhpDetector,
    mteam_detector: MTeamDetector,
    store: Any,
    log_step: Callable[[Site, str, str, str], Awaitable[None]],
    persist_and_notify: Callable[[Site, SiteCheckResult, datetime], Awaitable[None]],
    format_error_detail: Callable[[Exception], str],
    normalize_domain: Callable[[str], str],
    retry_delay_seconds: int,
) -> None:
    await log_step(site, "home", "check_reachability", f"正在检测连通性: {site.url}")
    ua = site.ua or default_user_agent or None
    cookie_override = (getattr(site, "cookie_override", None) or "").strip()
    cookie_header_for_invites: Optional[str] = None
    if cookie_override:
        cookie_header_for_invites = cookie_override
    else:
        try:
            cookie_header_for_invites = await cookie_mgr.cookie_header_for(site.url, fallback_cookie=getattr(site, "cookie", None))
        except Exception:
            logger.exception("cookie build failed: %s", site.domain)
            cookie_header_for_invites = None

    cookie_header_for_probe = cookie_header_for_invites or (getattr(site, "cookie", None) or "").strip() or None
    reachability, engine_hint = await probe_reachability(
        client,
        site.url,
        ua,
        cookie_header=cookie_header_for_probe,
        retry_delay_seconds=retry_delay_seconds,
    )
    engine = engine_for_site(site, hint=engine_hint)
    is_mteam = engine == "mteam"

    reg_path = (getattr(site, "registration_path", None) or "").strip() or "signup.php"
    inv_path = (getattr(site, "invite_path", None) or "").strip() or "invite.php"

    if reachability.state != "up":
        await log_step(site, "home", "site_unreachable", f"站点无法访问: {reachability.evidence.reason}")
        result = build_unreachable_result(
            site=site,
            engine=engine,
            reachability=reachability,
            checked_at=now,
            reg_path=reg_path,
            inv_path=inv_path,
        )
        await persist_and_notify(site, result, now)
        return

    try:
        await log_step(site, "signup", "check_registration", "正在检测注册状态")
        registration = await detector.check_registration(client, site, ua, retry_delay_seconds=retry_delay_seconds)
    except Exception as e:
        logger.exception("registration check failed: %s", site.domain)
        registration = AspectResult(
            state="unknown",
            evidence=Evidence(
                url=urljoin(site.url.rstrip("/") + "/", reg_path),
                http_status=None,
                reason=f"registration_error:{type(e).__name__}",
                detail=format_error_detail(e),
            ),
        )

    try:
        manual_no_cookie_skip = getattr(site, "id", None) is None and not cookie_header_for_invites and not is_mteam
        if is_mteam:
            await log_step(site, "invite", "check_invites", "正在检测邀请 (M-Team)")
        elif not manual_no_cookie_skip:
            await log_step(site, "invite", "check_invites", "正在检测邀请/个人中心")

        invites = await check_invites_for_site(
            is_mteam=is_mteam,
            store=store,
            detector=detector,
            mteam_detector=mteam_detector,
            client=client,
            site=site,
            user_agent=ua,
            cookie_header_for_invites=cookie_header_for_invites,
            inv_path=inv_path,
            retry_delay_seconds=retry_delay_seconds,
            domain=normalize_domain(site.domain),
        )
    except Exception as e:
        logger.exception("invites check failed: %s", site.domain)
        invites = AspectResult(
            state="unknown",
            evidence=Evidence(
                url=urljoin(site.url.rstrip("/") + "/", inv_path),
                http_status=None,
                reason=f"invites_error:{type(e).__name__}",
                detail=format_error_detail(e),
            ),
        )

    result = SiteCheckResult(
        site=site,
        engine=engine,
        reachability=reachability,
        registration=registration,
        invites=invites,
        checked_at=now,
    )
    await persist_and_notify(site, result, now)


__all__ = ["check_one_site"]
