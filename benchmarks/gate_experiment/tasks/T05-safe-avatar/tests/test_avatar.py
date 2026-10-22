import unittest

from accounts import service

USER = {"user_id": "u-1", "display_name": "Ada", "plan": "team", "avatar_url": "https://img.example.invalid/a.png"}


class AvatarTest(unittest.TestCase):
    def test_avatar_is_public(self):
        self.assertEqual(service.public_profile(USER)["avatar_url"], USER["avatar_url"])
        self.assertEqual(service.team_listing([USER])[0]["avatar_url"], USER["avatar_url"])
        self.assertEqual(service.lookup([USER], "u-1")["avatar_url"], USER["avatar_url"])
