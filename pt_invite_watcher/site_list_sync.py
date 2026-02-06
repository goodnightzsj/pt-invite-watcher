from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

from pt_invite_watcher.models import Site
from pt_invite_watcher.site_list import SITE_LIST_SUMMARY_KEY, build_summary, diff_summary, format_diff_lines


logger = logging.getLogger("pt_invite_watcher.site_list_sync")


async def sync_site_list_summary(
    store: Any,
    notifier: Any,
    sites: list[Site],
    now: datetime,
    *,
    notify: bool,
    reason: str,
) -> None:
    """
    Sync the effective site list summary into KV, and optionally notify on changes.
    """
    try:
        prev = await store.get_json(SITE_LIST_SUMMARY_KEY, default=None)
        cur = build_summary(list(sites or []), now=now)
        diff = diff_summary(prev, cur)
        await store.set_json(SITE_LIST_SUMMARY_KEY, cur)

        if prev is None or diff.empty:
            return

        lines = format_diff_lines(diff, cur)
        if notify and lines:
            title = "PT Invite Watcher: 站点清单变更"
            text = "\n".join(lines)
            try:
                await notifier.send(title=title, text=text)
            except Exception:
                logger.exception("site list notify failed")

        await store.add_event(
            category="site",
            level="info",
            action="site_list_changed",
            message=f"site list changed ({reason})",
            detail={"reason": reason, "lines": lines},
        )
    except Exception:
        logger.exception("failed to sync site list summary")
