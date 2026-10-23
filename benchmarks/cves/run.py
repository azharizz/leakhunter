"""Real-advisory benchmark: does Unspool flag each leak at its vulnerable commit and clear it at the fix?

    python -m benchmarks.cves.run                         # static analysis only (free)
    python -m benchmarks.cves.run --decision-model openai/gpt-6-luna-decisions   # plus Luna (paid)

For every case in cases.json the exact vulnerable and fixed commits are fetched, only the
files changed by the fix are exported, and the named functions are analyzed as entrypoints.
Static analysis and Luna are scored separately; every case is reported, misses included.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tarfile
import tempfile

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
sys.path.insert(0, str(ROOT))

from unspool.analyzers.python_ast import analyze_project  # noqa: E402
from unspool.policy.engine import Policy  # noqa: E402


def cases():
    return json.loads((HERE / "cases.json").read_text(encoding="utf-8"))["cases"]


def qualified(file, function):
    return file.removesuffix(".py").replace("/", ".") + "." + function


def _git(cache, *args):
    return subprocess.run(["git", "-C", str(cache), *args], check=True, capture_output=True, timeout=600)


def export(case, commit, cache_root, destination):
    """Fetch exactly one commit (no full clone) and export only the fix's files."""
    cache = cache_root / hashlib.sha256(case["repository"].encode()).hexdigest()[:16]
    if not cache.exists():
        cache.mkdir(parents=True)
        _git(cache, "init", "-q")
    if subprocess.run(["git", "-C", str(cache), "cat-file", "-e", f"{commit}^{{commit}}"],
                      capture_output=True).returncode:
        _git(cache, "fetch", "-q", "--depth", "1", case["repository"], commit)
    archive = _git(cache, "archive", "--format=tar", commit, "--", *case["files"]).stdout
    with tempfile.NamedTemporaryFile(suffix=".tar") as handle:
        handle.write(archive)
        handle.flush()
        with tarfile.open(handle.name) as bundle:
            parents = {"/".join(file.split("/")[:index]) for file in case["files"]
                       for index in range(1, file.count("/") + 1)}
            for member in bundle.getmembers():
                name = member.name.rstrip("/")
                if not ((member.isfile() and name in case["files"]) or (member.isdir() and name in parents)):
                    raise ValueError(f"unexpected archive entry {member.name}")
            bundle.extractall(destination, filter="data")


def luna_verdicts(root, analysis, policy, targets, model, call):
    from unspool.providers.context import build_review_contexts
    from unspool.providers.reviews import review_contexts
    from unspool.providers.verdict import decide
    revision = hashlib.sha256(b"".join(path.read_bytes() for path in sorted(root.rglob("*.py")))).hexdigest()
    runtime = {"status": "NOT_RUN", "passed": False, "cases": [], "reason": "Static and Luna review only"}
    contexts = build_review_contexts(root, analysis, policy, runtime, None, revision)
    decision, _, _ = review_contexts(contexts, call, model)
    luna = decide(decision, analysis["findings"], "required")
    found = [unit["verdict"] for unit in luna["units"] if unit["function"] in targets]
    for name in ("LEAK", "UNREVIEWED", "UNCERTAIN", "CLEAR"):
        if name in found:
            return name, luna["units"]
    return "UNREVIEWED", luna["units"]


def evaluate(case, root, model=None, call=None):
    policy = Policy(case["policy"])
    targets = [qualified(file, function) for file in case["files"] for function in case["functions"]]
    analysis = analyze_project(root, policy, entrypoints=targets)
    findings = [item for item in analysis["findings"] if item["function"] in targets]
    stage = {"static_flagged": bool(findings), "findings": [
        {key: item.get(key) for key in ("function", "source", "sink", "line", "exposure")} for item in findings],
        "parse_errors": analysis["coverage"]["parse_errors"]}
    if model:
        stage["luna_verdict"], units = luna_verdicts(root, analysis, policy, targets, model, call)
        stage["luna_units"] = [unit for unit in units if unit["function"] in targets]
    return stage


def outcome(vulnerable, fixed):
    """HIT flags only the vulnerable commit; FALSE_ALARM flags both; MISS flags neither; INVERTED only the fix."""
    if vulnerable is None or fixed is None:
        return "UNKNOWN"
    return {(True, False): "HIT", (True, True): "FALSE_ALARM_ON_FIX",
            (False, False): "MISS", (False, True): "INVERTED"}[(vulnerable, fixed)]


def luna_flag(stage):
    verdict = stage.get("luna_verdict")
    return True if verdict == "LEAK" else False if verdict == "CLEAR" else None


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--case", action="append", help="Limit to an advisory ID (repeatable)")
    parser.add_argument("--cache", type=Path, default=Path(tempfile.gettempdir()) / "unspool-cve-cache")
    parser.add_argument("--decision-model", default=os.environ.get("AGENT_PROVIDER_MODEL", ""))
    parser.add_argument("--provider-url", default=os.environ.get("AGENT_PROVIDER_URL",
                                                                 "https://openrouter.ai/api/v1/chat/completions"))
    args = parser.parse_args(argv)
    call = None
    if args.decision_model:
        from unspool.providers.openrouter import OpenRouterClient
        call = OpenRouterClient(args.provider_url, os.environ.get("AGENT_PROVIDER_API_KEY", "")).call
    rows = []
    for case in cases():
        if args.case and case["id"] not in args.case:
            continue
        row = {"id": case["id"], "cve": case["cve"], "advisory": case["advisory"]}
        with tempfile.TemporaryDirectory(prefix="unspool-cve-") as temporary:
            try:
                for stage, commit in (("vulnerable", case["vulnerable_commit"]), ("fixed", case["fix_commit"])):
                    root = Path(temporary) / stage
                    root.mkdir()
                    export(case, commit, args.cache, root)
                    row[stage] = dict(evaluate(case, root, args.decision_model or None, call), commit=commit)
                row["static_outcome"] = outcome(row["vulnerable"]["static_flagged"], row["fixed"]["static_flagged"])
                row["luna_outcome"] = (outcome(luna_flag(row["vulnerable"]), luna_flag(row["fixed"]))
                                       if args.decision_model else "NOT_RUN")
            except Exception as error:  # an unreproducible case is a result, not a skipped row
                row["error"] = f"{type(error).__name__}: {error}"[:500]
                row["static_outcome"] = row["luna_outcome"] = "NOT_REPRODUCED"
        row["runtime"] = case["runtime_note"]
        rows.append(row)
        print(json.dumps({key: row[key] for key in ("id", "static_outcome", "luna_outcome")}), flush=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    output = HERE / "results" / stamp
    output.mkdir(parents=True)
    (output / "results.json").write_text(json.dumps({"decision_model": args.decision_model or None,
                                                     "cases_sha256": hashlib.sha256((HERE / "cases.json").read_bytes()).hexdigest(),
                                                     "rows": rows}, indent=1) + "\n", encoding="utf-8")
    table = ["| Advisory | CVE | Static | Luna | Notes |", "| --- | --- | --- | --- | --- |"]
    for row in rows:
        table.append(f"| [{row['id']}]({row['advisory']}) | {row['cve'] or '—'} | {row['static_outcome']} | "
                     f"{row['luna_outcome']} | {row.get('error', '')} |")
    counts = {name: sum(row["static_outcome"] == name for row in rows)
              for name in ("HIT", "FALSE_ALARM_ON_FIX", "MISS", "INVERTED", "NOT_REPRODUCED")}
    (output / "RESULTS.md").write_text("\n".join(table) + f"\n\nStatic totals: {counts}\n", encoding="utf-8")
    print(f"results: {output}")


if __name__ == "__main__":
    main()
