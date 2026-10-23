"""Create a reviewable Markdown issue from a frozen Unspool analysis snapshot.

The draft is printed only; a person reviews it and opens the issue.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import re

from unspool.execution.runtime import load_manifest
from unspool.languages import finding_function
from unspool.issue_binding import (_END, _START, boundary_fingerprint, finding_fingerprint,
                                   probe_fingerprint, repository_path)


def _actionable(finding: dict) -> bool:
    return isinstance(finding, dict) and bool(finding.get("sink")) and (
        finding.get("policy_violation") is True or finding.get("status") == "CONFIRMED_IN_TEST")


def _violates(case_result, sink):
    violations = case_result.get("violations") if isinstance(case_result, dict) else None
    return isinstance(violations, list) and any(
        isinstance(item, dict) and item.get("sink") == sink for item in violations)


def _case_matches(case, file, function, sink):
    mapping = case.get("finding") if isinstance(case, dict) else None
    return (isinstance(mapping, dict) and mapping.get("file") == file
            and finding_function(case) == function and mapping.get("sink") == sink)


def _review_for(snapshot, file, function, review_id=None):
    decision = snapshot.get("decision") if isinstance(snapshot, dict) else None
    reviews = decision.get("reviews", []) if isinstance(decision, dict) else []
    matches = [review for review in reviews if isinstance(review, dict)
               and (not review_id or review.get("review_id") == review_id)
               and (review.get("context", {}).get("boundary", {}).get("file"),
                    review.get("context", {}).get("boundary", {}).get("function")) == (file, function)]
    return matches[0] if len(matches) == 1 else None


def _lines_for(review, findings, runtime_cases):
    lines = {item.get("line") for item in findings if isinstance(item.get("line"), int)}
    if not lines and isinstance(review, dict):
        boundary = (review.get("context") or {}).get("boundary") or {}
        locations = boundary.get("source_locations") or []
        lines.update(item.get("line") for item in locations if isinstance(item, dict)
                     and type(item.get("line")) is int and item["line"] > 0)
        entrypoint = boundary.get("entrypoint") or {}
        if not lines and type(entrypoint.get("line")) is int and entrypoint["line"] > 0:
            lines.add(entrypoint["line"])
    if not lines:
        lines.update(line.get("line") for case in runtime_cases for line in case.get("executed_lines", [])
                     if isinstance(line, dict) and type(line.get("line")) is int and line["line"] > 0)
    return sorted(lines)


def draft(snapshot: dict, manifest: dict, allowlisted_file: str, base_sha: str,
          finding_id: str | None = None, target_directory: str = ".",
          review_id: str | None = None) -> str:
    """Bind one confirmed source-to-sink issue and the exact probes that reproduced it.

    A Luna-only issue is draftable when a source-backed LEAK decision and a configured
    runtime probe independently observed the same boundary leaking. Luna alone is not
    enough to label a source-to-sink exposure.
    """
    if not isinstance(snapshot, dict) or not isinstance(manifest, dict):
        raise ValueError("Analysis snapshot and runtime manifest must be objects")
    content = snapshot.get("revision_sha")
    policy = snapshot.get("policy")
    policy_sha = policy.get("digest") if isinstance(policy, dict) else None
    if (not isinstance(base_sha, str) or not re.fullmatch(r"[0-9a-f]{40}", base_sha)
            or not isinstance(content, str) or not re.fullmatch(r"[0-9a-f]{64}", content)
            or not isinstance(policy_sha, str) or not re.fullmatch(r"[0-9a-f]{64}", policy_sha)):
        raise ValueError("A full base commit SHA plus the snapshot content and policy hashes are required")
    findings, cases, runtime = snapshot.get("findings"), manifest.get("cases"), snapshot.get("runtime")
    runtime_cases = runtime.get("cases") if isinstance(runtime, dict) else None
    decision = snapshot.get("decision")
    luna = decision.get("luna") if isinstance(decision, dict) else None
    if (not isinstance(findings, list) or not isinstance(cases, list)
            or not isinstance(runtime, dict) or runtime.get("status") != "COMPLETED"
            or not isinstance(runtime_cases, list) or not isinstance(luna, dict)
            or luna.get("mode") != "required" or luna.get("status") != "DECIDED"):
        raise ValueError("Complete findings, required Luna decisions, manifest cases, and baseline probes are required")
    observed = {case.get("id"): case for case in runtime_cases if isinstance(case, dict)}
    actionable = [item for item in findings if _actionable(item)]
    group_of = lambda item: (item.get("file"), item.get("function"), item.get("sink"))
    static_groups = {}
    if finding_id:
        selected = [item for item in actionable if item.get("id") == finding_id]
        if not selected:
            raise ValueError("The requested finding is not actionable in this snapshot")
        group = group_of(selected[0])
        static_groups = {group: [item for item in actionable if group_of(item) == group]}
    elif review_id:
        static_groups = {}
    else:
        confirmed = [item for item in actionable if item.get("status") == "CONFIRMED_IN_TEST"]
        for item in confirmed:
            static_groups.setdefault(group_of(item), []).append(item)

    candidates = []
    for group, items in static_groups.items():
        file, function, sink = group
        unit = next((item for item in luna.get("units", []) if isinstance(item, dict)
                     and (item.get("file"), item.get("function")) == (file, function)), None)
        candidates.append((file, function, sink, items, unit))

    if not candidates:
        wanted_units = [unit for unit in luna.get("units", []) if isinstance(unit, dict)
                        and unit.get("verdict") == "LEAK"
                        and (not review_id or unit.get("review_id") == review_id)]
        for unit in wanted_units:
            file, function = unit.get("file"), unit.get("function")
            for case in cases:
                mapping = case.get("finding") if isinstance(case, dict) else None
                if not isinstance(mapping, dict) or mapping.get("file") != file or finding_function(case) != function:
                    continue
                sink = mapping.get("sink")
                result = observed.get(case.get("id"))
                if sink and _violates(result, sink):
                    key = (file, function, sink)
                    if not any(candidate[:3] == key for candidate in candidates):
                        candidates.append((file, function, sink, [], unit))
    if len(candidates) != 1:
        raise ValueError("Select exactly one confirmed finding group or Luna boundary with a failing probe")
    file, function, sink, group, luna_unit = candidates[0]
    location = {"target_directory": target_directory, "file": file}
    if not isinstance(target_directory, str) or not target_directory or allowlisted_file != repository_path(location):
        raise ValueError("Allowlisted path must be the finding's file within the analyzed target directory")
    probes, coverage_probes, public_fields, sources = [], [], set(), set()
    related_cases = [case for case in cases if _case_matches(case, file, function, sink)]
    for case in related_cases:
        case_id = case.get("id")
        result = observed.get(case_id)
        if (not isinstance(case_id, str) or not isinstance(result, dict)
                or result.get("passed") is not True or result.get("error")
                or not isinstance(result.get("violations"), list)):
            raise ValueError("Every configured probe for the bound boundary must have completed")
        coverage_probes.append(case_id)
        if _violates(result, sink):
            probes.append(case_id)
            mapping = case.get("finding", {})
            if isinstance(mapping.get("symbol"), str):
                sources.add(mapping["symbol"])
            for violation in result.get("violations", []):
                if isinstance(violation, dict) and violation.get("sink") == sink and isinstance(violation.get("symbol"), str):
                    sources.add(violation["symbol"])
            if isinstance(case.get("expect"), dict):
                public_fields.update(map(str, case["expect"]))
    if not probes:
        raise ValueError("No completed runtime probe observed this finding group leaking")
    if group:
        sources.update(item["source"] for item in group if isinstance(item.get("source"), str))
        lines = _lines_for(_review_for(snapshot, file, function), group, [])
        finding_hashes = sorted({finding_fingerprint(item) for item in group})
    else:
        lines = _lines_for(_review_for(snapshot, file, function, review_id), [],
                           [observed[case_id] for case_id in coverage_probes])
        finding_hashes = []
    if not lines:
        raise ValueError("A source line for the confirmed boundary is required")
    luna_hashes = ([boundary_fingerprint(file, function)]
                   if isinstance(luna_unit, dict) and luna_unit.get("verdict") == "LEAK" else [])
    block = {"version": 3, "findings_sha256": finding_hashes,
             "luna_sha256": luna_hashes,
             "probe_sha256": sorted({probe_fingerprint(case_id) for case_id in probes}),
             "coverage_probe_sha256": sorted({probe_fingerprint(case_id) for case_id in coverage_probes}),
             "policy_sha256": policy_sha, "revision_sha": base_sha, "content_sha256": content,
             "allowlisted_file": allowlisted_file, "target_directory": target_directory,
             "file": file, "function": function, "sink": sink}
    source_text = ", ".join(f"`{item}`" for item in sorted(sources)) or "the observed synthetic source"
    luna_line = ((f"Luna verdict for this boundary: **{luna_unit['verdict']}**"
                  + (f" (unauthorized disclosure plausible p={luna_unit['disclosure']:.2f})"
                     if luna_unit.get("disclosure") is not None else "") + ".\n\n")
                 if isinstance(luna_unit, dict) else "")
    where = ", ".join(f"`{file}:{line}`" for line in lines)
    keep = ("- These public response fields keep their current values: "
            + ", ".join(f"`{name}`" for name in sorted(public_fields)) + ".\n") if public_fields else ""
    if group:
        exposure = (f"Unspool found {source_text} reaching `{sink}` at {where} in `{function}`. "
                    f"{len(probes)} runtime probe(s) observed the synthetic value leaving through this sink.")
        static_acceptance = "- Every bound source-to-sink finding is absent when the repair revision is analyzed independently.\n"
    else:
        exposure = (f"Luna flagged the source-backed boundary `{function}` in `{file}`, and "
                    f"{len(probes)} runtime probe(s) independently observed {source_text} reaching `{sink}` at {where}. "
                    "This is limited to the configured synthetic probe and does not claim a general finding.")
        static_acceptance = ("- The exact repair revision has a complete required Luna review; every bound probe "
                             "passes without an observed violation. Luna's verdict alone does not approve or reject it.\n")
    return (
        f"## Exposure finding\n\n{exposure}\n\n"
        f"{luna_line}Analyzed commit `{base_sha}`; policy SHA-256 `{policy_sha}`. "
        f"Only `{allowlisted_file}` may change. Probe IDs are recorded as hashes; probe values are never included.\n\n"
        "## Acceptance criteria\n\n"
        f"{static_acceptance}"
        "- Every configured probe for this boundary passes its functional check with no observed violation on the repair revision.\n"
        f"{keep}"
        "- Policy, tests, probes and CI stay unchanged.\n\n"
        f"{_START}{json.dumps(block, sort_keys=True, separators=(',', ':'))}{_END}\n"
    )


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--snapshot", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--allowlisted-file", required=True)
    parser.add_argument("--base-sha", required=True, help="Full Git commit SHA that was analyzed")
    parser.add_argument("--target-directory", default=".", help="Analyzed directory, relative to the repository")
    parser.add_argument("--finding-id")
    parser.add_argument("--review-id", help="Select a Luna review boundary when no static finding was emitted")
    args = parser.parse_args(argv)
    print(draft(json.loads(args.snapshot.read_text(encoding="utf-8")), load_manifest(args.manifest),
                args.allowlisted_file, args.base_sha, args.finding_id, args.target_directory,
                args.review_id), end="")


if __name__ == "__main__":
    main()
