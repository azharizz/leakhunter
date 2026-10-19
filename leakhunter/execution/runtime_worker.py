"""Private subprocess worker. The result protocol never uses target stdout."""
from __future__ import annotations

import asyncio
import hashlib
import importlib
import inspect
import io
import json
import logging
import os
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import types
import urllib.parse
import urllib.request
from unittest.mock import patch


def _subset(actual, expected):
    if isinstance(expected, dict):
        return isinstance(actual, dict) and all(key in actual and _subset(actual[key], value) for key, value in expected.items())
    if isinstance(expected, list):
        return isinstance(actual, list) and len(actual) == len(expected) and all(_subset(a, b) for a, b in zip(actual, expected))
    return type(actual) is type(expected) and actual == expected


def _strings(value):
    if isinstance(value, bytes):
        yield value.decode("utf-8", errors="replace")
    elif isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for key, item in value.items():
            yield from _strings(key)
            yield from _strings(item)
    elif isinstance(value, (list, tuple)):
        for item in value:
            yield from _strings(item)
    elif value is None or isinstance(value, (bool, int, float)):
        return
    else:
        # Common response objects expose a JSON body or textual body, not repr().
        if hasattr(value, "body"):
            yield from _strings(value.body)
        else:
            raise TypeError("unsupported captured payload type")


class _Output(io.TextIOBase):
    def __init__(self, capture):
        self.capture = capture
        self.buffer = _BinaryOutput(self)
        self.pending = ""

    def write(self, text):
        self.capture("APPLICATION_LOG", self.pending + text)
        # Preserve split markers without retaining full target output.
        self.pending = (self.pending + text)[-self.capture.marker_length:]
        return len(text)

    def flush(self):
        pass


class _BinaryOutput:
    def __init__(self, output):
        self.output = output

    def write(self, value):
        self.output.write(value.decode("utf-8", errors="replace"))
        return len(value)

    def flush(self):
        pass


class _HTTPResponse(io.BytesIO):
    status = 200
    code = 200
    reason = "OK"
    headers = {"Content-Type": "application/json"}

    def __init__(self, url):
        super().__init__(b'{"accepted":true}')
        self.url = url

    @property
    def status_code(self):
        return self.status

    @property
    def ok(self):
        return True

    @property
    def content(self):
        return self.getvalue()

    @property
    def text(self):
        return self.content.decode("utf-8")

    def json(self):
        return json.loads(self.text)

    def raise_for_status(self):
        pass

    def getcode(self):
        return self.code

    def geturl(self):
        return self.url

    def info(self):
        return self.headers


def _resolve(module, dotted):
    value = module
    parts = dotted.split(".")
    for part in parts[:-1]:
        value = getattr(value, part)
    return value, parts[-1]
def _relative(repository, filename):
    path = Path(filename)
    if not path.is_absolute():
        return None
    try:
        return path.resolve().relative_to(repository).as_posix()
    except (OSError, ValueError):
        return None


def _record_event(events, event):
    if len(events) < 512:
        events.append(event)


def _observed_call(result, model, original):
    def invoke(*args, **kwargs):
        event = {"module": model["module"], "callable": model["callable"], "role": model["role"],
                 "order": len(result["call_events"])}
        try:
            returned = original(*args, **kwargs)
        except BaseException:
            event["raised"] = True
            _record_event(result["call_events"], event)
            raise
        event["returned_type"] = type(returned).__name__
        if type(returned) is bool:
            event["returned_bool"] = returned
        _record_event(result["call_events"], event)
        return returned
    return invoke


def _trace_lines(repository, result):
    def trace(frame, event, arg):
        if event == "line":
            relative = _relative(repository, frame.f_code.co_filename)
            if relative is not None:
                _record_event(result["executed_lines"], {"file": relative, "line": frame.f_lineno})
        return trace
    return trace


def _case(repository, case):
    observations = []
    captured = set()
    capture_errors = []
    result = {"id": case["id"], "passed": False, "observations": observations, "captured_sinks": [],
              "call_events": [], "executed_lines": []}
    artifact_workspace = tempfile.TemporaryDirectory(prefix="leakhunter-artifacts-") if case.get("artifacts") else None
    artifact_root = Path(artifact_workspace.name).resolve() if artifact_workspace else repository

    def capture(sink, payload):
        captured.add(sink)
        try:
            texts = list(_strings(payload))
        except BaseException:
            capture_errors.append("unsupported_capture")
            raise
        for source in case["sensitive"]:
            if any(source["marker"] in text or source["marker"] in urllib.parse.unquote_plus(text) for text in texts):
                observation = {"sink": sink, "symbol": source["symbol"],
                               "marker_hash": hashlib.sha256(source["marker"].encode()).hexdigest()}
                if observation not in observations:
                    observations.append(observation)

    capture.marker_length = max(len(s["marker"]) for s in case["sensitive"])

    def http(request, data=None, *args, **kwargs):
        if isinstance(request, urllib.request.Request):
            url = request.full_url
            payload = (url, request.headers, data if data is not None else request.data)
        else:
            url = str(request)
            payload = (url, data, kwargs)
        models = sorted(case.get("capture_http", []), key=lambda m: len(m["url_prefix"]), reverse=True)
        sink = next((m["sink"] for m in models if url.startswith(m["url_prefix"])), "THIRD_PARTY_ANALYTICS")
        capture(sink, payload)
        return _HTTPResponse(url)

    def requests_call(session, method, url, **kwargs):
        return http(url, (method, kwargs))

    def log(logger, record):
        payload = record.getMessage()
        if record.exc_info:
            payload += logging.Formatter().formatException(record.exc_info)
        capture("APPLICATION_LOG", payload)

    def sdk(sink, returned):
        def invoke(*args, **kwargs):
            capture(sink, (args, kwargs))
            return json.loads(json.dumps(returned))
        return invoke

    def blocked(*args, **kwargs):
        capture_errors.append("uncaptured_network")
        raise RuntimeError("uncaptured_network_disabled")

    output = _Output(capture)
    patches = [patch("sys.stdout", output), patch("sys.stderr", output),
               patch.object(logging.Logger, "callHandlers", log),
               patch.object(socket.socket, "connect", blocked), patch.object(socket.socket, "connect_ex", blocked),
               patch.object(socket.socket, "sendto", blocked), patch.object(socket, "create_connection", blocked),
               patch.object(socket, "getaddrinfo", blocked),
               patch.object(urllib.request, "urlopen", http),
               patch.object(urllib.request.OpenerDirector, "open", lambda self, request, data=None, *a, **kw: http(request, data, *a, **kw))]
    try:
        os.chdir(artifact_root)
        for item in patches:
            item.start()
        try:
            requests = importlib.import_module("requests")
        except ImportError:
            # The stdlib-only image models the common requests transport API.
            # Unsupported requests APIs raise rather than silently passing.
            requests = types.ModuleType("requests")

            class Session:
                def request(self, method, url, **kwargs):
                    return requests_call(self, method, url, **kwargs)

                def get(self, url, **kwargs):
                    return self.request("GET", url, **kwargs)

                def post(self, url, **kwargs):
                    return self.request("POST", url, **kwargs)

                def close(self):
                    pass

                def __enter__(self):
                    return self

                def __exit__(self, *exc):
                    self.close()

            requests.Session = Session
            requests.session = Session
            requests.request = lambda method, url, **kwargs: requests_call(None, method, url, **kwargs)
            for method in ("get", "post", "put", "patch", "delete", "head", "options"):
                setattr(requests, method, lambda url, _method=method, **kwargs: requests_call(None, _method.upper(), url, **kwargs))
            item = patch.dict(sys.modules, {"requests": requests})
        else:
            item = patch.object(requests.sessions.Session, "request", requests_call)
        item.start()
        patches.append(item)
        for model in case.get("capture_calls", []):
            module = importlib.import_module(model["module"])
            _inside(repository, module)
            owner, name = _resolve(module, model["callable"])
            if not callable(getattr(owner, name)):
                raise TypeError("capture model target is not callable")
            item = patch.object(owner, name, sdk(model["sink"], model.get("return_value")))
            item.start()
            patches.append(item)
        for model in case.get("observe_calls", []):
            module = importlib.import_module(model["module"])
            _inside(repository, module)
            owner, name = _resolve(module, model["callable"])
            original = getattr(owner, name)
            if not callable(original):
                raise TypeError("call observation target is not callable")
            item = patch.object(owner, name, _observed_call(result, model, original))
            item.start()
            patches.append(item)
        module = importlib.import_module(case["module"])
        _inside(repository, module)
        owner, name = _resolve(module, case["callable"])
        previous_trace = sys.gettrace()
        if case.get("trace"):
            sys.settrace(_trace_lines(repository, result))
        try:
            returned = getattr(owner, name)(*case["args"], **case["kwargs"])
            if inspect.isawaitable(returned):
                returned = asyncio.run(returned)
        finally:
            if case.get("trace"):
                sys.settrace(previous_trace)
        capture("HTTP_RESPONSE", returned)
        result["passed"] = _subset(returned, case["expect"])
        for artifact in case.get("artifacts", []):
            path = artifact_root / artifact["path"]
            if path.is_symlink() or not path.resolve().is_relative_to(artifact_root) or not path.is_file():
                raise ValueError("artifact missing or escaped workspace")
            capture(artifact["sink"], path.read_bytes())
        if capture_errors:
            raise RuntimeError("capture_failed")
    except BaseException:
        result["error"] = "fixture_execution_failed"
    finally:
        os.chdir(repository)
        if artifact_workspace:
            artifact_workspace.cleanup()
        for item in reversed(patches):
            item.stop()
        for name, module in list(sys.modules.items()):
            file = getattr(module, "__file__", None)
            if file and Path(file).resolve().is_relative_to(repository):
                sys.modules.pop(name, None)
        result["captured_sinks"] = sorted(captured)
    return result


def _inside(repository, module):
    file = getattr(module, "__file__", None)
    if not file or not Path(file).resolve().is_relative_to(repository):
        raise ValueError("configured module must originate inside repository")


def _regression(repository, command, timeout):
    argv = list(command)
    if argv[0] in {"python", "python3"}:
        argv[0] = sys.executable
    else:
        argv[0] = str(repository / argv[0])
    # The manifest is trusted and pinned by the caller; never a model-provided shell string.
    with tempfile.TemporaryFile() as stdout, tempfile.TemporaryFile() as stderr:
        process = subprocess.Popen(argv, cwd=repository,
                                   env={"PATH": os.defpath, "HOME": "/tmp", "PYTHONDONTWRITEBYTECODE": "1", "LANG": "C.UTF-8"},
                                   stdout=stdout, stderr=stderr)
        try:
            passed = process.wait(timeout=timeout) == 0
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait()
            passed = False
        hashes = []
        for stream in (stdout, stderr):
            stream.seek(0)
            digest = hashlib.sha256()
            for chunk in iter(lambda: stream.read(65536), b""):
                digest.update(chunk)
            hashes.append(digest.hexdigest())
    return {"passed": passed, "stdout_hash": hashes[0], "stderr_hash": hashes[1]}


def main():
    repository = Path(sys.argv[1]).resolve(strict=True)
    manifest = json.loads(Path(sys.argv[2]).read_text(encoding="utf-8"))
    result_path = Path(sys.argv[3])
    timeout = float(sys.argv[4])
    os.chdir(repository)
    # -I -S plus only the supplied harness and repository: no cwd/PYTHONPATH/site hooks.
    sys.path.insert(1, str(repository))
    sys.dont_write_bytecode = True
    cases = []
    # Import state is shared just as in a normal test suite; every case reinstalls captures.
    for case in manifest["cases"]:
        cases.append(_case(repository, case))
    result = {"cases": cases}
    if "regression_command" in manifest:
        try:
            result["regression"] = _regression(repository, manifest["regression_command"], timeout)
        except BaseException:
            result["regression"] = {"passed": False}
    result_path.write_text(json.dumps(result, allow_nan=False), encoding="utf-8")


if __name__ == "__main__":
    main()
