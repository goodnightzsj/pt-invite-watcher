from __future__ import annotations

import asyncio
import logging
import re
from typing import Any, Optional

import httpx

from pt_invite_watcher.models import AspectResult, Evidence, Site


logger = logging.getLogger("pt_invite_watcher.mteam")

_PROFILE_URL = "https://api.m-team.cc/api/member/profile"
_MAX_DETAIL_LEN = 240
_MAX_INT_VALUE = 1_000_000


def _truncate_detail(value: str) -> str:
    text = str(value or "").strip()
    text = re.sub(r"\s+", " ", text)
    if len(text) > _MAX_DETAIL_LEN:
        return text[: _MAX_DETAIL_LEN - 1] + "…"
    return text


def _coerce_int(value: Any) -> Optional[int]:
    if value is None:
        return None
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        if value.is_integer():
            return int(value)
        return None
    if isinstance(value, str):
        s = value.strip()
        if not s:
            return None
        if re.fullmatch(r"\d+", s):
            try:
                return int(s)
            except Exception:
                return None
    return None


def _collect_numeric_fields(obj: Any, prefix: str = "") -> list[tuple[str, int]]:
    items: list[tuple[str, int]] = []
    if isinstance(obj, dict):
        for k, v in obj.items():
            key = str(k)
            path = f"{prefix}.{key}" if prefix else key
            num = _coerce_int(v)
            if num is not None:
                items.append((path, num))
            else:
                items.extend(_collect_numeric_fields(v, path))
        return items
    if isinstance(obj, list):
        for i, v in enumerate(obj):
            path = f"{prefix}[{i}]" if prefix else f"[{i}]"
            num = _coerce_int(v)
            if num is not None:
                items.append((path, num))
            else:
                items.extend(_collect_numeric_fields(v, path))
        return items
    return items


_INVITE_TOKEN_RE = re.compile(r"(invite|invitation)", re.I)
_INVITE_VALUE_RE = re.compile(r"(count|quota|num|number|remain|left|available|rest)", re.I)
_INVITE_EXCLUDE_RE = re.compile(r"(limit|max|min|token|code|hash|url)", re.I)
_INVITE_TEMP_RE = re.compile(r"(temp|temporary)", re.I)
_INVITE_TOTAL_RE = re.compile(r"(total|sum)", re.I)


def _extract_invite_quota(payload: Any) -> tuple[Optional[int], Optional[int], Optional[str]]:
    fields = _collect_numeric_fields(payload)
    candidates: list[tuple[str, int]] = []
    for path, value in fields:
        if value < 0 or value > _MAX_INT_VALUE:
            continue
        path_lower = path.lower()
        if not _INVITE_TOKEN_RE.search(path_lower):
            continue
        if _INVITE_EXCLUDE_RE.search(path_lower):
            continue
        leaf = path.split(".")[-1].lower()
        if _INVITE_EXCLUDE_RE.search(leaf):
            continue
        if not (
            _INVITE_VALUE_RE.search(leaf)
            or leaf in {"invite", "invites", "invitation", "invitations", "perm", "permanent", "temp", "temporary"}
        ):
            continue
        candidates.append((path, value))

    if not candidates:
        return None, None, None

    temp: Optional[tuple[str, int]] = None
    perm: Optional[tuple[str, int]] = None
    total: Optional[tuple[str, int]] = None

    for path, value in candidates:
        k = path.lower()
        if _INVITE_TEMP_RE.search(k):
            if temp is None or value > temp[1]:
                temp = (path, value)
            continue
        if _INVITE_TOTAL_RE.search(k):
            if total is None or value > total[1]:
                total = (path, value)
            continue
        if perm is None or value > perm[1]:
            perm = (path, value)

    perm_value = perm[1] if perm else None
    temp_value = temp[1] if temp else None
    total_value = total[1] if total else None

    matched_parts: list[str] = []
    if perm is not None:
        matched_parts.append(f"perm={perm[0]}")
    if temp is not None:
        matched_parts.append(f"temp={temp[0]}")
    if total is not None:
        matched_parts.append(f"total={total[0]}")
    matched = "; ".join(matched_parts) if matched_parts else None

    if perm_value is None and total_value is not None and temp_value is not None and total_value >= temp_value:
        perm_value = total_value - temp_value

    if perm_value is None and total_value is not None:
        perm_value = total_value
        temp_value = temp_value or 0

    if perm_value is None and temp_value is not None:
        perm_value = 0

    return perm_value, temp_value or 0, matched


class MTeamDetector:
    async def check_invites(self, client: httpx.AsyncClient, site: Site, user_agent: Optional[str]) -> AspectResult:
        api_key = (site.did or "").strip()
        authorization = (site.authorization or "").strip()
        if not api_key:
            return AspectResult(
                state="unknown",
                evidence=Evidence(
                    url=_PROFILE_URL,
                    http_status=None,
                    reason="missing_auth",
                    detail="api-key (did) not configured",
                ),
            )

        headers: dict[str, str] = {
            "Accept": "application/json, text/plain, */*",
            "x-api-key": api_key,
        }
        if authorization:
            # Optional: some clients store extra token here; API key is the primary auth.
            headers["Authorization"] = authorization
        if user_agent:
            headers["User-Agent"] = user_agent

        last_err: Optional[Exception] = None
        last_resp: Optional[httpx.Response] = None
        used = 1
        for attempt in range(3):
            used = attempt + 1
            try:
                resp = await client.post(_PROFILE_URL, headers=headers)
                last_resp = resp
                if resp.status_code >= 500 and attempt < 2:
                    await asyncio.sleep(0.3 * (attempt + 1))
                    continue
                break
            except httpx.RequestError as e:
                last_err = e
                if attempt < 2:
                    await asyncio.sleep(0.3 * (attempt + 1))
                    continue
            except Exception as e:
                last_err = e
                break

        if last_err is not None and last_resp is None:
            detail = _truncate_detail(str(last_err))
            if used > 1:
                detail = f"{detail} (retries={used})"
            return AspectResult(
                state="unknown",
                evidence=Evidence(
                    url=_PROFILE_URL,
                    http_status=None,
                    reason=f"mteam_error:{type(last_err).__name__}",
                    detail=detail,
                ),
            )

        resp = last_resp
        assert resp is not None

        if resp.status_code in {401, 403}:
            detail = _truncate_detail(resp.text)
            if used > 1:
                detail = f"{detail} (retries={used})"
            return AspectResult(
                state="unknown",
                evidence=Evidence(url=str(resp.url), http_status=resp.status_code, reason="mteam_auth_failed", detail=detail or None),
            )

        if resp.status_code != 200:
            detail = None
            if used > 1:
                detail = f"retries={used}"
            return AspectResult(
                state="unknown",
                evidence=Evidence(
                    url=str(resp.url),
                    http_status=resp.status_code,
                    reason=f"mteam_error:HTTP{resp.status_code}",
                    detail=detail,
                ),
            )

        try:
            payload = resp.json()
        except Exception as e:
            detail = _truncate_detail(str(e))
            return AspectResult(
                state="unknown",
                evidence=Evidence(
                    url=str(resp.url),
                    http_status=resp.status_code,
                    reason="mteam_non_json",
                    detail=detail,
                ),
            )

        if not isinstance(payload, dict):
            return AspectResult(
                state="unknown",
                evidence=Evidence(
                    url=str(resp.url),
                    http_status=resp.status_code,
                    reason="mteam_non_object",
                ),
            )

        code = payload.get("code")
        message = payload.get("message")
        data = payload.get("data")

        if str(code) not in {"0", ""} and code is not None:
            msg = _truncate_detail(message)
            msg_lower = (msg or "").lower()
            if str(code) in {"401", "403"} or "authentication" in msg_lower or "鉴权" in msg_lower:
                return AspectResult(
                    state="unknown",
                    evidence=Evidence(
                        url=str(resp.url),
                        http_status=resp.status_code,
                        reason="mteam_auth_failed",
                        detail=msg or f"code={code}",
                    ),
                )
            return AspectResult(
                state="unknown",
                evidence=Evidence(
                    url=str(resp.url),
                    http_status=resp.status_code,
                    reason=f"mteam_api_error:{code}",
                    detail=msg or None,
                ),
            )

        perm = _coerce_int(data.get("invites")) if isinstance(data, dict) else None
        temp = _coerce_int(data.get("limitInvites")) if isinstance(data, dict) else None
        matched: Optional[str] = None
        if perm is not None or temp is not None:
            perm = perm or 0
            temp = temp or 0
            matched = "invites/limitInvites"
        else:
            perm, temp, matched = _extract_invite_quota(data)
        if perm is None:
            return AspectResult(
                state="unknown",
                evidence=Evidence(
                    url=str(resp.url),
                    http_status=resp.status_code,
                    reason="mteam_invite_quota_not_found",
                ),
            )

        total = perm + (temp or 0)
        return AspectResult(
            state="open" if total > 0 else "closed",
            available=total,
            permanent=perm,
            temporary=temp or 0,
            evidence=Evidence(
                url=str(resp.url),
                http_status=resp.status_code,
                reason="mteam_profile",
                matched=matched,
            ),
        )
