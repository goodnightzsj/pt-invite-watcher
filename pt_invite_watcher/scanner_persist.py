from __future__ import annotations

import asyncio
import logging
from datetime import datetime
from typing import Any

from pt_invite_watcher.models import Site, SiteCheckResult
from pt_invite_watcher.scanner_change import (
    build_state_changed_event_detail,
    build_state_changed_notification,
)
from pt_invite_watcher.scanner_diff import diff as _diff
from pt_invite_watcher.storage.event_hooks import dispatch_event_hooks as _dispatch_event_hooks
from pt_invite_watcher.storage.event_log_store import add_event as _add_event
from pt_invite_watcher.storage.site_state_write import save_site_result as _save_site_result
from pt_invite_watcher.utils.parse import normalize_domain


logger = logging.getLogger("pt_invite_watcher.scanner_persist")


async def persist_and_notify(
    *,
    store: Any,
    notifier: Any,
    site: Site,
    result: SiteCheckResult,
    now: datetime,
) -> None:
    try:
        prev = await store.get_site_state(site.domain)
        changes = _diff(prev, result)
        changed_at = now.isoformat() if changes else None
        events: list[dict[str, Any]] = []
        write_txn = getattr(store, "write_transaction", None)
        if callable(write_txn):
            async with write_txn() as conn:
                await _save_site_result(store, result, changed_at, conn=conn, commit=False)
                if changes:
                    evt = await _add_event(
                        store,
                        category="site",
                        level="info",
                        action="state_changed",
                        message="; ".join(changes)[:200],
                        domain=normalize_domain(site.domain),
                        detail=build_state_changed_event_detail(site, result, changes),
                        conn=conn,
                        commit=False,
                        dispatch_hooks=False,
                        best_effort=False,
                    )
                    if evt is not None:
                        events.append(evt)
        else:
            await store.save_site_result(result, changed_at=changed_at)
            if changes:
                await store.add_event(
                    category="site",
                    level="info",
                    action="state_changed",
                    message="; ".join(changes)[:200],
                    domain=normalize_domain(site.domain),
                    detail=build_state_changed_event_detail(site, result, changes),
                )
    except asyncio.CancelledError:
        raise
    except Exception:
        logger.exception("failed to persist site result: %s", site.domain)
        return

    if events:
        for evt in events:
            _dispatch_event_hooks(store, evt)

    if not changes:
        return

    title, text = build_state_changed_notification(site, result, changes)
    try:
        await notifier.send(title=title, text=text)
    except asyncio.CancelledError:
        raise
    except Exception:
        logger.exception("notify failed: %s", site.domain)

    # Native mobile push (APN / FCM) — only when an invite JUST transitioned
    # to open. Other changes (registration closed, reachability down) stay
    # on the Telegram / 企业微信 channels because they're less actionable
    # from a phone lock screen. `is_configured()` is a fast env-var check so
    # the typical operator with no mobile push setup pays nothing here.
    try:
        from pt_invite_watcher.notify.mobile_push import dispatch_invites_opened, is_configured
        if is_configured():
            prev_inv = (prev.invites_state if prev else None) or ""
            new_inv = result.invites.state or ""
            if prev_inv != "open" and new_inv == "open":
                await dispatch_invites_opened(
                    store,
                    domain=normalize_domain(site.domain),
                    site_name=getattr(site, "name", "") or "",
                    count=getattr(result.invites, "available", None),
                )
    except asyncio.CancelledError:
        raise
    except Exception:
        logger.exception("mobile push dispatch failed: %s", site.domain)


__all__ = ["persist_and_notify"]
