"""Check that the live deployment serves the exact verified revision."""
import argparse
import json
import re
import time
from urllib.error import URLError
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, ProxyHandler, build_opener


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def check(url, commit, attempts=12):
    parsed = urlsplit(url)
    if (parsed.scheme != "https" or not parsed.hostname or parsed.username is not None
            or parsed.password is not None or parsed.query or parsed.fragment
            or not re.fullmatch(r"[0-9a-f]{40}", commit)):
        raise ValueError("Smoke checks require an HTTPS origin/path without credentials, query or fragment and a full source SHA")
    # Validate the port without accepting malformed URL authority syntax.
    parsed.port
    opener = build_opener(ProxyHandler({}), NoRedirect())
    for attempt in range(attempts):
        try:
            with opener.open(url.rstrip("/") + "/health.json", timeout=15) as response:
                raw = response.read(65537)
            if len(raw) > 65536:
                raise ValueError("Health response exceeded the limit")
            health = json.loads(raw)
            if (isinstance(health, dict) and health.get("verified") is True
                    and health == {"status": "ok", "commit": commit, "verified": True}):
                print("Production serves verified revision " + commit)
                return
        except (URLError, ValueError):
            pass
        if attempt + 1 < attempts:
            time.sleep(10)
    raise SystemExit("Production did not serve the expected verified revision")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", required=True)
    parser.add_argument("--commit", required=True)
    args = parser.parse_args()
    check(args.url, args.commit)
