from __future__ import annotations

import asyncio
import html as html_lib
import logging
import re
from dataclasses import dataclass
from typing import Any, Optional
from urllib.parse import urljoin

import httpx
from bs4 import BeautifulSoup

from pt_invite_watcher.models import AspectResult, Evidence, Site


logger = logging.getLogger("pt_invite_watcher.nexusphp")

_UA_DEFAULT = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
_HTTP_RETRY_ATTEMPTS = 3
_MAX_ERROR_DETAIL_LEN = 240
_MAX_SIGNUP_SNIPPET_LEN = 160


def _format_error_detail(exc: Exception) -> str:
    msg = str(exc or "").strip() or type(exc).__name__
    msg = re.sub(r"\s+", " ", msg)
    if len(msg) > _MAX_ERROR_DETAIL_LEN:
        msg = msg[: _MAX_ERROR_DETAIL_LEN - 1] + "…"
    return msg


def _truncate_detail(text: str, limit: int = _MAX_ERROR_DETAIL_LEN) -> str:
    s = _normalize_text(text)
    if len(s) > limit:
        return s[: limit - 1] + "…"
    return s


def _extract_html_title(raw_html: str) -> str:
    m = re.search(r"<title[^>]*>(.*?)</title>", raw_html or "", flags=re.I | re.S)
    if not m:
        return ""
    title = html_lib.unescape(m.group(1) or "")
    return _normalize_text(title)


def _append_retry_detail(detail: Optional[str], attempts: int) -> Optional[str]:
    if attempts <= 1:
        return detail
    suffix = f"retries={attempts}"
    if not detail:
        return suffix
    if suffix in detail:
        return detail
    return f"{detail} ({suffix})"


async def _get_with_retry(
    client: httpx.AsyncClient, url: str, headers: dict[str, str], attempts: int = _HTTP_RETRY_ATTEMPTS
) -> tuple[Optional[httpx.Response], Optional[Exception], int]:
    last_exc: Optional[Exception] = None
    last_resp: Optional[httpx.Response] = None
    for attempt in range(max(1, attempts)):
        try:
            resp = await client.get(url, headers=headers)
            last_resp = resp
            if resp.status_code >= 500 and attempt < attempts - 1:
                await asyncio.sleep(0.3 * (attempt + 1))
                continue
            return resp, None, attempt + 1
        except httpx.RequestError as e:
            last_exc = e
            if attempt < attempts - 1:
                await asyncio.sleep(0.3 * (attempt + 1))
                continue
            return None, e, attempt + 1
    return last_resp, last_exc, attempts


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


def _normalize_text(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").strip())


def _extract_text(resp: httpx.Response) -> str:
    try:
        soup = BeautifulSoup(resp.text or "", "html.parser")
        return _normalize_text(soup.get_text(" ", strip=True))
    except Exception:
        return _normalize_text(resp.text or "")


def _has_invite_field(resp: httpx.Response) -> bool:
    try:
        soup = BeautifulSoup(resp.text or "", "html.parser")
        for inp in soup.find_all("input"):
            name = (inp.get("name") or "").lower()
            if "invite" in name:
                return True
        text = soup.get_text(" ", strip=True)
        return "邀请码" in text or "邀請碼" in text or "invitation" in text.lower()
    except Exception:
        return False


def _has_signup_form(resp: httpx.Response) -> bool:
    try:
        soup = BeautifulSoup(resp.text or "", "html.parser")
        return soup.find("form") is not None
    except Exception:
        return False


def _is_registration_closed(text: str) -> Optional[str]:
    patterns = [
        r"registration\s+closed",
        r"signups?\s+(are\s+)?closed",
        r"signup\s+closed",
        r"closed\s+registration",
        r"invite\s+only",
        r"invitation\s+only",
        r"注册(已经)?关闭",
        r"暂停注册",
        r"停止注册",
        r"当前不开放注册",
        r"自由注册.{0,10}关闭",
        r"(?:自由|开放)注册.{0,10}打烊",
        r"(?:只|仅)(?:允许|接受).{0,10}邀请注册",
    ]
    for pat in patterns:
        if re.search(pat, text, flags=re.I):
            return pat
    return None


def _parse_invite_count(text: str) -> tuple[Optional[int], Optional[str]]:
    patterns = [
        r"you\s+have\s+(\d{1,4})\s+invites?",
        r"available\s+invites?\s*[:：]\s*(\d{1,4})",
        r"invites?\s*available\s*[:：]\s*(\d{1,4})",
        r"invites?\s*(?:left|remaining)\s*[:：]?\s*(\d{1,4})",
        r"可用(?:邀请|邀請)\s*[:：]?\s*(\d{1,4})",
        r"(?:剩余|剩餘)(?:邀请|邀請)\s*[:：]?\s*(\d{1,4})",
        r"(?:你|您)\s*(?:还|還)?\s*有\s*(\d{1,4})\s*(?:个)?\s*(?:邀请|邀請)",
    ]
    for pat in patterns:
        m = re.search(pat, text, flags=re.I)
        if not m:
            continue
        try:
            return int(m.group(1)), m.group(0)
        except Exception:
            continue
    return None, None


def _is_invite_disabled(text: str) -> Optional[str]:
    patterns = [
        r"invites?\s+(are\s+)?disabled",
        r"inviting\s+is\s+disabled",
        r"you\s+are\s+not\s+allowed\s+to\s+invite",
        r"邀请功能(已经)?关闭",
        r"禁止邀请",
        r"无邀请权限",
    ]
    for pat in patterns:
        if re.search(pat, text, flags=re.I):
            return pat
    return None


def _parse_home_invite_quota(text: str) -> tuple[Optional[int], Optional[int], Optional[str]]:
    patterns = [
        r"(?:邀请|邀請)\s*\[\s*(?:发送|發送)\s*\]\s*[:：]?\s*(\d{1,4})\s*(?:\(\s*(\d{1,4})\s*\))?",
    ]
    for pat in patterns:
        m = re.search(pat, text, flags=re.I)
        if not m:
            continue
        try:
            permanent = int(m.group(1))
            temporary = int(m.group(2)) if m.group(2) else 0
            return permanent, temporary, m.group(0)
        except Exception:
            continue
    return None, None, None


def _extract_user_id_from_html(html: str) -> Optional[str]:
    m = re.search(r"userdetails\.php\?id=(\d{1,10})", html or "", flags=re.I)
    return m.group(1) if m else None


def _extract_invite_url_from_html(html: str, base_url: str) -> Optional[str]:
    try:
        soup = BeautifulSoup(html or "", "html.parser")
        candidates: list[tuple[int, str]] = []
        for a in soup.find_all("a"):
            href = (a.get("href") or "").strip()
            if not href or href.startswith("#") or href.lower().startswith("javascript:"):
                continue
            text = _normalize_text(a.get_text(" ", strip=True))
            score = 0
            if "invite" in href.lower():
                score += 2
            if "邀请" in text or "邀請" in text:
                score += 2
            if "发送" in text or "發送" in text:
                score += 1
            if score <= 0:
                continue
            candidates.append((score, href))

        if not candidates:
            return None

        candidates.sort(key=lambda x: x[0], reverse=True)
        return _join(base_url, candidates[0][1])
    except Exception:
        return None


def _invite_permission_denied(text: str) -> Optional[str]:
    patterns = [
        r"(?:或以上|及以上).{0,80}(?:才可(?:以)?|才能).{0,20}(?:发送|發送).{0,10}(?:邀请|邀請)",
        r"(?:你|您).{0,30}(?:没有|無).{0,30}(?:邀请|邀請).{0,20}(?:权限|權限)",
        r"(?:not\s+allowed\s+to\s+invite|invites?\s+are\s+disabled)",
    ]
    for pat in patterns:
        if re.search(pat, text, flags=re.I):
            return pat
    return None


def _invite_permission_denied_any(text: str, raw_html: str) -> Optional[str]:
    return _invite_permission_denied(text) or _invite_permission_denied(raw_html or "")


def _extract_action_label(tag: Any) -> str:
    try:
        if getattr(tag, "name", None) == "input":
            return _normalize_text(tag.get("value") or "")
        return _normalize_text(tag.get_text(" ", strip=True))
    except Exception:
        return ""


def _invite_send_action_status(raw_html: str) -> tuple[Optional[bool], Optional[str]]:
    """
    Returns (status, matched):
    - status=True: invite "send/create" action exists and is enabled
    - status=False: invite send/create action exists but is disabled (permission denied)
    - status=None: cannot determine from html
    """
    try:
        soup = BeautifulSoup(raw_html or "", "html.parser")
    except Exception:
        return None, None

    # First: NexusPHP usually exposes "create invite" as a POST form with action "...type=new"
    # and a submit input/button. If it's disabled, current user has no permission.
    for form in soup.find_all("form"):
        action = (form.get("action") or "").lower()
        if "type=new" not in action and "takeinvite.php" not in action:
            continue
        for ctl in form.find_all(["input", "button"]):
            if ctl.name == "input":
                itype = (ctl.get("type") or "").lower()
                if itype and itype not in {"submit", "button"}:
                    continue
            label = _extract_action_label(ctl) or action
            if ctl.has_attr("disabled"):
                return False, label
            return True, label

    # Second: some sites might expose a link to "type=new" instead of a form.
    for a in soup.find_all("a"):
        href = (a.get("href") or "").lower()
        if "type=new" in href or "takeinvite.php" in href:
            label = _normalize_text(a.get_text(" ", strip=True)) or href
            return True, label

    # Fallback: look for explicit "invite others" action text.
    body_text = _normalize_text(soup.get_text(" ", strip=True))
    if any(token in body_text for token in ("邀请其他人", "邀請其他人", "邀请他人", "邀請他人")):
        return True, "邀请其他人"

    # Fallback: disabled control with a permission hint in value/text (e.g. Power User...).
    for ctl in soup.find_all(["input", "button"]):
        if not ctl.has_attr("disabled"):
            continue
        label = _extract_action_label(ctl)
        if not label:
            continue
        if re.search(r"(?:发送|發送).{0,5}(?:邀请|邀請)|send\\s+invite", label, flags=re.I):
            return False, label

    return None, None


@dataclass(frozen=True)
class NexusPhpDetector:
    async def check_registration(self, client: httpx.AsyncClient, site: Site, user_agent: Optional[str]) -> AspectResult:
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
            resp, err, used = await _get_with_retry(client, url, headers={"User-Agent": ua})
            if err:
                last_err = err
                last_err_url = url
                last_err_detail = _append_retry_detail(_format_error_detail(err), used)
                continue
            assert resp is not None
            if resp.status_code == 404:
                continue
            if resp.status_code >= 500:
                last_http_err = resp
                last_http_used = used
                continue

            text = _extract_text(resp)
            closed_pat = _is_registration_closed(text)
            if closed_pat:
                return AspectResult(
                    state="closed",
                    evidence=Evidence(url=str(resp.url), http_status=resp.status_code, reason="registration_closed", matched=closed_pat),
                )

            if not _has_signup_form(resp):
                return AspectResult(
                    state="closed",
                    evidence=Evidence(url=str(resp.url), http_status=resp.status_code, reason="signup_form_missing"),
                )

            if _has_invite_field(resp):
                return AspectResult(
                    state="closed",
                    evidence=Evidence(url=str(resp.url), http_status=resp.status_code, reason="invite_required"),
                )

            return AspectResult(
                state="open",
                evidence=Evidence(url=str(resp.url), http_status=resp.status_code, reason="signup_form_detected"),
            )

            title = _extract_html_title(resp.text or "")
            snippet = text[:_MAX_SIGNUP_SNIPPET_LEN]
            debug = _truncate_detail(f"title={title or '-'}; snippet={snippet or '-'}")
            logger.info("signup unknown: %s %s HTTP %s %s", site.domain, resp.url, resp.status_code, debug)
            last_unknown = AspectResult(
                state="unknown",
                evidence=Evidence(url=str(resp.url), http_status=resp.status_code, reason="unable_to_determine", detail=debug),
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
    ) -> AspectResult:
        ua = user_agent or _UA_DEFAULT
        if not cookie_header:
            return AspectResult(
                state="unknown",
                evidence=Evidence(url=_join(site.url, "invite.php"), http_status=None, reason="missing_cookie"),
            )

        # Many NexusPHP sites expose the invite quota in the top nav on homepage:
        # "邀请[发送]: 12(0)" (M-Team may show Traditional).
        home_resp, err, used = await _get_with_retry(client, site.url, headers={"User-Agent": ua, "Cookie": cookie_header})
        if err:
            return AspectResult(
                state="unknown",
                evidence=Evidence(
                    url=site.url,
                    http_status=None,
                    reason=f"invites_error:{type(err).__name__}",
                    detail=_append_retry_detail(_format_error_detail(err), used),
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

        home_text = _extract_text(home_resp)
        quota_perm, quota_temp, quota_matched = _parse_home_invite_quota(home_text)
        quota_total: Optional[int] = None
        if quota_perm is not None:
            quota_total = quota_perm + (quota_temp or 0)
            if quota_perm == 0 and (quota_temp or 0) == 0 and quota_matched:
                user_id = _extract_user_id_from_html(home_resp.text)
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
                    ),
                )
        invite_url = _extract_invite_url_from_html(home_resp.text, site.url)
        if not invite_url:
            user_id = _extract_user_id_from_html(home_resp.text)
            if user_id:
                invite_url = _join(site.url, f"invite.php?id={user_id}")

        # Some sites use /invite without .php (e.g. M-Team); keep a small fallback list.
        preferred_invite = (site.invite_path or "").strip()
        preferred_invite_url = _join(site.url, preferred_invite) if preferred_invite else None
        invite_candidates = [u for u in [preferred_invite_url, invite_url, _join(site.url, "invite.php"), _join(site.url, "invite")] if u]
        invite_resp: Optional[httpx.Response] = None
        last_err: Optional[Exception] = None
        last_err_url: Optional[str] = None
        last_err_detail: Optional[str] = None
        last_http_err: Optional[httpx.Response] = None
        last_http_used: int = 1
        for u in invite_candidates:
            r, fetch_err, fetch_used = await _get_with_retry(client, u, headers={"User-Agent": ua, "Cookie": cookie_header})
            if fetch_err:
                last_err = fetch_err
                last_err_url = u
                last_err_detail = _append_retry_detail(_format_error_detail(fetch_err), fetch_used)
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
                        detail=last_err_detail,
                    ),
                )
            if last_http_err is not None:
                return AspectResult(
                    state="unknown",
                    evidence=Evidence(
                        url=str(last_http_err.url),
                        http_status=last_http_err.status_code,
                        reason=f"invites_error:HTTP{last_http_err.status_code}",
                        detail=_append_retry_detail(None, last_http_used),
                    ),
                )
            return AspectResult(
                state="unknown",
                evidence=Evidence(
                    url=invite_url or _join(site.url, "invite.php"),
                    http_status=404,
                    reason="invite_page_not_found",
                    detail=f"quota_perm={quota_perm} quota_temp={quota_temp} quota_total={quota_total}" if quota_total is not None else None,
                ),
            )

        if _looks_like_login(invite_resp):
            return AspectResult(
                state="unknown",
                evidence=Evidence(url=str(invite_resp.url), http_status=invite_resp.status_code, reason="not_logged_in"),
            )

        invite_text = _extract_text(invite_resp)
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
                    detail=f"quota_perm={quota_perm} quota_temp={quota_temp} quota_total={quota_total}" if quota_total is not None else None,
                ),
            )

        count = quota_total
        matched = quota_matched
        if count is None:
            count, matched = _parse_invite_count(invite_text)

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
                    detail=f"quota_total={count}" if count is not None else None,
                ),
            )

        denied_pat = _invite_permission_denied_any(invite_text, invite_resp.text)
        if denied_pat:
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
                    detail=f"quota_total={count}" if count is not None else None,
                ),
            )

        if count is None:
            return AspectResult(
                state="unknown",
                evidence=Evidence(
                    url=str(invite_resp.url),
                    http_status=invite_resp.status_code,
                    reason="invite_count_not_found",
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
                    detail=f"quota_total={count}",
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
                reason="invite_count_parsed" if quota_total is None else "invite_quota_home_header",
                matched=action_matched or matched,
            ),
        )
