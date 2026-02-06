from __future__ import annotations

from typing import Any


def moviepilot_warning(*, mp_configured: bool, mp_fields: dict[str, Any]) -> str:
    if not mp_configured:
        return ""
    mp_error = str(mp_fields.get("moviepilot_error") or "")
    if not mp_error:
        return ""

    mp_source = str(mp_fields.get("moviepilot_source") or "none")
    mp_cache_age_seconds = mp_fields.get("moviepilot_cache_age_seconds")
    if mp_source in {"cache", "state", "summary"} and mp_cache_age_seconds is not None:
        return f"moviepilot_failed: {mp_error} (fallback={mp_source} age={mp_cache_age_seconds}s)"
    return f"moviepilot_failed: {mp_error}"


__all__ = ["moviepilot_warning"]
