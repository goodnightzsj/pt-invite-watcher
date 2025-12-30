from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import json
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

    @staticmethod
    def _safe_json(resp: httpx.Response) -> dict:
        try:
            return resp.json()
        except Exception:
            try:
                return json.loads(resp.text or "")
            except Exception:
                return {}

    async def _get_token_detail(self, client: httpx.AsyncClient) -> tuple[Optional[str], str, dict]:
        now = datetime.now(timezone.utc)
        if self._token and self._token.expires_at > now + timedelta(seconds=30):
            return self._token.value, "token cached", {"stage": "gettoken", "cached": True}

        url = f"{self._base_url}/cgi-bin/gettoken"
        resp, err, _ = await request_with_retry(
            lambda: client.get(url, params={"corpid": self._corpid, "corpsecret": self._app_secret}),
            attempts=self._retry_attempts,
            delay_seconds=self._retry_delay_seconds,
        )
        if err:
            return None, f"gettoken request error: {type(err).__name__}", {"stage": "gettoken", "error": str(err)}
        assert resp is not None
        data = self._safe_json(resp)
        if resp.status_code != 200:
            return (
                None,
                f"gettoken http {resp.status_code}",
                {"stage": "gettoken", "http_status": resp.status_code, "response": data or (resp.text or "")[:200]},
            )
        if data.get("errcode") != 0:
            return (
                None,
                f"gettoken errcode={data.get('errcode')} errmsg={data.get('errmsg')}",
                {"stage": "gettoken", "http_status": resp.status_code, "response": data},
            )

        expires_in = int(data.get("expires_in") or 7200)
        token = data.get("access_token")
        if not token:
            return (
                None,
                "gettoken missing access_token",
                {"stage": "gettoken", "http_status": resp.status_code, "response": data},
            )
        self._token = _Token(value=token, expires_at=now + timedelta(seconds=expires_in))
        return token, "token ok", {"stage": "gettoken", "http_status": resp.status_code, "expires_in": expires_in}

    async def send_detail(self, text: str) -> tuple[bool, str, dict]:
        async with httpx.AsyncClient(timeout=15) as client:
            token, token_msg, token_detail = await self._get_token_detail(client)
            if not token:
                return False, token_msg, token_detail
            try:
                agentid = int(str(self._agent_id).strip())
            except Exception:
                return (
                    False,
                    f"invalid agent_id: {self._agent_id}",
                    {"stage": "send", "error": "invalid_agent_id", "agent_id": self._agent_id},
                )
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
                        "agentid": agentid,
                        "text": {"content": text},
                        "safe": 0,
                    },
                ),
                attempts=self._retry_attempts,
                delay_seconds=self._retry_delay_seconds,
            )
            if err:
                return (
                    False,
                    f"send request error: {type(err).__name__}",
                    {"stage": "send", "error": str(err), "token": token_detail},
                )
            assert resp is not None
            data = self._safe_json(resp)
            if resp.status_code != 200:
                return (
                    False,
                    f"send http {resp.status_code}",
                    {"stage": "send", "http_status": resp.status_code, "response": data or (resp.text or "")[:200], "token": token_detail},
                )
            if data.get("errcode") != 0:
                return (
                    False,
                    f"send errcode={data.get('errcode')} errmsg={data.get('errmsg')}",
                    {"stage": "send", "http_status": resp.status_code, "response": data, "token": token_detail},
                )
            return True, "sent", {"stage": "send", "http_status": resp.status_code, "response": data, "token": token_detail}

    async def send(self, text: str) -> bool:
        ok, _, _ = await self.send_detail(text)
        return ok
