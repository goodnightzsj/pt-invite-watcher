from __future__ import annotations

from datetime import datetime
from typing import Any

from pt_invite_watcher.models import AspectResult, Evidence, ReachabilityResult, SiteCheckResult
from pt_invite_watcher.utils.url import join_url


def build_unreachable_result(
    *,
    site: Any,
    engine: str,
    reachability: ReachabilityResult,
    checked_at: datetime,
    reg_path: str,
    inv_path: str,
) -> SiteCheckResult:
    detail = reachability.evidence.detail or reachability.evidence.reason
    registration = AspectResult(
        state="unknown",
        evidence=Evidence(
            url=join_url(str(getattr(site, "url", "")), reg_path),
            http_status=None,
            reason="site_unreachable",
            detail=detail,
        ),
    )
    invites = AspectResult(
        state="unknown",
        evidence=Evidence(
            url=join_url(str(getattr(site, "url", "")), inv_path),
            http_status=None,
            reason="site_unreachable",
            detail=detail,
        ),
    )
    return SiteCheckResult(
        site=site,
        engine=engine,
        reachability=reachability,
        registration=registration,
        invites=invites,
        checked_at=checked_at,
    )


__all__ = ["build_unreachable_result"]
