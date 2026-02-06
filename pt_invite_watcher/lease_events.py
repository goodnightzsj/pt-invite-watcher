from __future__ import annotations

import asyncio
import logging
from typing import Any, Optional


logger = logging.getLogger("pt_invite_watcher.lease_events")


def build_lease_detail(
    *,
    kind: str,
    key: str,
    owner: str,
    ttl_seconds: Optional[int] = None,
    error: str = "",
    extra: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    """
    Build a consistent lease event detail payload.

    This is intentionally a small helper so scheduler leadership and scan locking
    can share the same schema without duplicating per-call dict literals.
    """
    detail: dict[str, Any] = {
        "kind": str(kind or "").strip().lower() or "unknown",
        "key": str(key or ""),
        "owner": str(owner or ""),
    }
    if ttl_seconds is not None:
        detail["ttl_seconds"] = int(ttl_seconds or 0)
    if error:
        detail["error"] = str(error)
    if extra:
        detail.update(extra)
    return detail


async def best_effort_lease_event(
    store: Any,
    *,
    level: str,
    action: str,
    message: str,
    detail: dict[str, Any],
) -> None:
    add_event = getattr(store, "add_event", None)
    if not callable(add_event):
        return
    try:
        await add_event(category="lease", level=level, action=action, message=message, detail=detail)
    except asyncio.CancelledError:
        raise
    except Exception:
        logger.exception("failed to write lease event (action=%s)", action)


__all__ = ["best_effort_lease_event", "build_lease_detail"]
