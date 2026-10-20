"""Check that the live deployment serves the exact verified revision."""
import argparse
import json
import time
from urllib.error import URLError
from urllib.request import urlopen


def check(url, commit, attempts=12):
    for attempt in range(attempts):
        try:
            with urlopen(url.rstrip("/") + "/health.json", timeout=15) as response:
                health = json.load(response)
            if health == {"status": "ok", "commit": commit, "verified": True}:
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
