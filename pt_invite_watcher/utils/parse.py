from __future__ import annotations

import re
from typing import Any, Optional

_TRUTHY = {"1", "true", "yes", "y", "on"}


def safe_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def safe_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def safe_str(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def normalize_domain(domain: str) -> str:
    return safe_str(domain).lower()


def cfg_str(value: Any) -> str:
    return safe_str(value)


def cfg_int(value: Any, default: int, min_value: int, max_value: int) -> int:
    if value is None or value == "":
        return default
    try:
        parsed = int(str(value).strip())
    except Exception:
        return default
    return max(min_value, min(max_value, parsed))


def cfg_bool(value: Any, default: bool) -> bool:
    if value is None or value == "":
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, int):
        return value != 0
    return safe_str(value).lower() in _TRUTHY


def format_error_detail(exc: Exception, *, max_len: int = 240) -> str:
    msg = safe_str(exc)
    if not msg:
        cause = getattr(exc, "__cause__", None)
        if cause is not None:
            msg = safe_str(cause)
    if not msg:
        msg = type(exc).__name__
    msg = re.sub(r"\s+", " ", msg).strip()
    if max_len and len(msg) > max_len:
        msg = msg[: max_len - 1] + "…"
    return msg


def safe_int(value: Any) -> Optional[int]:
    if value is None or value == "":
        return None
    try:
        return int(value)
    except Exception:
        return None

