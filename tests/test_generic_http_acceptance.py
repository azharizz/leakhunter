import copy
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import unittest

from unspool.http_acceptance import check, strict_json, subset, validate


class HTTPAcceptanceTest(unittest.TestCase):
    def plan(self):
        return {"version": 1, "markers": ["${secret}"], "forbidden_fields": ["password"], "cases": [
            {"id": "create", "method": "POST", "path": "/register", "status": 200, "expect": {"ok": True},
             "json": {"name": "${nonce}", "password": "${secret}"}},
            {"id": "read", "method": "GET", "path": "/users", "status": 200,
             "expect": {"users": [{"name": "${nonce}"}]}}]}

    def test_real_http_in_separate_client_process_distinguishes_safe_leaking_and_invalid(self):
        state = {"mode": "safe", "traps": 0}

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def do_POST(self):
                state["user"] = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
                self.send_response(200)
                self.end_headers()
                self.wfile.write(b'{"ok":true}')

            def do_GET(self):
                if self.path == "/trap":
                    state["traps"] += 1
                if state["mode"] == "redirect":
                    self.send_response(302)
                    self.send_header("Location", "/trap")
                    self.end_headers()
                    return
                self.send_response(200)
                if state["mode"] == "header":
                    self.send_header("X-Synthetic-Value", state["user"]["password"])
                self.end_headers()
                user = dict(state["user"])
                if state["mode"] != "leak":
                    user.pop("password")
                body = json.dumps({"users": [user]}).encode()
                if state["mode"] == "escaped":
                    user["password"] = state["user"]["password"]
                    body = json.dumps({"users": [user]}).encode()
                    secret = state["user"]["password"]
                    body = body.replace(secret.encode(), "".join(f"\\u{ord(c):04x}" for c in secret).encode())
                if state["mode"] == "empty":
                    body = b'{"users":[]}'
                elif state["mode"] == "oversize":
                    body = b"x" * (1024 * 1024 + 1)
                elif state["mode"] == "duplicate":
                    body = b'{"users":[],"users":[]}'
                elif state["mode"] == "field":
                    user["password"] = "redacted"
                    body = json.dumps({"users": [user]}).encode()
                try:
                    self.wfile.write(body)
                except (BrokenPipeError, ConnectionResetError):
                    pass

        server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        worker = threading.Thread(target=server.serve_forever, daemon=True)
        worker.start()
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)
        with tempfile.TemporaryDirectory() as directory:
            plan = Path(directory) / "plan.json"
            plan.write_text(json.dumps(self.plan()))
            for mode in ("safe", "leak", "escaped", "header", "empty", "oversize", "duplicate", "field", "redirect"):
                with self.subTest(mode=mode):
                    state["mode"] = mode
                    p = subprocess.run([sys.executable, "-m", "unspool.http_acceptance", "--plan", str(plan),
                                        "--base-url", f"http://127.0.0.1:{server.server_port}"],
                                       cwd=Path(__file__).resolve().parents[1], capture_output=True, text=True, timeout=10,
                                       env={**os.environ, "HTTP_PROXY": "http://127.0.0.1:1"})
                    report = json.loads(p.stdout)
                    self.assertEqual(report["gate"]["passed"], mode == "safe")
                    self.assertEqual(p.returncode, 0 if mode == "safe" else 1)
                    self.assertNotIn(state["user"]["password"], p.stdout + p.stderr)
                    if mode == "leak":
                        self.assertTrue(report["runtime"]["functional_passed"])
                        self.assertFalse(report["runtime"]["security_passed"])
                    self.assertEqual(state["traps"], 0)

    def test_cli_refuses_a_special_plan_file_without_network(self):
        # Create the special file after interpreter startup to exercise the loader itself.
        code = '''import os, runpy, sys, tempfile
from pathlib import Path
with tempfile.TemporaryDirectory() as directory:
    path = Path(directory) / "plan.json"
    os.mkfifo(path)
    sys.argv = ["acceptance", "--plan", str(path), "--base-url", "http://127.0.0.1:1"]
    runpy.run_module("unspool.http_acceptance", run_name="__main__")
'''
        p = subprocess.run([sys.executable, "-c", code], cwd=Path(__file__).resolve().parents[1],
                           capture_output=True, text=True, timeout=5)
        self.assertEqual(p.returncode, 1)
        self.assertFalse(json.loads(p.stdout)["gate"]["passed"])

    def test_configuration_and_comparison_fail_closed(self):
        plan = self.plan()
        for mutation in ({"version": True}, {"markers": [], "forbidden_fields": []}, {"extra": "ignored"}):
            with self.assertRaises(ValueError):
                validate({**plan, **mutation})
        for path in ("//elsewhere", "https://elsewhere/", "/x\r\nHost: elsewhere", "/x#fragment"):
            bad = copy.deepcopy(plan)
            bad["cases"][0]["path"] = path
            with self.assertRaises(ValueError):
                validate(bad)
        for base in ("file:///tmp", "http://user:password@localhost", "http://localhost:0", "http://localhost/path"):
            with self.assertRaises(ValueError):
                check(base, plan, startup_timeout=0)
        self.assertTrue(subset({"rows": [{"id": 1}, {"id": 2}]}, {"rows": [{"id": 2}]}))
        self.assertFalse(subset([1], []))
        with self.assertRaises(ValueError):
            subset([1] * 100, [2], [5])
        for raw in ('{"x":1,"x":2}', '{"x":NaN}'):
            with self.assertRaises(ValueError):
                strict_json(raw)
