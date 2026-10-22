from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch

import yaml

from benchmarks.closed_loop.build_manifest import _replace_placeholder
from benchmarks.closed_loop.seed import seed
from leakhunter.analyzers.python_ast import analyze_project
from leakhunter.policy.engine import Policy
from leakhunter.providers.probes import (calibration_report, merge_runtime, probe_evidence_report,
                                         select_targeted_probes)
from leakhunter.providers.verdict import decide
from unspool.attestation import statement, verify
from unspool.closed_loop_evidence import bind_diff
from unspool.exposure_diff import diff_revisions, sast_report
from unspool.gate_experiment import summarize
from unspool.issue_binding import parse_issue_binding, validate_issue_evidence
from unspool.issue_draft import draft

ROOT = Path(__file__).resolve().parent.parent
FIXTURE = ROOT / "benchmarks" / "closed_loop"
MARKERS = {"password_hash": "SYNTHETIC_UNSPOOL_SECRET_c41a_0000000", "api_token": "SYNTHETIC_UNSPOOL_TOKEN_9e2f_00000000"}
PARTIAL_FIX = '''"""Synthetic accounts service."""

PUBLIC_FIELDS = ("customer_id", "display_name", "plan")


def account_summary(account):
    summary = dict(account)
    summary.pop("password_hash", None)
    summary["display_name"] = " ".join(summary["display_name"].split())
    return summary
'''


def git(repo, *args):
    return subprocess.run(["git", "-C", str(repo), "-c", "user.name=t", "-c", "user.email=t@example.invalid", *args],
                          check=True, capture_output=True, text=True).stdout.strip()


class FakeLuna(BaseHTTPRequestHandler):
    """Loopback stand-in for the Decisions API: plausible disclosure iff the unit carries a finding."""

    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        assert self.path == "/api/alpha/decisions" and set(body) == {"model", "state", "questions"}
        context = json.loads(body["state"])["context"]
        leak = getattr(self.server, "forced_disclosure", None)
        if leak is None:
            leak = 0.95 if context.get("findings") else 0.05
        answers = {"unauthorized_disclosure_plausible": leak, "additional_context_required": 0.1,
                   "targeted_runtime_test_required": 0.1}
        payload = json.dumps({"model": body["model"], "answers": {
            name: {"type": "noul", "noul": value} for name, value in answers.items()}}).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def log_message(self, *args):
        pass


def analyze(target, manifest, data, luna_url=""):
    """The real CLI analysis; --gate exits 1 when blocked, so parse output either way."""
    result = subprocess.run(
        [sys.executable, "-m", "unspool", "--repository", str(target), "--policy", str(FIXTURE / "policy.yaml"),
         "--runtime-manifest", str(manifest), "--runtime-backend", "local", "--data-dir", str(data),
         "--provider-url", luna_url, "--decision-model", "test/luna-decisions", "--once", "analyze", "--gate"],
        cwd=ROOT, capture_output=True, text=True, timeout=120,
        env={**os.environ, "PYTHONPATH": str(ROOT), "AGENT_PROVIDER_API_KEY": "loopback-test"})
    return json.loads(result.stdout)


class ClosedLoopEndToEndTest(unittest.TestCase):
    """Real analyzer, real runtime probe, real Git revisions: plant → draft → repair → bind."""

    def setUp(self):
        self.luna = ThreadingHTTPServer(("127.0.0.1", 0), FakeLuna)
        threading.Thread(target=self.luna.serve_forever, daemon=True).start()
        self.luna_url = f"http://127.0.0.1:{self.luna.server_port}/api/v1/chat/completions"

    def tearDown(self):
        self.luna.shutdown()
        self.luna.server_close()

    def test_issue_drafted_from_leak_is_satisfied_only_by_a_complete_repair(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            repo, app = root / "repo", root / "repo" / "app"
            app.mkdir(parents=True)
            seed(FIXTURE / "target" / "accounts.py", app / "accounts.py")
            manifest = root / "runtime.yaml"
            case = {"id": "account-summary-secret-probe", "module": "accounts", "callable": "account_summary",
                    "args": [{"customer_id": "cust-1", "display_name": "  Synthetic   Account ", "plan": "team",
                              **MARKERS}],
                    "kwargs": {}, "context": {"synthetic": True},
                    "sensitive": [{"marker": value, "class": "SECRET", "symbol": f"account.{name}"}
                                  for name, value in MARKERS.items()],
                    "expect": {"customer_id": "cust-1", "display_name": "Synthetic Account", "plan": "team"},
                    "expected_violation": True,
                    "finding": {"file": "accounts.py", "function": "account_summary", "sink": "HTTP_RESPONSE"}}
            manifest.write_text(yaml.safe_dump({"version": 1, "cases": [case]}))
            git(repo, "init", "-q")
            git(repo, "add", "-A")
            git(repo, "commit", "-qm", "planted leak")
            base = git(repo, "rev-parse", "HEAD")

            leaking = analyze(app, manifest, root / "data-base", self.luna_url)
            self.assertFalse(leaking["gate"]["passed"])
            self.assertEqual(leaking["decision"]["luna"]["status"], "DECIDED")
            self.assertTrue(any(unit["verdict"] == "LEAK" for unit in leaking["decision"]["luna"]["units"]))
            self.assertFalse(any("Luna flags disclosure" in reason for reason in leaking["gate"]["reasons"]))
            self.assertTrue(any(item.get("exposure") == "WHOLE_RECORD" for item in leaking["findings"]))
            text = draft(leaking, yaml.safe_load(manifest.read_text()), "app/accounts.py", base,
                         target_directory="app")
            self.assertTrue(all(value not in text for value in MARKERS.values()), "probe values must not leak")
            self.assertIn("`customer_id`", text)
            block = parse_issue_binding(text)
            self.assertEqual(block["revision_sha"], base)
            self.assertEqual(block["content_sha256"], leaking["revision_sha"])

            # A partial fix still leaks api_token: it stays blocked and cannot be bound.
            (app / "accounts.py").write_text(PARTIAL_FIX)
            self.assertFalse(analyze(app, manifest, root / "data-partial", self.luna_url)["gate"]["passed"])

            # The complete repair is the frozen safe baseline.
            (app / "accounts.py").write_text((FIXTURE / "target" / "accounts.py").read_text())
            git(repo, "commit", "-qam", "repair")
            head = git(repo, "rev-parse", "HEAD")
            # Luna is required: without it even the repaired revision cannot pass.
            unreviewed = analyze(app, manifest, root / "data-no-luna")
            self.assertFalse(unreviewed["gate"]["passed"])
            self.assertTrue(any("Luna decision review incomplete" in reason for reason in unreviewed["gate"]["reasons"]))
            repaired = analyze(app, manifest, root / "data-head", self.luna_url)
            self.assertTrue(repaired["gate"]["passed"], repaired["gate"])
            self.assertTrue(repaired["decision"]["luna"]["units"])
            self.luna.forced_disclosure = 0.6
            false_positive = analyze(app, manifest, root / "data-false-positive", self.luna_url)
            self.assertTrue(false_positive["gate"]["passed"], false_positive["gate"])
            self.assertTrue(any(unit["verdict"] == "LEAK" for unit in false_positive["decision"]["luna"]["units"]))
            self.assertTrue(false_positive["decision"]["luna"]["probe_evidence"]["complete"])
            self.luna.forced_disclosure = None
            diff = diff_revisions(repo, FIXTURE / "policy.yaml", base, head, target_directory="app",
                                  manifest_path=manifest)
            self.assertTrue(diff["changes"])
            self.assertTrue(all(change["change"] == "removed" for change in diff["changes"]))
            self.assertEqual(diff["sast_report"]["vulnerabilities"], [])
            evidence = bind_diff(diff, repaired, head_sha=head, base=leaking, base_sha=base)
            validate_issue_evidence(evidence, block, base_sha=base, allowed_paths=("app/accounts.py",), head_sha=head)
            with self.assertRaises(ValueError):
                validate_issue_evidence(evidence, block, base_sha=head, allowed_paths=("app/accounts.py",), head_sha=head)
            with self.assertRaises(ValueError):
                validate_issue_evidence(evidence, block, base_sha=base, allowed_paths=("accounts.py",), head_sha=head)
            # The reverse diff (introducing the leak) appears once in GitLab's SAST format.
            report = diff_revisions(repo, FIXTURE / "policy.yaml", head, base, target_directory="app",
                                    manifest_path=manifest)["sast_report"]
            self.assertEqual(len(report["vulnerabilities"]), 1)
            self.assertRegex(report["scan"]["start_time"], r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}$")


class ClosedLoopUnitTest(unittest.TestCase):
    def test_issue_binding_requires_clean_probes_not_just_functional_success(self):
        finding = {"file": "accounts.py", "function": "accounts.account_summary", "source": "*.api_token",
                   "sink": "HTTP_RESPONSE", "line": 3, "classification": "SECRET", "policy_violation": True,
                   "status": "CONFIRMED_IN_TEST"}
        leaking_case = {"id": "probe-1", "passed": True,
                        "violations": [{"sink": "HTTP_RESPONSE", "classification": "SECRET"}]}
        clean_case = {"id": "probe-2", "passed": True, "violations": []}
        base_luna = {"mode": "required", "status": "DECIDED",
                     "units": [{"file": "accounts.py", "function": "accounts.account_summary", "verdict": "LEAK"}]}
        snapshot = {"revision_sha": "c" * 64, "policy": {"digest": "b" * 64}, "findings": [finding],
                    "runtime": {"status": "COMPLETED", "cases": [leaking_case, clean_case]},
                    "decision": {"luna": base_luna}}
        manifest = {"cases": [{"id": "probe-1", "module": "accounts", "expect": {"customer_id": "x"},
                               "finding": {"file": "accounts.py", "function": "account_summary",
                                           "sink": "HTTP_RESPONSE"}},
                              {"id": "probe-2", "module": "accounts", "on_demand": True,
                               "finding": {"file": "accounts.py", "function": "account_summary",
                                           "sink": "HTTP_RESPONSE"}}]}
        block = parse_issue_binding(draft(snapshot, manifest, "accounts.py", "a" * 40))
        self.assertEqual(block["version"], 3)
        self.assertEqual(len(block["probe_sha256"]), 1)
        self.assertEqual(len(block["coverage_probe_sha256"]), 2)
        evidence = {"base_sha": "a" * 40, "head_sha": "d" * 40,
                    "base_content_sha256": "c" * 64, "content_sha256": "e" * 64,
                    "analysis": {"base_findings": [finding], "head_findings": []},
                    "policy": {"base_sha256": "b" * 64, "head_sha256": "b" * 64},
                    "base_decision": {"luna": base_luna},
                    "decision": {"luna": {"mode": "required", "status": "DECIDED",
                                             "units": [{"file": "accounts.py", "function": "accounts.account_summary",
                                                        "verdict": "LEAK"}],
                                             "probe_evidence": {"status": "COMPLETE", "complete": True, "boundaries": [
                                                 {"file": "accounts.py", "function": "accounts.account_summary",
                                                  "probe_ids": ["probe-1"], "executed_probe_ids": ["probe-1"],
                                                  "status": "PASS"}]}}},
                    "base_runtime": {"status": "COMPLETED", "cases": [leaking_case, clean_case]},
                    "runtime": {"status": "COMPLETED", "passed": True, "cases": [leaking_case]}}
        with self.assertRaises(ValueError):  # functional pass with a violation is not a clean probe
            validate_issue_evidence(evidence, block, base_sha="a" * 40, allowed_paths=("accounts.py",), head_sha="d" * 40)
        evidence["runtime"]["cases"] = [{"id": "probe-1", "passed": True, "violations": []},
                                          {"id": "probe-2", "passed": True, "violations": []}]
        # A clean, exact bound probe can resolve Luna's false-positive LEAK verdict.
        validate_issue_evidence(evidence, block, base_sha="a" * 40, allowed_paths=("accounts.py",), head_sha="d" * 40)
        evidence["runtime"]["cases"].pop()
        with self.assertRaises(ValueError):
            validate_issue_evidence(evidence, block, base_sha="a" * 40, allowed_paths=("accounts.py",), head_sha="d" * 40)
        evidence["runtime"]["cases"].append({"id": "probe-2", "passed": True,
                                             "violations": [{"sink": "HTTP_RESPONSE"}]})
        with self.assertRaises(ValueError):
            validate_issue_evidence(evidence, block, base_sha="a" * 40, allowed_paths=("accounts.py",), head_sha="d" * 40)
        evidence["analysis"]["head_findings"] = [finding]
        with self.assertRaises(ValueError):
            validate_issue_evidence(evidence, block, base_sha="a" * 40, allowed_paths=("accounts.py",), head_sha="d" * 40)
        with self.assertRaises(ValueError):  # a content hash is not a commit SHA
            draft(snapshot, manifest, "accounts.py", "c" * 64)

    def test_luna_triages_without_blocking_or_dismissing_static_findings(self):
        def review(file, function, disclosure, context=0.1, status="ok", observed=False):
            return {"review_id": f"{file}|{function}", "provider_status": status,
                    "context": {"boundary": {"file": file, "function": function}},
                    "deterministic_evidence": {"observed_policy_violations": observed},
                    "decision": {"answers": {
                        "unauthorized_disclosure_plausible": {"type": "noul", "noul": disclosure},
                        "additional_context_required": {"type": "noul", "noul": context},
                        "targeted_runtime_test_required": {"type": "noul", "noul": 0.1}}}}
        noise = {"id": "noise", "file": "a.py", "function": "a.summary", "status": "POSSIBLE",
                 "runtime_evidence": {"observed": False}}
        missed_by_rules = review("b.py", "b.debug", 0.93)  # no static finding; Luna requests probe evidence
        verdict = decide({"status": "completed", "scope": {}, "reviews": [review("a.py", "a.summary", 0.05),
                                                                          missed_by_rules]}, [noise])
        self.assertEqual(verdict["dismissed"], [])
        self.assertEqual(verdict["would_dismiss"], ["noise"])
        self.assertEqual([unit["function"] for unit in verdict["flagged"]], ["b.debug"])
        self.assertFalse(verdict["reasons"])
        self.assertTrue(any("b.py:b.debug" in reason for reason in verdict["would_block"]))
        # A probe-observed leak outranks a CLEAR answer and is never dismissed.
        confirmed = dict(noise, status="CONFIRMED_IN_TEST", runtime_evidence={"observed": True})
        verdict = decide({"status": "completed", "scope": {},
                          "reviews": [review("a.py", "a.summary", 0.01, observed=True)]}, [confirmed])
        self.assertEqual((verdict["dismissed"], len(verdict["flagged"])), ([], 1))
        clear_model = review("a.py", "a.summary", 0.01)
        clear_model["post_probe_evidence"] = {"observed_policy_violations": True}
        verdict = decide({"status": "completed", "scope": {}, "reviews": [clear_model]}, [])
        self.assertEqual(verdict["units"][0]["verdict"], "LEAK")
        # Needing more context, an uncertain answer, or no answer never clears anything.
        for answer in (review("a.py", "a.summary", 0.05, context=0.8), review("a.py", "a.summary", 0.35),
                       review("a.py", "a.summary", 0.05, status="error")):
            self.assertEqual(decide({"status": "completed", "scope": {}, "reviews": [answer]}, [noise])["dismissed"], [])
        incomplete = decide({"status": "skipped", "scope": {}, "reviews": [review("a.py", "a.summary", 0.05,
                                                                                   status="skipped")]}, [noise])
        self.assertEqual(incomplete["status"], "INCOMPLETE")
        self.assertTrue(incomplete["reasons"])
        omitted = decide({"status": "partial", "scope": {"omitted_review_units": 2},
                          "reviews": [review("a.py", "a.summary", 0.05)]}, [])
        self.assertEqual(omitted["status"], "INCOMPLETE")
        advisory = decide({"status": "completed", "scope": {}, "reviews": [missed_by_rules]}, [], "advisory")
        self.assertEqual((advisory["reasons"], advisory["dismissed"]), ([], []))
        self.assertTrue(advisory["would_block"])

    def test_marker_replaces_only_its_named_field(self):
        value, count = _replace_placeholder(
            [{"password_hash": "unset", "note": "unset", "nested": {"token": "unset"}}],
            "unset", "synthetic-private-marker", "password_hash")
        self.assertEqual(count, 1)
        self.assertEqual(value[0], {"password_hash": "synthetic-private-marker", "note": "unset",
                                    "nested": {"token": "unset"}})

    def test_sast_report_groups_one_whole_record_and_uses_gitlab_time_format(self):
        changes = [{"change": "added", "identity": ["a.py", "a.f", source, "HTTP_RESPONSE"],
                    "finding": {"file": "a.py", "function": "a.f", "source": source, "sink": "HTTP_RESPONSE",
                                "line": 4, "severity": severity, "exposure": "WHOLE_RECORD",
                                "title": "Whole record containing SECRET field reaches HTTP_RESPONSE"}}
                   for source, severity in (("*.api_token", "critical"), ("*.email", "high"))]
        report = sast_report(changes)
        self.assertEqual(len(report["vulnerabilities"]), 1)
        self.assertEqual(report["vulnerabilities"][0]["severity"], "Critical")
        self.assertRegex(report["scan"]["end_time"], r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}$")

    def test_experiment_report_counts_catches_misses_false_blocks_and_unknowns(self):
        report = summarize({
            "case_set_sha256": "a" * 64, "probe_set_sha256": "b" * 64,
            "task_ids": ["leak", "safe", "unknown"], "held_out_task_ids": ["unknown"],
            "runs": [
                {"task_id": "leak", "run_id": "1", "own_tests": "passed", "gate": "blocked", "leaked": True,
                 "latency_ms": 100, "model_cost_usd": 0.01,
                 "probe_evidence": {"complete": True, "boundaries": [
                     {"status": "PASS", "probe_ids": ["probe-1"]}]}},
                {"task_id": "leak", "run_id": "2", "own_tests": "passed", "gate": "passed", "leaked": True},
                {"task_id": "safe", "run_id": "1", "own_tests": "passed", "gate": "blocked", "leaked": False,
                 "latency_ms": 200, "model_cost_usd": 0.02},
                {"task_id": "unknown", "run_id": "1", "own_tests": "error", "gate": "error", "leaked": None,
                 "error": "fixture unavailable"},
            ]}, expected_runs_per_task=1, expected_task_count=3)
        self.assertEqual((report["green_but_leaky"], report["green_leaks_blocked"],
                          report["green_leaks_missed_by_gate"], report["safe_green_patches_blocked"]), (2, 1, 1, 1))
        self.assertEqual((report["unknown_runs"], report["error_runs"]), (1, 1))
        self.assertEqual(report["model_cost_usd"]["total"], 0.03)
        self.assertEqual(report["configured_probe_coverage"],
                         {"observed_runs": 1, "complete_runs": 1, "boundaries": 1, "passing_boundaries": 1})
        self.assertEqual(report["incomplete_tasks"], {"leak": {"runs": 2, "expected": 1}})
        self.assertEqual(report["held_out_run_count"], 1)

    def test_review_selects_nonclear_probes_and_reports_complete_boundary_coverage(self):
        context = {"boundary": {"file": "support.py", "function": "support.summarize"}}
        answers = {"targeted_runtime_test_required": {"type": "noul", "noul": 0.9},
                   "unauthorized_disclosure_plausible": {"type": "noul", "noul": 0.8}}
        decision = {"reviews": [{"provider_status": "ok", "context": context, "decision": {"answers": answers}}]}
        manifest = {"cases": [
            {"id": "baseline", "module": "support", "finding": {"file": "support.py", "function": "summarize"}},
            {"id": "match", "module": "support", "on_demand": True,
             "finding": {"file": "support.py", "function": "summarize"}},
            {"id": "other", "module": "accounts", "on_demand": True,
             "finding": {"file": "accounts.py", "function": "summary"}}]}
        self.assertEqual([case["id"] for case in select_targeted_probes(decision, manifest)], ["match"])
        baseline = {"status": "COMPLETED", "passed": True, "functional_passed": True,
                    "cases": [{"id": "baseline", "passed": True, "violations": []}]}
        targeted = {"status": "COMPLETED", "passed": False, "functional_passed": True,
                    "cases": [{"id": "match", "passed": True, "violations": [{"sink": "AI_PROMPT"}]}]}
        merged = merge_runtime(baseline, targeted)
        self.assertFalse(merged["passed"])  # a leak found by a model-selected probe blocks the gate
        self.assertEqual(merged["targeted_case_ids"], ["match"])
        manifest["cases"] = manifest["cases"][1:]  # calibration needs exactly one probe per boundary
        report = calibration_report(decision, merge_runtime({"status": "NOT_RUN", "cases": []}, targeted), manifest)
        self.assertEqual((report["sample_count"], report["brier_score"]), (1, 0.04))
        uncertain_reviews = [{"provider_status": "ok", "context": context,
                              "decision": {"answers": {
                                  "targeted_runtime_test_required": {"type": "noul", "noul": 0.1},
                                  "unauthorized_disclosure_plausible": {"type": "noul", "noul": 0.35},
                                  "additional_context_required": {"type": "noul", "noul": 0.1}}}},
                             {"provider_status": "ok",
                              "context": {"boundary": {"file": "accounts.py", "function": "accounts.summary"}},
                              "decision": {"answers": {
                                  "targeted_runtime_test_required": {"type": "noul", "noul": 0.1},
                                  "unauthorized_disclosure_plausible": {"type": "noul", "noul": 0.05},
                                  "additional_context_required": {"type": "noul", "noul": 0.8}}}}]
        uncertain = {"reviews": uncertain_reviews}
        self.assertEqual([case["id"] for case in select_targeted_probes(uncertain, manifest)], ["match", "other"])
        verdict = decide({"status": "completed", "scope": {}, "reviews": uncertain["reviews"]}, [])
        uncertain["luna"] = verdict
        complete_runtime = {"status": "COMPLETED", "cases": [
            {"id": "match", "passed": True, "error": None, "violations": []},
            {"id": "other", "passed": True, "error": None, "violations": []}]}
        coverage = probe_evidence_report(uncertain, {"cases": manifest["cases"]}, complete_runtime)
        self.assertTrue(coverage["complete"])
        self.assertEqual(len(coverage["boundaries"]), 2)
        coverage = probe_evidence_report(uncertain, {"cases": manifest["cases"]}, baseline)
        self.assertFalse(coverage["complete"])  # selected probe is missing

    def test_probe_coverage_includes_connected_helpers_and_module_import_cases(self):
        module_review = {"review_id": "module", "provider_status": "ok",
                         "context": {"boundary": {"file": "billing/service.py", "function": "billing.service",
                                                     "connected_functions": []}},
                         "decision": {"answers": {
                             "unauthorized_disclosure_plausible": {"type": "noul", "noul": 0.4},
                             "additional_context_required": {"type": "noul", "noul": 0.1}}}}
        helper_review = {"review_id": "helper", "provider_status": "ok",
                         "context": {"boundary": {"file": "support/llm.py", "function": "support.llm.complete",
                                                     "connected_functions": ["support.service.summarize"]}},
                         "decision": {"answers": {
                             "unauthorized_disclosure_plausible": {"type": "noul", "noul": 0.4},
                             "additional_context_required": {"type": "noul", "noul": 0.1}}}}
        cases = [
            {"id": "charge", "module": "billing.service", "callable": "charge",
             "finding": {"file": "billing/service.py", "function": "charge", "sink": "HTTP_RESPONSE"}},
            {"id": "notify", "module": "billing.service", "callable": "notify",
             "finding": {"file": "billing/service.py", "function": "notify", "sink": "WEBHOOK"}},
            {"id": "summarize", "module": "support.service", "callable": "summarize", "on_demand": True,
             "finding": {"file": "support/service.py", "function": "summarize", "sink": "AI_PROMPT"}},
        ]
        decision = {"reviews": [module_review, helper_review], "luna": {"units": [
            {"review_id": "module", "file": "billing/service.py", "function": "billing.service", "verdict": "UNCERTAIN"},
            {"review_id": "helper", "file": "support/llm.py", "function": "support.llm.complete", "verdict": "UNCERTAIN"},
        ]}}
        self.assertEqual([case["id"] for case in select_targeted_probes(decision, {"cases": cases})], ["summarize"])
        runtime = {"status": "COMPLETED", "cases": [
            {"id": case_id, "passed": True, "error": None, "violations": []}
            for case_id in ("charge", "notify", "summarize")
        ]}
        report = probe_evidence_report(decision, {"cases": cases}, runtime)
        self.assertTrue(report["complete"])
        by_function = {item["function"]: item for item in report["boundaries"]}
        self.assertEqual(set(by_function["billing.service"]["probe_ids"]), {"charge", "notify"})
        self.assertEqual(by_function["support.llm.complete"]["probe_ids"], ["summarize"])

    def test_whole_record_and_common_llm_sdk_calls_are_findings_but_projections_are_not(self):
        policy = Policy({"version": 1, "classifications": {"PUBLIC": 0, "PII": 1, "SECRET": 2},
                         "sources": [{"selector": "*.email", "class": "PII"},
                                     {"selector": "*.password_hash", "class": "SECRET"}],
                         "sinks": [{"kind": "HTTP_RESPONSE", "allow": ["PUBLIC"]},
                                   {"kind": "AI_PROMPT", "allow": ["PUBLIC"]}]})
        code = (
            "import openai\n"
            "client = openai.OpenAI()\n"
            "PUBLIC = ('name',)\n"
            "def account_summary(account):\n"
            "    return dict(account)\n"
            "def projected(account):\n"
            "    return {field: account[field] for field in PUBLIC}\n"
            "def summarize(ticket):\n"
            "    prompt = f\"{ticket['subject']}: {ticket}\"\n"
            "    return client.chat.completions.create(messages=[{'role': 'user', 'content': prompt}])\n"
        )
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "app.py").write_text(code)
            result = analyze_project(root, policy, entrypoints=["app.account_summary", "app.projected", "app.summarize"])
        functions = {(item["function"], item["sink"]) for item in result["findings"]}
        self.assertIn(("app.account_summary", "HTTP_RESPONSE"), functions)
        self.assertIn(("app.summarize", "AI_PROMPT"), functions)
        self.assertNotIn("app.projected", {function for function, _ in functions})
        # A scalar argument echoed back (an ID) is not a whole record.
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "app.py").write_text("def lookup(user_id):\n    return {'error': 'not_found', 'user_id': user_id}\n")
            self.assertEqual(analyze_project(root, policy, entrypoints=["app.lookup"])["findings"], [])

    def test_attestation_rejects_evidence_changed_after_signing(self):
        evidence = {"version": 1, "base_sha": "1" * 40, "head_sha": "2" * 40,
                    "analysis": {"base_findings": [], "head_findings": []},
                    "policy": {"base_sha256": "a" * 64, "head_sha256": "a" * 64}, "flow_diff": [],
                    "runtime": {"status": "COMPLETED", "passed": True,
                                "cases": [{"id": "probe", "passed": True, "violations": []}]},
                    "decision": {"luna": {"mode": "required", "status": "DECIDED",
                                            "flagged": [], "dismissed": [], "units": [],
                                            "probe_evidence": {"status": "COMPLETE", "complete": True,
                                                               "boundaries": []}}},
                    "gate": {"passed": True}}
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            evidence_path, statement_path, bundle_path = (root / name for name in
                                                          ("evidence.json", "statement.json", "bundle.json"))
            evidence["decision"]["luna"]["probe_evidence"]["complete"] = False
            evidence_path.write_text(json.dumps(evidence))
            with self.assertRaises(ValueError):
                statement(evidence_path, base_sha="1" * 40, head_sha="2" * 40)
            evidence["decision"]["luna"]["probe_evidence"]["complete"] = True
            evidence_path.write_text(json.dumps(evidence))
            statement_path.write_text(json.dumps(statement(evidence_path, base_sha="1" * 40, head_sha="2" * 40)))
            bundle_path.write_text("signed bundle placeholder")
            ok = type("Result", (), {"returncode": 0})()
            identity = "https://gitlab.com/group/project//.gitlab-ci.yml@refs/heads/main"
            with patch("unspool.attestation.subprocess.run", return_value=ok):
                verify(evidence_path, statement_path, bundle_path, expected_identity=identity,
                       expected_head_sha="2" * 40)
                evidence_path.write_text(json.dumps({**evidence, "flow_diff": [{"change": "added"}]}))
                with self.assertRaises(ValueError):
                    verify(evidence_path, statement_path, bundle_path, expected_identity=identity,
                           expected_head_sha="2" * 40)


if __name__ == "__main__":
    unittest.main()
