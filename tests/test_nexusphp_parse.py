import unittest
from urllib.parse import urljoin

from pt_invite_watcher.engines.nexusphp_parse import (
    _extract_invite_url_from_html,
    _extract_text,
    _has_invite_field,
    _has_signup_form,
    _invite_send_action_status,
)


class NexusPhpParseTest(unittest.TestCase):
    def test_extract_text_strips_html(self) -> None:
        html = "<html><body>Hello <b>World</b></body></html>"
        self.assertEqual(_extract_text(html), "Hello World")

    def test_has_signup_form(self) -> None:
        self.assertTrue(_has_signup_form("<html><form action='signup.php'></form></html>"))
        self.assertFalse(_has_signup_form("<html><body>no form</body></html>"))

    def test_has_invite_field(self) -> None:
        self.assertTrue(_has_invite_field("<html><input name='invitecode' /></html>"))
        self.assertTrue(_has_invite_field("<html><body>需要邀请码才能注册</body></html>"))
        self.assertFalse(_has_invite_field("<html><body>free signup</body></html>"))

    def test_extract_invite_url_from_html_uses_join(self) -> None:
        def join(base: str, path: str) -> str:
            return urljoin(base.rstrip("/") + "/", path.lstrip("/"))

        html = """
        <html><body>
          <a href="userdetails.php?id=1">邀请</a>
          <a href="invite.php?id=2">邀请 发送</a>
        </body></html>
        """
        self.assertEqual(_extract_invite_url_from_html(html, "https://example.com", join=join), "https://example.com/invite.php?id=2")

    def test_invite_send_action_status(self) -> None:
        ok_html = "<html><form action='takeinvite.php?type=new'><input type='submit' value='发送邀请'></form></html>"
        status, matched = _invite_send_action_status(ok_html)
        self.assertTrue(status)
        self.assertEqual(matched, "发送邀请")

        disabled_html = (
            "<html><form action='takeinvite.php?type=new'><input type='submit' value='发送邀请' disabled></form></html>"
        )
        status, matched = _invite_send_action_status(disabled_html)
        self.assertFalse(status)
        self.assertEqual(matched, "发送邀请")


if __name__ == "__main__":
    unittest.main()

