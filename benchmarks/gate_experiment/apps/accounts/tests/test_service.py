import unittest

from accounts import service

USER = {"user_id": "u-1", "display_name": "Ada", "plan": "team", "password_hash": "x", "api_token": "y",
        "email": "ada@example.invalid", "team": {"team_id": "t-1", "name": "Core", "billing_token": "z"}}


class ServiceTest(unittest.TestCase):
    def test_public_profile(self):
        profile = service.public_profile(USER)
        self.assertEqual((profile["user_id"], profile["display_name"], profile["plan"]), ("u-1", "Ada", "team"))

    def test_team_listing(self):
        listing = service.team_listing([USER, dict(USER, user_id="u-2", display_name="Grace")])
        self.assertEqual([item["display_name"] for item in listing], ["Ada", "Grace"])

    def test_lookup(self):
        self.assertEqual(service.lookup([USER], "u-1")["display_name"], "Ada")
        self.assertEqual(service.lookup([USER], "missing")["error"], "not_found")
        incomplete = {key: value for key, value in USER.items() if key != "plan"}
        self.assertEqual(service.lookup([incomplete], "u-1")["error"], "incomplete_record")
