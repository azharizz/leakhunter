"""Publish a sanitized, immutable graph without exposing the local repair server."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import shutil


def publish(evidence: dict, output: Path, commit: str) -> None:
    if not re.fullmatch(r"[0-9a-f]{40,64}", commit):
        raise ValueError("A full Git commit SHA is required")
    runtime = evidence.get("runtime", {})
    if (evidence.get("gate", {}).get("passed") is not True
            or runtime.get("status") != "COMPLETED" or runtime.get("passed") is not True):
        raise ValueError("Only independently passing analysis can be published")
    graph = evidence.get("graph", evidence)
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
                 "/api/metrics": [], "/api/snapshots": [], "/api/repairs": [], "/api/policies": []}
    output.mkdir(parents=True, exist_ok=True)
    assets = Path(__file__).resolve().parents[1] / "leakhunter" / "static"
    (output / "static").mkdir(exist_ok=True)
    for name in ("app.js", "styles.css"):
        shutil.copyfile(assets / name, output / "static" / name)
    html = (assets / "index.html").read_text().replace('<html lang="en">', '<html lang="en" data-mode="published">')
    html = html.replace('"/static/', '"./static/')
    html = html.replace("Local workspace · annotations persist across analysis", f"Verified commit {commit[:12]} · immutable public report")
    (output / "index.html").write_text(html)
    (output / "workspace.json").write_text(json.dumps(workspace, ensure_ascii=False))
    (output / "health.json").write_text(json.dumps({"status": "ok", "commit": commit, "verified": True}))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--evidence", type=Path, required=True)
    parser.add_argument("--output", type=Path, default=Path("public"))
    parser.add_argument("--commit", required=True)
    args = parser.parse_args()
    publish(json.loads(args.evidence.read_text()), args.output, args.commit)


if __name__ == "__main__":
    main()
