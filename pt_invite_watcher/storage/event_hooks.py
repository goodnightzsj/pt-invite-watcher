from __future__ import annotations

import asyncio
import logging
from typing import Any

from pt_invite_watcher.utils.asyncio_tasks import create_task_logged


logger = logging.getLogger("pt_invite_watcher.storage.event_hooks")


def dispatch_event_hooks(store: Any, evt: dict[str, Any]) -> None:
    """
    Best-effort event hook dispatch.

    Prefer store-provided `dispatch_event_hooks()` (public), otherwise fall back to
    legacy `store._event_hooks` list.
    """
    dispatcher = getattr(store, "dispatch_event_hooks", None)
    if callable(dispatcher):
        dispatcher(evt)
        return

    hooks = list(getattr(store, "_event_hooks", []) or [])
    action = str(evt.get("action") or "event").strip() or "event"
    domain = (str(evt.get("domain") or "").strip().lower() if evt.get("domain") is not None else "") or ""
    task_name = f"event_hook_{action}"
    if domain:
        task_name = f"{task_name}_{domain}"
    task_name = task_name.replace(" ", "_")[:120]
    label = f"event hook (action={action} domain={domain or '-'})"
    for hook in hooks:
        try:
            res = hook(evt)
            if asyncio.iscoroutine(res):
                create_task_logged(res, logger=logger, name=task_name, label=label)
        except Exception:
            logger.exception("event hook failed")


__all__ = ["dispatch_event_hooks"]
