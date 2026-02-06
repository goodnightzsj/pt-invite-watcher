from __future__ import annotations

"""
Lease policy helpers.

This module centralizes TTL calculations so scheduler leadership (app loop) and
scan locking can share the same, reviewable policy without duplicating magic
numbers across modules.
"""


def scheduler_lease_ttl_seconds(*, interval_seconds: int, timeout_seconds: int) -> int:
    """
    Scheduler leader lock TTL.

    Keep the formula consistent with historical behavior:
    - at least 300s
    - at least 3x scan interval
    - at least 30x scan timeout
    """
    interval = int(interval_seconds or 0)
    timeout = int(timeout_seconds or 0)
    return max(300, interval * 3, timeout * 30)


def scan_lease_ttl_seconds(*, timeout_seconds: int) -> int:
    """
    Scan lock TTL.

    Keep the formula consistent with historical behavior:
    - at least 60s
    - at least 20x scan timeout
    """
    timeout = int(timeout_seconds or 0)
    return max(60, timeout * 20)

