from __future__ import annotations

import html as html_lib
import re
from typing import Any, Optional

from bs4 import BeautifulSoup


_MAX_ERROR_DETAIL_LEN = 240
def _normalize_text(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").strip())


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


def _extract_text(resp_text: str) -> str:
    try:
        soup = BeautifulSoup(resp_text or "", "html.parser")
        return _normalize_text(soup.get_text(" ", strip=True))
    except Exception:
        return _normalize_text(resp_text or "")


def _has_invite_field(resp_text: str) -> bool:
    try:
        soup = BeautifulSoup(resp_text or "", "html.parser")
        for inp in soup.find_all("input"):
            name = (inp.get("name") or "").lower()
            if "invite" in name:
                return True
        text = soup.get_text(" ", strip=True)
        return "邀请码" in text or "邀請碼" in text or "invitation" in text.lower()
    except Exception:
        return False


def _has_signup_form(resp_text: str) -> bool:
    try:
        soup = BeautifulSoup(resp_text or "", "html.parser")
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
        r"\[\s*(?:邀请|邀請)\s*\]\s*[:：]?\s*(\d{1,4})\s*(?:\(\s*(\d{1,4})\s*\))?",
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


def _extract_user_id_and_source(html: str) -> tuple[Optional[str], Optional[str]]:
    raw = html or ""
    m = re.search(r"userdetails\.php\?id=(\d{1,10})", raw, flags=re.I)
    if m:
        return m.group(1), "userdetail"
    m = re.search(r"\bUID\s*=\s*(\d{1,10})\b", raw, flags=re.I)
    if m:
        return m.group(1), "home"
    m = re.search(r"\buser(?:id|_id)\s*=\s*(\d{1,10})\b", raw, flags=re.I)
    if m:
        return m.group(1), "home"
    m = re.search(r"\buid\s*=\s*(\d{1,10})\b", raw, flags=re.I)
    if m:
        return m.group(1), "home"
    return None, None


def _extract_user_id_from_html(html: str) -> Optional[str]:
    uid, _ = _extract_user_id_and_source(html)
    return uid


def _extract_invite_url_from_html(html: str, base_url: str, *, join: Any) -> Optional[str]:
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
        return join(base_url, candidates[0][1])
    except Exception:
        return None


def _invite_permission_denied(text: str) -> Optional[str]:
    patterns = [
        r"对不起[,，]?\s*.+?(?:这里|返回)",
        r"(?:或以上|及以上).{0,80}(?:才可(?:以)?|才能).{0,20}(?:发送|發送).{0,10}(?:邀请|邀請)",
        r"只有.{0,80}(?:才可(?:以)?|才能).{0,20}(?:发送|發送).{0,10}(?:邀请|邀請)",
        r"(?:贵宾|VIP).{0,40}(?:或以上|及以上).{0,80}(?:才可(?:以)?|才能).{0,20}(?:发送|發送).{0,10}(?:邀请|邀請)",
        r"(?:当前)?账户上限|上限数已到|已达到最大邀请数|已达上限|达到上限|当前邀请注册人数已达上限",
        r"(?:你|您).{0,30}(?:没有|無).{0,30}(?:邀请|邀請).{0,20}(?:权限|權限)",
        r"(?:not\s+allowed\s+to\s+invite|invites?\s+are\s+disabled)",
    ]
    for pat in patterns:
        if re.search(pat, text, flags=re.I):
            return pat
    return None


def _invite_permission_denied_any(text: str, raw_html: str) -> Optional[str]:
    return _invite_permission_denied(text) or _invite_permission_denied(raw_html or "")


def _clean_invite_reason(text: str) -> str:
    s = _normalize_text(text or "")
    if not s:
        return ""
    s = re.sub(r"\s*这里.*返回。?$", "", s)
    s = re.sub(r"\s*这里.*$", "", s)
    return s.strip(" ,，。;；")


def _extract_invite_permission_reason(text: str) -> Optional[str]:
    """
    Extract a human-readable "permission denied" reason from the invite page text.
    This is best-effort and should stay short for Evidence.detail.
    """
    t = _normalize_text(text or "")
    if not t:
        return None

    if "对不起" in t:
        m = re.search(r"对不起[,，]?\s*(.*)", t)
        reason = _clean_invite_reason(m.group(1) if m else t)
        return reason or "对不起"
    if "sorry" in t.lower():
        m = re.search(r"sorry[,\\s]*([^\\n\\r]+)", t, flags=re.I)
        reason = _clean_invite_reason(m.group(1) if m else t)
        return reason or "Sorry"

    patterns = [
        r"只有.{0,120}(?:才可(?:以)?|才能).{0,30}(?:发送|發送).{0,20}(?:邀请|邀請)",
        r"(?:或以上|及以上).{0,120}(?:才可(?:以)?|才能).{0,30}(?:发送|發送).{0,20}(?:邀请|邀請)",
        r"(?:贵宾|VIP).{0,120}(?:才可(?:以)?|才能).{0,30}(?:发送|發送).{0,20}(?:邀请|邀請)",
        r"(?:当前)?账户上限.*",
        r"(?:上限数已到|已达到最大邀请数|已达上限|达到上限|当前邀请注册人数已达上限)",
        r"(?:你|您).{0,60}(?:没有|無).{0,60}(?:邀请|邀請).{0,20}(?:权限|權限)",
    ]
    for pat in patterns:
        m = re.search(pat, t, flags=re.I)
        if not m:
            continue
        reason = _clean_invite_reason(m.group(0))
        if reason:
            return reason
    return None


def _extract_invite_quota_insufficient(text: str) -> Optional[str]:
    t = _normalize_text(text or "")
    if not t:
        return None
    patterns = [
        r"邀请数量不足",
        r"邀请名额不足",
        r"没有剩余邀请",
        r"没有足够的邀请",
    ]
    for pat in patterns:
        if re.search(pat, t, flags=re.I):
            return pat
    return None


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


def _append_retry_detail(detail: Optional[str], attempts: int) -> Optional[str]:
    if attempts <= 1:
        return detail
    suffix = f"retries={attempts}"
    if not detail:
        return suffix
    if suffix in detail:
        return detail
    return f"{detail} ({suffix})"


def _merge_detail(a: Optional[str], b: Optional[str]) -> Optional[str]:
    if not b:
        return a
    if not a:
        return b
    if b in a:
        return a
    return f"{a} | {b}"
