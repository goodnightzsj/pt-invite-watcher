from __future__ import annotations

import asyncio
import logging
from typing import Awaitable, Optional, TypeVar


T = TypeVar("T")


def create_task_logged(
    coro: Awaitable[T],
    *,
    logger: logging.Logger,
    name: str,
    label: Optional[str] = None,
) -> asyncio.Task[T]:
    """
    Create an asyncio Task and log exceptions via done callback.

    - Never logs CancelledError (normal shutdown).
    - Always names the task for debugging (`asyncio.all_tasks()` / debug tools).
    """
    task_name = str(name or "").strip() or "task"
    try:
        task = asyncio.create_task(coro, name=task_name)
    except RuntimeError:
        # Avoid leaking coroutine objects when called without a running loop
        # (e.g. during interpreter/loop shutdown).
        closer = getattr(coro, "close", None)
        if callable(closer):
            try:
                closer()
            except Exception:
                pass
        raise

    def _done(t: asyncio.Task[T]) -> None:
        try:
            t.result()
        except asyncio.CancelledError:
            return
        except Exception:
            if label:
                logger.exception("%s task failed (task=%s)", label, task_name)
            else:
                logger.exception("task failed (task=%s)", task_name)

    task.add_done_callback(_done)
    return task


__all__ = ["create_task_logged"]
