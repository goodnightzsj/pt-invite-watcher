from __future__ import annotations

from typing import Any

from pt_invite_watcher.models import Site, SiteCheckResult
from pt_invite_watcher.utils.url import page_kind_from_url


def build_state_changed_event_detail(site: Site, result: SiteCheckResult, changes: list[str]) -> dict[str, Any]:
    reach_ev = result.reachability.evidence
    reg_ev = result.registration.evidence
    inv_ev = result.invites.evidence
    reach_page = page_kind_from_url(reach_ev.url) or "other"
    reg_page = page_kind_from_url(reg_ev.url) or "other"
    inv_page = page_kind_from_url(inv_ev.url) or "other"

    primary_kind = inv_page
    primary_url = inv_ev.url
    if not any("邀请" in c for c in changes):
        primary_kind = reg_page
        primary_url = reg_ev.url
    if not any(("邀请" in c or "注册" in c) for c in changes):
        primary_kind = reach_page
        primary_url = reach_ev.url

    return {
        "changes": list(changes),
        "page": {"kind": primary_kind, "url": primary_url},
        "reachability": {
            "state": result.reachability.state,
            "evidence": {
                "page": reach_page,
                "url": reach_ev.url,
                "http_status": reach_ev.http_status,
                "reason": reach_ev.reason,
                "matched": reach_ev.matched,
                "detail": reach_ev.detail,
            },
        },
        "registration": {
            "state": result.registration.state,
            "evidence": {
                "page": reg_page,
                "url": reg_ev.url,
                "http_status": reg_ev.http_status,
                "reason": reg_ev.reason,
                "matched": reg_ev.matched,
                "detail": reg_ev.detail,
            },
        },
        "invites": {
            "state": result.invites.state,
            "available": result.invites.available,
            "permanent": result.invites.permanent,
            "temporary": result.invites.temporary,
            "evidence": {
                "page": inv_page,
                "url": inv_ev.url,
                "http_status": inv_ev.http_status,
                "reason": inv_ev.reason,
                "matched": inv_ev.matched,
                "detail": inv_ev.detail,
            },
        },
    }


def build_state_changed_notification(site: Site, result: SiteCheckResult, changes: list[str]) -> tuple[str, str]:
    invite_display = "-"
    if result.invites.permanent is not None:
        invite_display = f"{int(result.invites.permanent)}({int(result.invites.temporary or 0)})"
    elif result.invites.available is not None:
        invite_display = str(int(result.invites.available))

    title = "PT Invite Watcher: 状态变化"
    text = "\n".join(
        [
            f"站点：{site.name} ({site.domain})",
            f"URL：{site.url}",
            *changes,
            f"注册：{result.registration.state} ({result.registration.evidence.reason})",
            f"邀请：{result.invites.state} {invite_display}",
        ]
    )
    return title, text


__all__ = ["build_state_changed_event_detail", "build_state_changed_notification"]

