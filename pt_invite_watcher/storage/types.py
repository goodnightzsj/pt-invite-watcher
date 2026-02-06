from __future__ import annotations

from contextlib import AbstractAsyncContextManager
from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class SupportsConn(Protocol):
    def require_conn(self) -> Any: ...


@runtime_checkable
class SupportsWriteTransaction(Protocol):
    def write_transaction(self) -> AbstractAsyncContextManager[Any]: ...


@runtime_checkable
class SupportsLeaseOperation(Protocol):
    def lease_operation(self) -> AbstractAsyncContextManager[Any]: ...


@runtime_checkable
class SupportsEventHooks(Protocol):
    def dispatch_event_hooks(self, evt: dict[str, Any]) -> None: ...


@runtime_checkable
class SupportsJsonKV(Protocol):
    async def get_json(self, key: str, default: Any) -> Any: ...

    async def set_json(self, key: str, value: Any) -> None: ...


@runtime_checkable
class SupportsAddEvent(Protocol):
    async def add_event(
        self,
        *,
        category: str,
        level: str,
        action: str,
        message: str,
        domain: str | None = None,
        detail: Any = None,
        max_rows: int = 5000,
    ) -> Any: ...


@runtime_checkable
class SupportsLeaseStore(Protocol):
    async def try_acquire_lease(self, key: str, *, owner: str, ttl_seconds: int) -> bool: ...

    async def release_lease(self, key: str, *, owner: str) -> None: ...


@runtime_checkable
class SupportsLeaseStoreWithEvents(SupportsLeaseStore, SupportsAddEvent, Protocol):
    pass


__all__ = [
    "SupportsAddEvent",
    "SupportsConn",
    "SupportsEventHooks",
    "SupportsJsonKV",
    "SupportsLeaseOperation",
    "SupportsLeaseStore",
    "SupportsLeaseStoreWithEvents",
    "SupportsWriteTransaction",
]
