"""Strict parser and verifier for additive Unspool finding checks in issues."""
from __future__ import annotations

import hashlib
import json
import posixpath
import re

from unspool.providers.probes import probe_evidence_complete

_START_V1 = "<!-- unspool:finding:v1\n"
_START_V2 = "<!-- unspool:finding:v2\n"
_START = "<!-- unspool:finding:v3\n"
_END = "\n-->"
_SHA256 = re.compile(r"[0-9a-f]{64}")
_SHA1 = re.compile(r"[0-9a-f]{40}")
_FIELDS_V1 = {"version", "findings_sha256", "probe_sha256", "policy_sha256", "revision_sha",
              "content_sha256", "allowlisted_file", "target_directory", "file", "function", "sink"}
_FIELDS = _FIELDS_V1 | {"luna_sha256"}
_FIELDS_V3 = _FIELDS | {"coverage_probe_sha256"}


def finding_fingerprint(finding: dict) -> str:
    """Stable identity for one policy flow, independent of its line number."""
    values = [finding.get(key) for key in ("file", "function", "source", "sink")]
    if any(not isinstance(value, str) or not value for value in values):
        raise ValueError("Finding lacks stable source-flow fields")
    return hashlib.sha256("\0".join(values).encode()).hexdigest()


def boundary_fingerprint(file: str, function: str) -> str:
    """Stable identity for a reviewed function boundary, independent of graph node IDs."""
    if not isinstance(file, str) or not file or not isinstance(function, str) or not function:
        raise ValueError("Luna boundary lacks stable source fields")
    return hashlib.sha256((file + "\0" + function).encode()).hexdigest()


def repository_path(block: dict) -> str:
    """Analyzer files are relative to the analyzed directory; allowlists are repository-relative."""
    return posixpath.normpath(posixpath.join(block["target_directory"], block["file"]))


def probe_fingerprint(case_id: str) -> str:
    return hashlib.sha256(case_id.encode()).hexdigest()


def _hashes(value, name, *, empty=False):
    if (not isinstance(value, list) or (not value and not empty)
            or any(not isinstance(item, str) or not _SHA256.fullmatch(item) for item in value)
            or len(set(value)) != len(value)):
        raise ValueError(f"Invalid {name} in Unspool finding block")
    return value


def parse_issue_binding(description: str) -> dict | None:
    """Return the issue's finding block, or None. Issue text is data: it can only add checks."""
    if not isinstance(description, str):
        return None
    starts = [(marker, version) for marker, version in ((_START, 3), (_START_V2, 2), (_START_V1, 1))
              if marker in description]
    if not starts:
        return None
    if len(starts) != 1 or description.count(starts[0][0]) != 1:
        raise ValueError("Issue must contain exactly one Unspool finding block")
    marker, version = starts[0]
    raw = description.split(marker, 1)[1]
    if _END not in raw:
        raise ValueError("Unterminated Unspool finding block")
    raw = raw.split(_END, 1)[0]

    def unique(pairs):
        value = {}
        for key, item in pairs:
            if key in value:
                raise ValueError("Duplicate issue finding field")
            value[key] = item
        return value

    block = json.loads(raw, object_pairs_hook=unique)
    fields = _FIELDS_V3 if version == 3 else _FIELDS if version == 2 else _FIELDS_V1
    if (not isinstance(block, dict) or set(block) != fields
            or type(block.get("version")) is not int or block["version"] != version
            or any(not isinstance(block.get(key), str) or not _SHA256.fullmatch(block[key])
                   for key in ("policy_sha256", "content_sha256"))
            or not isinstance(block.get("revision_sha"), str) or not _SHA1.fullmatch(block["revision_sha"])
            or any(not isinstance(block.get(key), str) or not block[key].strip()
                   for key in ("allowlisted_file", "target_directory", "file", "function", "sink"))):
        raise ValueError("Invalid Unspool finding block")
    _hashes(block["findings_sha256"], "finding hashes", empty=version in {2, 3})
    _hashes(block["probe_sha256"], "probe hashes")
    if version in {2, 3}:
        _hashes(block["luna_sha256"], "Luna boundary hashes", empty=True)
        if not block["findings_sha256"] and not block["luna_sha256"]:
            raise ValueError("Finding block must bind a static finding or a Luna boundary")
    else:
        block["luna_sha256"] = []
    if version == 3:
        _hashes(block["coverage_probe_sha256"], "configured coverage probe hashes")
    else:
        block["coverage_probe_sha256"] = list(block["probe_sha256"])
    return block


def _luna(evidence, name):
    decision = evidence.get("decision") if isinstance(evidence, dict) else None
    if name == "base":
        decision = evidence.get("base_decision") if isinstance(evidence, dict) else None
    luna = decision.get("luna") if isinstance(decision, dict) else None
    if (not isinstance(luna, dict) or luna.get("mode") != "required" or luna.get("status") != "DECIDED"
            or not isinstance(luna.get("units"), list)):
        raise ValueError(f"Issue-bound {name} evidence requires complete Luna decisions in required mode")
    return luna


def _unit_map(luna):
    units = {}
    for unit in luna["units"]:
        if not isinstance(unit, dict):
            raise ValueError("Invalid Luna unit in issue-bound evidence")
        key = boundary_fingerprint(unit.get("file"), unit.get("function"))
        if key in units:
            raise ValueError("Duplicate Luna boundary in issue-bound evidence")
        units[key] = unit
    return units


def validate_issue_evidence(evidence: dict, block: dict, *, base_sha: str, allowed_paths,
                            head_sha: str) -> None:
    """Require the bound baseline exposure to disappear and its probes to pass cleanly."""
    allowed = set(allowed_paths)
    if block["allowlisted_file"] not in allowed or repository_path(block) != block["allowlisted_file"]:
        raise ValueError("Issue finding is outside the operator allowlist")
    if block["revision_sha"] != base_sha:
        raise ValueError("Issue finding was analyzed against another base revision; redraft or rebase")
    if (not isinstance(evidence, dict) or evidence.get("base_sha") != base_sha
            or not isinstance(head_sha, str) or not _SHA1.fullmatch(head_sha)
            or evidence.get("head_sha") != head_sha or head_sha == base_sha):
        raise ValueError("Issue-bound evidence does not analyze the exact merge-request revisions")
    if (not isinstance(evidence.get("base_content_sha256"), str)
            or not _SHA256.fullmatch(evidence["base_content_sha256"])
            or evidence["base_content_sha256"] != block["content_sha256"]):
        raise ValueError("Issue evidence was drafted from different base-revision content")
    analysis = evidence.get("analysis")
    baseline = analysis.get("base_findings") if isinstance(analysis, dict) else None
    current = analysis.get("head_findings") if isinstance(analysis, dict) else None
    if not isinstance(baseline, list) or not isinstance(current, list):
        raise ValueError("Issue-bound baseline and head findings are required")
    baseline_ids = {finding_fingerprint(item) for item in baseline if isinstance(item, dict)}
    current_ids = {finding_fingerprint(item) for item in current if isinstance(item, dict)}
    bound = set(block["findings_sha256"])
    if not bound <= baseline_ids:
        raise ValueError("Issue finding was not present in the independently analyzed base revision")
    if bound & current_ids:
        raise ValueError("Issue finding remains in the merge-request revision")
    policy = evidence.get("policy")
    if (not isinstance(policy, dict) or policy.get("base_sha256") != block["policy_sha256"]
            or policy.get("head_sha256") != block["policy_sha256"]):
        raise ValueError("Issue policy hash differs from the verified evidence")

    base_luna, head_luna = _luna(evidence, "base"), _luna(evidence, "head")
    base_units, head_units = _unit_map(base_luna), _unit_map(head_luna)
    for key in block["luna_sha256"]:
        if key not in base_units or base_units[key].get("verdict") != "LEAK":
            raise ValueError("Issue Luna boundary was not flagged in the exact analyzed base revision")
        if key not in head_units:
            raise ValueError("Issue Luna boundary is missing from the complete repair-revision review")
    head_probe_evidence = head_luna.get("probe_evidence")
    if not probe_evidence_complete(head_probe_evidence):
        raise ValueError("Repair evidence lacks complete configured probes for non-clear Luna boundaries")
    reported = {(item.get("file"), item.get("function")): item
                for item in head_probe_evidence.get("boundaries", []) if isinstance(item, dict)}
    for key in block["luna_sha256"]:
        unit = head_units[key]
        identity = (unit.get("file"), unit.get("function"))
        if unit.get("verdict") in {"LEAK", "UNCERTAIN"} and reported.get(identity, {}).get("status") != "PASS":
            raise ValueError("A non-clear repair-revision Luna boundary lacks passing configured probe evidence")

    base_runtime = evidence.get("base_runtime")
    baseline_cases = base_runtime.get("cases") if isinstance(base_runtime, dict) else None
    runtime = evidence.get("runtime")
    cases = runtime.get("cases") if isinstance(runtime, dict) else None
    if (not isinstance(base_runtime, dict) or base_runtime.get("status") != "COMPLETED"
            or not isinstance(baseline_cases, list)
            or not isinstance(runtime, dict) or runtime.get("status") != "COMPLETED"
            or runtime.get("passed") is not True or not isinstance(cases, list)):
        raise ValueError("Issue-bound base and head runtime probe evidence is missing")
    bound_probes = set(block["probe_sha256"])
    coverage_probes = set(block["coverage_probe_sha256"])
    if not bound_probes <= coverage_probes:
        raise ValueError("Every leak-proving probe must be included in configured boundary coverage")
    for probe_hash in bound_probes:
        base_matches = [case for case in baseline_cases if isinstance(case, dict)
                        and isinstance(case.get("id"), str)
                        and probe_fingerprint(case["id"]) == probe_hash]
        head_matches = [case for case in cases if isinstance(case, dict)
                        and isinstance(case.get("id"), str)
                        and probe_fingerprint(case["id"]) == probe_hash]
        if (len(base_matches) != 1 or base_matches[0].get("passed") is not True
                or not isinstance(base_matches[0].get("violations"), list)
                or not any(isinstance(item, dict) and item.get("sink") == block["sink"]
                           for item in base_matches[0]["violations"])):
            raise ValueError("Bound probe did not uniquely observe the reported baseline exposure")
    for probe_hash in coverage_probes:
        base_matches = [case for case in baseline_cases if isinstance(case, dict)
                        and isinstance(case.get("id"), str)
                        and probe_fingerprint(case["id"]) == probe_hash]
        head_matches = [case for case in cases if isinstance(case, dict)
                        and isinstance(case.get("id"), str)
                        and probe_fingerprint(case["id"]) == probe_hash]
        if (len(base_matches) != 1 or base_matches[0].get("passed") is not True
                or base_matches[0].get("error") or not isinstance(base_matches[0].get("violations"), list)):
            raise ValueError("Every configured boundary probe must be present exactly once in baseline evidence")
        if (len(head_matches) != 1 or head_matches[0].get("passed") is not True
                or head_matches[0].get("error") or head_matches[0].get("violations") != []):
            raise ValueError("Every configured boundary probe must pass cleanly exactly once on the repair revision")
