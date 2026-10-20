"""Declarative JSON HTTP acceptance; run outside the target process/container."""
from __future__ import annotations

import argparse
from hashlib import sha256
from http.cookiejar import CookieJar
import json
import os
from pathlib import Path
import re
import secrets
import socket
import stat
import time
from urllib.error import HTTPError
from urllib.parse import urlsplit
from urllib.request import HTTPCookieProcessor, HTTPRedirectHandler, ProxyHandler, Request, build_opener


MAX_PLAN = 65536
MAX_RESPONSE = 1024 * 1024


def strict_json(raw):
    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError("Duplicate JSON key")
            result[key] = value
        return result

    def invalid(value):
        raise ValueError("Nonfinite JSON value")

    return json.loads(raw, object_pairs_hook=unique, parse_constant=invalid)


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def validate(plan):
    if (not isinstance(plan, dict) or set(plan) != {"version", "markers", "forbidden_fields", "cases"}
            or type(plan["version"]) is not int or plan["version"] != 1
            or len(json.dumps(plan, allow_nan=False).encode()) > MAX_PLAN):
        raise ValueError("Invalid or oversized HTTP acceptance plan")
    for name in ("markers", "forbidden_fields"):
        values = plan[name]
        if (not isinstance(values, list) or len(values) > 32
                or any(not isinstance(v, str) or not v or len(v) > 200 for v in values)
                or len(set(values)) != len(values)):
            raise ValueError("Invalid HTTP security assertions")
    if not plan["markers"] and not plan["forbidden_fields"]:
        raise ValueError("HTTP acceptance requires security assertions")
    if not isinstance(plan["cases"], list) or not 1 <= len(plan["cases"]) <= 64:
        raise ValueError("HTTP acceptance requires 1–64 ordered cases")
    ids = set()
    for case in plan["cases"]:
        if (not isinstance(case, dict) or set(case) - {"id", "method", "path", "status", "expect", "json", "headers"}
                or {"id", "method", "path", "status", "expect"} - set(case)):
            raise ValueError("Invalid HTTP case fields")
        if (not isinstance(case["id"], str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,80}", case["id"])
                or case["id"] in ids):
            raise ValueError("HTTP case IDs must be distinct")
        ids.add(case["id"])
        if case["method"] not in ("GET", "POST", "PUT", "PATCH", "DELETE"):
            raise ValueError("Unsupported HTTP method")
        path = case["path"]
        if (not isinstance(path, str) or not path.startswith("/") or path.startswith("//")
                or "\\" in path or "#" in path or any(ord(c) < 32 or ord(c) == 127 for c in path)):
            raise ValueError("HTTP paths must stay on the configured origin")
        if type(case["status"]) is not int or not 200 <= case["status"] <= 599 or 300 <= case["status"] < 400:
            raise ValueError("Invalid expected HTTP status; redirects are forbidden")
        headers = case.get("headers", {})
        if (not isinstance(headers, dict) or any(
                not isinstance(k, str) or not re.fullmatch(r"[A-Za-z0-9-]+", k)
                or k.lower() in {"host", "proxy-authorization", "content-length", "transfer-encoding", "connection"}
                or not isinstance(v, str) or any(ord(c) < 32 or ord(c) == 127 for c in v)
                for k, v in headers.items())):
            raise ValueError("Invalid HTTP request headers")


def subset(actual, expected, budget=None):
    budget = [100000] if budget is None else budget
    budget[0] -= 1
    if budget[0] < 0:
        raise ValueError("HTTP contract comparison limit exceeded")
    if isinstance(expected, dict):
        return isinstance(actual, dict) and all(k in actual and subset(actual[k], v, budget) for k, v in expected.items())
    if isinstance(expected, list):
        # Each expected list item must occur; unrelated existing records are allowed.
        if not expected:
            return isinstance(actual, list) and not actual
        return isinstance(actual, list) and all(any(subset(a, e, budget) for a in actual) for e in expected)
    return type(actual) is type(expected) and actual == expected


def forbidden(value, names):
    found, pending = set(), [value]
    while pending:
        item = pending.pop()
        if isinstance(item, dict):
            found.update(names.intersection(item))
            pending.extend(item.values())
        elif isinstance(item, list):
            pending.extend(item)
    return sorted(found)


def check(base, plan, *, startup_timeout=30, request_timeout=3):
    validate(plan)
    address = urlsplit(base)
    if (address.scheme not in {"http", "https"} or not address.hostname or address.username is not None
            or address.password is not None or address.path not in {"", "/"} or address.query or address.fragment
            or any(ord(c) < 33 or ord(c) == 127 for c in base)):
        raise ValueError("Use one explicit HTTP origin without credentials or a path")
    port = address.port if address.port is not None else (443 if address.scheme == "https" else 80)
    if not 1 <= port <= 65535:
        raise ValueError("Invalid HTTP port")
    if not 0 <= startup_timeout <= 120 or not 0 < request_timeout <= 30:
        raise ValueError("Invalid HTTP time budget")
    original = json.dumps(plan, allow_nan=False)
    rendered = original.replace("${nonce}", secrets.token_hex(12)).replace("${secret}", secrets.token_hex(24))
    if "${" in rendered:
        raise ValueError("Unknown HTTP plan placeholder")
    plan = json.loads(rendered)
    validate(plan)
    client = build_opener(ProxyHandler({}), NoRedirect(), HTTPCookieProcessor(CookieJar()))
    deadline = time.monotonic() + startup_timeout
    while startup_timeout:
        try:
            with socket.create_connection((address.hostname, port), timeout=min(1, request_timeout)):
                break
        except OSError:
            if time.monotonic() >= deadline:
                raise RuntimeError("HTTP application unavailable") from None
            time.sleep(0.1)
    cases, stopped = [], False
    for case in plan["cases"]:
        result = {"id": case["id"], "passed": False, "status": "NOT_RUN", "observations": [], "violations": []}
        cases.append(result)
        if stopped:
            continue
        try:
            body = json.dumps(case["json"], allow_nan=False).encode() if "json" in case else None
            headers = {"Content-Type": "application/json", **case.get("headers", {})}
            request = Request(base.rstrip("/") + case["path"], data=body, method=case["method"], headers=headers)
            try:
                response = client.open(request, timeout=request_timeout)
            except HTTPError as error:
                response = error
            with response:
                if 300 <= response.status < 400:
                    raise ValueError("HTTP redirect refused")
                raw = response.read(MAX_RESPONSE + 1)
                if len(raw) > MAX_RESPONSE:
                    raise ValueError("HTTP response limit exceeded")
                value = None if not raw and response.status == 204 else strict_json(raw)
                observed = raw.decode("utf-8") + json.dumps(value, ensure_ascii=False) + str(response.headers)
                result["http_status"] = response.status
                result["passed"] = response.status == case["status"] and subset(value, case["expect"])
            for marker in plan["markers"]:
                if marker in observed:
                    result["observations"].append({"sink": "HTTP_RESPONSE", "marker_sha256": sha256(marker.encode()).hexdigest()})
            result["violations"] = [{"sink": "HTTP_RESPONSE", "forbidden_field": name}
                                    for name in forbidden(value, set(plan["forbidden_fields"]))]
            result["security_passed"] = not result["observations"] and not result["violations"]
            result["status"] = "COMPLETED"
            stopped = not result["passed"]
        except Exception as error:
            # Target bytes and exception messages never enter retained evidence.
            result.update(status="ERROR", error_type=type(error).__name__)
            stopped = True
    completed = all(c["status"] == "COMPLETED" for c in cases)
    functional = completed and all(c["passed"] for c in cases)
    security = completed and all(c.get("security_passed") is True for c in cases)
    passed = functional and security
    return {"kind": "external-json-http-acceptance", "plan_sha256": sha256(original.encode()).hexdigest(),
            "marker_sha256": [sha256(marker.encode()).hexdigest() for marker in plan["markers"]],
            "gate": {"passed": passed, "scope": "Configured HTTP responses only; not logs or arbitrary code safety"},
            "runtime": {"status": "COMPLETED" if completed else "ERROR", "passed": passed,
                        "functional_passed": functional, "security_passed": security, "cases": cases}}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", required=True)
    parser.add_argument("--plan", type=Path, required=True)
    args = parser.parse_args()
    try:
        descriptor = os.open(args.plan, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
        with os.fdopen(descriptor, "rb") as source:
            info = os.fstat(source.fileno())
            if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1 or info.st_size > MAX_PLAN:
                raise ValueError("HTTP plan must be a bounded regular file")
            raw = source.read(MAX_PLAN + 1)
        if len(raw) > MAX_PLAN:
            raise ValueError("HTTP plan limit exceeded")
        result = check(args.base_url, strict_json(raw))
    except Exception as error:
        print(json.dumps({"gate": {"passed": False}, "runtime": {"status": "ERROR", "passed": False},
                          "error_type": type(error).__name__}))
        raise SystemExit(1) from None
    print(json.dumps(result))
    if not result["gate"]["passed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
