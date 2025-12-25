from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime
from typing import Any, Literal, Optional


State = Literal["open", "closed", "unknown"]
ReachabilityState = Literal["up", "down", "unknown"]


@dataclass(frozen=True)
class Site:
    id: Optional[int]
    name: str
    domain: str
    url: str
    ua: Optional[str] = None
    cookie: Optional[str] = None
    is_active: bool = True


@dataclass(frozen=True)
class Evidence:
    url: str
    http_status: Optional[int]
    reason: str
    matched: Optional[str] = None
    detail: Optional[str] = None


@dataclass(frozen=True)
class AspectResult:
    state: State
    evidence: Evidence
    available: Optional[int] = None  # for invites
    permanent: Optional[int] = None  # for invites (home header)
    temporary: Optional[int] = None  # for invites (home header)


@dataclass(frozen=True)
class ReachabilityResult:
    state: ReachabilityState
    evidence: Evidence


@dataclass(frozen=True)
class SiteCheckResult:
    site: Site
    engine: str
    reachability: ReachabilityResult
    registration: AspectResult
    invites: AspectResult
    checked_at: datetime


def to_jsonable(obj: Any) -> Any:
    if isinstance(obj, datetime):
        return obj.isoformat()
    if hasattr(obj, "__dataclass_fields__"):
        data = asdict(obj)
        return {k: to_jsonable(v) for k, v in data.items()}
    if isinstance(obj, dict):
        return {k: to_jsonable(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [to_jsonable(v) for v in obj]
    return obj
