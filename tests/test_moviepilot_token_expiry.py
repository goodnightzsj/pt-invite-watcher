import base64
import json
import unittest
from datetime import datetime, timedelta, timezone

import pt_invite_watcher.providers.moviepilot_api as moviepilot_api


def _b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode("ascii").rstrip("=")


def _jwt(payload: dict) -> str:
    header = {"alg": "none", "typ": "JWT"}
    return f"{_b64url(json.dumps(header).encode('utf-8'))}.{_b64url(json.dumps(payload).encode('utf-8'))}."


class MoviePilotTokenExpiryTest(unittest.TestCase):
    def test_jwt_expires_at_parses_exp(self) -> None:
        exp = int((datetime.now(timezone.utc) + timedelta(seconds=3600)).timestamp())
        token = _jwt({"exp": exp})
        expires_at = moviepilot_api._jwt_expires_at(token)
        self.assertIsNotNone(expires_at)
        assert expires_at is not None
        self.assertEqual(int(expires_at.timestamp()), exp)

    def test_jwt_expires_at_returns_none_for_non_jwt(self) -> None:
        self.assertIsNone(moviepilot_api._jwt_expires_at("not-a-jwt"))

    def test_token_is_valid_uses_expiry(self) -> None:
        now = datetime.now(timezone.utc)
        valid = moviepilot_api._Token(access_token="x", expires_at=now + timedelta(seconds=120))
        self.assertTrue(moviepilot_api._token_is_valid(valid, now=now))

        expired = moviepilot_api._Token(access_token="x", expires_at=now - timedelta(seconds=1))
        self.assertFalse(moviepilot_api._token_is_valid(expired, now=now))

        unknown = moviepilot_api._Token(access_token="x", expires_at=None)
        self.assertTrue(moviepilot_api._token_is_valid(unknown, now=now))


if __name__ == "__main__":
    unittest.main()

