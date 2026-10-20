import json
import unittest
from unittest.mock import Mock, patch
from urllib.error import HTTPError

from unspool.smoke import check, NoRedirect


class SmokeTest(unittest.TestCase):
    def test_unsafe_url_and_revision_inputs_never_open(self):
        urls = ["file:///tmp/report", "http://example.invalid", "https://user:secret@example.invalid",
                "https://example.invalid?query=1", "https://example.invalid#fragment", "https://example.invalid:bad", "https:///missing"]
        with patch("unspool.smoke.build_opener") as build:
            for url in urls:
                with self.subTest(url=url), self.assertRaises(ValueError):
                    check(url, "a" * 40, attempts=1)
            with self.assertRaises(ValueError):
                check("https://example.invalid", "main", attempts=1)
            build.assert_not_called()

    def test_exact_health_passes_but_forged_oversize_and_redirect_do_not(self):
        health = {"status": "ok", "commit": "a" * 40, "verified": True}
        opener = Mock()
        response = Mock()
        response.__enter__ = Mock(return_value=response)
        response.__exit__ = Mock(return_value=False)
        opener.open.return_value = response
        with patch("unspool.smoke.build_opener", return_value=opener):
            response.read.return_value = json.dumps(health).encode()
            check("https://example.invalid/report", "a" * 40, attempts=1)
            opener.open.assert_called_with("https://example.invalid/report/health.json", timeout=15)
            for raw in (json.dumps(dict(health, commit="b" * 40)).encode(),
                        json.dumps(dict(health, verified=1)).encode(), b"x" * 65537):
                response.read.return_value = raw
                with self.assertRaises(SystemExit):
                    check("https://example.invalid", "a" * 40, attempts=1)
            opener.open.side_effect = HTTPError("https://example.invalid", 302, "redirect", {}, None)
            with self.assertRaises(SystemExit):
                check("https://example.invalid", "a" * 40, attempts=1)
        self.assertIsNone(NoRedirect().redirect_request(None, None, 302, "redirect", {}, "http://other.invalid"))
