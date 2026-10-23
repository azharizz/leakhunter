"""Bind exact-revision static, Luna and runtime evidence for the local controller."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import re

from unspool.exposure_diff import compare_findings, sast_report
from unspool.issue_binding import boundary_fingerprint

_SHA1 = re.compile(r"[0-9a-f]{40}")
_SHA256 = re.compile(r"[0-9a-f]{64}")


def _luna(evidence, label):
    decision = evidence.get("decision") if isinstance(evidence, dict) else None
    luna = decision.get("luna") if isinstance(decision, dict) else None
    if (not isinstance(luna, dict) or luna.get("mode") != "required" or luna.get("status") != "DECIDED"
            or not isinstance(luna.get("units"), list)):
        raise ValueError(f"{label} evidence must contain complete required Luna decisions")
    units = {}
    for unit in luna["units"]:
        if not isinstance(unit, dict):
            raise ValueError(f"{label} evidence contains an invalid Luna unit")
        identity = boundary_fingerprint(unit.get("file"), unit.get("function"))
        if identity in units:
            raise ValueError(f"{label} evidence contains duplicate Luna boundaries")
        units[identity] = unit
    reviews = decision.get("reviews", [])
    review_by_id = {review.get("review_id"): review for review in reviews
                    if isinstance(review, dict) and isinstance(review.get("review_id"), str)}
    return luna, units, review_by_id


def _line(unit, reviews):
    review = reviews.get(unit.get("review_id"), {})
    context = review.get("context") or {}
    boundary = context.get("boundary") or {}
    entrypoint = boundary.get("entrypoint") or {}
    line = entrypoint.get("line")
    if type(line) is int and line > 0:
        return line
    locations = boundary.get("source_locations") or []
    return next((item["line"] for item in locations
                 if isinstance(item, dict) and type(item.get("line")) is int and item["line"] > 0), None)


def _luna_changes(base, head):
    _, before, _ = _luna(base, "Base")
    _, after, reviews = _luna(head, "Head")
    changes = []
    for identity, unit in after.items():
        if unit.get("verdict") != "LEAK" or before.get(identity, {}).get("verdict") == "LEAK":
            continue
        line = _line(unit, reviews)
        if line is None:
            raise ValueError("Luna SAST finding has no source-backed line")
        changes.append({"identity": identity, "file": unit["file"], "function": unit["function"],
                        "line": line, "base_verdict": before.get(identity, {}).get("verdict"),
                        "head_verdict": "LEAK", "disclosure": unit.get("disclosure")})
    return sorted(changes, key=lambda item: (item["file"], item["line"], item["function"]))


def _runtime(evidence, label, *, require_pass):
    value = evidence.get("runtime") if isinstance(evidence, dict) else None
    cases = value.get("cases") if isinstance(value, dict) else None
    if (not isinstance(value, dict) or value.get("status") != "COMPLETED"
            or not isinstance(cases, list) or not cases
            or any(not isinstance(case, dict) or type(case.get("passed")) is not bool or case.get("error")
                   for case in cases)):
        raise ValueError(f"{label} revision lacks complete runtime evidence")
    if require_pass and (value.get("passed") is not True
                         or any(case.get("passed") is not True or case.get("violations") for case in cases)):
        raise ValueError("Head revision lacks complete passing runtime evidence")
    return value


def verification_note(evidence: dict) -> str:
    """Render a compact MR note from exact-revision evidence without probe values."""
    runtime = evidence.get("runtime") if isinstance(evidence, dict) else None
    cases = runtime.get("cases", []) if isinstance(runtime, dict) else []
    passed = sum(case.get("passed") is True and not case.get("violations")
                 for case in cases if isinstance(case, dict))
    gate = evidence.get("gate") if isinstance(evidence, dict) else None
    ready = (isinstance(gate, dict) and gate.get("passed") is True
             and isinstance(runtime, dict) and runtime.get("passed") is True
             and bool(cases) and passed == len(cases))
    flow_diff = evidence.get("flow_diff", []) if isinstance(evidence, dict) else []
    luna_diff = evidence.get("luna_diff", []) if isinstance(evidence, dict) else []
    sha = evidence.get("head_sha", "unknown") if isinstance(evidence, dict) else "unknown"
    base_sha = evidence.get("base_sha", "unknown") if isinstance(evidence, dict) else "unknown"
    luna = (evidence.get("decision") or {}).get("luna", {}) if isinstance(evidence, dict) else {}
    status = "passed" if ready else "blocked or incomplete"
    return (f"<!-- unspool-verification:{sha} -->\n"
            f"## Unspool verification\n\nBase revision: `{base_sha}`  \nCandidate revision: `{sha}`  \n"
            f"Gate: **{status}**  \n"
            f"Static flow changes: {len(flow_diff)}  \n"
            f"New Luna LEAK decisions: {len(luna_diff)}  \n"
            f"Luna review: `{luna.get('status', 'missing')}`  \n"
            f"Runtime probes: {passed}/{len(cases)} passed without observed violations.\n"
            + _why(gate, luna, cases) +
            "\nProbe values are excluded. Results cover only the configured synthetic probes.\n")


def _why(gate, luna, cases):
    """Explain the verdict per boundary: Luna's triage, the probes it selected, what they observed."""
    reasons = gate.get("reasons", []) if isinstance(gate, dict) else []
    lines = [f"- {reason}" for reason in reasons if isinstance(reason, str)]
    units = {(unit.get("file"), unit.get("function")): unit for unit in luna.get("units", [])
             if isinstance(unit, dict)} if isinstance(luna, dict) else {}
    results = {case.get("id"): case for case in cases if isinstance(case, dict)}
    rows = []
    boundaries = (luna.get("probe_evidence") or {}).get("boundaries", []) if isinstance(luna, dict) else []
    for item in boundaries:
        if not isinstance(item, dict):
            continue
        unit = units.get((item.get("file"), item.get("function")), {})
        disclosure = unit.get("disclosure")
        triage = f"{unit.get('verdict', '?')} ({disclosure:.2f})" if isinstance(disclosure, float) else unit.get("verdict", "?")
        seen = sorted({f"`{v.get('symbol')}` → {v.get('sink')}" for case_id in item.get("probe_ids", [])
                       for v in (results.get(case_id) or {}).get("violations") or [] if isinstance(v, dict)})
        failed = [f"`{case_id}`" for case_id in item.get("probe_ids", [])
                  if (results.get(case_id) or {}).get("violations")]
        outcome = (f"**{item.get('status')}**: {', '.join(failed)} observed {', '.join(seen)}" if seen
                   else f"**{item.get('status')}**")
        rows.append(f"| `{item.get('file')}:{item.get('function')}` | {triage} | "
                    f"{len(item.get('executed_probe_ids', []))}/{len(item.get('probe_ids', []))} | {outcome} |")
    text = ("\n### Why\n\n" + "\n".join(lines) + "\n") if lines else ""
    if rows:
        text += ("\n### Probes selected by Luna triage\n\n| Boundary | Luna (disclosure) | Probes run | Result |\n"
                 "| --- | --- | --- | --- |\n" + "\n".join(rows) + "\n")
    return text


def bind_diff(diff: dict, head: dict, *, head_sha: str, base: dict | None = None,
              base_sha: str | None = None, sast_output: Path | None = None,
              note_output: Path | None = None) -> dict:
    """Combine exact Git revisions with complete head and baseline evidence.

    Both model runs are retained. Baseline gates may fail because they reproduce the
    exposure; the candidate head must pass its evidence gate, required-review
    completeness, configured probe coverage and runtime checks. Luna verdicts are triage.
    """
    if (not isinstance(diff, dict) or not isinstance(head, dict)
            or not isinstance(diff.get("base_sha"), str) or not _SHA1.fullmatch(diff["base_sha"])
            or not isinstance(head_sha, str) or not _SHA1.fullmatch(head_sha)
            or diff.get("head_sha") != head_sha
            or not isinstance(head.get("revision_sha"), str) or not _SHA256.fullmatch(head["revision_sha"])
            or not isinstance(diff.get("policy_sha256"), str)
            or not _SHA256.fullmatch(diff["policy_sha256"])):
        raise ValueError("Exposure diff and gated head evidence must bind the exact requested revisions")
    if base is None or base_sha != diff["base_sha"] or not isinstance(base, dict):
        raise ValueError("Exact base-revision Luna and runtime evidence are required")
    if not isinstance(base.get("revision_sha"), str) or not _SHA256.fullmatch(base["revision_sha"]):
        raise ValueError("Base evidence must include its analyzed content hash")
    base_findings, head_findings = diff.get("base_findings"), diff.get("head_findings")
    if (not isinstance(base_findings, list) or not isinstance(head_findings, list)
            or any(not isinstance(item, dict) for item in base_findings + head_findings)
            or not isinstance(base.get("findings"), list) or not isinstance(head.get("findings"), list)
            or compare_findings(base_findings, base["findings"])
            or compare_findings(head_findings, head["findings"])):
        raise ValueError("Exact-revision findings must match the independently analyzed base and head snapshots")
    base_policy, head_policy = base.get("policy"), head.get("policy")
    if (not isinstance(base_policy, dict) or not isinstance(head_policy, dict)
            or base_policy.get("digest") != diff["policy_sha256"]
            or head_policy.get("digest") != diff["policy_sha256"]):
        raise ValueError("Base, static diff and head evidence use different policies")
    if not isinstance(diff.get("changes"), list):
        raise ValueError("Exposure diff must include a complete flow-change list")
    base_luna, _, _ = _luna(base, "Base")
    _luna(head, "Head")
    decision_changes = _luna_changes(base, head)

    # Emit review artifacts before enforcing the candidate gate so a blocked MR
    # still receives its SAST finding and an honest evidence summary.
    report = sast_report(diff["changes"], luna_changes=decision_changes)
    if sast_output:
        Path(sast_output).write_text(json.dumps(report, sort_keys=True) + "\n", encoding="utf-8")
    base_runtime = base.get("runtime")
    combined = dict(head)
    combined.update({
        "base_sha": diff["base_sha"],
        "head_sha": head_sha,
        "base_content_sha256": base["revision_sha"],
        "content_sha256": head["revision_sha"],
        "analysis": {"base_findings": base_findings, "head_findings": head_findings},
        "base_runtime": base_runtime,
        "base_decision": {"luna": base_luna},
        "policy": {**head_policy, "base_sha256": diff["policy_sha256"], "head_sha256": diff["policy_sha256"]},
        "flow_diff": diff["changes"],
        "luna_diff": decision_changes,
    })
    if note_output:
        Path(note_output).write_text(verification_note(combined), encoding="utf-8")

    base_runtime = _runtime(base, "Base", require_pass=False)
    _runtime(head, "Head", require_pass=False)
    gate = head.get("gate")
    if not isinstance(gate, dict) or gate.get("passed") is not True:
        reasons = gate.get("reasons") if isinstance(gate, dict) else None
        raise ValueError("candidate gate blocked: " + "; ".join(reasons or ["no passing gate"]))
    _runtime(head, "Head", require_pass=True)
    return combined


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--diff", type=Path, required=True)
    parser.add_argument("--base-evidence", type=Path, required=True)
    parser.add_argument("--head-evidence", type=Path, required=True)
    parser.add_argument("--base-sha", required=True)
    parser.add_argument("--head-sha", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--sast-output", type=Path)
    parser.add_argument("--note-output", type=Path)
    args = parser.parse_args(argv)
    try:
        value = bind_diff(json.loads(args.diff.read_text(encoding="utf-8")),
                          json.loads(args.head_evidence.read_text(encoding="utf-8")), head_sha=args.head_sha,
                          base=json.loads(args.base_evidence.read_text(encoding="utf-8")),
                          base_sha=args.base_sha, sast_output=args.sast_output, note_output=args.note_output)
    except ValueError as error:
        _print_note(args.note_output)
        raise SystemExit(f"Unspool blocked revision {args.head_sha[:12]}: {error}") from None
    args.output.write_text(json.dumps(value, sort_keys=True, separators=(",", ":")), encoding="utf-8")
    _print_note(args.note_output)


def _print_note(path):
    """Show the verdict in the job log, not only in an artifact."""
    if path and Path(path).is_file():
        print(Path(path).read_text(encoding="utf-8").split("\n", 1)[-1])


if __name__ == "__main__":
    main()
