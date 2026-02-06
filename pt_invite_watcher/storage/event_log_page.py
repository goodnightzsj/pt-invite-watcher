from __future__ import annotations

from typing import Any, Optional

from pt_invite_watcher.utils.url import page_kind_from_url


def infer_page_from_action(action: str, detail: dict[str, Any]) -> Optional[str]:
    act = str(action or "").strip().lower()
    if not act:
        return None

    if act.startswith("inv_"):
        if "home" in act:
            return "home"
        if "usercp" in act:
            return "usercp"
        if "userdetail" in act or "userdetails" in act:
            return "userdetail"
        return "invite"

    if act.startswith("reg_"):
        return "signup"

    src = str(detail.get("source") or "").strip().lower()
    if src in {"home", "usercp", "userdetail", "invite", "signup"}:
        return src

    return None


def extract_url_from_detail(detail: dict[str, Any]) -> str:
    direct = str(detail.get("url") or "").strip()
    if direct:
        return direct
    ev = detail.get("evidence")
    if isinstance(ev, dict):
        u = str(ev.get("url") or "").strip()
        if u:
            return u
    return ""


def enrich_event_page(item: dict[str, Any]) -> None:
    """
    Best-effort: attach a normalized site page kind (home/usercp/signup/userdetail/invite) into event detail.
    This is derived from `detail.url`/`detail.evidence.url`, or inferred from `action`.
    """
    detail = item.get("detail")
    if not isinstance(detail, dict):
        return
    if "page" in detail and isinstance(detail.get("page"), dict):
        return

    url = extract_url_from_detail(detail)
    kind = page_kind_from_url(url) or infer_page_from_action(str(item.get("action") or ""), detail)
    if not kind:
        return

    detail["page"] = {"kind": kind, "url": url} if url else {"kind": kind}


__all__ = ["enrich_event_page", "extract_url_from_detail", "infer_page_from_action"]

