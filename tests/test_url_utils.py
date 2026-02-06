import unittest

from pt_invite_watcher.utils.url import hosts_related, join_url, page_kind_from_url


class UrlUtilsTest(unittest.TestCase):
    def test_join_url(self) -> None:
        self.assertEqual(join_url("https://example.com", "signup.php"), "https://example.com/signup.php")
        self.assertEqual(join_url("https://example.com/", "signup.php"), "https://example.com/signup.php")
        self.assertEqual(join_url("https://example.com", "/signup.php"), "https://example.com/signup.php")
        self.assertEqual(join_url("https://example.com/base", "signup.php"), "https://example.com/base/signup.php")
        self.assertEqual(join_url("https://example.com/base/", "signup.php"), "https://example.com/base/signup.php")
        self.assertEqual(join_url("https://example.com/base/", "/signup.php"), "https://example.com/base/signup.php")
        self.assertEqual(join_url("", "signup.php"), "/signup.php")

    def test_page_kind_from_url(self) -> None:
        self.assertIsNone(page_kind_from_url(""))
        self.assertEqual(page_kind_from_url("https://example.com/"), "home")
        self.assertEqual(page_kind_from_url("https://example.com/usercp.php"), "usercp")
        self.assertEqual(page_kind_from_url("https://example.com/signup"), "signup")
        self.assertEqual(page_kind_from_url("https://example.com/userdetails.php?id=1"), "userdetail")
        self.assertEqual(page_kind_from_url("https://example.com/invite.php?id=1"), "invite")
        self.assertEqual(page_kind_from_url("https://example.com/login.php"), "login")
        self.assertEqual(page_kind_from_url("https://example.com/torrents.php"), "torrents.php")

    def test_hosts_related(self) -> None:
        self.assertTrue(hosts_related("", "a.example.com"))
        self.assertTrue(hosts_related("example.com", "example.com"))
        self.assertTrue(hosts_related("a.example.com", "example.com"))
        self.assertTrue(hosts_related("example.com", "a.example.com"))
        self.assertFalse(hosts_related("a.example.com", "b.example.com"))


if __name__ == "__main__":
    unittest.main()
