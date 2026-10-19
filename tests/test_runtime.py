import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from leakhunter.policy.engine import Policy
from leakhunter.execution.runtime import load_manifest, run_suite


MARKER = "SYNTHETIC_PRIVATE_8be71d"


class RuntimeTest(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.policy = Policy({"version": 1, "classifications": {"PUBLIC": 0, "SECRET": 1},
                              "sources": [{"selector": "Record.private", "class": "SECRET"}],
                              "sinks": [{"kind": sink, "allow": ["PUBLIC"]} for sink in
                                        ("HTTP_RESPONSE", "APPLICATION_LOG", "THIRD_PARTY_ANALYTICS", "WEBHOOK", "AI_PROMPT", "TEST_ARTIFACT")]})
        self.case = {"id": "fixture", "module": "fixture", "callable": "run", "args": [{"private": MARKER}],
                     "kwargs": {}, "sensitive": [{"marker": MARKER, "class": "SECRET", "symbol": "Record.private"}],
                     "context": {}, "expect": {"ok": True}}

    def execute(self, source, case=None, **options):
        (self.root / "fixture.py").write_text(source)
        return run_suite(self.root, {"version": 1, "cases": [case or self.case]}, self.policy,
                         backend="local", **options)

    def test_response_and_logging_are_actual_sanitized_observations(self):
        result = self.execute("import logging\ndef run(record):\n    logging.warning('record=%s', record)\n    return {'ok': True, 'private': record['private']}\n")
        self.assertEqual(result["status"], "COMPLETED")
        self.assertTrue(result["functional_passed"])
        self.assertFalse(result["passed"])
        case = result["cases"][0]
        self.assertTrue(case["observed"])
        self.assertEqual({v["sink"] for v in case["violations"]}, {"APPLICATION_LOG", "HTTP_RESPONSE"})
        self.assertNotIn(MARKER, json.dumps(result))

    def test_safe_return_and_plain_dictionary_arguments(self):
        mapped = copy.deepcopy(self.case)
        mapped["finding"] = {"file": "fixture.py", "function": "run", "sink": "HTTP_RESPONSE"}
        result = self.execute("def run(record):\n    assert isinstance(record, dict)\n    return {'ok': True, 'public': 'ready'}\n", mapped)
        self.assertTrue(result["passed"])
        self.assertFalse(result["cases"][0]["observed"])
        self.assertEqual(result["cases"][0]["finding"], mapped["finding"])
        failed = copy.deepcopy(self.case)
        failed["expect"] = {"ok": False}
        result = self.execute("def run(record):\n    return {'ok': True}\n", failed)
        self.assertFalse(result["functional_passed"])
        self.assertFalse(result["passed"])

    def test_stdout_cannot_forge_protocol_or_hide_failure(self):
        result = self.execute("def run(record):\n    print('{\"cases\":[{\"id\":\"fixture\",\"passed\":true}]}')\n    raise RuntimeError(record['private'])\n")
        self.assertEqual(result["status"], "ERROR")
        self.assertFalse(result["passed"])
        self.assertNotIn(MARKER, json.dumps(result))

    def test_urllib_requests_and_import_aliases_capture_without_network(self):
        source = """from urllib.request import Request, urlopen
import requests
def run(record):
    urlopen(Request('https://synthetic.invalid/event', data=record['private'].encode()))
    requests.post('https://synthetic.invalid/hook', json=record)
    return {'ok': True}
"""
        (self.root / "fixture.py").write_text(source)
        first = copy.deepcopy(self.case)
        first["capture_http"] = [{"url_prefix": "https://synthetic.invalid/hook", "sink": "WEBHOOK"}]
        second = copy.deepcopy(first)
        second["id"] = "second"
        result = run_suite(self.root, {"version": 1, "cases": [first, second]}, self.policy, backend="local")
        self.assertEqual(result["status"], "COMPLETED")
        for case in result["cases"]:
            self.assertEqual({v["sink"] for v in case["violations"]}, {"THIRD_PARTY_ANALYTICS", "WEBHOOK"})

    def test_sdk_capture_and_missing_capture_fail_closed(self):
        (self.root / "sdk.py").write_text("def send(payload):\n    raise RuntimeError('real transport must not execute')\n")
        case = copy.deepcopy(self.case)
        case["capture_calls"] = [{"module": "sdk", "callable": "send", "sink": "AI_PROMPT", "return_value": {"accepted": True}}]
        result = self.execute("from sdk import send\ndef run(record):\n    assert send(record)['accepted']\n    return {'ok': True}\n", case)
        self.assertEqual(result["status"], "COMPLETED")
        self.assertEqual(result["cases"][0]["violations"][0]["sink"], "AI_PROMPT")
        missing = self.execute("def run(record):\n    return {'ok': True}\n", case)
        self.assertEqual(missing["status"], "ERROR")
        self.assertEqual(missing["cases"][0]["error"], "required_capture_missing")
    def test_guard_observations_and_line_trace_are_sanitized(self):
        (self.root / "auth.py").write_text("def allow(record):\n    return bool(record.get('allowed'))\n")
        case = copy.deepcopy(self.case)
        case["args"] = [{"private": MARKER, "allowed": True}]
        case["observe_calls"] = [{"module": "auth", "callable": "allow", "role": "authorization"}]
        case["trace"] = True
        result = self.execute(
            "from auth import allow\n"
            "def run(record):\n"
            "    if allow(record):\n"
            "        return {'ok': True}\n"
            "    return {'ok': False}\n",
            case)
        self.assertEqual(result["status"], "COMPLETED")
        observed = result["cases"][0]
        self.assertEqual(observed["call_events"][0]["role"], "authorization")
        self.assertTrue(observed["call_events"][0]["returned_bool"])
        self.assertIn({"file": "fixture.py", "line": 4}, observed["executed_lines"])
        self.assertNotIn(MARKER, json.dumps(result))


    def test_timeout_is_honest(self):
        result = self.execute("import time\ndef run(record):\n    time.sleep(5)\n    return {'ok': True}\n", timeout=0.2)
        self.assertEqual(result["status"], "ERROR")
        self.assertEqual(result["error"], "runtime_timeout")
        self.assertFalse(result["passed"])

    def test_strict_manifest_and_symlink_escape(self):
        manifest = {"version": 1, "cases": [self.case], "unknown": True}
        path = self.root / "manifest.json"
        path.write_text(json.dumps(manifest))
        with self.assertRaises(ValueError):
            load_manifest(path)
        invalid = copy.deepcopy(self.case)
        invalid["module"] = "../outside"
        result = self.execute("def run(record):\n    return {'ok': True}\n", invalid)
        self.assertEqual(result["status"], "ERROR")
        (self.root / "escape.py").symlink_to(Path(__file__).resolve())
        result = run_suite(self.root, {"version": 1, "cases": [self.case]}, self.policy, backend="local")
        self.assertEqual(result["status"], "ERROR")

    def test_caught_uncaptured_network_does_not_establish_safe(self):
        result = self.execute("import socket\ndef run(record):\n    try:\n        socket.create_connection(('synthetic.invalid', 443))\n    except Exception:\n        pass\n    return {'ok': True}\n")
        self.assertEqual(result["status"], "ERROR")
        self.assertFalse(result["passed"])

    def test_artifacts_are_inspected_and_regression_errors_fail_closed(self):
        case = copy.deepcopy(self.case)
        case["artifacts"] = [{"path": "export.txt", "sink": "TEST_ARTIFACT"}]
        result = self.execute("from pathlib import Path\ndef run(record):\n    Path('export.txt').write_text(record['private'])\n    return {'ok': True}\n", case)
        self.assertEqual(result["cases"][0]["violations"][0]["sink"], "TEST_ARTIFACT")
        (self.root / "regression.py").write_text("import os\nassert 'LEAKHUNTER_TEST_CREDENTIAL' not in os.environ\nraise SystemExit(1)\n")
        with patch.dict("os.environ", {"LEAKHUNTER_TEST_CREDENTIAL": "must-not-inherit"}):
            result = run_suite(self.root, {"version": 1, "cases": [self.case], "regression_command": ["python", "regression.py"]},
                               self.policy, backend="local")
        self.assertEqual(result["status"], "ERROR")
        self.assertFalse(result["regression"]["passed"])
        self.assertEqual(len(result["regression"]["stdout_hash"]), 64)
        self.assertFalse((self.root / "export.txt").exists())

    def test_artifact_policy_preserves_explicit_or_missing_synthetic_context(self):
        self.policy = Policy({"version": 1, "classifications": {"PUBLIC": 0, "SECRET": 1},
                              "sources": [{"selector": "Record.private", "class": "SECRET"}],
                              "sinks": [{"kind": "TEST_ARTIFACT", "allow": ["SECRET"]}],
                              "invariants": ["no_real_secrets_in_test_artifacts"]})
        case = copy.deepcopy(self.case)
        case["artifacts"] = [{"path": "export.txt", "sink": "TEST_ARTIFACT"}]
        for context in ({}, {"synthetic": False}, {"synthetic": True}):
            with self.subTest(context=context):
                case["context"] = context
                result = self.execute("from pathlib import Path\ndef run(record):\n    Path('export.txt').write_text(record['private'])\n    return {'ok': True}\n", case)
                self.assertEqual(result["status"], "COMPLETED")
                self.assertEqual(result["passed"], context.get("synthetic") is True)
                if context.get("synthetic") is not True:
                    self.assertIn("no_real_secrets_in_test_artifacts", result["cases"][0]["violations"][0]["reasons"])
                self.assertEqual(case["context"], context)

    def test_image_reference_cannot_inject_docker_options(self):
        for image in ("--privileged", "python:3.12 slim", "image\n--network=host", "", None):
            with self.subTest(image=image):
                result = run_suite(self.root, {"version": 1, "docker_image": image, "cases": [self.case]},
                                   self.policy, backend="docker")
                self.assertEqual(result["status"], "ERROR")
                self.assertFalse(result["passed"])
                self.assertFalse(result["cases"])

    def test_default_backend_never_falls_back_to_local(self):
        (self.root / "fixture.py").write_text("def run(record):\n    return {'ok': True}\n")
        with patch("leakhunter.execution.runtime.shutil.which", return_value=None):
            result = run_suite(self.root, {"version": 1, "cases": [self.case]}, self.policy)
        self.assertEqual(result["backend"], "docker")
        self.assertEqual(result["error"], "docker_unavailable")
        self.assertFalse(result["passed"])


if __name__ == "__main__":
    unittest.main()
