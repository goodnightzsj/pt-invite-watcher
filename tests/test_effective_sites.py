import unittest

from pt_invite_watcher.effective_sites import merge_sites
from pt_invite_watcher.models import Site


class MergeSitesTest(unittest.TestCase):
    def test_override_merges_fields(self) -> None:
        mp_sites = [
            Site(
                id=1,
                name="MP",
                domain="example.com",
                url="https://example.com",
                ua="ua",
                cookie="mp_cookie",
                cookie_override=None,
                authorization=None,
                did=None,
                is_active=True,
            )
        ]
        entries = {
            "example.com": {
                "mode": "override",
                "name": "Local",
                "cookie": "local_cookie",
                "template": "nexusphp",
            }
        }

        merged = merge_sites(mp_sites, entries)
        by_domain = {s.domain: s for s in merged}
        self.assertIn("example.com", by_domain)
        site = by_domain["example.com"]
        self.assertEqual(site.id, 1)
        self.assertEqual(site.name, "Local")
        self.assertEqual(site.cookie, "mp_cookie")
        self.assertEqual(site.cookie_override, "local_cookie")
        self.assertEqual(site.template, "nexusphp")

    def test_manual_site_added_when_not_in_mp(self) -> None:
        mp_sites: list[Site] = []
        entries = {
            "manual.example": {
                "mode": "manual",
                "name": "Manual",
                "url": "https://manual.example",
                "template": "custom",
                "registration_path": "signup",
                "invite_path": "invite",
            }
        }
        merged = merge_sites(mp_sites, entries)
        by_domain = {s.domain: s for s in merged}
        self.assertIn("manual.example", by_domain)
        site = by_domain["manual.example"]
        self.assertIsNone(site.id)
        self.assertEqual(site.name, "Manual")
        self.assertEqual(site.url, "https://manual.example")
        self.assertEqual(site.template, "custom")

    def test_mteam_defaults(self) -> None:
        mp_sites = [
            Site(
                id=2,
                name="M-Team",
                domain="x.m-team.cc",
                url="https://x.m-team.cc",
                ua=None,
                cookie=None,
                cookie_override=None,
                authorization=None,
                did=None,
                is_active=True,
            )
        ]
        merged = merge_sites(mp_sites, {})
        by_domain = {s.domain: s for s in merged}
        site = by_domain["x.m-team.cc"]
        self.assertEqual(site.template, "mteam")
        self.assertEqual(site.registration_path, "signup")
        self.assertEqual(site.invite_path, "invite")

    def test_mteam_manual_defaults(self) -> None:
        entries = {
            "x.m-team.cc": {
                "mode": "manual",
                "name": "M-Team",
                "url": "https://x.m-team.cc",
            }
        }
        merged = merge_sites([], entries)
        by_domain = {s.domain: s for s in merged}
        site = by_domain["x.m-team.cc"]
        self.assertEqual(site.template, "mteam")
        self.assertEqual(site.registration_path, "signup")
        self.assertEqual(site.invite_path, "invite")

    def test_mteam_override_template_can_disable_mteam_default_paths(self) -> None:
        mp_sites = [
            Site(
                id=2,
                name="M-Team",
                domain="x.m-team.cc",
                url="https://x.m-team.cc",
                ua=None,
                cookie=None,
                cookie_override=None,
                authorization=None,
                did=None,
                is_active=True,
            )
        ]
        merged = merge_sites(mp_sites, {"x.m-team.cc": {"mode": "override", "template": "nexusphp"}})
        by_domain = {s.domain: s for s in merged}
        site = by_domain["x.m-team.cc"]
        self.assertEqual(site.template, "nexusphp")
        self.assertIsNone(site.registration_path)
        self.assertIsNone(site.invite_path)


if __name__ == "__main__":
    unittest.main()
