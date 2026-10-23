"""HTTP transport kept separate from application orchestration."""
from __future__ import annotations

import json
from http.server import BaseHTTPRequestHandler
from pathlib import Path
from urllib.parse import unquote, urlsplit


STATIC = Path(__file__).resolve().parents[1] / "static"
STATIC_CONTENT_TYPES = {
    "index.html": "text/html; charset=utf-8",
    "styles.css": "text/css; charset=utf-8",
    "app.js": "text/javascript; charset=utf-8",
}


def create_handler(service):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_args):
            pass

        def send_json(self, value, status=200):
            body = service.encoded(value).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

        def send_static(self, name: str):
            body = (STATIC / name).read_bytes()
            self.send_response(200)
            self.send_header("Content-Type", STATIC_CONTENT_TYPES[name])
            self.send_header("Content-Length", str(len(body)))
            self.send_header("X-Content-Type-Options", "nosniff")
            self.end_headers()
            self.wfile.write(body)

        def read_json(self) -> dict:
            length = int(self.headers.get("Content-Length", "0"))
            if length < 0 or length > 2_000_000:
                raise ValueError("Request body exceeds limit")
            content_type = self.headers.get("Content-Type", "").split(";", 1)[0]
            if length and content_type != "application/json":
                raise ValueError("Content-Type must be application/json")
            value = json.loads(self.rfile.read(length) or b"{}")
            if not isinstance(value, dict):
                raise ValueError("Request body must be an object")
            return value

        def trusted_request(self) -> bool:
            # Loopback binding is not CSRF protection: reject DNS rebinding and browser cross-origin mutations.
            host = urlsplit("http://" + self.headers.get("Host", "")).hostname
            if host not in {"localhost", "127.0.0.1", "::1"}:
                return False
            origin = self.headers.get("Origin")
            if origin and origin != "http://" + self.headers.get("Host", ""):
                return False
            return self.headers.get("Sec-Fetch-Site") not in {"cross-site"}

        def do_GET(self):
            self.dispatch("GET")

        def do_POST(self):
            self.dispatch("POST")

        def do_PUT(self):
            self.dispatch("PUT")

        def do_DELETE(self):
            self.dispatch("DELETE")

        def dispatch(self, method):
            try:
                if not self.trusted_request():
                    return self.send_json({"error": "Only same-origin loopback requests are accepted"}, 403)
                path = urlsplit(self.path).path
                parts = path.strip("/").split("/")
                if method == "GET":
                    if path in {"/", "/index.html"}:
                        return self.send_static("index.html")
                    if path.startswith("/static/"):
                        name = path.removeprefix("/static/")
                        if name in STATIC_CONTENT_TYPES:
                            return self.send_static(name)
                    if path == "/api/knowledge":
                        return self.send_json(service.graph())
                    if path == "/api/config":
                        return self.send_json({"decision_model": service.DECISION_MODEL, "duo_model": service.DUO_MODEL,
                                               "repository": str(service.REPOSITORY),
                                               "runtime_manifest": str(service.MANIFEST_FILE) if service.MANIFEST_FILE else None,
                                               "provider_configured": bool(service.API_KEY and service.API_URL),
                                               "analysis": "python-flow", "runtime_backend": service.RUNTIME_BACKEND,
                                               "runtime_configured": service.MANIFEST is not None,
                                               "runtime": service.runtime_config()})
                    if path in {"/api/metrics", "/api/repairs", "/api/evaluations"}:
                        return self.send_json(service.BANK.records(parts[1]))
                    if path == "/api/policies":
                        return self.send_json(service.BANK.policies())
                    if path == "/api/snapshots":
                        return self.send_json(service.BANK.snapshots())
                    if len(parts) == 3 and parts[:2] == ["api", "snapshots"]:
                        value = service.BANK.snapshot(unquote(parts[2]))
                        if value is None:
                            raise KeyError(parts[2])
                        return self.send_json(value)
                if method in {"POST", "PUT", "DELETE"}:
                    body = self.read_json() if method != "DELETE" else {}
                    if path == "/api/analyze" and method == "POST":
                        return self.send_json(service.analyze(branch=body.get("branch", "main"), base_snapshot_id=body.get("base_snapshot_id")))
                    if path == "/api/repair" and method == "POST":
                        allowed = body.get("allowed_paths")
                        if allowed is not None and (not isinstance(allowed, list) or not all(isinstance(p, str) for p in allowed)):
                            raise ValueError("allowed_paths must be a list of repository-relative paths")
                        return self.send_json(service.repair(allowed))
                    if path == "/api/evaluate" and method == "POST":
                        return self.send_json(service.evaluate())
                    if path == "/api/policies/approve" and method == "POST":
                        raw = body.get("policy")
                        candidate = service.Policy(raw)
                        configured = service.load_policy(service.POLICY_FILE)
                        if candidate.version != configured.version or service.policy_digest(raw) != service.policy_digest(configured.raw):
                            raise ValueError("Only the configured policy can be approved; configure a new version first")
                        if not isinstance(body.get("approved_by"), str) or not body["approved_by"].strip():
                            raise ValueError("Approval requires a named approved_by operator")
                        return self.send_json(service.BANK.register_policy(candidate.raw, approve_by=body.get("approved_by", "")))
                    if len(parts) in {3, 4} and parts[:2] == ["api", "knowledge"] and parts[2] in {"nodes", "edges"}:
                        if (method == "POST" and len(parts) == 3) or (method in {"PUT", "DELETE"} and len(parts) == 4):
                            with service.LOCK:
                                value = service.BANK.mutate(parts[2], {"POST": "create", "PUT": "update", "DELETE": "delete"}[method], body,
                                                            unquote(parts[3]) if len(parts) == 4 else None)
                            return self.send_json(value, 201 if method == "POST" else 200)
                return self.send_json({"error": "Not found"}, 404)
            except KeyError:
                self.send_json({"error": "Record not found"}, 404)
            except (RuntimeError, FileExistsError) as exc:
                self.send_json({"error": str(exc)}, 409)
            except (ValueError, TypeError) as exc:
                self.send_json({"error": str(exc)}, 400)
            except Exception as exc:
                # Do not echo target data, provider responses, paths or credentials into server errors.
                self.send_json({"error": f"Operation failed: {type(exc).__name__}"}, 500)

    return Handler
