from __future__ import annotations

import asyncio
import random
from contextlib import suppress
from email.utils import parsedate_to_datetime
from datetime import datetime, timezone
from typing import Awaitable, Callable, Optional, Set, Tuple, TypeVar

import httpx


DEFAULT_REQUEST_RETRY_ATTEMPTS = 3
DEFAULT_REQUEST_RETRY_DELAY_SECONDS = 30

RETRYABLE_STATUS_CODES: Set[int] = {408, 429, *range(500, 600)}

# Upper bound for any single wait between retries. PT sites occasionally send absurd Retry-After
# values (hours); we never want a single scan cycle to block for that long.
_MAX_WAIT_SECONDS = 300

# When we hit a connection-level error (DNS, TCP), a few-second retry is almost always right —
# a full retry_delay (often 30s) would waste the scan cycle budget.
_CONNECT_RETRY_BASE_SECONDS = 1

TResponse = TypeVar("TResponse", bound=httpx.Response)


def is_retryable_status(status_code: int, retry_statuses: Optional[Set[int]] = None) -> bool:
    statuses = RETRYABLE_STATUS_CODES if retry_statuses is None else retry_statuses
    return int(status_code) in statuses


def _parse_retry_after(value: str) -> Optional[int]:
    """Parse an HTTP Retry-After header (RFC 7231) — either an integer second count or a date.

    Returns the wait in seconds, or None if the header is missing/unparseable.
    """
    raw = (value or "").strip()
    if not raw:
        return None
    # Integer form (seconds)
    try:
        secs = int(raw)
        return max(0, min(secs, _MAX_WAIT_SECONDS))
    except ValueError:
        pass
    # HTTP-date form
    try:
        when = parsedate_to_datetime(raw)
    except (TypeError, ValueError):
        return None
    if when is None:
        return None
    if when.tzinfo is None:
        when = when.replace(tzinfo=timezone.utc)
    delta = (when - datetime.now(timezone.utc)).total_seconds()
    if delta <= 0:
        return 0
    return min(int(delta), _MAX_WAIT_SECONDS)


def _backoff_seconds(attempt: int, base_delay: int) -> int:
    """Exponential backoff with ±25% jitter. Attempt is 0-indexed."""
    base = max(1, int(base_delay or 1))
    exponent = min(attempt, 6)  # cap growth (2^6 = 64x)
    scaled = base * (2 ** exponent)
    scaled = min(scaled, _MAX_WAIT_SECONDS)
    jitter = random.uniform(-scaled * 0.25, scaled * 0.25)
    return max(0, int(scaled + jitter))


async def request_with_retry(
    request_fn: Callable[[], Awaitable[TResponse]],
    *,
    attempts: int = DEFAULT_REQUEST_RETRY_ATTEMPTS,
    delay_seconds: int = DEFAULT_REQUEST_RETRY_DELAY_SECONDS,
    retry_statuses: Optional[Set[int]] = None,
) -> Tuple[Optional[TResponse], Optional[Exception], int]:
    used_attempts = max(1, int(attempts or 0))
    wait_seconds = max(0, int(delay_seconds or 0))

    last_exc: Optional[Exception] = None
    last_resp: Optional[TResponse] = None
    # Cap the *cumulative* sleep across all retries. _MAX_WAIT_SECONDS already
    # caps a single Retry-After, but `attempts × 300s` would still let one
    # hostile site hold a scan task for many minutes. Once the budget is spent
    # we stop retrying and hand back whatever we have.
    total_waited = 0

    async def _bounded_sleep(seconds: int) -> bool:
        """Sleep up to ``seconds``, clipped to the remaining budget.

        Returns ``False`` when the budget is exhausted (caller should give up
        and return immediately rather than retry again)."""
        nonlocal total_waited
        remaining = _MAX_WAIT_SECONDS - total_waited
        if remaining <= 0:
            return False
        clipped = min(int(seconds), remaining)
        if clipped > 0:
            await asyncio.sleep(clipped)
            total_waited += clipped
        return True

    for attempt in range(used_attempts):
        try:
            resp = await request_fn()
            last_resp = resp
            if is_retryable_status(resp.status_code, retry_statuses) and attempt < used_attempts - 1:
                # Respect Retry-After from the server (covers 429 / 503 rate limiting & maintenance).
                headers = getattr(resp, "headers", None)
                retry_after_raw = ""
                if headers is not None:
                    try:
                        retry_after_raw = headers.get("Retry-After", "") or ""
                    except Exception:
                        retry_after_raw = ""
                retry_after = _parse_retry_after(retry_after_raw)
                with suppress(Exception):
                    await resp.aclose()
                if retry_after is not None:
                    sleep_for = min(retry_after, _MAX_WAIT_SECONDS)
                else:
                    sleep_for = _backoff_seconds(attempt, wait_seconds)
                if not await _bounded_sleep(sleep_for):
                    # Out of retry budget — return the (closed) last response.
                    return resp, None, attempt + 1
                continue
            return resp, None, attempt + 1
        except asyncio.CancelledError:
            raise
        except httpx.ConnectError as e:
            # Transient TCP/DNS failures — retry quickly, these rarely need 30s cooling.
            last_exc = e
            if attempt < used_attempts - 1:
                if not await _bounded_sleep(_backoff_seconds(attempt, _CONNECT_RETRY_BASE_SECONDS)):
                    return None, e, attempt + 1
                continue
            return None, e, attempt + 1
        except httpx.RequestError as e:
            last_exc = e
            if attempt < used_attempts - 1:
                if not await _bounded_sleep(_backoff_seconds(attempt, wait_seconds)):
                    return None, e, attempt + 1
                continue
            return None, e, attempt + 1
        except Exception as e:
            last_exc = e
            return None, e, attempt + 1

    return last_resp, last_exc, used_attempts
