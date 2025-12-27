from __future__ import annotations

import httpx

from pt_invite_watcher.net import DEFAULT_REQUEST_RETRY_ATTEMPTS, DEFAULT_REQUEST_RETRY_DELAY_SECONDS, request_with_retry


class TelegramNotifier:
    def __init__(
        self,
        token: str,
        chat_id: str,
        *,
        retry_attempts: int = DEFAULT_REQUEST_RETRY_ATTEMPTS,
        retry_delay_seconds: int = DEFAULT_REQUEST_RETRY_DELAY_SECONDS,
    ):
        self._token = token
        self._chat_id = chat_id
        self._retry_attempts = max(1, int(retry_attempts or DEFAULT_REQUEST_RETRY_ATTEMPTS))
        self._retry_delay_seconds = max(0, int(retry_delay_seconds or 0))

    async def send(self, text: str) -> bool:
        url = f"https://api.telegram.org/bot{self._token}/sendMessage"
        async with httpx.AsyncClient(timeout=15) as client:
            resp, err, _ = await request_with_retry(
                lambda: client.post(
                    url,
                    json={
                        "chat_id": self._chat_id,
                        "text": text,
                        "disable_web_page_preview": True,
                    },
                ),
                attempts=self._retry_attempts,
                delay_seconds=self._retry_delay_seconds,
            )
            if err:
                return False
            assert resp is not None
            return resp.status_code == 200
