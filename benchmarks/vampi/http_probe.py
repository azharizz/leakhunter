"""HTTP acceptance client; run separately from VAmPI with no target source mount."""
import argparse
import hashlib
import json
import secrets
import time
from urllib.error import URLError
from urllib.request import HTTPRedirectHandler, ProxyHandler, Request, build_opener


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def check(base, *, expect_vulnerable, startup_timeout=30):
    # No inherited proxy credentials and no redirects to other services.
    client = build_opener(ProxyHandler({}), NoRedirect())

    def request(path, body=None):
        data = json.dumps(body).encode() if body is not None else None
        req = Request(base + path, data=data, headers={"Content-Type": "application/json"})
        with client.open(req, timeout=3) as response:
            if response.status != 200:
                raise ValueError("unexpected_http_status")
            raw = response.read(1024 * 1024 + 1)
            if len(raw) > 1024 * 1024:
                raise ValueError("response_limit_exceeded")
            return json.loads(raw)

    deadline = time.monotonic() + startup_timeout
    while True:
        try:
            request("/createdb")
            break
        except (URLError, TimeoutError):
            if time.monotonic() >= deadline:
                raise RuntimeError("application_unavailable") from None
            time.sleep(0.25)

    nonce = secrets.token_hex(12)
    marker = "UNSPOOL_SYNTHETIC_" + secrets.token_hex(24)
    username, email = "unspool" + nonce, nonce + "@example.invalid"
    request("/users/v1/register", {"username": username, "password": marker, "email": email})
    public = request("/users/v1")
    lookup = request("/users/v1/" + username)
    debug = request("/users/v1/_debug")
    identity = {"username": username, "email": email}

    def contains_identity(response):
        return any(all(user.get(key) == value for key, value in identity.items())
                   for user in response["users"])

    if (not contains_identity(public) or any(lookup.get(k) != v for k, v in identity.items())
            or not contains_identity(debug) or marker in json.dumps(public)
            or marker in json.dumps(lookup)):
        raise ValueError("public_contract_failed")
    leaked = marker in json.dumps(debug)
    if leaked != expect_vulnerable:
        raise ValueError("unexpected_security_behavior")
    if not expect_vulnerable and any("password" in user or "admin" in user for user in debug["users"]):
        raise ValueError("forbidden_debug_field")
    return {"kind": "separate-container-http-acceptance", "http_functionality_passed": True,
            "security_passed": not leaked, "secret_observed_at_http_response": leaked,
            "expected_behavior_reproduced": True,
            "canary_sha256": hashlib.sha256(marker.encode()).hexdigest()}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    expected = parser.add_mutually_exclusive_group(required=True)
    expected.add_argument("--expect-vulnerable", action="store_true")
    expected.add_argument("--expect-fixed", action="store_true")
    args = parser.parse_args()
    try:
        result = check("http://vampi:8080", expect_vulnerable=args.expect_vulnerable)
    except Exception as error:
        # Never print target responses, exceptions, passwords or credential-bearing URLs.
        print(json.dumps({"status": "STOPPED", "error_type": type(error).__name__}))
        raise SystemExit(1) from None
    print(json.dumps(result))


if __name__ == "__main__":
    main()
