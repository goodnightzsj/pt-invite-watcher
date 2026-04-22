from __future__ import annotations

from typing import Optional
from urllib.parse import urlparse
from contextlib import suppress

import httpx

from pt_invite_watcher.engines.redirect_guard import (
    GuardedResponse,
    RedirectedAwayError,
    guarded_get,
    is_blacklisted_host,
    off_site_detail,
    same_registrable_domain,
)
from pt_invite_watcher.models import Evidence, ReachabilityResult
from pt_invite_watcher.net import DEFAULT_REQUEST_RETRY_ATTEMPTS
from pt_invite_watcher.utils.parse import format_error_detail as _format_error_detail_util


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

    gr: GuardedResponse = await guarded_get(
        client,
        site_url,
        expected_host=orig_host,
        headers=headers or None,
        attempts=DEFAULT_REQUEST_RETRY_ATTEMPTS,
        delay_seconds=max(0, int(retry_delay_seconds or 0)),
    )

    err = gr.error
    resp = gr.response
    used = gr.retries

    if err is not None or (resp is None and gr.off_site_reason is None):
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
                    reason=f"probe_error:{type(err).__name__}" if err else "probe_failed",
                    detail=detail,
                ),
            ),
            None,
        )

    # Detected an off-site redirect during the 3xx hop chain. Treat as `down` and attach
    # the chain summary so operators can see *which* host we bailed on.
    if gr.off_site_reason and resp is None:
        detail = off_site_detail(gr) or f"redirect_{gr.off_site_reason}"
        if used > 1:
            detail = f"{detail} (retries={used})"
        # Use the stable "probe_redirect" reason for all "followed a 3xx away from the
        # expected domain" outcomes; the detail carries the specific sub-reason (off_site,
        # blacklisted, too_many_redirects, …) so dashboards stay informative.
        if gr.off_site_host:
            detail = f"redirected_to:{gr.off_site_host} | {detail}"
        return (
            ReachabilityResult(
                state="down",
                evidence=Evidence(
                    url=site_url,
                    http_status=None,
                    reason="probe_redirect",
                    detail=detail,
                ),
            ),
            None,
        )

    # We got a final response. Before falling through to the usual status-code logic,
    # also reject cases where the final host (or an HTML-level redirect in the body)
    # points away from the expected registrable domain.
    assert resp is not None
    try:
        hint = engine_hint_from_html(resp.text)
        status = resp.status_code

        # HTML-level meta-refresh / JS redirect detected during guarded_get.
        if gr.off_site_reason == "html_redirect":
            detail = off_site_detail(gr) or "html_redirect"
            if used > 1:
                detail = f"{detail} (retries={used})"
            return (
                ReachabilityResult(
                    state="down",
                    evidence=Evidence(
                        url=str(resp.url),
                        http_status=status,
                        reason="probe_html_redirect",
                        detail=detail,
                    ),
                ),
                hint,
            )

        # Safety net: even if guarded_get didn't flag anything, cross-check the final URL
        # host against the expected domain and the blacklist (covers exotic cases like
        # httpx silently following a hop we didn't see).
        final_host = resp.url.host if resp.url else ""
        if orig_host and final_host:
            if is_blacklisted_host(final_host) or not same_registrable_domain(orig_host, final_host):
                detail = f"redirected_to:{final_host}"
                if used > 1:
                    detail = f"{detail} (retries={used})"
                return (
                    ReachabilityResult(
                        state="down",
                        evidence=Evidence(
                            url=str(resp.url),
                            http_status=status,
                            reason="probe_redirect",
                            detail=detail,
                        ),
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


__all__ = ["RedirectedAwayError", "engine_hint_from_html", "probe_reachability"]
