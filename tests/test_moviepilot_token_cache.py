import unittest

import httpx

import pt_invite_watcher.providers.moviepilot_api as moviepilot_api
from pt_invite_watcher.providers.moviepilot_api import MoviePilotClient


class MoviePilotTokenCacheTest(unittest.IsolatedAsyncioTestCase):
    async def test_reuse_token_across_client_instances(self) -> None:
        moviepilot_api._TOKEN_CACHE.clear()

        call_count = 0

        async def fake_request_with_retry(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return httpx.Response(200, json={"access_token": "tok"}), None, 1
            return (
                httpx.Response(
                    200,
                    json=[
                        {
                            "id": 1,
                            "name": "S",
                            "domain": "example.com",
                            "url": "https://example.com",
                            "is_active": True,
                        }
                    ],
                ),
                None,
                1,
            )

        original = moviepilot_api.request_with_retry
        moviepilot_api.request_with_retry = fake_request_with_retry
        try:
            c1 = MoviePilotClient(base_url="http://moviepilot", username="u", password="p")
            sites1 = await c1.list_sites(only_active=True)
            self.assertEqual(len(sites1), 1)
            self.assertEqual(call_count, 2)  # login + list

            c2 = MoviePilotClient(base_url="http://moviepilot", username="u", password="p")
            sites2 = await c2.list_sites(only_active=True)
            self.assertEqual(len(sites2), 1)
            self.assertEqual(call_count, 3)  # token reused: list only
        finally:
            moviepilot_api.request_with_retry = original
            moviepilot_api._TOKEN_CACHE.clear()


if __name__ == "__main__":
    unittest.main()

