from __future__ import annotations
import logging
from dataclasses import dataclass
from typing import Any, Optional
from urllib.parse import urljoin

import httpx

from pt_invite_watcher.engines.nexusphp_sites import NexusPhpSiteAdapter, get_nexusphp_site_adapter
from pt_invite_watcher.engines.nexusphp_parse import (
    _append_retry_detail,
    _extract_html_title,
    _extract_invite_permission_reason,
    _extract_invite_quota_insufficient,
    _extract_invite_url_from_html,
    _extract_text,
    _extract_user_id_and_source,
    _extract_user_id_from_html,
    _has_invite_field,
    _has_signup_form,
    _invite_permission_denied_any,
    _invite_send_action_status,
    _is_invite_disabled,
    _is_registration_closed,
    _merge_detail,
    _normalize_text,
    _parse_home_invite_quota,
    _parse_invite_count,
    _truncate_detail,
)
from pt_invite_watcher.models import AspectResult, Evidence, Site
from pt_invite_watcher.net import DEFAULT_REQUEST_RETRY_ATTEMPTS, DEFAULT_REQUEST_RETRY_DELAY_SECONDS, request_with_retry
from pt_invite_watcher.utils.parse import format_error_detail


logger = logging.getLogger("pt_invite_watcher.nexusphp")

_UA_DEFAULT = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
_HTTP_RETRY_ATTEMPTS = DEFAULT_REQUEST_RETRY_ATTEMPTS
_MAX_ERROR_DETAIL_LEN = 240
_MAX_SIGNUP_SNIPPET_LEN = 160


async def _get_with_retry(
    client: httpx.AsyncClient,
    url: str,
    headers: dict[str, str],
    *,
    attempts: int = _HTTP_RETRY_ATTEMPTS,
    delay_seconds: int = DEFAULT_REQUEST_RETRY_DELAY_SECONDS,
) -> tuple[Optional[httpx.Response], Optional[Exception], int]:
    return await request_with_retry(
        lambda: client.get(url, headers=headers),
        attempts=max(1, int(attempts or 0)),
        delay_seconds=max(0, int(delay_seconds or 0)),
    )


def _join(base: str, path: str) -> str:
    if not base.endswith("/"):
        base += "/"
    return urljoin(base, path.lstrip("/"))


def _looks_like_login(resp: httpx.Response) -> bool:
    try:
        if "login.php" in str(resp.url):
            return True
    except Exception:
        pass
    text = (resp.text or "").lower()
    if "type=\"password\"" in text and ("login" in text or "登录" in text or "登陆" in text):
        return True
    return False
async def _probe_user_id_from_usercp(
    client: httpx.AsyncClient,
    site_url: str,
    ua: str,
    cookie_header: str,
    adapter: Optional[NexusPhpSiteAdapter] = None,
    *,
    retry_delay_seconds: int,
) -> Optional[str]:
    url = _join(site_url, "usercp.php")
    resp, err, _ = await _get_with_retry(client, url, headers={"User-Agent": ua, "Cookie": cookie_header}, delay_seconds=retry_delay_seconds)
    if err or resp is None:
        return None
    if resp.status_code == 404 or resp.status_code >= 500:
        return None
    if _looks_like_login(resp):
        return None
    raw_html = resp.text or ""
    if adapter:
        uid = adapter.extract_uid(raw_html)
        if uid:
            return uid
    return _extract_user_id_from_html(raw_html)


@dataclass(frozen=True)
class NexusPhpDetector:
    async def check_registration(
        self,
        client: httpx.AsyncClient,
        site: Site,
        user_agent: Optional[str],
        *,
        retry_delay_seconds: int = DEFAULT_REQUEST_RETRY_DELAY_SECONDS,
    ) -> AspectResult:
        ua = user_agent or _UA_DEFAULT
        last_err: Optional[Exception] = None
        last_err_url: Optional[str] = None
        last_err_detail: Optional[str] = None
        last_http_err: Optional[httpx.Response] = None
        last_http_used: int = 1
        last_unknown: Optional[AspectResult] = None
        raw_path = (site.registration_path or "").strip()
        paths = [raw_path] if raw_path else ["signup.php"]
        for path in paths:
            url = _join(site.url, path)
            resp, err, used = await _get_with_retry(client, url, headers={"User-Agent": ua}, delay_seconds=retry_delay_seconds)
            if err:
                last_err = err
                last_err_url = url
                last_err_detail = _append_retry_detail(format_error_detail(err, max_len=_MAX_ERROR_DETAIL_LEN), used)
                continue
            assert resp is not None
            if resp.status_code == 404:
                continue
            if resp.status_code >= 500:
                last_http_err = resp
                last_http_used = used
                continue

            text = _extract_text(resp.text or "")
            closed_pat = _is_registration_closed(text)
            if closed_pat:
                return AspectResult(
                    state="closed",
                    evidence=Evidence(url=str(resp.url), http_status=resp.status_code, reason="registration_closed", matched=closed_pat),
                )

            if not _has_signup_form(resp.text or ""):
                return AspectResult(
                    state="closed",
                    evidence=Evidence(url=str(resp.url), http_status=resp.status_code, reason="signup_form_missing"),
                )

            if _has_invite_field(resp.text or ""):
                return AspectResult(
                    state="closed",
                    evidence=Evidence(url=str(resp.url), http_status=resp.status_code, reason="invite_required"),
                )

            return AspectResult(
                state="open",
                evidence=Evidence(url=str(resp.url), http_status=resp.status_code, reason="signup_form_detected"),
            )

        if last_unknown is not None:
            return last_unknown

        if last_err is not None:
            return AspectResult(
                state="unknown",
                evidence=Evidence(
                    url=last_err_url or _join(site.url, "signup.php"),
                    http_status=None,
                    reason=f"registration_error:{type(last_err).__name__}",
                    detail=last_err_detail,
                ),
            )

        if last_http_err is not None:
            return AspectResult(
                state="unknown",
                evidence=Evidence(
                    url=str(last_http_err.url),
                    http_status=last_http_err.status_code,
                    reason=f"registration_error:HTTP{last_http_err.status_code}",
                    detail=_append_retry_detail(None, last_http_used),
                ),
            )

        return AspectResult(
            state="unknown",
            evidence=Evidence(url=_join(site.url, "signup.php"), http_status=404, reason="signup_page_not_found"),
        )

    async def check_invites(
        self,
        client: httpx.AsyncClient,
        site: Site,
        user_agent: Optional[str],
        cookie_header: Optional[str],
        *,
        retry_delay_seconds: int = DEFAULT_REQUEST_RETRY_DELAY_SECONDS,
    ) -> AspectResult:
        ua = user_agent or _UA_DEFAULT
        if not cookie_header:
            return AspectResult(
                state="unknown",
                evidence=Evidence(url=_join(site.url, "invite.php"), http_status=None, reason="missing_cookie"),
            )

        adapter = get_nexusphp_site_adapter(site)

        # Many NexusPHP sites expose the invite quota in the top nav on homepage:
        # "邀请[发送]: 12(0)" (M-Team may show Traditional).
        home_resp, err, used = await _get_with_retry(
            client,
            site.url,
            headers={"User-Agent": ua, "Cookie": cookie_header},
            delay_seconds=retry_delay_seconds,
        )
        if err:
            return AspectResult(
                state="unknown",
                evidence=Evidence(
                    url=site.url,
                    http_status=None,
                    reason=f"invites_error:{type(err).__name__}",
                    detail=_append_retry_detail(format_error_detail(err, max_len=_MAX_ERROR_DETAIL_LEN), used),
                ),
            )
        assert home_resp is not None
        if home_resp.status_code >= 500:
            return AspectResult(
                state="unknown",
                evidence=Evidence(
                    url=str(home_resp.url),
                    http_status=home_resp.status_code,
                    reason=f"invites_error:HTTP{home_resp.status_code}",
                    detail=_append_retry_detail(None, used),
                ),
            )
        if _looks_like_login(home_resp):
            return AspectResult(
                state="unknown",
                evidence=Evidence(url=str(home_resp.url), http_status=home_resp.status_code, reason="not_logged_in"),
            )

        home_text = _extract_text(home_resp.text or "")
        uid_source: Optional[str] = None
        user_id = await _probe_user_id_from_usercp(
            client,
            site.url,
            ua,
            cookie_header,
            adapter,
            retry_delay_seconds=retry_delay_seconds,
        )
        if user_id:
            uid_source = "usercp"
        if not user_id and adapter:
            user_id = adapter.extract_uid(home_resp.text or "") or None
            if user_id:
                uid_source = "home"
        if not user_id:
            user_id, uid_source = _extract_user_id_and_source(home_resp.text)
        uid_detail = f"uid_source={uid_source}" if uid_source else None
        quota_perm, quota_temp, quota_matched = _parse_home_invite_quota(home_text)
        quota_total: Optional[int] = None
        if quota_perm is not None:
            quota_total = quota_perm + (quota_temp or 0)
            if quota_perm == 0 and (quota_temp or 0) == 0 and quota_matched:
                evidence_url = _join(site.url, f"invite.php?id={user_id}") if user_id else str(home_resp.url)
                return AspectResult(
                    state="closed",
                    available=0,
                    permanent=quota_perm,
                    temporary=quota_temp or 0,
                    evidence=Evidence(
                        url=evidence_url,
                        http_status=home_resp.status_code,
                        reason="invite_quota_home_zero",
                        matched=quota_matched,
                        detail=uid_detail,
                    ),
                )
        invite_url = _extract_invite_url_from_html(home_resp.text or "", site.url, join=_join)
        invite_url_with_id = _join(site.url, f"invite.php?id={user_id}") if user_id else None
        if invite_url and user_id:
            raw = invite_url.lower()
            if "invite.php" in raw and "id=" not in raw:
                invite_url = invite_url_with_id
        elif not invite_url and invite_url_with_id:
            invite_url = invite_url_with_id

        # Some sites use /invite without .php (e.g. M-Team); keep a small fallback list.
        preferred_invite = (site.invite_path or "").strip()
        preferred_invite_url = _join(site.url, preferred_invite) if preferred_invite else None
        if preferred_invite_url and invite_url_with_id:
            raw = preferred_invite_url.lower()
            if "invite.php" in raw and "id=" not in raw:
                preferred_invite_url = invite_url_with_id

        seen: set[str] = set()
        invite_candidates: list[str] = []
        for u in [preferred_invite_url, invite_url_with_id, invite_url, _join(site.url, "invite.php"), _join(site.url, "invite")]:
            if not u:
                continue
            key = str(u).strip()
            if not key or key in seen:
                continue
            seen.add(key)
            invite_candidates.append(key)
        invite_resp: Optional[httpx.Response] = None
        last_err: Optional[Exception] = None
        last_err_url: Optional[str] = None
        last_err_detail: Optional[str] = None
        last_http_err: Optional[httpx.Response] = None
        last_http_used: int = 1
        for u in invite_candidates:
            r, fetch_err, fetch_used = await _get_with_retry(
                client,
                u,
                headers={"User-Agent": ua, "Cookie": cookie_header},
                delay_seconds=retry_delay_seconds,
            )
            if fetch_err:
                last_err = fetch_err
                last_err_url = u
                last_err_detail = _append_retry_detail(format_error_detail(fetch_err, max_len=_MAX_ERROR_DETAIL_LEN), fetch_used)
                continue
            assert r is not None
            if r.status_code == 404:
                continue
            if r.status_code >= 500:
                last_http_err = r
                last_http_used = fetch_used
                continue
            invite_resp = r
            break

        if not invite_resp:
            if last_err is not None:
                return AspectResult(
                    state="unknown",
                    evidence=Evidence(
                        url=last_err_url or (invite_url or _join(site.url, "invite.php")),
                        http_status=None,
                        reason=f"invites_error:{type(last_err).__name__}",
                        detail=_merge_detail(last_err_detail, uid_detail),
                    ),
                )
            if last_http_err is not None:
                return AspectResult(
                    state="unknown",
                    evidence=Evidence(
                        url=str(last_http_err.url),
                        http_status=last_http_err.status_code,
                        reason=f"invites_error:HTTP{last_http_err.status_code}",
                        detail=_merge_detail(_append_retry_detail(None, last_http_used), uid_detail),
                    ),
                )
            return AspectResult(
                state="unknown",
                evidence=Evidence(
                    url=invite_url or _join(site.url, "invite.php"),
                    http_status=404,
                    reason="invite_page_not_found",
                    detail=_merge_detail(
                        f"quota_perm={quota_perm} quota_temp={quota_temp} quota_total={quota_total}" if quota_total is not None else None,
                        uid_detail,
                    ),
                ),
            )

        if _looks_like_login(invite_resp):
            return AspectResult(
                state="unknown",
                evidence=Evidence(url=str(invite_resp.url), http_status=invite_resp.status_code, reason="not_logged_in"),
            )

        invite_text = _extract_text(invite_resp.text or "")
        disabled_pat = _is_invite_disabled(invite_text)
        if disabled_pat:
            return AspectResult(
                state="closed",
                available=0,
                permanent=quota_perm,
                temporary=quota_temp,
                evidence=Evidence(
                    url=str(invite_resp.url),
                    http_status=invite_resp.status_code,
                    reason="invites_disabled",
                    matched=disabled_pat,
                    detail=_merge_detail(
                        f"quota_perm={quota_perm} quota_temp={quota_temp} quota_total={quota_total}" if quota_total is not None else None,
                        uid_detail,
                    ),
                ),
            )

        count_reason: Optional[str] = None
        count = quota_total
        matched = quota_matched
        if count is None:
            count, matched = _parse_invite_count(invite_text)
            if count is None:
                quota_insufficient = _extract_invite_quota_insufficient(invite_text)
                if quota_insufficient:
                    count = 0
                    matched = quota_insufficient
                    count_reason = "invite_quota_insufficient"

        action_status, action_matched = _invite_send_action_status(invite_resp.text)
        if action_status is False:
            return AspectResult(
                state="closed",
                available=0,
                permanent=quota_perm if quota_perm is not None else count,
                temporary=quota_temp if quota_perm is not None else 0,
                evidence=Evidence(
                    url=str(invite_resp.url),
                    http_status=invite_resp.status_code,
                    reason="invite_permission_denied",
                    matched=action_matched,
                    detail=_merge_detail(f"quota_total={count}" if count is not None else None, uid_detail),
                ),
            )

        permission_reason: Optional[str] = None
        if adapter:
            try:
                permission_reason = adapter.invite_permission_reason(invite_text, invite_resp.text or "")
            except Exception:
                permission_reason = None
        permission_reason = permission_reason or _extract_invite_permission_reason(invite_text)
        denied_pat = _invite_permission_denied_any(invite_text, invite_resp.text)
        if denied_pat or permission_reason:
            detail = _truncate_detail(permission_reason) if permission_reason else None
            if not detail and count is not None:
                detail = f"quota_total={count}"
            return AspectResult(
                state="closed",
                available=0,
                permanent=quota_perm if quota_perm is not None else count,
                temporary=quota_temp if quota_perm is not None else 0,
                evidence=Evidence(
                    url=str(invite_resp.url),
                    http_status=invite_resp.status_code,
                    reason="invite_permission_denied",
                    matched=denied_pat,
                    detail=_merge_detail(detail, uid_detail),
                ),
            )

        if count is None:
            return AspectResult(
                state="unknown",
                evidence=Evidence(
                    url=str(invite_resp.url),
                    http_status=invite_resp.status_code,
                    reason="invite_count_not_found",
                    detail=uid_detail,
                ),
            )

        if action_status is None and count > 0:
            # Some sites hide/disable the send-invite action without a clear text marker.
            # For "open invites", we require that a send/create invite action is visible.
            return AspectResult(
                state="closed",
                available=0,
                permanent=quota_perm if quota_perm is not None else count,
                temporary=quota_temp if quota_perm is not None else 0,
                evidence=Evidence(
                    url=str(invite_resp.url),
                    http_status=invite_resp.status_code,
                    reason="invite_action_not_found",
                    detail=_merge_detail(f"quota_total={count}", uid_detail),
                ),
            )

        return AspectResult(
            state="open" if count > 0 else "closed",
            available=count,
            permanent=quota_perm if quota_perm is not None else count,
            temporary=quota_temp if quota_perm is not None else 0,
            evidence=Evidence(
                url=str(invite_resp.url),
                http_status=invite_resp.status_code,
                reason=count_reason or ("invite_count_parsed" if quota_total is None else "invite_quota_home_header"),
                matched=action_matched or matched,
                detail=uid_detail,
            ),
        )
