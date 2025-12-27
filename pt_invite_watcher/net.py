from __future__ import annotations

import asyncio
from typing import Awaitable, Callable, Optional, Set, Tuple, TypeVar

import httpx


DEFAULT_REQUEST_RETRY_ATTEMPTS = 3
DEFAULT_REQUEST_RETRY_DELAY_SECONDS = 30

RETRYABLE_STATUS_CODES: Set[int] = {408, 429, *range(500, 600)}

TResponse = TypeVar("TResponse", bound=httpx.Response)


def is_retryable_status(status_code: int, retry_statuses: Optional[Set[int]] = None) -> bool:
    statuses = RETRYABLE_STATUS_CODES if retry_statuses is None else retry_statuses
    return int(status_code) in statuses


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

    for attempt in range(used_attempts):
        try:
            resp = await request_fn()
            last_resp = resp
            if is_retryable_status(resp.status_code, retry_statuses) and attempt < used_attempts - 1:
                if wait_seconds:
                    await asyncio.sleep(wait_seconds)
                continue
            return resp, None, attempt + 1
        except httpx.RequestError as e:
            last_exc = e
            if attempt < used_attempts - 1:
                if wait_seconds:
                    await asyncio.sleep(wait_seconds)
                continue
            return None, e, attempt + 1
        except Exception as e:
            last_exc = e
            return None, e, attempt + 1

    return last_resp, last_exc, used_attempts

