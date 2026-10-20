"""HTTP acceptance probe for VAmPI's published excessive-data-exposure example.

Run only inside the isolated validation container; this starts no public listener.
The expected vulnerability is independently published by the upstream author.
"""
import argparse
import hashlib
import json
import threading
from urllib.request import Request, urlopen

from werkzeug.serving import make_server

from config import vuln_app


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    expected = parser.add_mutually_exclusive_group(required=True)
    expected.add_argument("--expect-vulnerable", action="store_true")
    expected.add_argument("--expect-fixed", action="store_true")
    args = parser.parse_args()
    marker = "UNSPOOL_PUBLIC_SYNTHETIC_CANARY_73c1"
    server = make_server("127.0.0.1", 0, vuln_app.app)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()

    def request(path, body=None):
        data = json.dumps(body).encode() if body is not None else None
        req = Request(f"http://127.0.0.1:{server.server_port}" + path, data=data,
                      headers={"Content-Type": "application/json"})
        with urlopen(req, timeout=5) as response:
            assert response.status == 200
            return json.load(response)

    try:
        request("/createdb")
        request("/users/v1/register", {"username": "unspoolcanary", "password": marker,
                                       "email": "unspool@example.invalid"})
        public = request("/users/v1")
        assert any(user["username"] == "unspoolcanary" for user in public["users"])
        assert marker not in json.dumps(public)
        user = request("/users/v1/unspoolcanary")
        assert user["username"] == "unspoolcanary" and marker not in json.dumps(user)
        debug = request("/users/v1/_debug")
        assert any(user["username"] == "unspoolcanary" for user in debug["users"])
        leaked = marker in json.dumps(debug)
        assert leaked == args.expect_vulnerable, "Unexpected security behavior at the debug HTTP response"
        if args.expect_fixed:
            assert all("password" not in user and "admin" not in user for user in debug["users"])
        print(json.dumps({"subject": "erev0s/VAmPI published debug-endpoint exposure",
                          "evaluation_type": "known_intentionally_vulnerable_external_application",
                          "http_functionality_passed": True,
                          "secret_observed_at_http_response": leaked,
                          "security_passed": not leaked,
                          "expected_behavior_reproduced": True,
                          "canary_sha256": hashlib.sha256(marker.encode()).hexdigest()}))
    finally:
        server.shutdown()
        server.server_close()


if __name__ == "__main__":
    main()
