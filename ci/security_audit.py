"""Retain full scanner output; fail on advisories, scan errors or HIGH findings."""
from collections import Counter
import json
from pathlib import Path
import subprocess
import sys


def review_static(report):
    if (not isinstance(report, dict) or report.get("errors") != []
            or not isinstance(report.get("results"), list)):
        raise ValueError("Static scan was incomplete")
    severities = [item["issue_severity"] for item in report["results"]]
    if any(level not in {"LOW", "MEDIUM", "HIGH"} for level in severities) or "HIGH" in severities:
        raise ValueError("Static scan found HIGH or unknown-severity findings")
    return dict(Counter(severities))


def main():
    output = Path("security-reports")
    output.mkdir(exist_ok=True)
    subprocess.run([sys.executable, "-m", "pip_audit", "-r", "requirements.lock", "-r", "requirements.build.lock",
                    "--no-deps", "--disable-pip", "--progress-spinner", "off", "-f", "json",
                    "-o", str(output / "dependencies.json")], check=True, timeout=180)
    scan = subprocess.run([sys.executable, "-m", "bandit", "-r", "unspool", "unspool", "-f", "json",
                           "-o", str(output / "bandit.json")], timeout=120)
    if scan.returncode not in {0, 1}:
        raise RuntimeError("Static scanner failed to execute")
    counts = review_static(json.loads((output / "bandit.json").read_text()))
    print(json.dumps({"dependency_advisories": 0, "bandit_findings": counts,
                      "policy": "block-advisories-errors-and-HIGH; retain-LOW-MEDIUM-for-review"}))


if __name__ == "__main__":
    main()
