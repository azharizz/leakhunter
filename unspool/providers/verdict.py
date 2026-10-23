"""Classify typed Luna Decisions as triage signals for graph review units.

Each review unit is one code boundary with its source spans, flow paths, findings and
runtime observations. Luna's answers decide, per boundary:

- LEAK      disclosure plausible >= LEAK_AT                -> request independent probe evidence
- CLEAR     disclosure <= CLEAR_AT and no context needed   -> low-priority triage signal only
- UNCERTAIN anything in between                            -> request independent probe evidence
- UNREVIEWED no valid answer                               -> required review is incomplete

Luna neither clears static candidates nor blocks a release by probability alone.
An observed runtime violation remains a factual block; missing review evidence also
blocks a required-mode gate.
"""
from __future__ import annotations

import math

LEAK_AT = 0.5
CLEAR_AT = 0.2
CONTEXT_AT = 0.5
MODES = ("required", "advisory")


def probability(decision, question):
    answers = decision.get("answers") if isinstance(decision, dict) else None
    answer = answers.get(question) if isinstance(answers, dict) else None
    value = answer.get("noul") if isinstance(answer, dict) and answer.get("type") == "noul" else None
    if type(value) not in (int, float) or not math.isfinite(value) or not 0 <= value <= 1:
        return None
    return float(value)


def _boundary(review):
    context = review.get("context") if isinstance(review, dict) else None
    boundary = context.get("boundary") if isinstance(context, dict) else None
    if not isinstance(boundary, dict):
        return None, None
    return boundary.get("file"), boundary.get("function")


def unit_verdict(review: dict) -> dict:
    file, function = _boundary(review)
    answer = review.get("decision") if isinstance(review, dict) else None
    disclosure = probability(answer, "unauthorized_disclosure_plausible")
    context = probability(answer, "additional_context_required")
    targeted = probability(answer, "targeted_runtime_test_required")
    observed = ((review.get("post_probe_evidence") or review.get("deterministic_evidence") or {})
                .get("observed_policy_violations") is True)
    if observed:
        verdict, basis = "LEAK", "runtime probe observed a policy violation"
    elif review.get("provider_status") != "ok" or disclosure is None or context is None:
        verdict, basis = "UNREVIEWED", f"no valid Luna decision ({review.get('provider_status')})"
    elif disclosure >= LEAK_AT:
        verdict, basis = "LEAK", "Luna: unauthorized disclosure plausible"
    elif disclosure <= CLEAR_AT and context < CONTEXT_AT:
        verdict, basis = "CLEAR", "Luna: disclosure implausible with sufficient context"
    else:
        verdict, basis = "UNCERTAIN", "Luna: neither plausible nor clearly implausible"
    return {"review_id": review.get("review_id", "") if isinstance(review, dict) else "",
            "file": file, "function": function, "verdict": verdict, "basis": basis,
            "disclosure": disclosure, "context_required": context, "targeted_test": targeted}


def decide(decision: dict, findings: list[dict], mode: str = "required") -> dict:
    """Return triage verdicts; only incomplete required reviews are gate reasons."""
    if mode not in MODES:
        raise ValueError(f"decision mode must be one of {MODES}")
    reviews = decision.get("reviews", []) if isinstance(decision, dict) else []
    units = [unit_verdict(review) for review in reviews if isinstance(review, dict)]
    scope = decision.get("scope", {}) if isinstance(decision, dict) else {}
    omitted = scope.get("omitted_review_units") or 0
    unreviewed = [unit for unit in units if unit["verdict"] == "UNREVIEWED"]
    flagged = [unit for unit in units if unit["verdict"] == "LEAK"]
    nothing_to_review = not units and decision.get("status") == "no_review_units" and not findings
    complete = nothing_to_review or (bool(units) and not unreviewed and not omitted)
    by_boundary = {}
    for unit in units:
        by_boundary.setdefault((unit["file"], unit["function"]), []).append(unit)
    would_dismiss = []
    for finding in findings:
        covering = by_boundary.get((finding.get("file"), finding.get("function")), [])
        observed = (finding.get("runtime_evidence") or {}).get("observed") is True
        if (covering and all(unit["verdict"] == "CLEAR" for unit in covering)
                and not observed and finding.get("status") != "CONFIRMED_IN_TEST"):
            would_dismiss.append(finding["id"])
    reasons = []
    if not complete:
        reasons.append(f"Luna decision review incomplete: {len(units) - len(unreviewed)} of "
                       f"{len(units) + omitted} boundaries decided ({decision.get('status', 'missing')})")
    triage = [unit for unit in units if unit["verdict"] in {"LEAK", "UNCERTAIN"}]
    would_block = [
        f"Luna requests independent probe evidence at {unit['file']}:{unit['function']}"
        for unit in triage
    ]
    status = "DECIDED" if complete else "INCOMPLETE"
    if mode == "advisory":  # recorded for comparison only; the gate ignores it
        return {"mode": mode, "status": status, "units": units, "flagged": flagged,
                "dismissed": [], "would_dismiss": would_dismiss, "reasons": [],
                "would_block": would_block + reasons, "thresholds": _thresholds()}
    return {"mode": mode, "status": status, "units": units, "flagged": flagged,
            "dismissed": [], "would_dismiss": would_dismiss, "reasons": reasons,
            "would_block": would_block, "thresholds": _thresholds()}


def _thresholds():
    return {"leak_at": LEAK_AT, "clear_at": CLEAR_AT, "context_at": CONTEXT_AT}
