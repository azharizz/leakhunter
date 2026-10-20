"""Parse pinned upstream Git blobs without importing/executing target application code."""
import argparse
import ast
from collections import Counter
import hashlib
from importlib.metadata import version
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import time

from leakhunter.analyzers import python_ast, sources
from leakhunter.analyzers.python_ast import analyze_project
from leakhunter.policy.engine import Policy


def classification(expected, observed, failed=False):
    if failed:
        return "EXECUTION_ERROR"
    if expected is None:
        return "UNKNOWN_LABEL"
    return ("TP" if observed else "FN") if expected else ("FP" if observed else "TN")


def verify_case_target(case, content):
    module = case["file"][:-3].replace("/", ".")
    functions = set()

    def visit(nodes, prefix):
        for node in nodes:
            if isinstance(node, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
                qualified = prefix + "." + node.name
                if not isinstance(node, ast.ClassDef):
                    functions.add(qualified)
                visit(node.body, qualified)

    visit(ast.parse(content).body, module)
    if case["entrypoint"] not in functions or case["entrypoint"].rsplit(".", 1)[-1] != case["function"]:
        raise ValueError("Case does not identify an existing qualified source callable")


def source_files(root, sha):
    actual = subprocess.check_output(["git", "-C", str(root), "rev-parse", sha + "^{commit}"], text=True).strip()
    if actual != sha:
        raise ValueError("Source revision mismatch")
    names = subprocess.check_output(["git", "-C", str(root), "ls-tree", "-r", "--name-only", sha], text=True).splitlines()
    files = {}
    for name in names:
        if not name.endswith(".py"):
            continue
        if Path(name).is_absolute() or any(part in {"", ".", ".."} for part in name.split("/")):
            raise ValueError("Unsafe source path")
        files[name] = subprocess.check_output(["git", "-C", str(root), "show", sha + ":" + name])
    return files


def worker(manifest, repository, checkout, output):
    spec = next(item for item in manifest["repositories"] if item["id"] == repository)
    cases = [case for case in manifest["cases"] if case["repository"] == repository]
    files = source_files(checkout, spec["sha"])
    for case in cases:
        verify_case_target(case, files[case["file"]])
    with tempfile.TemporaryDirectory(prefix="unspool-external-static-") as directory:
        root = Path(directory)
        for name, content in files.items():
            target = root / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(content)
        started = time.monotonic()
        result = analyze_project(root, Policy(manifest["policy"]), entrypoints=[c["entrypoint"] for c in cases])
        duration = round((time.monotonic() - started) * 1000, 2)
    coverage = result["coverage"]
    rows = []
    for case in cases:
        matching = [f for f in result["findings"] if f["file"] == case["file"]
                    and f["sink"] == case["sink"]
                    and (f["function"] == case["function"] or f["function"].endswith("." + case["function"]))]
        failed = any(e["file"] == case["file"] for e in coverage["parse_errors"])
        rows.append({"id": case["id"], "expected_violation": case["expected_violation"],
                     "observed_possible_flow": bool(matching),
                     "classification": classification(case["expected_violation"], bool(matching), failed),
                     "matching_finding_count": len(matching),
                     "source_file_sha256": hashlib.sha256(files[case["file"]]).hexdigest()})
    output.write_text(json.dumps({"repository": repository, "sha": spec["sha"], "duration_ms": duration,
                                  "python_files": len(files), "coverage": {k: len(coverage[k]) for k in
                                  ("parse_errors", "unresolved_calls", "unsupported_constructs")}, "cases": rows}))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, default=Path(__file__).with_name("cases.json"))
    parser.add_argument("--checkout", action="append", default=[], help="repository-id=/authorized/checkout")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--worker")
    args = parser.parse_args()
    raw = args.manifest.read_bytes()
    manifest = json.loads(raw)
    checkouts = dict(item.split("=", 1) for item in args.checkout)
    if args.worker:
        worker(manifest, args.worker, Path(checkouts[args.worker]), args.output)
        return
    results = []
    with tempfile.TemporaryDirectory(prefix="unspool-static-results-") as directory:
        for spec in manifest["repositories"]:
            repository = spec["id"]
            output = Path(directory) / (repository + ".json")
            command = [sys.executable, "-I", str(Path(__file__).resolve()), "--manifest", str(args.manifest.resolve()),
                       "--worker", repository, "--checkout", repository + "=" + checkouts[repository], "--output", str(output)]
            try:
                subprocess.run(command, check=True, timeout=90, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                results.append(json.loads(output.read_text()))
            except (subprocess.SubprocessError, OSError, ValueError):
                results.append({"repository": repository, "sha": spec["sha"], "status": "EXECUTION_ERROR", "cases": [
                    {"id": c["id"], "expected_violation": c["expected_violation"], "classification": "EXECUTION_ERROR"}
                    for c in manifest["cases"] if c["repository"] == repository]})
    counts = Counter(c["classification"] for result in results for c in result["cases"])
    report = {"kind": "frozen-external-static-feasibility", "unspool_version": version("unspool"),
              "analyzer_sha256": hashlib.sha256(Path(python_ast.__file__).read_bytes()).hexdigest(),
              "source_reader_sha256": hashlib.sha256(Path(sources.__file__).read_bytes()).hexdigest(),
              "manifest_sha256": hashlib.sha256(raw).hexdigest(), "repositories": results,
              "counts": dict(counts), "total_cases": sum(counts.values()),
              "runtime_cases_executed": 0, "model_calls": 0,
              "binary_labeled_cases": sum(counts[k] for k in ("TP", "FP", "TN", "FN")),
              "precision_on_labeled_cases": counts["TP"] / (counts["TP"] + counts["FP"]) if counts["TP"] + counts["FP"] else None,
              "recall_on_labeled_cases": counts["TP"] / (counts["TP"] + counts["FN"]) if counts["TP"] + counts["FN"] else None,
              "limitations": ["Source-labeled security-lab cases, not held-out", "Possible static flow is not executed vulnerability proof",
                              "No-match is a miss/negative prediction, never application safety", "Unknown labels excluded from binary metrics but retained"]}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps({"counts": dict(counts), "total_cases": report["total_cases"], "manifest_sha256": report["manifest_sha256"]}))


if __name__ == "__main__":
    main()
