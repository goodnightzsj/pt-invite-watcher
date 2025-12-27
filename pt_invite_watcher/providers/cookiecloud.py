from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Optional
from urllib.parse import urljoin, urlparse

import httpx

from pt_invite_watcher.net import DEFAULT_REQUEST_RETRY_ATTEMPTS, DEFAULT_REQUEST_RETRY_DELAY_SECONDS, request_with_retry


logger = logging.getLogger("pt_invite_watcher.cookiecloud")


def _join(base: str, path: str) -> str:
    if not base.endswith("/"):
        base += "/"
    return urljoin(base, path.lstrip("/"))


def _cookie_domain_matches(cookie_domain: str, hostname: str) -> bool:
    cd = (cookie_domain or "").lstrip(".").lower()
    hn = (hostname or "").lower()
    if not cd or not hn:
        return False
    return hn == cd or hn.endswith("." + cd)


def _is_expired(expires: Any) -> bool:
    if expires is None:
        return False
    try:
        exp = float(expires)
    except Exception:
        return False
    if exp <= 0:
        return False
    now = datetime.now(timezone.utc).timestamp()
    return exp < now


@dataclass
class CookieCloudClient:
    base_url: str
    uuid: str
    password: str
    timeout_seconds: int = 15
    retry_attempts: int = DEFAULT_REQUEST_RETRY_ATTEMPTS
    retry_delay_seconds: int = DEFAULT_REQUEST_RETRY_DELAY_SECONDS

    async def fetch_cookie_items(self) -> list[dict[str, Any]]:
        if not self.base_url or not self.uuid or not self.password:
            raise ValueError("CookieCloud config missing (COOKIECLOUD_BASE_URL/UUID/PASSWORD)")

        url = _join(self.base_url, f"get/{self.uuid}")
        # CookieCloud is usually on LAN; ignore proxy env vars like ALL_PROXY to avoid 502 via local proxy.
        async with httpx.AsyncClient(timeout=self.timeout_seconds, trust_env=False) as client:
            resp, err, _ = await request_with_retry(
                lambda: client.post(url, json={"password": self.password}),
                attempts=max(1, int(self.retry_attempts or 0)),
                delay_seconds=max(0, int(self.retry_delay_seconds or 0)),
            )
            if err:
                raise err
            assert resp is not None
            resp.raise_for_status()
            data = resp.json()

        cookie_data = data.get("cookie_data") or {}
        cookies: list[dict[str, Any]] = []
        if isinstance(cookie_data, dict):
            for _, items in cookie_data.items():
                if isinstance(items, list):
                    cookies.extend([c for c in items if isinstance(c, dict)])
        return cookies


class CookieManager:
    def __init__(
        self,
        cookie_source: str,
        cookiecloud: Optional[CookieCloudClient],
        refresh_interval_seconds: int,
        prefetched_cookies: Optional[list[dict[str, Any]]] = None,
        prefetched_at: Optional[datetime] = None,
    ):
        self._source = (cookie_source or "auto").strip().lower()
        self._cc = cookiecloud
        self._refresh_interval_seconds = max(30, int(refresh_interval_seconds or 300))

        if prefetched_cookies is not None and prefetched_at is None:
            prefetched_at = datetime.now(timezone.utc)

        self._cached_at: Optional[datetime] = prefetched_at
        self._cached: Optional[list[dict[str, Any]]] = prefetched_cookies

    async def _ensure_cookiecloud(self) -> list[dict[str, Any]]:
        if not self._cc:
            raise ValueError("CookieCloud client not configured")

        now = datetime.now(timezone.utc)
        if self._cached is not None and self._cached_at is not None:
            age = (now - self._cached_at).total_seconds()
            if age < self._refresh_interval_seconds:
                return self._cached

        cookies = await self._cc.fetch_cookie_items()
        self._cached = cookies
        self._cached_at = now
        return cookies

    async def cookie_header_for(self, site_url: str, fallback_cookie: Optional[str]) -> Optional[str]:
        source = self._source
        hostname = urlparse(site_url).hostname or ""

        if source in {"cookiecloud", "auto"}:
            if not self._cc:
                if source == "cookiecloud":
                    return None
            else:
                try:
                    cookies = await self._ensure_cookiecloud()
                    header = self._build_cookie_header(cookies, hostname)
                    if header:
                        return header
                except Exception:
                    logger.exception("cookiecloud failed, fallback=%s", "enabled" if source == "auto" else "disabled")
                    if source == "cookiecloud":
                        return None

        if source in {"moviepilot", "auto"}:
            return (fallback_cookie or "").strip() or None

        return None

    @staticmethod
    def _build_cookie_header(cookies: list[dict[str, Any]], hostname: str) -> str:
        jar: dict[str, str] = {}
        for c in cookies:
            name = c.get("name")
            value = c.get("value")
            domain = c.get("domain")
            if not name or value is None or not domain:
                continue
            if not _cookie_domain_matches(str(domain), hostname):
                continue
            if _is_expired(c.get("expires")):
                continue
            jar[str(name)] = str(value)

        return "; ".join([f"{k}={v}" for k, v in jar.items()])
