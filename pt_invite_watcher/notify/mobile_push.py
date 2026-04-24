"""Native mobile push delivery — APN (iOS) + FCM (Android).

Design notes:

- Backend is OPT-IN. Without the corresponding env vars set, this module
  is a no-op; no tokens are fetched, no HTTP requests made.
- FCM uses Legacy HTTP server-key API (single env var, simplest). Migrating
  to FCM HTTP v1 later is a drop-in change in `_send_fcm()`.
- APN uses JWT-based HTTP/2 API. We don't vendor the `apns2` package to keep
  runtime deps minimal; instead we use httpx's HTTP/2 + manual JWT. This
  also lets us retry via the existing net.py retry helper.

Credentials (all optional, each controls one platform):

  PTIW_FCM_SERVER_KEY     Legacy FCM server key (string). Presence enables Android.
  PTIW_APNS_KEY_P8        Contents of AuthKey_<KEY_ID>.p8 (PKCS#8 PEM).
  PTIW_APNS_KEY_ID        10-char key ID from Apple Developer Portal.
  PTIW_APNS_TEAM_ID       10-char team ID.
  PTIW_APNS_BUNDLE_ID     App bundle id, e.g. com.pt_invite_watcher.app.
  PTIW_APNS_USE_SANDBOX   "1" to use api.sandbox.push.apple.com (default prod).

Called from `scanner_change.py` after diffing site state — the invite-
opened transition is the only event that triggers a push today; add more
triggers there, not here.
"""
from __future__ import annotations

import base64
import json
import logging
import os
import time
from typing import Optional

import httpx

from pt_invite_watcher.storage.device_tokens_store import list_device_tokens, remove_device_token


logger = logging.getLogger("pt_invite_watcher.push")


def _fcm_server_key() -> Optional[str]:
    key = os.getenv("PTIW_FCM_SERVER_KEY", "").strip()
    return key or None


def _apns_configured() -> bool:
    return all(
        os.getenv(n, "").strip()
        for n in ("PTIW_APNS_KEY_P8", "PTIW_APNS_KEY_ID", "PTIW_APNS_TEAM_ID", "PTIW_APNS_BUNDLE_ID")
    )


def is_configured() -> bool:
    return _fcm_server_key() is not None or _apns_configured()


async def dispatch_invites_opened(
    store,
    *,
    domain: str,
    site_name: str,
    count: Optional[int],
) -> int:
    """Send a push to every registered device subscribed to `domain`.
    Returns count of pushes attempted (best-effort; individual failures log).
    """
    if not is_configured():
        return 0
    tokens = await list_device_tokens(store, domain=domain)
    if not tokens:
        return 0

    title = f"邀请已开放：{site_name or domain}"
    body = f"{domain}" + (f" · 可用 {count}" if count is not None else "")
    sent = 0

    fcm_key = _fcm_server_key()
    apns_ready = _apns_configured()

    async with httpx.AsyncClient(timeout=10.0, http2=True) as client:
        for row in tokens:
            try:
                if row["platform"] == "android" and fcm_key:
                    await _send_fcm(client, fcm_key, row["token"], title, body, domain, store)
                    sent += 1
                elif row["platform"] == "ios" and apns_ready:
                    await _send_apns(client, row["token"], title, body, domain, store)
                    sent += 1
            except Exception:
                logger.exception("push dispatch failed for %s device", row["platform"])
    return sent


async def _send_fcm(
    client: httpx.AsyncClient,
    server_key: str,
    token: str,
    title: str,
    body: str,
    domain: str,
    store,
) -> None:
    resp = await client.post(
        "https://fcm.googleapis.com/fcm/send",
        headers={
            "Authorization": f"key={server_key}",
            "Content-Type": "application/json",
        },
        json={
            "to": token,
            "notification": {"title": title, "body": body},
            "data": {"domain": domain, "type": "invites_opened"},
        },
    )
    if resp.status_code >= 300:
        logger.warning("FCM %s: %s", resp.status_code, resp.text[:200])
        return
    payload = resp.json()
    # FCM signals "Unregistered" / "InvalidRegistration" per-token in the
    # response. Drop those tokens so we don't re-send forever.
    for result in (payload.get("results") or []):
        err = result.get("error") or ""
        if err in ("NotRegistered", "InvalidRegistration"):
            await remove_device_token(store, token)
            break


async def _send_apns(
    client: httpx.AsyncClient,
    token: str,
    title: str,
    body: str,
    domain: str,
    store,
) -> None:
    jwt = _apns_jwt()
    if not jwt:
        return
    bundle = os.getenv("PTIW_APNS_BUNDLE_ID", "")
    use_sandbox = os.getenv("PTIW_APNS_USE_SANDBOX", "").strip() == "1"
    host = "api.sandbox.push.apple.com" if use_sandbox else "api.push.apple.com"
    resp = await client.post(
        f"https://{host}/3/device/{token}",
        headers={
            "authorization": f"bearer {jwt}",
            "apns-topic": bundle,
            "apns-push-type": "alert",
            "apns-priority": "10",
        },
        content=json.dumps({
            "aps": {
                "alert": {"title": title, "body": body},
                "sound": "default",
            },
            "domain": domain,
            "type": "invites_opened",
        }),
    )
    if resp.status_code == 410:
        # APN tells us the token is no longer valid.
        await remove_device_token(store, token)
    elif resp.status_code >= 300:
        logger.warning("APNS %s: %s", resp.status_code, resp.text[:200])


def _apns_jwt() -> Optional[str]:
    """Build APN's JWT Bearer (ES256 signed). Cached for ~50 min —
    Apple rejects JWTs older than 60 min."""
    global _APNS_JWT_CACHE  # noqa: PLW0603
    now = int(time.time())
    cached = _APNS_JWT_CACHE
    if cached and (now - cached[0]) < 50 * 60:
        return cached[1]

    key_p8 = os.getenv("PTIW_APNS_KEY_P8", "").strip()
    key_id = os.getenv("PTIW_APNS_KEY_ID", "").strip()
    team_id = os.getenv("PTIW_APNS_TEAM_ID", "").strip()
    if not (key_p8 and key_id and team_id):
        return None

    try:
        # Lazy import — the cryptography package is heavy; only pulled in when
        # APNS is actually configured.
        from cryptography.hazmat.primitives import hashes, serialization
        from cryptography.hazmat.primitives.asymmetric import ec
        from cryptography.hazmat.primitives.asymmetric.utils import decode_dss_signature
    except Exception:
        logger.warning("APNS configured but `cryptography` not available — install with pip install cryptography")
        return None

    header = _b64url(json.dumps({"alg": "ES256", "kid": key_id}).encode())
    claims = _b64url(json.dumps({"iss": team_id, "iat": now}).encode())
    signing_input = f"{header}.{claims}".encode()

    try:
        private_key = serialization.load_pem_private_key(key_p8.encode(), password=None)
        if not isinstance(private_key, ec.EllipticCurvePrivateKey):
            logger.warning("APNS key is not an ECDSA key")
            return None
        der_sig = private_key.sign(signing_input, ec.ECDSA(hashes.SHA256()))
        r, s = decode_dss_signature(der_sig)
        raw_sig = r.to_bytes(32, "big") + s.to_bytes(32, "big")
    except Exception:
        logger.exception("APNS JWT sign failed")
        return None

    token = f"{header}.{claims}.{_b64url(raw_sig)}"
    _APNS_JWT_CACHE = (now, token)
    return token


_APNS_JWT_CACHE: Optional[tuple[int, str]] = None


def _b64url(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode()


__all__ = ["dispatch_invites_opened", "is_configured"]
