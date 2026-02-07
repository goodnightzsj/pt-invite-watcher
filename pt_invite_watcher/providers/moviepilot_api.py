from __future__ import annotations

import base64
import hashlib
import json
import logging
from contextlib import suppress
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Optional
from urllib.parse import urlparse

import httpx

from pt_invite_watcher.models import Site
from pt_invite_watcher.net import DEFAULT_REQUEST_RETRY_ATTEMPTS, DEFAULT_REQUEST_RETRY_DELAY_SECONDS, request_with_retry
from pt_invite_watcher.utils.parse import safe_str


logger = logging.getLogger("pt_invite_watcher.moviepilot")


class MoviePilotError(RuntimeError):
    pass


@dataclass
class _Token:
    access_token: str
    expires_at: Optional[datetime] = None


def _hash_secret(secret: str) -> str:
    s = safe_str(secret)
    if not s:
        return ""
    return hashlib.sha256(s.encode("utf-8")).hexdigest()


def _token_cache_key(*, base_url: str, username: str, password: str, otp_password: Optional[str]) -> str:
    b = safe_str(base_url).rstrip("/")
    u = safe_str(username)
    if not b or not u:
        return ""
    pw = _hash_secret(password)
    otp = _hash_secret(safe_str(otp_password))
    return f"{b}|{u}|{pw}|{otp}"


_TOKEN_CACHE: dict[str, _Token] = {}


def _jwt_expires_at(token: str) -> Optional[datetime]:
    """
    Best-effort JWT `exp` parsing.

    MoviePilot access_token is often a JWT. If we can parse `exp`, we can avoid
    using a known-expired cached token and save an extra 401 round-trip.
    """
    raw = safe_str(token)
    parts = raw.split(".")
    if len(parts) < 2:
        return None
    payload_b64 = parts[1]
    if not payload_b64:
        return None
    try:
        padded = payload_b64 + "=" * (-len(payload_b64) % 4)
        decoded = base64.urlsafe_b64decode(padded.encode("ascii"))
        obj = json.loads(decoded.decode("utf-8"))
    except Exception:
        return None
    if not isinstance(obj, dict):
        return None
    exp = obj.get("exp")
    try:
        exp_ts = int(exp)
    except Exception:
        return None
    if exp_ts <= 0:
        return None
    return datetime.fromtimestamp(exp_ts, tz=timezone.utc)


def _token_is_valid(token: _Token, *, now: datetime) -> bool:
    access_token = safe_str(getattr(token, "access_token", ""))
    if not access_token:
        return False
    expires_at = getattr(token, "expires_at", None)
    if not isinstance(expires_at, datetime):
        return True
    return expires_at > (now + timedelta(seconds=30))


def _domain_from_url(url: str) -> str:
    try:
        host = urlparse(url).hostname
        return (host or "").lower()
    except Exception:
        return ""


class MoviePilotClient:
    def __init__(
        self,
        base_url: str,
        username: str,
        password: str,
        otp_password: Optional[str] = None,
        timeout_seconds: int = 15,
        retry_attempts: int = DEFAULT_REQUEST_RETRY_ATTEMPTS,
        retry_delay_seconds: int = DEFAULT_REQUEST_RETRY_DELAY_SECONDS,
    ):
        self._base_url = base_url.rstrip("/")
        self._username = username
        self._password = password
        self._otp_password = otp_password
        self._timeout = timeout_seconds
        self._token: Optional[_Token] = None
        self._token_cache_key = _token_cache_key(
            base_url=self._base_url,
            username=self._username,
            password=self._password,
            otp_password=self._otp_password,
        )
        self._retry_attempts = max(1, int(retry_attempts or DEFAULT_REQUEST_RETRY_ATTEMPTS))
        self._retry_delay_seconds = max(0, int(retry_delay_seconds or 0))

        if self._token_cache_key:
            cached = _TOKEN_CACHE.get(self._token_cache_key)
            if cached and _token_is_valid(cached, now=datetime.now(timezone.utc)):
                self._token = cached

    async def _login(self, client: httpx.AsyncClient) -> str:
        if not self._base_url:
            raise MoviePilotError("MoviePilot base_url is empty (MP_BASE_URL)")
        if not self._username or not self._password:
            raise MoviePilotError("MoviePilot credentials missing (MP_USERNAME/MP_PASSWORD)")

        url = f"{self._base_url}/api/v1/login/access-token"
        data: dict[str, str] = {"username": self._username, "password": self._password}
        if self._otp_password:
            data["otp_password"] = self._otp_password

        resp, err, used = await request_with_retry(
            lambda: client.post(url, data=data),
            attempts=self._retry_attempts,
            delay_seconds=self._retry_delay_seconds,
        )
        if err:
            raise MoviePilotError(f"login failed: {type(err).__name__} {str(err)[:200]}")
        assert resp is not None
        try:
            if resp.status_code != 200:
                hint = ""
                if resp.status_code == 404:
                    hint = (
                        " (check MP_BASE_URL: it must be the MoviePilot backend address; "
                        "verify in browser that `${MP_BASE_URL}/docs` is reachable)"
                    )
                retry_hint = f" (retries={used})" if used > 1 else ""
                raise MoviePilotError(f"login failed: {resp.status_code} {resp.text[:200]}{hint}{retry_hint}")

            payload = resp.json()
            token = safe_str(payload.get("access_token"))
            if not token:
                raise MoviePilotError("login failed: access_token missing")

            self._token = _Token(access_token=token, expires_at=_jwt_expires_at(token))
            if self._token_cache_key:
                _TOKEN_CACHE[self._token_cache_key] = self._token
            return token
        finally:
            with suppress(Exception):
                await resp.aclose()

    async def _get_token(self, client: httpx.AsyncClient) -> str:
        now = datetime.now(timezone.utc)
        if self._token and _token_is_valid(self._token, now=now):
            return self._token.access_token
        if self._token_cache_key:
            cached = _TOKEN_CACHE.get(self._token_cache_key)
            if cached and _token_is_valid(cached, now=now):
                self._token = cached
                return cached.access_token
        return await self._login(client)

    async def list_sites(self, only_active: bool = True) -> list[Site]:
        # MoviePilot is usually on LAN; ignore proxy env vars like ALL_PROXY to avoid 502 via local proxy.
        async with httpx.AsyncClient(timeout=self._timeout, trust_env=False) as client:
            token = await self._get_token(client)
            url = f"{self._base_url}/api/v1/site/"
            headers = {"Authorization": f"Bearer {token}"}
            resp, err, used = await request_with_retry(
                lambda: client.get(url, headers=headers),
                attempts=self._retry_attempts,
                delay_seconds=self._retry_delay_seconds,
            )
            if err:
                raise MoviePilotError(f"list sites failed: {type(err).__name__} {str(err)[:200]}")
            assert resp is not None
            try:
                if resp.status_code == 401:
                    with suppress(Exception):
                        await resp.aclose()
                    token = await self._login(client)
                    headers = {"Authorization": f"Bearer {token}"}
                    resp2, err2, used2 = await request_with_retry(
                        lambda: client.get(url, headers=headers),
                        attempts=self._retry_attempts,
                        delay_seconds=self._retry_delay_seconds,
                    )
                    if err2:
                        raise MoviePilotError(f"list sites failed: {type(err2).__name__} {str(err2)[:200]}")
                    assert resp2 is not None
                    resp = resp2
                    used = used2

                if resp.status_code != 200:
                    retry_hint = f" (retries={used})" if used > 1 else ""
                    raise MoviePilotError(f"list sites failed: {resp.status_code} {resp.text[:200]}{retry_hint}")

                items = resp.json()
                if not isinstance(items, list):
                    raise MoviePilotError("list sites failed: response is not a list")

                sites: list[Site] = []
                for item in items:
                    if not isinstance(item, dict):
                        continue
                    is_active = bool(item.get("is_active", True))
                    if only_active and not is_active:
                        continue

                    url_value = safe_str(item.get("url"))
                    domain_value = safe_str(item.get("domain")) or _domain_from_url(url_value)
                    if not domain_value or not url_value:
                        continue

                    sites.append(
                        Site(
                            id=item.get("id"),
                            name=safe_str(item.get("name")) or domain_value,
                            domain=domain_value,
                            url=url_value,
                            ua=safe_str(item.get("ua")) or None,
                            cookie=safe_str(item.get("cookie")) or None,
                            is_active=is_active,
                        )
                    )
                return sites
            finally:
                with suppress(Exception):
                    await resp.aclose()
