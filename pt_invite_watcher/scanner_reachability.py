from __future__ import annotations

from typing import Optional
from urllib.parse import urlparse
from contextlib import suppress

import httpx

from pt_invite_watcher.models import Evidence, ReachabilityResult
from pt_invite_watcher.net import DEFAULT_REQUEST_RETRY_ATTEMPTS, request_with_retry
from pt_invite_watcher.utils.parse import format_error_detail as _format_error_detail_util
from pt_invite_watcher.utils.url import hosts_related


_MAX_ERROR_DETAIL_LEN = 240
_DOWN_HTTP_STATUSES = set(range(520, 530))


def _format_error_detail(exc: Exception) -> str:
    return _format_error_detail_util(exc, max_len=_MAX_ERROR_DETAIL_LEN)


def engine_hint_from_html(html: str) -> Optional[str]:
    h = (html or "").lower()
    if not h:
        return None
    if "nexusphp" in h:
        return "nexusphp"
    if any(token in h for token in ("torrents.php", "userdetails.php", "takesignup.php", "takeinvite.php", "login.php")):
        return "nexusphp"
    return None


async def probe_reachability(
    client: httpx.AsyncClient,
    site_url: str,
    user_agent: Optional[str],
    cookie_header: Optional[str],
    *,
    retry_delay_seconds: int,
) -> tuple[ReachabilityResult, Optional[str]]:
    ua = user_agent or None
    orig_host = urlparse(site_url).hostname or ""

    headers: dict[str, str] = {}
    if ua:
        headers["User-Agent"] = ua
    if cookie_header:
        headers["Cookie"] = cookie_header

    resp, err, used = await request_with_retry(
        lambda: client.get(site_url, headers=headers or None),
        attempts=DEFAULT_REQUEST_RETRY_ATTEMPTS,
        delay_seconds=max(0, int(retry_delay_seconds or 0)),
    )

    if err is not None or resp is None:
        detail = _format_error_detail(err or RuntimeError("probe failed"))
        if used > 1:
            detail = f"{detail} (retries={used})"
        state = "down" if isinstance(err, httpx.RequestError) else "unknown"
        return (
            ReachabilityResult(
                state=state,
                evidence=Evidence(
                    url=site_url,
                    http_status=None,
                    reason=f"probe_error:{type(err).__name__}",
                    detail=detail,
                ),
            ),
            None,
        )

    try:
        hint = engine_hint_from_html(resp.text)
        status = resp.status_code

        final_host = resp.url.host if resp.url else ""
        if orig_host and final_host and not hosts_related(orig_host, final_host):
            detail = f"redirected_to:{final_host}"
            if used > 1:
                detail = f"{detail} (retries={used})"
            return (
                ReachabilityResult(
                    state="down",
                    evidence=Evidence(url=str(resp.url), http_status=status, reason="probe_redirect", detail=detail),
                ),
                hint,
            )

        if status >= 500 or status in _DOWN_HTTP_STATUSES:
            detail = f"retries={used}" if used > 1 else None
            return (
                ReachabilityResult(
                    state="down",
                    evidence=Evidence(url=str(resp.url), http_status=status, reason=f"probe_http_{status}", detail=detail),
                ),
                hint,
            )

        if status in {408, 429}:
            detail = f"retries={used}" if used > 1 else None
            return (
                ReachabilityResult(
                    state="down",
                    evidence=Evidence(url=str(resp.url), http_status=status, reason=f"probe_http_{status}", detail=detail),
                ),
                hint,
            )

        return (
            ReachabilityResult(
                state="up",
                evidence=Evidence(url=str(resp.url), http_status=status, reason="probe_ok"),
            ),
            hint,
        )
    finally:
        with suppress(Exception):
            await resp.aclose()


__all__ = ["engine_hint_from_html", "probe_reachability"]
