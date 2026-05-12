from __future__ import annotations

from typing import Any, Optional

from pt_invite_watcher.models import AspectResult, Evidence
from pt_invite_watcher.utils.url import join_url


async def check_invites_for_site(
    *,
    is_mteam: bool,
    store: Any,
    detector: Any,
    mteam_detector: Any,
    client: Any,
    site: Any,
    user_agent: Optional[str],
    cookie_header_for_invites: Optional[str],
    inv_path: str,
    retry_delay_seconds: int,
    domain: str,
) -> AspectResult:
    if is_mteam:
        api_key = (getattr(site, "did", None) or "").strip()
        if api_key:
            invites = await mteam_detector.check_invites(client, site, user_agent, retry_delay_seconds=retry_delay_seconds)
            if invites.state == "unknown":
                if cookie_header_for_invites:
                    # Fallback path keeps the default retry delay on purpose
                    # (see tests/test_scanner_invites); the M-Team JSON probe
                    # already burned the per-site retry budget.
                    invites = await detector.check_invites(client, site, user_agent, cookie_header_for_invites)
            return invites

        if cookie_header_for_invites:
            return await detector.check_invites(
                client,
                site,
                user_agent,
                cookie_header_for_invites,
                retry_delay_seconds=retry_delay_seconds,
            )

        return AspectResult(
            state="unknown",
            evidence=Evidence(
                url="https://api.m-team.cc/api/member/profile",
                http_status=None,
                reason="missing_auth",
                detail="api-key (did) not configured",
            ),
        )

    if getattr(site, "id", None) is None and not cookie_header_for_invites:
        # Manual site, no cookie -> Explicitly SKIP invites check
        await store.add_event(
            category="scan",
            level="warn",
            action="skip_invites",
            message="跳过邀请检测 (手动站点无Cookie)",
            domain=domain,
            detail={"site_name": getattr(site, "name", "")},
        )
        return AspectResult(
            state="unknown",
            available=None,
            permanent=None,
            temporary=None,
            evidence=Evidence(
                url=join_url(str(getattr(site, "url", "")), inv_path),
                http_status=None,
                reason="manual_no_cookie_skip_invites",
                detail="manual site without cookie; skip invites probe",
            ),
        )

    return await detector.check_invites(
        client,
        site,
        user_agent,
        cookie_header_for_invites,
        retry_delay_seconds=retry_delay_seconds,
    )


__all__ = ["check_invites_for_site"]
