from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from typing import Any, Dict, Optional

import httpx
import re
from urllib.parse import urljoin, urlparse

from pt_invite_watcher.config import Settings
from pt_invite_watcher.engines.nexusphp import NexusPhpDetector
from pt_invite_watcher.models import AspectResult, Evidence, ReachabilityResult, SiteCheckResult
from pt_invite_watcher.notify.manager import NotifierManager
from pt_invite_watcher.providers.cookiecloud import CookieCloudClient, CookieManager
from pt_invite_watcher.providers.moviepilot_api import MoviePilotClient
from pt_invite_watcher.storage.sqlite import SqliteStore


logger = logging.getLogger("pt_invite_watcher.scanner")

_MAX_ERROR_DETAIL_LEN = 240
_DOWN_HTTP_STATUSES = set(range(520, 530))


def _format_error_detail(exc: Exception) -> str:
    msg = str(exc or "").strip()
    if not msg:
        msg = getattr(getattr(exc, "__cause__", None), "args", None) and str(exc.__cause__).strip() or ""
    if not msg:
        msg = type(exc).__name__
    msg = re.sub(r"\s+", " ", msg)
    if len(msg) > _MAX_ERROR_DETAIL_LEN:
        msg = msg[: _MAX_ERROR_DETAIL_LEN - 1] + "…"
    return msg


def _hosts_related(host_a: str, host_b: str) -> bool:
    a = (host_a or "").lower().strip(".")
    b = (host_b or "").lower().strip(".")
    if not a or not b:
        return True
    return a == b or a.endswith("." + b) or b.endswith("." + a)


def _engine_hint_from_html(html: str) -> Optional[str]:
    h = (html or "").lower()
    if not h:
        return None
    if "nexusphp" in h:
        return "nexusphp"
    if any(token in h for token in ("torrents.php", "userdetails.php", "takesignup.php", "takeinvite.php", "login.php")):
        return "nexusphp"
    return None


def _safe_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


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


class Scanner:
    def __init__(self, settings: Settings, store: SqliteStore, notifier: NotifierManager):
        self._settings = settings
        self._store = store
        self._notifier = notifier

        self._lock = asyncio.Lock()
        self._sem = asyncio.Semaphore(max(1, settings.scan.concurrency))
        self._detector = NexusPhpDetector()

    async def _load_app_config(self) -> dict[str, Any]:
        try:
            data = await self._store.get_json("app_config", default={})
            return _safe_dict(data)
        except Exception:
            return {}

    async def run_once(self) -> Dict[str, Any]:
        async with self._lock:
            started_at = datetime.now(timezone.utc)
            cfg = await self._load_app_config()

            mp_cfg = _safe_dict(cfg.get("moviepilot"))
            cookie_cfg = _safe_dict(cfg.get("cookie"))
            cc_cfg = _safe_dict(cookie_cfg.get("cookiecloud"))
            scan_cfg = _safe_dict(cfg.get("scan"))

            mp_base_url = _cfg_str(mp_cfg.get("base_url")) or self._settings.moviepilot.base_url
            mp_username = _cfg_str(mp_cfg.get("username")) or self._settings.moviepilot.username
            mp_password = _cfg_str(mp_cfg.get("password")) or self._settings.moviepilot.password
            mp_otp_password = _cfg_str(mp_cfg.get("otp_password")) or (self._settings.moviepilot.otp_password or "")

            cookie_source = (_cfg_str(cookie_cfg.get("source")) or self._settings.cookie.source or "auto").strip().lower()
            cc_base_url = _cfg_str(cc_cfg.get("base_url")) or self._settings.cookie.cookiecloud.base_url
            cc_uuid = _cfg_str(cc_cfg.get("uuid")) or self._settings.cookie.cookiecloud.uuid
            cc_password = _cfg_str(cc_cfg.get("password")) or self._settings.cookie.cookiecloud.password
            cc_refresh = _cfg_int(
                cc_cfg.get("refresh_interval_seconds"),
                default=int(self._settings.cookie.cookiecloud.refresh_interval_seconds),
                min_value=30,
                max_value=24 * 3600,
            )

            scan_timeout = _cfg_int(
                scan_cfg.get("timeout_seconds"),
                default=int(self._settings.scan.timeout_seconds),
                min_value=5,
                max_value=180,
            )
            scan_concurrency = _cfg_int(
                scan_cfg.get("concurrency"),
                default=int(self._settings.scan.concurrency),
                min_value=1,
                max_value=64,
            )
            scan_user_agent = _cfg_str(scan_cfg.get("user_agent")) or self._settings.scan.user_agent or ""
            scan_trust_env = _cfg_bool(scan_cfg.get("trust_env"), default=bool(self._settings.scan.trust_env))

            self._sem = asyncio.Semaphore(max(1, scan_concurrency))

            mp_client = MoviePilotClient(
                base_url=mp_base_url,
                username=mp_username,
                password=mp_password,
                otp_password=mp_otp_password or None,
                timeout_seconds=scan_timeout,
            )

            cc_client = None
            if cc_base_url and cc_uuid and cc_password:
                cc_client = CookieCloudClient(
                    base_url=cc_base_url,
                    uuid=cc_uuid,
                    password=cc_password,
                    timeout_seconds=scan_timeout,
                )
            cookie_mgr = CookieManager(
                cookie_source=cookie_source,
                cookiecloud=cc_client,
                refresh_interval_seconds=cc_refresh,
            )

            try:
                sites = await mp_client.list_sites(only_active=True)
            except Exception as e:
                logger.exception("failed to load sites from MoviePilot")
                status = {
                    "ok": False,
                    "site_count": 0,
                    "error": str(e),
                    "last_run_at": started_at.isoformat(),
                }
                await self._store.set_json("scan_status", status)
                return status

            logger.info("scan start: %d sites", len(sites))

            timeout = httpx.Timeout(scan_timeout)
            async with httpx.AsyncClient(
                timeout=timeout,
                follow_redirects=True,
                trust_env=scan_trust_env,
            ) as client:
                tasks = [self._check_one(client, site, started_at, cookie_mgr, scan_user_agent or None) for site in sites]
                results = await asyncio.gather(*tasks, return_exceptions=True)
                errors = [r for r in results if isinstance(r, Exception)]
                if errors:
                    logger.warning("scan completed with %d task errors", len(errors))

            logger.info("scan done")
            status = {
                "ok": True,
                "site_count": len(sites),
                "error": "",
                "last_run_at": datetime.now(timezone.utc).isoformat(),
            }
            await self._store.set_json("scan_status", status)
            return status

    async def _check_one(
        self,
        client: httpx.AsyncClient,
        site,
        now: datetime,
        cookie_mgr: CookieManager,
        default_user_agent: Optional[str],
    ) -> None:
        async with self._sem:
            ua = site.ua or default_user_agent or None
            reachability, engine_hint = await self._probe_reachability(client, site.url, ua)
            engine = engine_hint or "unknown"

            if reachability.state != "up":
                registration = AspectResult(
                    state="unknown",
                    evidence=Evidence(
                        url=urljoin(site.url.rstrip("/") + "/", "signup.php"),
                        http_status=None,
                        reason="site_unreachable",
                        detail=reachability.evidence.detail or reachability.evidence.reason,
                    ),
                )
                invites = AspectResult(
                    state="unknown",
                    evidence=Evidence(
                        url=urljoin(site.url.rstrip("/") + "/", "invite.php"),
                        http_status=None,
                        reason="site_unreachable",
                        detail=reachability.evidence.detail or reachability.evidence.reason,
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
                await self._persist_and_notify(site, result, now)
                return

            if (site.domain or "").lower().endswith("m-team.cc"):
                registration = AspectResult(
                    state="closed",
                    evidence=Evidence(
                        url=urljoin(site.url.rstrip("/") + "/", "signup.php"),
                        http_status=reachability.evidence.http_status,
                        reason="mteam_default_closed",
                    ),
                )
            else:
                try:
                    registration = await self._detector.check_registration(client, site, ua)
                except Exception as e:
                    logger.exception("registration check failed: %s", site.domain)
                    registration = AspectResult(
                        state="unknown",
                        evidence=Evidence(
                            url=urljoin(site.url.rstrip("/") + "/", "signup.php"),
                            http_status=None,
                            reason=f"registration_error:{type(e).__name__}",
                            detail=_format_error_detail(e),
                        ),
                    )

            cookie_header = None
            try:
                cookie_header = await cookie_mgr.cookie_header_for(site.url, fallback_cookie=site.cookie)
            except Exception:
                logger.exception("cookie build failed: %s", site.domain)

            try:
                invites = await self._detector.check_invites(client, site, ua, cookie_header)
            except Exception as e:
                logger.exception("invites check failed: %s", site.domain)
                invites = AspectResult(
                    state="unknown",
                    evidence=Evidence(
                        url=urljoin(site.url.rstrip("/") + "/", "invite.php"),
                        http_status=None,
                        reason=f"invites_error:{type(e).__name__}",
                        detail=_format_error_detail(e),
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
            await self._persist_and_notify(site, result, now)

    async def _probe_reachability(
        self,
        client: httpx.AsyncClient,
        site_url: str,
        user_agent: Optional[str],
    ) -> tuple[ReachabilityResult, Optional[str]]:
        ua = user_agent or None
        orig_host = urlparse(site_url).hostname or ""

        engine_hint: Optional[str] = None
        last: tuple[ReachabilityResult, Optional[str]] = (
            ReachabilityResult(state="unknown", evidence=Evidence(url=site_url, http_status=None, reason="probe_not_run")),
            None,
        )

        attempts = 3
        for attempt in range(attempts):
            try:
                resp = await client.get(site_url, headers={"User-Agent": ua} if ua else None)
                status = resp.status_code
                engine_hint = engine_hint or _engine_hint_from_html(resp.text)

                final_host = resp.url.host if resp.url else ""
                if orig_host and final_host and not _hosts_related(orig_host, final_host):
                    last = (
                        ReachabilityResult(
                            state="down",
                            evidence=Evidence(
                                url=str(resp.url),
                                http_status=status,
                                reason="probe_redirect",
                                detail=f"redirected_to:{final_host}",
                            ),
                        ),
                        engine_hint,
                    )
                elif status >= 500 or status in _DOWN_HTTP_STATUSES:
                    last = (
                        ReachabilityResult(
                            state="down",
                            evidence=Evidence(url=str(resp.url), http_status=status, reason=f"probe_http_{status}"),
                        ),
                        engine_hint,
                    )
                else:
                    return (
                        ReachabilityResult(
                            state="up",
                            evidence=Evidence(url=str(resp.url), http_status=status, reason="probe_ok"),
                        ),
                        engine_hint,
                    )
            except httpx.RequestError as e:
                last = (
                    ReachabilityResult(
                        state="down",
                        evidence=Evidence(
                            url=site_url,
                            http_status=None,
                            reason=f"probe_error:{type(e).__name__}",
                            detail=_format_error_detail(e),
                        ),
                    ),
                    engine_hint,
                )
            except Exception as e:
                last = (
                    ReachabilityResult(
                        state="unknown",
                        evidence=Evidence(
                            url=site_url,
                            http_status=None,
                            reason=f"probe_error:{type(e).__name__}",
                            detail=_format_error_detail(e),
                        ),
                    ),
                    engine_hint,
                )

            if attempt < attempts - 1:
                await asyncio.sleep(0.3 * (attempt + 1))

        # Mark that we retried before concluding it's down/unknown.
        result, hint = last
        ev = result.evidence
        if ev.detail:
            detail = f"{ev.detail} (retries={attempts})"
        else:
            detail = f"retries={attempts}"
        return (
            ReachabilityResult(
                state=result.state,
                evidence=Evidence(url=ev.url, http_status=ev.http_status, reason=ev.reason, matched=ev.matched, detail=detail),
            ),
            hint,
        )

    async def _persist_and_notify(self, site, result: SiteCheckResult, now: datetime) -> None:
        try:
            prev = await self._store.get_site_state(site.domain)
            changes = self._diff(prev, result)
            changed_at = now.isoformat() if changes else None
            await self._store.save_site_result(result, changed_at=changed_at)
        except Exception:
            logger.exception("failed to persist site result: %s", site.domain)
            return

        if not changes:
            return

        title = "PT Invite Watcher: 状态变化"
        text = "\n".join(
            [
                f"站点：{site.name} ({site.domain})",
                f"URL：{site.url}",
                *changes,
                f"注册：{result.registration.state} ({result.registration.evidence.reason})",
                f"邀请：{result.invites.state} ({result.invites.available if result.invites.available is not None else '-'})",
            ]
        )
        try:
            await self._notifier.send(title=title, text=text)
        except Exception:
            logger.exception("notify failed: %s", site.domain)

    @staticmethod
    def _diff(prev, cur: SiteCheckResult) -> list[str]:
        if prev is None:
            return []

        changes: list[str] = []

        if cur.registration.state == "open" and prev.registration_state != "open":
            changes.append("开放注册：open")
        elif cur.registration.state == "closed" and prev.registration_state == "open":
            changes.append("开放注册：closed")

        if cur.invites.available is not None:
            prev_count = prev.invites_available
            cur_count = cur.invites.available
            if cur_count > 0 and (prev_count is None or prev_count <= 0):
                changes.append(f"可用邀请数：{prev_count or 0} -> {cur_count}")
            elif cur_count <= 0 and (prev_count is not None and prev_count > 0):
                changes.append(f"可用邀请数：{prev_count} -> {cur_count}")

        return changes
