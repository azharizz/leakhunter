"""Publish a sanitized, immutable graph without exposing the local repair server."""
from __future__ import annotations

import argparse
import html
import json
import math
from pathlib import Path
import re
import shutil


def _calibration(evidence):
    decision = evidence.get("decision") if isinstance(evidence, dict) else None
    value = decision.get("calibration") if isinstance(decision, dict) else None
    if not isinstance(value, dict):
        raise ValueError("Passing evidence must include the bounded Luna calibration summary")
    count, unknown = value.get("sample_count"), value.get("unknown_count")
    score, reliability = value.get("brier_score"), value.get("reliability")
    if (type(count) is not int or count < 0 or type(unknown) is not int or unknown < 0
            or (score is not None and (isinstance(score, bool) or not isinstance(score, (int, float))
                                      or not math.isfinite(score) or not 0 <= score <= 1))
            or not isinstance(reliability, list)):
        raise ValueError("Invalid Luna calibration summary")
    bins = []
    for item in reliability:
        if (not isinstance(item, dict) or type(item.get("count")) is not int or item["count"] <= 0
                or any(isinstance(item.get(key), bool) or not isinstance(item.get(key), (int, float))
                       or not math.isfinite(item[key]) or not 0 <= item[key] <= 1
                       for key in ("lower", "upper", "mean_probability", "observed_rate"))):
            raise ValueError("Invalid Luna reliability bin")
        bins.append({key: item[key] for key in ("lower", "upper", "count", "mean_probability", "observed_rate")})
    return {"sample_count": count, "unknown_count": unknown, "brier_score": score,
            "reliability": bins,
            "scope": "Matched configured synthetic probes only; not a production calibration estimate."}


def _calibration_page(value):
    rows = "".join(
        "<tr>" + "".join(f"<td>{html.escape(str(item[key]))}</td>" for key in
                           ("lower", "upper", "count", "mean_probability", "observed_rate")) + "</tr>"
        for item in value["reliability"])
    if not rows:
        rows = '<tr><td colspan="5">No matched probe samples</td></tr>'
    score = "n/a" if value["brier_score"] is None else f'{value["brier_score"]:.4f}'
    return ("<!doctype html><html lang=\"en\"><meta charset=\"utf-8\"><meta name=\"viewport\" content=\"width=device-width\">"
            "<title>Unspool Luna calibration</title><style>body{font:16px system-ui;max-width:900px;margin:3rem auto;padding:0 1rem;color:#182321}"
            "table{border-collapse:collapse;width:100%;margin:1rem 0}th,td{border:1px solid #ccd5d2;padding:.6rem;text-align:left}"
            ".scope{color:#53635f}</style><main><p><a href=\"./index.html\">← Demo report</a></p>"
            "<h1>Luna calibration</h1><p>Matched probe samples: " + str(value["sample_count"])
            + " · Unknown samples: " + str(value["unknown_count"]) + " · Brier score: " + score
            + "</p><table><thead><tr><th>Probability bin</th><th>Upper bound</th><th>Samples</th>"
              "<th>Mean probability</th><th>Observed leak rate</th></tr></thead><tbody>" + rows
            + "</tbody></table><p class=\"scope\">" + html.escape(value["scope"])
            + "</p></main></html>\n")


def publish(evidence: dict, output: Path, commit: str) -> None:
    if not re.fullmatch(r"[0-9a-f]{40,64}", commit):
        raise ValueError("A full Git commit SHA is required")
    runtime = evidence.get("runtime", {})
    if (evidence.get("gate", {}).get("passed") is not True
            or runtime.get("status") != "COMPLETED" or runtime.get("passed") is not True):
        raise ValueError("Only independently passing analysis can be published")
    graph = evidence.get("graph", evidence)
    calibration = _calibration(evidence)
    nodes = [{key: node[key] for key in ("id", "label", "kind", "type", "file", "line", "classification") if key in node}
             for node in graph.get("nodes", [])]
    edges = [{key: edge[key] for key in ("id", "source", "target", "type") if key in edge}
             for edge in graph.get("edges", [])]
    if not nodes:
        raise ValueError("Analysis contains no graph nodes")
    knowledge = {
        "nodes": nodes, "edges": edges, "findings": [], "commit_sha": commit,
        "last_run": evidence.get("last_run"), "gate": {"passed": True},
        "runtime": {"status": "COMPLETED", "passed": True,
                    "functional_passed": runtime.get("functional_passed"),
                    "cases": [{key: case[key] for key in ("id", "passed", "observed", "duration_ms") if key in case}
                              for case in runtime.get("cases", [])]},
    }
    workspace = {"/api/knowledge": knowledge, "/api/config": {"repository": "Unspool synthetic demo", "runtime_backend": "CI worker", "runtime_configured": True},
                 "/api/metrics": [], "/api/snapshots": [], "/api/repairs": [], "/api/policies": [],
                 "/api/calibration": calibration}
    output.mkdir(parents=True, exist_ok=True)
    assets = Path(__file__).resolve().parents[1] / "unspool" / "static"
    (output / "static").mkdir(exist_ok=True)
    for name in ("app.js", "styles.css"):
        shutil.copyfile(assets / name, output / "static" / name)
    html = (assets / "index.html").read_text().replace('<html lang="en">', '<html lang="en" data-mode="published">')
    html = html.replace('"/static/', '"./static/')
    html = html.replace("Local workspace · annotations persist across analysis", f"Verified commit {commit[:12]} · immutable public report")
    html = html.replace("</footer>", '<a href="./calibration.html">Luna calibration</a></footer>')
    (output / "index.html").write_text(html)
    (output / "workspace.json").write_text(json.dumps(workspace, ensure_ascii=False))
    (output / "health.json").write_text(json.dumps({"status": "ok", "commit": commit, "verified": True}))
    (output / "calibration.json").write_text(json.dumps(calibration, sort_keys=True) + "\n")
    (output / "calibration.html").write_text(_calibration_page(calibration))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--evidence", type=Path, required=True)
    parser.add_argument("--output", type=Path, default=Path("public"))
    parser.add_argument("--commit", required=True)
    args = parser.parse_args()
    publish(json.loads(args.evidence.read_text()), args.output, args.commit)


if __name__ == "__main__":
    main()
