"""Opt-in crash + error reporting.

Wraps `sentry_sdk` so the rest of the codebase can call `init_observability()`
and `capture_exception()` without caring whether Sentry is actually configured.
All functions degrade to a no-op when `PTIW_SENTRY_DSN` is unset — no network
calls, no breadcrumb accumulation, no import penalty beyond the `sentry-sdk`
being on disk.

Scrubbing policy:
  - BasicAuth header values are dropped from captured requests.
  - Query strings containing `token=` (our WebSocket auth pattern) are
    redacted to `token=REDACTED`.
  - URLs under `/api/sites/icon` skip capture entirely (noisy, low signal).
"""
from __future__ import annotations

import logging
import os
import re
from typing import Any, Optional

logger = logging.getLogger("pt_invite_watcher.observability")

_ENABLED = False


def _scrub_event(event: dict, _hint: Any) -> Optional[dict]:
    """Sentry `before_send` hook — run on every outgoing event."""
    try:
        req = (event or {}).get("request") or {}
        url = req.get("url") or ""
        # Icon proxy spam: skip entirely. ~155 GETs every dashboard refresh,
        # almost all succeed; any captured errors are duplicate and noise.
        if "/api/sites/icon" in url:
            return None

        # Redact token= in both URL and query_string.
        if "token=" in url:
            req["url"] = re.sub(r"token=[^&]*", "token=REDACTED", url)
        qs = req.get("query_string")
        if isinstance(qs, str) and "token=" in qs:
            req["query_string"] = re.sub(r"token=[^&]*", "token=REDACTED", qs)

        # Drop Authorization header.
        headers = req.get("headers") or {}
        if isinstance(headers, dict):
            for k in list(headers.keys()):
                if k.lower() == "authorization":
                    headers[k] = "REDACTED"

        event["request"] = req
    except Exception:
        # A scrubbing bug mustn't lose the event. Let Sentry send the raw event.
        logger.exception("sentry _scrub_event failed; passing event through unscrubbed")
    return event


def init_observability(release: str = "") -> bool:
    """Initialize Sentry if configured. Returns True when active.

    Call once from the app lifespan — subsequent calls are ignored.
    """
    global _ENABLED
    if _ENABLED:
        return True
    dsn = os.getenv("PTIW_SENTRY_DSN", "").strip()
    if not dsn:
        return False
    try:
        import sentry_sdk
        from sentry_sdk.integrations.fastapi import FastApiIntegration
    except Exception:
        logger.warning("PTIW_SENTRY_DSN is set but sentry-sdk isn't importable")
        return False

    try:
        sentry_sdk.init(
            dsn=dsn,
            release=release or None,
            traces_sample_rate=0.0,  # errors only by default; set PTIW_SENTRY_TRACES_SAMPLE=0.1 to opt in
            send_default_pii=False,
            before_send=_scrub_event,
            integrations=[FastApiIntegration()],
            environment=os.getenv("PTIW_SENTRY_ENV", "self-hosted"),
        )
        # Opt-in traces sampling — separate env var so operators don't
        # accidentally pay for performance data.
        traces = float(os.getenv("PTIW_SENTRY_TRACES_SAMPLE", "0") or "0")
        if traces > 0:
            # sentry_sdk doesn't expose a rebind after init for traces_sample_rate
            # in a simple way; we re-init with the new rate.
            sentry_sdk.init(
                dsn=dsn,
                release=release or None,
                traces_sample_rate=min(max(traces, 0.0), 1.0),
                send_default_pii=False,
                before_send=_scrub_event,
                integrations=[FastApiIntegration()],
                environment=os.getenv("PTIW_SENTRY_ENV", "self-hosted"),
            )
        _ENABLED = True
        logger.info("sentry: initialized (env=%s)", os.getenv("PTIW_SENTRY_ENV", "self-hosted"))
        return True
    except Exception:
        logger.exception("sentry init failed; continuing without observability")
        return False


def capture_exception(exc: BaseException) -> None:
    """Fire-and-forget exception capture. Silent no-op when disabled."""
    if not _ENABLED:
        return
    try:
        import sentry_sdk
        sentry_sdk.capture_exception(exc)
    except Exception:
        logger.exception("sentry capture_exception failed")


def is_enabled() -> bool:
    return _ENABLED


def public_frontend_dsn() -> str:
    """Sentry DSN for the webui bundle to forward JS errors to.

    Returned via /api/config so the frontend can lazy-load @sentry/browser
    only when observability is actually configured. `PTIW_SENTRY_FRONTEND_DSN`
    is expected to be a separate DSN (backend + frontend can share one project
    but typically use different DSNs so you can filter by source).
    Empty string → frontend observability stays off.
    """
    return os.getenv("PTIW_SENTRY_FRONTEND_DSN", "").strip() or os.getenv("PTIW_SENTRY_DSN", "").strip()
