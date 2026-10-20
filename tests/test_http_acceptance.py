import importlib.util
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import threading
import unittest


spec = importlib.util.spec_from_file_location("vampi_http_probe", Path(__file__).parents[1] / "benchmarks/vampi/http_probe.py")
probe = importlib.util.module_from_spec(spec)
spec.loader.exec_module(probe)


class HTTPAcceptanceTest(unittest.TestCase):
    def run_probe(self, mode, expected):
        stored = {}

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def do_POST(self):
                stored.update(json.loads(self.rfile.read(int(self.headers["Content-Length"]))))
                self.reply({"status": "ok"})

            def reply(self, value):
                self.send_response(200)
                self.end_headers()
                self.wfile.write(json.dumps(value).encode())

            def do_GET(self):
                public = {k: v for k, v in stored.items() if k != "password"}
                if self.path == "/createdb":
                    self.reply({"ok": True})
                elif self.path == "/users/v1/_debug":
                    if mode == "redirect":
                        self.send_response(302)
                        self.send_header("Location", "/unapproved")
                        self.end_headers()
                    elif mode == "oversize":
                        self.reply("x" * (1024 * 1024 + 1))
                    elif mode == "empty":
                        self.reply({"users": []})
                    else:
                        self.reply({"users": [stored if mode == "leak" else
                                              dict(public, admin=False) if mode == "admin" else public]})
                elif self.path == "/users/v1":
                    self.reply({"users": [public]})
                else:
                    self.reply(public)

        server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        try:
            return probe.check(f"http://127.0.0.1:{server.server_port}", expect_vulnerable=expected)
        finally:
            server.shutdown()
            server.server_close()

    def test_safe_and_vulnerable_actual_http_are_distinguished(self):
        safe = self.run_probe("safe", False)
        leaking = self.run_probe("leak", True)
        self.assertTrue(safe["security_passed"])
        self.assertFalse(leaking["security_passed"])
        self.assertNotEqual(safe["canary_sha256"], leaking["canary_sha256"])

    def test_leak_empty_response_admin_field_redirect_and_oversize_do_not_pass(self):
        for mode in ("leak", "empty", "admin", "redirect", "oversize"):
            with self.subTest(mode=mode), self.assertRaises(Exception):
                self.run_probe(mode, False)
