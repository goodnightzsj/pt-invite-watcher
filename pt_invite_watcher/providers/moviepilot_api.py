from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Optional
from urllib.parse import urlparse

import httpx

from pt_invite_watcher.models import Site
from pt_invite_watcher.net import DEFAULT_REQUEST_RETRY_ATTEMPTS, DEFAULT_REQUEST_RETRY_DELAY_SECONDS, request_with_retry


logger = logging.getLogger("pt_invite_watcher.moviepilot")


class MoviePilotError(RuntimeError):
    pass


@dataclass
class _Token:
    access_token: str


def _safe_str(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


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
        self._retry_attempts = max(1, int(retry_attempts or DEFAULT_REQUEST_RETRY_ATTEMPTS))
        self._retry_delay_seconds = max(0, int(retry_delay_seconds or 0))

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
        token = _safe_str(payload.get("access_token"))
        if not token:
            raise MoviePilotError("login failed: access_token missing")

        self._token = _Token(access_token=token)
        return token

    async def _get_token(self, client: httpx.AsyncClient) -> str:
        if self._token and self._token.access_token:
            return self._token.access_token
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
            if resp.status_code == 401:
                token = await self._login(client)
                headers = {"Authorization": f"Bearer {token}"}
                resp, err, used = await request_with_retry(
                    lambda: client.get(url, headers=headers),
                    attempts=self._retry_attempts,
                    delay_seconds=self._retry_delay_seconds,
                )
                if err:
                    raise MoviePilotError(f"list sites failed: {type(err).__name__} {str(err)[:200]}")
                assert resp is not None
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

                url_value = _safe_str(item.get("url"))
                domain_value = _safe_str(item.get("domain")) or _domain_from_url(url_value)
                if not domain_value or not url_value:
                    continue

                sites.append(
                    Site(
                        id=item.get("id"),
                        name=_safe_str(item.get("name")) or domain_value,
                        domain=domain_value,
                        url=url_value,
                        ua=_safe_str(item.get("ua")) or None,
                        cookie=_safe_str(item.get("cookie")) or None,
                        is_active=is_active,
                    )
                )
            return sites
