"""Let typed review answers choose on-demand probes, and score review calibration.

The model only chooses *where* to look: it can select operator-written ``on_demand``
manifest cases for a boundary. It never writes probe inputs, and only the executed
runtime result counts as evidence.
"""
from __future__ import annotations

from leakhunter.languages import finding_function
from leakhunter.providers.verdict import LEAK_AT, probability as _probability


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


def baseline_manifest(manifest: dict | None) -> dict | None:
    """The always-run suite: every case not reserved for model-selected execution."""
    if not manifest:
        return None
    return dict(manifest, cases=[case for case in manifest["cases"] if not case.get("on_demand")])


def select_targeted_probes(decision: dict, manifest: dict) -> list[dict]:
    """Pick on-demand cases at boundaries where the review asks for a targeted runtime test."""
    wanted = set()
    for review in decision.get("reviews", []) if isinstance(decision, dict) else []:
        if not isinstance(review, dict):
            continue
        probability = _probability(review.get("decision"), "targeted_runtime_test_required")
        disclosure = _probability(review.get("decision"), "unauthorized_disclosure_plausible")
        boundary = _boundary(review)
        if (review.get("provider_status") == "ok" and boundary
                and ((probability is not None and probability >= _THRESHOLD)
                     or (disclosure is not None and disclosure >= LEAK_AT))):
            wanted.add(boundary)
    return [case for case in (manifest or {}).get("cases", [])
            if case.get("on_demand") is True and _case_boundary(case) in wanted]


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
