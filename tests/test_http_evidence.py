import copy
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from unspool.handoff import complete
from unspool.handoff_config import HandoffConfig
from unspool.http_evidence import bind, snapshot_digest, validate_bound_evidence
import test_handoff_config as config_fixture


class HTTPEvidenceTest(unittest.TestCase):
    def setUp(self):
        self.root = Path(__file__).resolve().parents[1]
        self.record = json.loads((self.root / "benchmarks/vampi/results.generic.json").read_text())
        self.run = self.record["runs"][1]
        self.plan = json.loads((self.root / "benchmarks/vampi/http-plan.json").read_text())
        self.contract = {"plan_sha256": self.run["report"]["plan_sha256"],
                         "probe_sha256": self.record["probe_sha256"],
                         "probe_image_id": self.record["probe_image"],
                         "case_ids": [c["id"] for c in self.plan["cases"]]}

    def bound(self, report=None):
        return bind(report or self.run["report"], self.plan, self.run["source_sha"],
                    probe_sha256=self.record["probe_sha256"], app_image=self.run["application_image"],
                    probe_image=self.record["probe_image"], snapshot_sha256="c" * 64,
                    app_container="a" * 64, probe_container="b" * 64,
                    filter_image="sha256:" + "f" * 64, host_isolation_verified=True)

    def test_recorded_safe_http_passes_but_recorded_leak_is_never_promoted(self):
        validate_bound_evidence(self.bound(), self.run["source_sha"], self.contract)
        with self.assertRaises(ValueError):
            self.bound(self.record["runs"][0]["report"])
        for mutation in ("missing_case", "wrong_case", "hidden_observation", "string_flag", "wrong_plan"):
            raw = copy.deepcopy(self.run["report"])
            if mutation == "missing_case":
                raw["runtime"]["cases"].pop()
            elif mutation == "wrong_case":
                raw["runtime"]["cases"][0]["id"] = "other"
            elif mutation == "hidden_observation":
                raw["runtime"]["cases"][0]["observations"] = [{"sink": "HTTP_RESPONSE"}]
            elif mutation == "string_flag":
                raw["runtime"]["security_passed"] = "true"
            else:
                raw["plan_sha256"] = "d" * 64
            with self.subTest(mutation=mutation), self.assertRaises(ValueError):
                self.bound(raw)

    def test_controller_refuses_forged_revision_probe_image_and_container_provenance(self):
        for key, value in (("source_sha", "d" * 40), ("plan_sha256", "d" * 64),
                           ("probe_sha256", "d" * 64), ("probe_image_id", "sha256:" + "d" * 64),
                           ("application_container_id", "b" * 64), ("source_snapshot_sha256", "unknown"),
                           ("host_isolation_verified", False)):
            evidence = self.bound()
            evidence["provenance"][key] = value
            with self.subTest(key=key), self.assertRaises(ValueError):
                validate_bound_evidence(evidence, self.run["source_sha"], self.contract)

    def test_config_pins_are_optional_but_cannot_silently_change_existing_journal_identity(self):
        old = HandoffConfig.load(self.root / "config/handoff.vampi-delivery.json")
        self.assertEqual(old.digest, "888b3d9f4b78d985b3cfde7bea3f9550f06119c0116af3779065b6a18dedae5b")
        fixture = config_fixture.ConfigTest()
        config = fixture.load({**fixture.data(), "http_contract": self.contract})
        self.assertEqual(dict(config.http_contract)["case_ids"], tuple(self.contract["case_ids"]))
        self.assertNotEqual(config.digest, fixture.load(fixture.data()).digest)
        for contract in ({}, {**self.contract, "probe_sha256": "tag"}, {**self.contract, "case_ids": []}):
            with self.assertRaises(ValueError):
                fixture.load({**fixture.data(), "http_contract": contract})
        api, calls = fixture.api()
        with self.assertRaisesRegex(ValueError, "provenance"):
            complete(42, 1, api=api, config=config)
        self.assertTrue(all(method == "GET" for method, _ in calls))

    def test_controller_accepts_only_the_configured_http_case_set_and_source(self):
        fixture = config_fixture.ConfigTest()
        config = fixture.load({**fixture.data(), "http_contract": self.contract})
        for stale in (False, True):
            api, calls = fixture.api()
            original = api.request

            def request(method, path, body=None):
                if path.endswith("/artifacts/evidence.json"):
                    value = self.bound()
                    value["provenance"]["source_sha"] = ("c" if stale else "a") * 40
                    return value
                return original(method, path, body)

            api.request = request
            if stale:
                with self.assertRaisesRegex(ValueError, "another source"):
                    complete(42, 1, api=api, config=config)
            else:
                self.assertEqual(complete(42, 1, api=api, config=config)["status"], "READY_FOR_REVIEW")
            self.assertTrue(all(method == "GET" for method, _ in calls))

    def test_snapshot_binds_non_python_resources_and_failed_cli_removes_stale_success(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source"
            source.mkdir()
            (source / "server.py").write_text("pass")
            (source / "asset.json").write_text('{}')
            before = snapshot_digest(source)
            (source / "asset.json").write_text('{"changed":true}')
            self.assertNotEqual(before, snapshot_digest(source))
            output = root / "output"
            output.mkdir()
            for name in ("evidence.json", "health.json"):
                (output / name).write_text('{"verified":true}')
            report = root / "report.json"
            report.write_text(json.dumps(self.record["runs"][0]["report"]))
            p = subprocess.run([sys.executable, "-m", "unspool.http_evidence", "--report", str(report),
                                "--plan", str(self.root / "benchmarks/vampi/http-plan.json"),
                                "--probe", str(self.root / "unspool/http_acceptance.py"), "--snapshot", str(source),
                                "--source", self.run["source_sha"], "--app-image", self.run["application_image"],
                                "--probe-image", self.record["probe_image"], "--app-container", "a" * 64,
                                "--probe-container", "b" * 64, "--filter-image", "sha256:" + "f" * 64,
                                "--host-isolation-verified", "--output", str(output)],
                               cwd=self.root, capture_output=True, text=True, timeout=10)
            self.assertNotEqual(p.returncode, 0)
            self.assertFalse((output / "evidence.json").exists())
            self.assertFalse((output / "health.json").exists())
