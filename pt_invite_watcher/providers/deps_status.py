from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from pt_invite_watcher.utils.parse import safe_dict, safe_str

logger = logging.getLogger("pt_invite_watcher.deps_status")

DEPS_STATUS_KEY = "deps_status"
DEPS_STATUS_VERSION = 1

DEFAULT_RETRY_INTERVAL_SECONDS = 3600
MIN_RETRY_INTERVAL_SECONDS = 60
MAX_RETRY_INTERVAL_SECONDS = 24 * 3600


def _norm_base_url(value: Any) -> str:
    return safe_str(value).rstrip("/")


def _parse_dt(value: Any) -> Optional[datetime]:
    s = safe_str(value)
    if not s:
        return None
    try:
        dt = datetime.fromisoformat(s)
    except Exception:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def fingerprint_moviepilot(base_url: str) -> str:
    return _norm_base_url(base_url)


def fingerprint_cookiecloud(base_url: str, uuid: str) -> str:
    return f"{_norm_base_url(base_url)}|{safe_str(uuid)}"


@dataclass(frozen=True)
class DepStatus:
    ok: bool
    checked_at: Optional[datetime]
    next_retry_at: Optional[datetime]
    error: str
    fingerprint: str


def load_deps_status(payload: Any) -> dict[str, Any]:
    root = safe_dict(payload)
    if int(root.get("version") or 0) != DEPS_STATUS_VERSION:
        return {"version": DEPS_STATUS_VERSION}
    return {"version": DEPS_STATUS_VERSION, **{k: v for k, v in root.items() if k != "version"}}


def get_dep_status(status: dict[str, Any], name: str) -> DepStatus:
    raw = safe_dict(status.get(name))
    ok = bool(raw.get("ok", False))
    checked_at = _parse_dt(raw.get("checked_at"))
    next_retry_at = _parse_dt(raw.get("next_retry_at"))
    error = safe_str(raw.get("error"))
    fingerprint = safe_str(raw.get("fingerprint"))
    return DepStatus(ok=ok, checked_at=checked_at, next_retry_at=next_retry_at, error=error, fingerprint=fingerprint)


def can_attempt(dep: DepStatus, now: datetime, fingerprint: str) -> bool:
    if not fingerprint or dep.fingerprint != fingerprint:
        return True
    if dep.ok:
        return True
    if dep.next_retry_at is None:
        return True
    return now >= dep.next_retry_at


def update_dep_ok(status: dict[str, Any], name: str, now: datetime, fingerprint: str) -> dict[str, Any]:
    next_status = dict(status)
    next_status[name] = {
        "ok": True,
        "checked_at": now.isoformat(),
        "next_retry_at": "",
        "error": "",
        "fingerprint": fingerprint,
    }
    return next_status


def update_dep_fail(
    status: dict[str, Any],
    name: str,
    now: datetime,
    fingerprint: str,
    error: str,
    retry_interval_seconds: int,
) -> dict[str, Any]:
    retry_seconds = max(MIN_RETRY_INTERVAL_SECONDS, min(MAX_RETRY_INTERVAL_SECONDS, int(retry_interval_seconds or 0)))
    next_retry_at = (now + timedelta(seconds=retry_seconds)).isoformat()
    next_status = dict(status)
    next_status[name] = {
        "ok": False,
        "checked_at": now.isoformat(),
        "next_retry_at": next_retry_at,
        "error": safe_str(error),
        "fingerprint": fingerprint,
    }
    return next_status


async def best_effort_persist_deps_status(store: Any, status: dict[str, Any], *, reason: str = "") -> None:
    """
    Best-effort persist deps_status into the store KV.

    This helper centralizes persistence so callers don't hand-roll slightly different
    error handling patterns across modules. It intentionally does not catch
    asyncio.CancelledError (BaseException on Python 3.9+).
    """
    try:
        await store.set_json(DEPS_STATUS_KEY, load_deps_status(status))
    except Exception:
        if reason:
            logger.exception("failed to persist deps status (%s)", reason)
        else:
            logger.exception("failed to persist deps status")
