import copy
import json
import os
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
                         "application_image_id": self.run["application_image"],
                         "host_filter_image_id": "sha256:" + "f" * 64,
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
                           ("application_image_id", "sha256:" + "d" * 64),
                           ("host_filter_image_id", "sha256:" + "d" * 64),
                           ("application_container_id", "b" * 64), ("source_snapshot_sha256", "unknown"),
                           ("host_isolation_verified", False)):
            evidence = self.bound()
            evidence["provenance"][key] = value
            with self.subTest(key=key), self.assertRaises(ValueError):
                validate_bound_evidence(evidence, self.run["source_sha"], self.contract)

    def test_config_pins_are_optional_but_cannot_silently_change_existing_journal_identity(self):
        with tempfile.TemporaryDirectory() as directory:
            operator = Path(directory) / "operator.json"
            operator.write_bytes((self.root / "config/handoff.vampi-delivery.json").read_bytes())
            operator.chmod(0o600)
            old = HandoffConfig.load(operator)
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

    def test_real_runner_script_revokes_success_when_filter_cleanup_fails(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            repo, tools = root / "repo", root / "tools"
            repo.mkdir()
            tools.mkdir()
            (repo / "server.py").write_text("pass\n")
            env = {**os.environ, "GIT_CONFIG_GLOBAL": os.devnull, "GIT_CONFIG_NOSYSTEM": "1"}
            for args in (["init", "-q"], ["add", "server.py"],
                         ["-c", "user.name=Fixture", "-c", "user.email=fixture@example.invalid",
                          "-c", "commit.gpgsign=false", "commit", "-qm", "fixture"]):
                subprocess.run(["git", *args], cwd=repo, env=env, capture_output=True, check=True)
            source = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=repo, env=env, text=True).strip()
            report = root / "report.json"
            report.write_text(json.dumps(self.run["report"]))
            docker = tools / "docker"
            docker.write_text(f"#!{sys.executable}\n" + '''import json,os,sys
from pathlib import Path
a=sys.argv[1:]
if '-D' in a:
    out=Path.cwd()/'acceptance'
    assert json.loads((out/'evidence.json').read_text())['gate']['passed'] is True
    assert json.loads((out/'health.json').read_text())['verified'] is True
    Path(os.environ['CLEANUP_CONTROL']).write_text('verified-before-cleanup')
    sys.exit(97)
if a[:2]==['image','inspect']: print(a[-1])
elif a[:2]==['network','inspect']: print('172.20.0.0/24' if 'Subnet' in a[3] else '172.20.0.1')
elif a[:2]==['network','create']: print('network')
elif a[:2]==['network','rm'] or a[:2]==['rm','-f']: pass
elif a[0]=='create': print('b'*64)
elif a[0]=='start': print(Path(os.environ['HTTP_REPORT']).read_text())
elif a[0]=='inspect': print('true' if 'Running' in a[2] else '0')
elif a[0]=='run':
    if '-d' in a: print('a'*64)
else: raise AssertionError('Unexpected Docker invocation')
''')
            docker.chmod(0o700)
            control = root / "control"
            env.update(PATH=str(tools) + os.pathsep + env["PATH"], CI_JOB_ID="1", CI_COMMIT_SHA=source,
                       UNSPOOL_APP_IMAGE="sha256:" + "c" * 64, UNSPOOL_PROBE_IMAGE=self.record["probe_image"],
                       UNSPOOL_FILTER_IMAGE="sha256:" + "f" * 64, HTTP_REPORT=str(report), CLEANUP_CONTROL=str(control))
            result = subprocess.run(["sh", str(self.root / "benchmarks/vampi/ci-independent.sh")],
                                    cwd=repo, env=env, capture_output=True, text=True, timeout=30)
            self.assertEqual(control.read_text(), "verified-before-cleanup")
            self.assertEqual(result.returncode, 1, result.stderr)
            self.assertFalse((repo / "acceptance/evidence.json").exists())
            self.assertFalse((repo / "acceptance/health.json").exists())
