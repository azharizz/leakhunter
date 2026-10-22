"""Let typed review answers choose on-demand probes, and score review calibration.

The model only chooses *where* to look: it can select operator-written ``on_demand``
manifest cases for a boundary. It never writes probe inputs, and only the executed
runtime result counts as evidence.
"""
from __future__ import annotations

from leakhunter.languages import finding_function, module_name
from leakhunter.providers.verdict import CLEAR_AT, CONTEXT_AT, probability as _probability


_THRESHOLD = 0.8
_BINS = 10


def _boundary(review):
    context = review.get("context") if isinstance(review, dict) else None
    boundary = context.get("boundary") if isinstance(context, dict) else None
    if not isinstance(boundary, dict):
        return None
    file, function = boundary.get("file"), boundary.get("function")
    return (file, function) if isinstance(file, str) and isinstance(function, str) else None


def _case_boundary(case):
    """Manifest cases name a bare callable; review boundaries use qualified names."""
    finding = case.get("finding") if isinstance(case, dict) else None
    return (finding.get("file"), finding_function(case)) if isinstance(finding, dict) else None


def _mapped_cases(unit, review, cases):
    """Use configured cases for this function, its connected callees, or module import."""
    identity = (unit.get("file"), unit.get("function"))
    context = review.get("context") if isinstance(review, dict) else None
    boundary = context.get("boundary") if isinstance(context, dict) else None
    connected = set(boundary.get("connected_functions", [])) if isinstance(boundary, dict) else set()
    is_module = (isinstance(identity[0], str) and isinstance(identity[1], str)
                 and identity[1] == module_name(identity[0]))
    return [case for case in cases if (mapped := _case_boundary(case)) and (
        mapped == identity or mapped[1] in connected or is_module and mapped[0] == identity[0])]


def baseline_manifest(manifest: dict | None) -> dict | None:
    """The always-run suite: every case not reserved for model-selected execution."""
    if not manifest:
        return None
    return dict(manifest, cases=[case for case in manifest["cases"] if not case.get("on_demand")])


def select_targeted_probes(decision: dict, manifest: dict) -> list[dict]:
    """Pick on-demand cases for every boundary that is not clearly low risk."""
    wanted, connected, modules = set(), set(), set()
    for review in decision.get("reviews", []) if isinstance(decision, dict) else []:
        if not isinstance(review, dict):
            continue
        probability = _probability(review.get("decision"), "targeted_runtime_test_required")
        disclosure = _probability(review.get("decision"), "unauthorized_disclosure_plausible")
        context = _probability(review.get("decision"), "additional_context_required")
        boundary = _boundary(review)
        if (review.get("provider_status") == "ok" and boundary
                and ((probability is not None and probability >= _THRESHOLD)
                     or (disclosure is not None and disclosure > CLEAR_AT)
                     or (context is not None and context >= CONTEXT_AT)
                     or (review.get("deterministic_evidence") or {}).get("observed_policy_violations") is True)):
            wanted.add(boundary)
            review_context = review.get("context") or {}
            boundary_context = review_context.get("boundary") or {}
            connected.update(boundary_context.get("connected_functions", []))
            if boundary[1] == module_name(boundary[0]):
                modules.add(boundary[0])
    selected = []
    for case in (manifest or {}).get("cases", []):
        identity = _case_boundary(case)
        if (case.get("on_demand") is True and identity
                and (identity in wanted or identity[1] in connected or identity[0] in modules)):
            selected.append(case)
    return selected


def probe_evidence_report(decision: dict, manifest: dict | None, runtime: dict) -> dict:
    """Check configured probe coverage for every non-clear Luna boundary.

    This is bounded evidence: a pass means all configured cases mapped by exact
    function, connected call, or same-file module import ran cleanly.
    """
    specs = [case for case in (manifest or {}).get("cases", []) if isinstance(case, dict)]
    results = [case for case in runtime.get("cases", []) if isinstance(case, dict)] if isinstance(runtime, dict) else []
    units = ((decision.get("luna") or {}).get("units", []) if isinstance(decision, dict) else [])
    reviews = {review.get("review_id"): review for review in decision.get("reviews", [])
               if isinstance(review, dict)} if isinstance(decision, dict) else {}
    boundaries = []
    for unit in units:
        if not isinstance(unit, dict) or unit.get("verdict") not in {"LEAK", "UNCERTAIN"}:
            continue
        identity = (unit.get("file"), unit.get("function"))
        expected = _mapped_cases(unit, reviews.get(unit.get("review_id")), specs)
        expected_ids = [case.get("id") for case in expected]
        matched = {case_id: [case for case in results if case.get("id") == case_id]
                   for case_id in expected_ids if isinstance(case_id, str)}
        complete = bool(expected_ids) and all(len(matched.get(case_id, [])) == 1 for case_id in expected_ids)
        clean = complete and all(
            matched[case_id][0].get("passed") is True
            and not matched[case_id][0].get("error")
            and matched[case_id][0].get("violations") == []
            for case_id in expected_ids
        )
        boundaries.append({"file": identity[0], "function": identity[1],
                           "probe_ids": expected_ids,
                           "executed_probe_ids": [case_id for case_id, cases in matched.items() if len(cases) == 1],
                           "status": "PASS" if clean else "INCOMPLETE" if not complete else "FAILED"})
    complete = all(item["status"] == "PASS" for item in boundaries)
    return {"status": "COMPLETE" if complete else "INCOMPLETE", "complete": complete,
            "boundaries": boundaries,
            "scope": "Configured cases mapped by function/call graph/module import only; not all possible inputs."}


def probe_evidence_complete(report: dict | None) -> bool:
    """Validate the compact coverage report before it crosses a release boundary."""
    boundaries = report.get("boundaries") if isinstance(report, dict) else None
    return (isinstance(report, dict) and report.get("status") == "COMPLETE"
            and report.get("complete") is True and isinstance(boundaries, list)
            and all(isinstance(item, dict) and item.get("status") == "PASS"
                    and isinstance(item.get("file"), str) and isinstance(item.get("function"), str)
                    and isinstance(item.get("probe_ids"), list) and item["probe_ids"]
                    and all(isinstance(case_id, str) and case_id for case_id in item["probe_ids"])
                    and len(set(item["probe_ids"])) == len(item["probe_ids"])
                    and isinstance(item.get("executed_probe_ids"), list)
                    and all(isinstance(case_id, str) and case_id for case_id in item["executed_probe_ids"])
                    and set(item["probe_ids"]) == set(item["executed_probe_ids"])
                    for item in boundaries))


def merge_runtime(baseline: dict, targeted: dict | None) -> dict:
    """Evidence from model-selected probes counts exactly like baseline evidence."""
    if not targeted or not targeted.get("cases"):
        return baseline
    if baseline.get("status") == "NOT_RUN":
        return dict(targeted, targeted_case_ids=[case["id"] for case in targeted["cases"]])
    statuses = {baseline.get("status"), targeted.get("status")}
    status = "COMPLETED" if statuses == {"COMPLETED"} else next(item for item in statuses if item != "COMPLETED")
    cases = list(baseline.get("cases", [])) + list(targeted["cases"])
    functional = bool(baseline.get("functional_passed")) and bool(targeted.get("functional_passed"))
    return dict(baseline, status=status, cases=cases, functional_passed=functional,
                passed=status == "COMPLETED" and functional and not any(case.get("violations") for case in cases),
                duration_ms=(baseline.get("duration_ms") or 0) + (targeted.get("duration_ms") or 0),
                targeted_case_ids=[case["id"] for case in targeted["cases"]])


def calibration_report(decision: dict, runtime: dict, manifest: dict | None) -> dict:
    """Score disclosure probabilities only where exactly one executed probe covers the boundary."""
    specs = {case.get("id"): case for case in (manifest or {}).get("cases", []) if isinstance(case, dict)}
    cases = runtime.get("cases", []) if isinstance(runtime, dict) else []
    samples, unknown = [], 0
    for review in decision.get("reviews", []) if isinstance(decision, dict) else []:
        probability = _probability(review.get("decision"), "unauthorized_disclosure_plausible")
        boundary = _boundary(review)
        matches = [case for case in cases if isinstance(case, dict)
                   and _case_boundary(specs.get(case.get("id"))) == boundary]
        if (review.get("provider_status") != "ok" or probability is None or boundary is None
                or runtime.get("status") != "COMPLETED" or len(matches) != 1
                or matches[0].get("passed") is not True or matches[0].get("error")
                or not isinstance(matches[0].get("violations"), list)):
            unknown += 1
            continue
        samples.append((probability, bool(matches[0]["violations"])))
    bins = []
    for index in range(_BINS):
        entries = [(probability, label) for probability, label in samples
                   if index / _BINS <= probability < (index + 1) / _BINS
                   or index == _BINS - 1 and probability == 1]
        if entries:
            bins.append({"lower": index / _BINS, "upper": (index + 1) / _BINS,
                         "count": len(entries),
                         "mean_probability": round(sum(item[0] for item in entries) / len(entries), 6),
                         "observed_rate": round(sum(item[1] for item in entries) / len(entries), 6)})
    return {"sample_count": len(samples), "unknown_count": unknown,
            "brier_score": round(sum((probability - int(label)) ** 2 for probability, label in samples)
                                 / len(samples), 6) if samples else None,
            "reliability": bins,
            "scope": "Matched configured synthetic probes only; not a production calibration estimate."}
