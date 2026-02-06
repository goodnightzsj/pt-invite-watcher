from __future__ import annotations

import json
from typing import Any

from pt_invite_watcher.utils.parse import safe_dict


def _safe_json_obj(value: Any) -> dict[str, Any]:
    try:
        if value is None or value == "":
            return {}
        obj = json.loads(value)
        return obj if isinstance(obj, dict) else {}
    except Exception:
        return {}


def derive_state_view(row: dict[str, Any]) -> dict[str, Any]:
    errors: list[str] = []
    reachability_state = "unknown"
    reachability_note = ""
    registration_note = ""
    invites_display = ""

    try:
        payload = _safe_json_obj(row.get("last_evidence"))
        reach = safe_dict(payload.get("reachability"))
        reach_ev = safe_dict(reach.get("evidence"))

        reachability_state = str(reach.get("state") or "unknown")
        reach_status = reach_ev.get("http_status")
        reach_reason = str(reach_ev.get("reason") or "")
        reach_detail = str(reach_ev.get("detail") or "").strip()
        if reachability_state == "down":
            if reach_detail:
                reachability_note = reach_detail
            elif reach_status is not None:
                reachability_note = f"HTTP {reach_status}"
            else:
                reachability_note = reach_reason or "down"
            errors.append(f"站点不可访问：{reachability_note}")
        elif reach_status is not None:
            try:
                status_value = int(reach_status)
            except Exception:
                status_value = None
            reachability_note = "" if status_value == 200 else f"HTTP {reach_status}"

        reg_ev = safe_dict(safe_dict(payload.get("registration")).get("evidence"))
        inv_ev = safe_dict(safe_dict(payload.get("invites")).get("evidence"))
        inv_payload = safe_dict(payload.get("invites"))

        reg_reason = str(reg_ev.get("reason") or "")
        inv_reason = str(inv_ev.get("reason") or "")
        reg_detail = str(reg_ev.get("detail") or reg_ev.get("matched") or "").strip()
        inv_detail = str(inv_ev.get("detail") or inv_ev.get("matched") or "").strip()

        reg_status = reg_ev.get("http_status")
        if row.get("registration_state") == "unknown":
            if reg_detail:
                registration_note = reg_detail
            elif reg_status is not None and reg_reason:
                registration_note = f"HTTP {reg_status} {reg_reason}"
            elif reg_status is not None:
                registration_note = f"HTTP {reg_status}"
            else:
                registration_note = reg_reason

        if row.get("invites_state") == "open":
            inv_perm = inv_payload.get("permanent")
            inv_temp = inv_payload.get("temporary")
            if inv_perm is not None:
                invites_display = f"{int(inv_perm)}({int(inv_temp or 0)})"
            elif row.get("invites_available") is not None:
                invites_display = f"{int(row['invites_available'])}(0)"

        if reg_reason.startswith("registration_error:"):
            err_type = reg_reason.split(":", 1)[1] or "Error"
            errors.append(f"注册：{err_type} · {reg_detail or 'no details'}")
        if inv_reason.startswith("invites_error:"):
            err_type = inv_reason.split(":", 1)[1] or "Error"
            errors.append(f"邀请：{err_type} · {inv_detail or 'no details'}")
    except Exception:
        reachability_state = "unknown"
        reachability_note = ""
        registration_note = ""
        invites_display = ""
        errors = ["解析异常信息失败：请查看日志"]

    return {
        "reachability_state": reachability_state,
        "reachability_note": reachability_note,
        "registration_note": registration_note,
        "invites_display": invites_display,
        "errors": errors,
    }


__all__ = ["derive_state_view"]

