import unittest

from pt_invite_watcher.net import request_with_retry


class _FakeResponse:
    def __init__(self, status_code: int):
        self.status_code = int(status_code)
        self.closed = False

    async def aclose(self) -> None:
        self.closed = True


class RequestWithRetryClosesResponsesTest(unittest.IsolatedAsyncioTestCase):
    async def test_closes_retryable_responses_before_retry(self) -> None:
        first = _FakeResponse(500)
        second = _FakeResponse(200)
        items = [first, second]

        async def _request_fn():
            return items.pop(0)

        resp, err, used = await request_with_retry(_request_fn, attempts=2, delay_seconds=0)
        assert resp is not None

        self.assertIsNone(err)
        self.assertEqual(used, 2)
        self.assertTrue(first.closed)
        self.assertFalse(second.closed)
        self.assertIs(resp, second)

    async def test_does_not_close_final_response(self) -> None:
        first = _FakeResponse(500)
        second = _FakeResponse(500)
        third = _FakeResponse(500)
        items = [first, second, third]

        async def _request_fn():
            return items.pop(0)

        resp, err, used = await request_with_retry(_request_fn, attempts=3, delay_seconds=0)
        assert resp is not None

        self.assertIsNone(err)
        self.assertEqual(used, 3)
        self.assertTrue(first.closed)
        self.assertTrue(second.closed)
        self.assertFalse(third.closed)
        self.assertIs(resp, third)


if __name__ == "__main__":
    unittest.main()

