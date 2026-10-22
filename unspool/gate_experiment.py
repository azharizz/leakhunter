"""Aggregate frozen Unspool gate-experiment results without dropping failures."""
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
import re

_SHA256 = re.compile(r"[0-9a-f]{64}")
_TEST = {"passed", "failed", "unknown", "error"}
_GATE = {"passed", "blocked", "unknown", "error"}
_LUNA = {"LEAK", "CLEAR", "UNCERTAIN", "UNREVIEWED"}


def summarize(value: dict, *, expected_runs_per_task: int = 3, expected_task_count: int = 12) -> dict:
    if not isinstance(value, dict):
        raise ValueError("Frozen case/probe hashes and a run list are required")
    case_hash, probe_hash = value.get("case_set_sha256"), value.get("probe_set_sha256")
    if (not isinstance(case_hash, str) or not _SHA256.fullmatch(case_hash)
            or not isinstance(probe_hash, str) or not _SHA256.fullmatch(probe_hash)
            or not isinstance(value.get("runs"), list)
            or not isinstance(value.get("task_ids"), list) or not value["task_ids"]
            or len(value["task_ids"]) != expected_task_count
            or any(not isinstance(item, str) or not item for item in value["task_ids"])
            or len(set(value["task_ids"])) != len(value["task_ids"])
            or not isinstance(value.get("held_out_task_ids"), list) or not value["held_out_task_ids"]
            or any(item not in value["task_ids"] for item in value.get("held_out_task_ids", []))
            or len(value["held_out_task_ids"]) == len(value["task_ids"])
            or len(set(value.get("held_out_task_ids", []))) != len(value.get("held_out_task_ids", []))
            or type(expected_runs_per_task) is not int or expected_runs_per_task < 1
            or type(expected_task_count) is not int or expected_task_count < 2):
        raise ValueError("Frozen task IDs, case/probe hashes, and a run list are required")
    runs = value["runs"]
    unique = set()
    by_task = {}
    green_tests = green_leaky = caught = missed = false_blocks = unknowns = errors = 0
    luna_counts = {key: 0 for key in (*sorted(_LUNA), "MISSING")}
    luna_tp = luna_fp = luna_tn = luna_fn = luna_unknown = 0
    durations, costs = [], []
    probe_coverage_runs = probe_coverage_complete = probe_boundaries = probe_boundaries_passed = 0
    for run in runs:
        if (not isinstance(run, dict) or not isinstance(run.get("task_id"), str) or not run["task_id"]
                or not isinstance(run.get("run_id"), str) or not run["run_id"]
                or not isinstance(run.get("own_tests"), str) or run["own_tests"] not in _TEST
                or not isinstance(run.get("gate"), str) or run["gate"] not in _GATE
                or not (run.get("leaked") is True or run.get("leaked") is False or run.get("leaked") is None)):
            raise ValueError("Each run needs task/run IDs and explicit test, gate, and leak verdicts")
        luna = run.get("luna_verdict")
        if luna is not None and (not isinstance(luna, str) or luna not in _LUNA):
            raise ValueError("Luna verdict must be LEAK, CLEAR, UNCERTAIN, UNREVIEWED or omitted")
        probe_evidence = run.get("probe_evidence")
        if probe_evidence is not None:
            if not isinstance(probe_evidence, dict):
                raise ValueError("Invalid configured-probe evidence in a run result")
            boundaries = probe_evidence.get("boundaries")
            if (type(probe_evidence.get("complete")) is not bool or not isinstance(boundaries, list)
                    or any(not isinstance(item, dict) or item.get("status") not in {"PASS", "FAILED", "INCOMPLETE"}
                           for item in boundaries)):
                raise ValueError("Invalid configured-probe evidence in a run result")
            probe_coverage_runs += 1
            probe_coverage_complete += probe_evidence["complete"] is True
            probe_boundaries += len(boundaries)
            probe_boundaries_passed += sum(item["status"] == "PASS" for item in boundaries)
        luna_counts[luna if luna is not None else "MISSING"] += 1
        if run["leaked"] is None or luna not in {"LEAK", "CLEAR"}:
            luna_unknown += 1
        elif run["leaked"]:
            luna_tp += luna == "LEAK"
            luna_fn += luna == "CLEAR"
        else:
            luna_fp += luna == "LEAK"
            luna_tn += luna == "CLEAR"
        key = (run["task_id"], run["run_id"])
        if run["task_id"] not in value["task_ids"]:
            raise ValueError("Run results contain a task outside the frozen task set")
        if key in unique:
            raise ValueError("Duplicate task/run result")
        unique.add(key)
        by_task.setdefault(run["task_id"], []).append(run)
        green_tests += run["own_tests"] == "passed"
        if run["own_tests"] == "passed" and run["leaked"] is True:
            green_leaky += 1
            caught += run["gate"] == "blocked"
            missed += run["gate"] == "passed"
        if run["own_tests"] == "passed" and run["leaked"] is False and run["gate"] == "blocked":
            false_blocks += 1
        if run["own_tests"] == "unknown" or run["gate"] == "unknown" or run["leaked"] is None:
            unknowns += 1
        if run["own_tests"] == "error" or run["gate"] == "error" or run.get("error"):
            errors += 1
        for field, values in (("latency_ms", durations), ("model_cost_usd", costs)):
            number = run.get(field)
            if number is not None:
                if (isinstance(number, bool) or not isinstance(number, (int, float))
                        or not math.isfinite(number) or number < 0):
                    raise ValueError(f"Invalid {field} in run result")
                values.append(float(number))
    incomplete = {task: {"runs": len(by_task.get(task, [])), "expected": expected_runs_per_task}
                 for task in value["task_ids"]
                 if len(by_task.get(task, [])) != expected_runs_per_task}
    held_out_ids = set(value.get("held_out_task_ids", []))
    held_out_runs = [run for run in runs if run["task_id"] in held_out_ids]
    return {
        "version": 2,
        "case_set_sha256": case_hash,
        "probe_set_sha256": probe_hash,
        "expected_runs_per_task": expected_runs_per_task,
        "task_ids": value["task_ids"],
        "held_out_task_ids": sorted(held_out_ids),
        "held_out_run_count": len(held_out_runs),
        "run_count": len(runs),
        "task_count": len(value["task_ids"]),
        "observed_task_count": len(by_task),
        "green_test_patches": green_tests,
        "green_but_leaky": green_leaky,
        "green_leaks_blocked": caught,
        "green_leaks_missed_by_gate": missed,
        "safe_green_patches_blocked": false_blocks,
        "luna_verdict_counts": luna_counts,
        "luna_vs_probe_truth": {"tp": luna_tp, "fp": luna_fp, "tn": luna_tn,
                                 "fn": luna_fn, "unknown": luna_unknown},
        "configured_probe_coverage": {
            "observed_runs": probe_coverage_runs,
            "complete_runs": probe_coverage_complete,
            "boundaries": probe_boundaries,
            "passing_boundaries": probe_boundaries_passed,
        },
        "unknown_runs": unknowns,
        "error_runs": errors,
        "incomplete_tasks": incomplete,
        "latency_ms": {"count": len(durations), "mean": round(sum(durations) / len(durations), 3)
                       if durations else None},
        "model_cost_usd": {"count": len(costs), "total": round(sum(costs), 8),
                            "mean": round(sum(costs) / len(costs), 8) if costs else None},
        "runs": runs,
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--expected-runs-per-task", type=int, default=3)
    parser.add_argument("--expected-task-count", type=int, default=12)
    args = parser.parse_args(argv)
    report = summarize(json.loads(args.input.read_text(encoding="utf-8")),
                       expected_runs_per_task=args.expected_runs_per_task,
                       expected_task_count=args.expected_task_count)
    args.output.write_text(json.dumps(report, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({key: report[key] for key in (
        "run_count", "task_count", "observed_task_count", "held_out_run_count",
        "green_but_leaky", "green_leaks_blocked", "green_leaks_missed_by_gate",
        "safe_green_patches_blocked", "luna_verdict_counts", "luna_vs_probe_truth",
        "configured_probe_coverage", "unknown_runs", "error_runs", "incomplete_tasks")}, sort_keys=True))


if __name__ == "__main__":
    main()
