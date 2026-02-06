import unittest
from dataclasses import dataclass

from pt_invite_watcher.models import AspectResult, Evidence, Site
from pt_invite_watcher.scanner_invites import check_invites_for_site


@dataclass
class _Call:
    name: str
    kwargs: dict


class _FakeStore:
    def __init__(self) -> None:
        self.calls: list[_Call] = []

    async def add_event(self, **kwargs):
        self.calls.append(_Call("add_event", kwargs))


class _FakeDetector:
    def __init__(self, result: AspectResult) -> None:
        self.result = result
        self.calls: list[_Call] = []

    async def check_invites(self, client, site, user_agent, cookie_header, *, retry_delay_seconds: int = -1) -> AspectResult:
        self.calls.append(
            _Call(
                "check_invites",
                {
                    "cookie_header": cookie_header,
                    "retry_delay_seconds": retry_delay_seconds,
                },
            )
        )
        return self.result


class _FakeMTeamDetector:
    def __init__(self, result: AspectResult) -> None:
        self.result = result
        self.calls: list[_Call] = []

    async def check_invites(self, client, site, user_agent, *, retry_delay_seconds: int = -1) -> AspectResult:
        self.calls.append(_Call("check_invites", {"retry_delay_seconds": retry_delay_seconds}))
        return self.result


class ScannerInvitesTest(unittest.IsolatedAsyncioTestCase):
    async def test_manual_site_no_cookie_skips_and_emits_event(self) -> None:
        store = _FakeStore()
        det = _FakeDetector(AspectResult(state="open", evidence=Evidence(url="x", http_status=200, reason="ok")))
        mteam = _FakeMTeamDetector(AspectResult(state="open", evidence=Evidence(url="x", http_status=200, reason="ok")))

        site = Site(id=None, name="Manual", domain="manual.com", url="https://manual.com")
        invites = await check_invites_for_site(
            is_mteam=False,
            store=store,
            detector=det,
            mteam_detector=mteam,
            client=None,
            site=site,
            user_agent=None,
            cookie_header_for_invites=None,
            inv_path="invite.php",
            retry_delay_seconds=7,
            domain="manual.com",
        )
        self.assertEqual(invites.state, "unknown")
        self.assertEqual(invites.evidence.reason, "manual_no_cookie_skip_invites")
        self.assertEqual(invites.evidence.url, "https://manual.com/invite.php")
        self.assertEqual(len(store.calls), 1)
        self.assertEqual(store.calls[0].kwargs["action"], "skip_invites")
        self.assertEqual(store.calls[0].kwargs["level"], "warn")
        self.assertEqual(store.calls[0].kwargs["domain"], "manual.com")
        self.assertEqual(det.calls, [])
        self.assertEqual(mteam.calls, [])

    async def test_mteam_api_key_unknown_falls_back_to_cookie_without_retry_param(self) -> None:
        store = _FakeStore()
        det = _FakeDetector(AspectResult(state="open", evidence=Evidence(url="x", http_status=200, reason="ok")))
        mteam = _FakeMTeamDetector(AspectResult(state="unknown", evidence=Evidence(url="x", http_status=200, reason="mteam")))

        site = Site(id=1, name="M", domain="m-team.cc", url="https://m-team.cc", did="KEY")
        invites = await check_invites_for_site(
            is_mteam=True,
            store=store,
            detector=det,
            mteam_detector=mteam,
            client=None,
            site=site,
            user_agent="ua",
            cookie_header_for_invites="cookie",
            inv_path="invite.php",
            retry_delay_seconds=7,
            domain="m-team.cc",
        )
        self.assertEqual(invites.state, "open")
        self.assertEqual(len(mteam.calls), 1)
        self.assertEqual(mteam.calls[0].kwargs["retry_delay_seconds"], 7)
        self.assertEqual(len(det.calls), 1)
        self.assertEqual(det.calls[0].kwargs["cookie_header"], "cookie")
        self.assertEqual(det.calls[0].kwargs["retry_delay_seconds"], -1)
        self.assertEqual(store.calls, [])

    async def test_mteam_api_key_success_does_not_fallback(self) -> None:
        store = _FakeStore()
        det = _FakeDetector(AspectResult(state="open", evidence=Evidence(url="x", http_status=200, reason="ok")))
        mteam = _FakeMTeamDetector(AspectResult(state="open", evidence=Evidence(url="x", http_status=200, reason="mteam")))

        site = Site(id=1, name="M", domain="m-team.cc", url="https://m-team.cc", did="KEY")
        invites = await check_invites_for_site(
            is_mteam=True,
            store=store,
            detector=det,
            mteam_detector=mteam,
            client=None,
            site=site,
            user_agent="ua",
            cookie_header_for_invites="cookie",
            inv_path="invite.php",
            retry_delay_seconds=7,
            domain="m-team.cc",
        )
        self.assertEqual(invites.state, "open")
        self.assertEqual(len(mteam.calls), 1)
        self.assertEqual(det.calls, [])
        self.assertEqual(store.calls, [])

    async def test_mteam_no_api_key_with_cookie_uses_detector_with_retry_delay(self) -> None:
        store = _FakeStore()
        det = _FakeDetector(AspectResult(state="open", evidence=Evidence(url="x", http_status=200, reason="ok")))
        mteam = _FakeMTeamDetector(AspectResult(state="open", evidence=Evidence(url="x", http_status=200, reason="mteam")))

        site = Site(id=1, name="M", domain="m-team.cc", url="https://m-team.cc", did="")
        invites = await check_invites_for_site(
            is_mteam=True,
            store=store,
            detector=det,
            mteam_detector=mteam,
            client=None,
            site=site,
            user_agent="ua",
            cookie_header_for_invites="cookie",
            inv_path="invite.php",
            retry_delay_seconds=7,
            domain="m-team.cc",
        )
        self.assertEqual(invites.state, "open")
        self.assertEqual(mteam.calls, [])
        self.assertEqual(len(det.calls), 1)
        self.assertEqual(det.calls[0].kwargs["retry_delay_seconds"], 7)

    async def test_mteam_no_api_key_no_cookie_returns_missing_auth(self) -> None:
        store = _FakeStore()
        det = _FakeDetector(AspectResult(state="open", evidence=Evidence(url="x", http_status=200, reason="ok")))
        mteam = _FakeMTeamDetector(AspectResult(state="open", evidence=Evidence(url="x", http_status=200, reason="mteam")))

        site = Site(id=1, name="M", domain="m-team.cc", url="https://m-team.cc", did="")
        invites = await check_invites_for_site(
            is_mteam=True,
            store=store,
            detector=det,
            mteam_detector=mteam,
            client=None,
            site=site,
            user_agent="ua",
            cookie_header_for_invites=None,
            inv_path="invite.php",
            retry_delay_seconds=7,
            domain="m-team.cc",
        )
        self.assertEqual(invites.state, "unknown")
        self.assertEqual(invites.evidence.reason, "missing_auth")
        self.assertEqual(det.calls, [])
        self.assertEqual(mteam.calls, [])


if __name__ == "__main__":
    unittest.main()

