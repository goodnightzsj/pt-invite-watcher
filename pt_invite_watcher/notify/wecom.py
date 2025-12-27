from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Optional

import httpx

from pt_invite_watcher.net import DEFAULT_REQUEST_RETRY_ATTEMPTS, DEFAULT_REQUEST_RETRY_DELAY_SECONDS, request_with_retry


@dataclass
class _Token:
    value: str
    expires_at: datetime


class WeComNotifier:
    def __init__(
        self,
        corpid: str,
        app_secret: str,
        agent_id: str,
        to_user: str = "@all",
        to_party: str = "",
        to_tag: str = "",
        base_url: str = "https://qyapi.weixin.qq.com",
        retry_attempts: int = DEFAULT_REQUEST_RETRY_ATTEMPTS,
        retry_delay_seconds: int = DEFAULT_REQUEST_RETRY_DELAY_SECONDS,
    ):
        self._corpid = corpid
        self._app_secret = app_secret
        self._agent_id = agent_id
        self._to_user = to_user or "@all"
        self._to_party = to_party or ""
        self._to_tag = to_tag or ""
        self._base_url = base_url.rstrip("/")
        self._token: Optional[_Token] = None
        self._retry_attempts = max(1, int(retry_attempts or DEFAULT_REQUEST_RETRY_ATTEMPTS))
        self._retry_delay_seconds = max(0, int(retry_delay_seconds or 0))

    async def _get_token(self, client: httpx.AsyncClient) -> Optional[str]:
        now = datetime.now(timezone.utc)
        if self._token and self._token.expires_at > now + timedelta(seconds=30):
            return self._token.value

        url = f"{self._base_url}/cgi-bin/gettoken"
        resp, err, _ = await request_with_retry(
            lambda: client.get(url, params={"corpid": self._corpid, "corpsecret": self._app_secret}),
            attempts=self._retry_attempts,
            delay_seconds=self._retry_delay_seconds,
        )
        if err:
            return None
        assert resp is not None
        if resp.status_code != 200:
            return None
        data = resp.json()
        if data.get("errcode") != 0:
            return None

        expires_in = int(data.get("expires_in") or 7200)
        token = data.get("access_token")
        if not token:
            return None
        self._token = _Token(value=token, expires_at=now + timedelta(seconds=expires_in))
        return token

    async def send(self, text: str) -> bool:
        async with httpx.AsyncClient(timeout=15) as client:
            token = await self._get_token(client)
            if not token:
                return False
            url = f"{self._base_url}/cgi-bin/message/send"
            resp, err, _ = await request_with_retry(
                lambda: client.post(
                    url,
                    params={"access_token": token},
                    json={
                        "touser": self._to_user,
                        "toparty": self._to_party,
                        "totag": self._to_tag,
                        "msgtype": "text",
                        "agentid": self._agent_id,
                        "text": {"content": text},
                        "safe": 0,
                    },
                ),
                attempts=self._retry_attempts,
                delay_seconds=self._retry_delay_seconds,
            )
            if err:
                return False
            assert resp is not None
            if resp.status_code != 200:
                return False
            data = resp.json()
            return data.get("errcode") == 0
