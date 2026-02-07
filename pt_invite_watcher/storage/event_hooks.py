from __future__ import annotations

import asyncio
import logging
from typing import Any


logger = logging.getLogger("pt_invite_watcher.storage.event_hooks")

def _create_task_logged(coro: Any) -> None:
    task = asyncio.create_task(coro)

    def _done(t: asyncio.Task[Any]) -> None:
        try:
            t.result()
        except asyncio.CancelledError:
            return
        except Exception:
            logger.exception("event hook task failed")

    task.add_done_callback(_done)


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
    for hook in hooks:
        try:
            res = hook(evt)
            if asyncio.iscoroutine(res):
                _create_task_logged(res)
        except Exception:
            logger.exception("event hook failed")


__all__ = ["dispatch_event_hooks"]
