from __future__ import annotations

import asyncio
import logging
import time
from typing import Any

from pt_invite_watcher.storage.event_log_store import add_event as _add_event
from pt_invite_watcher.utils.asyncio_tasks import create_task_logged


logger = logging.getLogger("pt_invite_watcher.storage.scan_log_buffer")


def ensure_scan_log_flusher(store: Any) -> None:
    task = getattr(store, "_scan_log_flush_task", None)
    if task is not None and not task.done():
        return
    store._scan_log_flush_task = create_task_logged(  # type: ignore[attr-defined]
        scan_log_flush_loop(store),
        logger=logger,
        name="scan_log_flush_loop",
    )


async def scan_log_flush_loop(store: Any) -> None:
    while True:
        await asyncio.sleep(getattr(store, "_scan_log_flush_interval_seconds", 0.2))
        try:
            # Background flush should not contend with critical write transactions.
            write_lock = getattr(store, "_write_lock", None)
            flush_lock = getattr(store, "_scan_log_flush_lock", None)
            if (write_lock is not None and write_lock.locked()) or (flush_lock is not None and flush_lock.locked()):
                continue
            await flush_scan_logs(store, max_items=getattr(store, "_scan_log_batch_max", 100))
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("scan log flush loop failed")


async def enqueue_scan_log_event(
    store: Any,
    *,
    category: str,
    level: str,
    action: str,
    message: str,
    domain: str | None,
    detail: Any,
    max_rows: int,
) -> None:
    ensure_scan_log_flusher(store)
    item = {
        "category": category,
        "level": level,
        "action": action,
        "message": message,
        "domain": domain,
        "detail": detail,
        "max_rows": max_rows,
    }

    started = time.monotonic()
    while True:
        async with store._scan_log_buffer_lock:  # type: ignore[attr-defined]
            if len(store._scan_log_buffer) < store._scan_log_buffer_max:  # type: ignore[attr-defined]
                store._scan_log_buffer.append(item)  # type: ignore[attr-defined]
                return

        # Buffer is full: try to flush quickly and apply backpressure.
        before = store._scan_log_flush_count  # type: ignore[attr-defined]
        try:
            await flush_scan_logs(store, max_items=store._scan_log_buffer_max)  # type: ignore[attr-defined]
        except asyncio.CancelledError:
            raise
        except Exception:
            store._scan_log_flush_failures_pending += 1  # type: ignore[attr-defined]
            store._request_logs_resync(reason="scan_log_flush_failed")  # type: ignore[attr-defined]

        if store._scan_log_flush_count > before:  # type: ignore[attr-defined]
            continue

        if (time.monotonic() - started) >= store._scan_log_enqueue_max_wait_seconds:  # type: ignore[attr-defined]
            store._scan_log_dropped += 1  # type: ignore[attr-defined]
            store._scan_log_dropped_pending += 1  # type: ignore[attr-defined]
            now = time.monotonic()
            if now - store._scan_log_dropped_last_log >= 30:  # type: ignore[attr-defined]
                dropped = store._scan_log_dropped  # type: ignore[attr-defined]
                store._scan_log_dropped_last_log = now  # type: ignore[attr-defined]
                store._scan_log_dropped = 0  # type: ignore[attr-defined]
                logger.warning("scan log buffer full; dropping scan logs (dropped=%d)", dropped)
            store._request_logs_resync(reason="scan_log_buffer_full")  # type: ignore[attr-defined]
            return

        await asyncio.sleep(store._scan_log_enqueue_retry_sleep_seconds)  # type: ignore[attr-defined]


async def flush_scan_logs(store: Any, *, max_items: int | None = None) -> None:
    async with store._scan_log_flush_lock:  # type: ignore[attr-defined]
        while True:
            async with store._scan_log_buffer_lock:  # type: ignore[attr-defined]
                if not store._scan_log_buffer:  # type: ignore[attr-defined]
                    return
                limit = max_items if max_items is not None else store._scan_log_batch_max  # type: ignore[attr-defined]
                n = max(1, min(int(limit or 0), len(store._scan_log_buffer)))  # type: ignore[attr-defined]
                batch = list(store._scan_log_buffer[:n])  # type: ignore[attr-defined]

            events: list[dict[str, Any]] = []
            used_dropped = 0
            used_flush_failures = 0
            try:
                async with store.write_transaction() as conn:
                    if store._scan_log_dropped_pending or store._scan_log_flush_failures_pending:  # type: ignore[attr-defined]
                        used_dropped = int(store._scan_log_dropped_pending)  # type: ignore[attr-defined]
                        used_flush_failures = int(store._scan_log_flush_failures_pending)  # type: ignore[attr-defined]
                        detail = {
                            "dropped": used_dropped,
                            "flush_failures": used_flush_failures,
                            "buffer_size": len(store._scan_log_buffer),  # type: ignore[attr-defined]
                        }
                        evt = await _add_event(
                            store,
                            category="scan",
                            level="warn",
                            action="scan_log_degraded",
                            message=f"scan log degraded (dropped={detail['dropped']} flush_failures={detail['flush_failures']})",
                            detail=detail,
                            max_rows=5000,
                            conn=conn,
                            commit=False,
                            dispatch_hooks=False,
                            best_effort=True,
                        )
                        if evt is not None:
                            events.append(evt)

                    for item in batch:
                        evt = await _add_event(
                            store,
                            category=item["category"],
                            level=item["level"],
                            action=item["action"],
                            message=item["message"],
                            domain=item.get("domain"),
                            detail=item.get("detail"),
                            max_rows=int(item.get("max_rows") or 5000),
                            conn=conn,
                            commit=False,
                            dispatch_hooks=False,
                            best_effort=True,
                        )
                        if evt is not None:
                            events.append(evt)
            except asyncio.CancelledError:
                raise
            except Exception:
                now = time.monotonic()
                if now - store._scan_log_flush_failures_last_log >= 60:  # type: ignore[attr-defined]
                    suppressed = store._scan_log_flush_failures_suppressed  # type: ignore[attr-defined]
                    store._scan_log_flush_failures_last_log = now  # type: ignore[attr-defined]
                    store._scan_log_flush_failures_suppressed = 0  # type: ignore[attr-defined]
                    logger.exception("scan log flush failed (suppressed=%d)", suppressed)
                else:
                    store._scan_log_flush_failures_suppressed += 1  # type: ignore[attr-defined]
                store._scan_log_flush_failures_pending += 1  # type: ignore[attr-defined]
                store._request_logs_resync(reason="scan_log_flush_failed")  # type: ignore[attr-defined]
                return

            async with store._scan_log_buffer_lock:  # type: ignore[attr-defined]
                del store._scan_log_buffer[:n]  # type: ignore[attr-defined]
            store._scan_log_flush_count += n  # type: ignore[attr-defined]
            if used_dropped > 0:
                store._scan_log_dropped_pending = max(0, int(store._scan_log_dropped_pending) - used_dropped)  # type: ignore[attr-defined]
            if used_flush_failures > 0:
                store._scan_log_flush_failures_pending = max(  # type: ignore[attr-defined]
                    0, int(store._scan_log_flush_failures_pending) - used_flush_failures
                )

            if events:
                for evt in events:
                    store.dispatch_event_hooks(evt)

            if max_items is not None:
                return


__all__ = ["ensure_scan_log_flusher", "scan_log_flush_loop", "enqueue_scan_log_event", "flush_scan_logs"]
