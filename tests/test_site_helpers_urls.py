import unittest

from pt_invite_watcher.routes.site_helpers import derive_site_page_urls


class SiteHelpersURLsTest(unittest.TestCase):
    def test_nexusphp_defaults(self) -> None:
        urls = derive_site_page_urls(base_url="https://example.com", template="nexusphp")
        self.assertEqual(urls["registration_url"], "https://example.com/signup.php")
        self.assertEqual(urls["invite_url"], "https://example.com/invite.php")

    def test_mteam_defaults(self) -> None:
        urls = derive_site_page_urls(base_url="https://example.com", template="mteam")
        self.assertEqual(urls["registration_url"], "https://example.com/signup")
        self.assertEqual(urls["invite_url"], "https://example.com/invite")

    def test_custom_requires_paths(self) -> None:
        urls = derive_site_page_urls(base_url="https://example.com", template="custom")
        self.assertEqual(urls["registration_url"], "")
        self.assertEqual(urls["invite_url"], "")

    def test_custom_paths(self) -> None:
        urls = derive_site_page_urls(
            base_url="https://example.com",
            template="custom",
            registration_path="signup.php",
            invite_path="invite.php?x=1",
        )
        self.assertEqual(urls["registration_url"], "https://example.com/signup.php")
        self.assertEqual(urls["invite_url"], "https://example.com/invite.php?x=1")

    def test_invite_uid_overrides_nexusphp_invite_path(self) -> None:
        urls = derive_site_page_urls(
            base_url="https://example.com",
            template="nexusphp",
            invite_path="invite.php?x=1",
            invite_uid="42",
        )
        self.assertEqual(urls["invite_url"], "https://example.com/invite.php?id=42")

    def test_blank_template_defaults_and_invite_uid(self) -> None:
        urls = derive_site_page_urls(
            base_url="https://example.com",
            template="",
            invite_uid="7",
        )
        self.assertEqual(urls["registration_url"], "https://example.com/signup.php")
        self.assertEqual(urls["invite_url"], "https://example.com/invite.php?id=7")


if __name__ == "__main__":
    unittest.main()

