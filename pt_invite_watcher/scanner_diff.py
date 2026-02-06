from __future__ import annotations

from typing import Any

from pt_invite_watcher.models import SiteCheckResult


def diff(prev: Any, cur: SiteCheckResult) -> list[str]:
    if prev is None:
        return []

    changes: list[str] = []

    prev_reach = str(getattr(prev, "reachability_state", "unknown") or "unknown")
    cur_reach = cur.reachability.state
    if prev_reach in {"up", "down", "unknown"} and cur_reach in {"up", "down"} and prev_reach != cur_reach:
        from_label = "正常" if prev_reach == "up" else ("异常" if prev_reach == "down" else "unknown")
        to_label = "正常" if cur_reach == "up" else "异常"
        ev = cur.reachability.evidence
        ev_label = ""
        if ev.http_status is not None:
            ev_label = f"HTTP {ev.http_status}"
        else:
            reason = str(ev.reason or "")
            if reason.startswith("probe_error:"):
                ev_label = reason.split(":", 1)[1]
            elif reason.startswith("probe_http_"):
                ev_label = f"HTTP {reason.split('_', 2)[2]}"
            else:
                ev_label = reason
        changes.append(f"可访问：{from_label} -> {to_label}" + (f" ({ev_label})" if ev_label else ""))

    if cur.registration.state == "open" and prev.registration_state != "open":
        changes.append("开放注册：open")
    elif cur.registration.state == "closed" and prev.registration_state == "open":
        changes.append("开放注册：closed")
    elif cur.registration.state == "closed" and prev.registration_state == "unknown":
        changes.append("开放注册：unknown -> closed")

    prev_inv_state = str(getattr(prev, "invites_state", "unknown") or "unknown")
    cur_inv_state = str(cur.invites.state or "unknown")
    if prev_inv_state == "unknown" and cur_inv_state == "closed":
        changes.append("可用邀请：unknown -> closed")

    if cur.invites.available is not None:
        prev_count = prev.invites_available
        cur_count = cur.invites.available
        if cur_count > 0 and (prev_count is None or prev_count <= 0):
            changes.append(f"可用邀请数：{prev_count or 0} -> {cur_count}")
        elif cur_count <= 0 and (prev_count is not None and prev_count > 0):
            changes.append(f"可用邀请数：{prev_count} -> {cur_count}")

    return changes


__all__ = ["diff"]

