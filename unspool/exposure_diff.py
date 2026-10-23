"""Compare exact Git revisions and emit a GitLab SAST-compatible MR report."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import io
import json
import os
from pathlib import Path, PurePosixPath
import re
import subprocess
import tarfile
import tempfile
import uuid

from unspool.analyzers.python_ast import ANALYZER_VERSION, analyze_project
from unspool.execution.runtime import load_manifest
from unspool.languages import manifest_entrypoints
from unspool.policy.engine import load_policy


_SHA = re.compile(r"[0-9a-f]{40}")
_MAX_ARCHIVE_BYTES = 256 * 1024 * 1024
_MAX_FILES = 20000
_MAX_FILE_BYTES = 16 * 1024 * 1024
_IDENTIFIER_NS = uuid.UUID("fa9e5521-c9e2-4ee4-8dc5-7f96c00a0186")
_SCHEMA_VERSION = "15.2.5"
_SCHEMA_URL = ("https://gitlab.com/gitlab-org/security-products/security-report-schemas/"
               f"-/raw/v{_SCHEMA_VERSION}/dist/sast-report-format.json")


def _flow_key(finding):
    fields = (finding.get("file"), finding.get("function"), finding.get("source"), finding.get("sink"))
    if any(not isinstance(value, str) or not value for value in fields):
        raise ValueError("Analyzer returned an incomplete flow")
    return tuple(fields)


def _flow_state(finding):
    """Exposure-relevant state; a flow that only moved lines is unchanged."""
    return {key: finding.get(key) for key in ("severity", "classification", "policy_violation", "reasons")}


def compare_findings(base_findings, head_findings):
    if any(not isinstance(item, dict) for item in list(base_findings) + list(head_findings)):
        raise ValueError("Invalid analyzer finding set")
    base, head = {}, {}
    for finding in base_findings:
        base.setdefault(_flow_key(finding), []).append(finding)
    for finding in head_findings:
        head.setdefault(_flow_key(finding), []).append(finding)
    result = []
    for key in sorted(base.keys() | head.keys()):
        before = sorted(base.get(key, []), key=lambda item: json.dumps(_flow_state(item), sort_keys=True))
        after = sorted(head.get(key, []), key=lambda item: json.dumps(_flow_state(item), sort_keys=True))
        paired = min(len(before), len(after))
        for index in range(paired):
            if _flow_state(before[index]) != _flow_state(after[index]):
                result.append({"change": "changed", "identity": list(key),
                               "base": _flow_state(before[index]), "head": _flow_state(after[index]),
                               "finding": after[index]})
        for item in before[paired:]:
            result.append({"change": "removed", "identity": list(key),
                           "base": _flow_state(item), "head": None, "finding": item})
        for item in after[paired:]:
            result.append({"change": "added", "identity": list(key),
                           "base": None, "head": _flow_state(item), "finding": item})
    return result


def sast_report(changes, *, started=None, ended=None, luna_changes=()):
    started = started or datetime.now(timezone.utc).replace(microsecond=0)
    ended = ended or started
    if started.tzinfo is None or ended.tzinfo is None:
        raise ValueError("SAST report times must include a timezone")
    # GitLab's SAST schema requires yyyy-mm-ddThh:mm:ss in UTC, without a zone suffix.
    start_time = started.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")
    end_time = ended.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")
    rank = {"critical": 3, "high": 2, "medium": 1, "low": 0}
    groups = {}
    for item in changes:
        if item["change"] not in {"added", "changed"}:
            continue
        finding = item["finding"]
        line = finding.get("line")
        if type(line) is not int or line < 1:
            raise ValueError("Finding has no valid source line")
        # One opaque record expands to a flow per policy field; report it once per sink and line.
        file, function, source, sink = item["identity"]
        whole = finding.get("exposure") == "WHOLE_RECORD"
        key = (file, function, "<whole record>" if whole else source, sink, line if whole else 0)
        groups.setdefault(key, []).append((item, finding))
    vulnerabilities = []
    for (file, function, _, sink, _), entries in sorted(groups.items()):
        findings = [finding for _, finding in entries]
        identity = "\0".join([file, function, sink] + sorted(finding["source"] for finding in findings))
        worst = max(findings, key=lambda finding: rank.get(str(finding.get("severity", "")).lower(), -1))
        severity = {"critical": "Critical", "high": "High", "medium": "Medium", "low": "Low"}.get(
            str(worst.get("severity", "")).lower(), "Unknown")
        fields = ", ".join(sorted(finding["source"] for finding in findings))
        line = worst["line"]
        change = "Added" if all(item["change"] == "added" for item, _ in entries) else "Changed"
        vulnerabilities.append({
            "id": str(uuid.uuid5(_IDENTIFIER_NS, identity)),
            "name": str(worst.get("title") or "Sensitive data reaches a disallowed sink")[:255],
            "description": (f"{change} exposure flow at {file}:{line}: {fields} may reach {sink}, "
                            "which the configured policy does not allow."),
            "severity": severity,
            "solution": "Return or send only the fields the policy allows, and keep the public response contract.",
            "identifiers": [{"type": "unspool_flow", "name": "Unspool exposure flow",
                             "value": hashlib.sha256(identity.encode()).hexdigest()}],
            "location": {"file": file, "start_line": line, "end_line": line, "method": str(function)},
        })
    for item in luna_changes:
        file, function, line = item.get("file"), item.get("function"), item.get("line")
        if (not isinstance(file, str) or not isinstance(function, str)
                or type(line) is not int or line < 1 or item.get("head_verdict") != "LEAK"):
            raise ValueError("Luna SAST finding lacks a source-backed LEAK boundary")
        identity = f"luna\0{file}\0{function}"
        probability = item.get("disclosure")
        confidence = (f" Luna's disclosure probability was {probability:.2f}."
                      if type(probability) in (int, float) and 0 <= probability <= 1 else "")
        vulnerabilities.append({
            "id": str(uuid.uuid5(_IDENTIFIER_NS, identity)),
            "name": "Luna flagged a potential exposure boundary",
            "description": (f"Luna classified the source-backed boundary at {file}:{line} in {function} as LEAK."
                            f"{confidence} This is a model decision, not an independently confirmed runtime leak."),
            "severity": "Unknown",
            "solution": "Review source, recipient authorization and contracts; add or run a bounded probe.",
            "identifiers": [{"type": "unspool_luna_boundary", "name": "Unspool Luna boundary",
                             "value": hashlib.sha256(identity.encode()).hexdigest()}],
            "location": {"file": file, "start_line": line, "end_line": line, "method": function},
        })
    return {"schema": _SCHEMA_URL, "version": _SCHEMA_VERSION,
            "scan": {"analyzer": {"id": "unspool", "name": "Unspool", "version": ANALYZER_VERSION,
                                    "vendor": {"name": "Unspool"}},
                     "scanner": {"id": "unspool", "name": "Unspool", "version": ANALYZER_VERSION,
                                  "vendor": {"name": "Unspool"}},
                     "start_time": start_time, "end_time": end_time,
                     "status": "success", "type": "sast"},
            "vulnerabilities": vulnerabilities}


def _commit(repository, sha):
    if not isinstance(sha, str) or not _SHA.fullmatch(sha):
        raise ValueError("Base and head must be full commit SHAs")
    result = subprocess.run(["git", "-C", str(repository), "rev-parse", "--verify", "--end-of-options",
                             f"{sha}^{{commit}}"], stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                            text=True, timeout=15)
    if result.returncode or result.stdout.strip() != sha:
        raise ValueError("Requested revision is unavailable or does not resolve exactly")
    return sha


def _extract_revision(repository, sha, destination):
    process = subprocess.Popen(["git", "-C", str(repository), "archive", "--format=tar", sha],
                               stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
    archive = bytearray()
    try:
        while True:
            chunk = process.stdout.read(65536)
            if not chunk:
                break
            if len(archive) + len(chunk) > _MAX_ARCHIVE_BYTES:
                process.kill()
                process.wait()
                raise ValueError("Revision archive exceeds the analysis size limit")
            archive.extend(chunk)
        if process.wait(timeout=120):
            raise ValueError("Unable to export requested revision")
        count = total = 0
        with tarfile.open(fileobj=io.BytesIO(archive), mode="r:") as bundle:
            for member in bundle:
                count += 1
                path = PurePosixPath(member.name)
                if (count > _MAX_FILES or path.is_absolute() or "\\" in member.name
                        or any(part in {"", ".", ".."} for part in path.parts)
                        or not (member.isdir() or member.isfile())):
                    raise ValueError("Revision contains an unsupported or unsafe archive entry")
                target = destination.joinpath(*path.parts)
                if member.isdir():
                    target.mkdir(parents=True, exist_ok=True)
                    continue
                if member.size < 0 or member.size > _MAX_FILE_BYTES:
                    raise ValueError("Revision contains a file outside the analysis size limit")
                total += member.size
                if total > _MAX_ARCHIVE_BYTES:
                    raise ValueError("Revision contents exceed the analysis size limit")
                target.parent.mkdir(parents=True, exist_ok=True)
                source = bundle.extractfile(member)
                if source is None:
                    raise ValueError("Unable to read revision file")
                flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
                descriptor = os.open(target, flags, 0o600)
                with os.fdopen(descriptor, "wb") as output:
                    remaining = member.size
                    while remaining:
                        part = source.read(min(65536, remaining))
                        if not part:
                            raise ValueError("Truncated revision archive")
                        output.write(part)
                        remaining -= len(part)
    finally:
        if process.poll() is None:
            process.kill()
            process.wait()
        process.stdout.close()


def diff_revisions(repository: Path, policy_path: Path, base_sha: str, head_sha: str, *,
                   output: Path | None = None, target_directory: str = ".", manifest_path: Path | None = None):
    repository = Path(repository).resolve(strict=True)
    if not repository.is_dir():
        raise ValueError("Repository must be a directory")
    if not isinstance(target_directory, str) or not target_directory or "\x00" in target_directory:
        raise ValueError("Target directory must be a repository-relative path")
    target = PurePosixPath(target_directory)
    if target.is_absolute() or "\\" in target_directory or ".." in target.parts:
        raise ValueError("Target directory must remain inside the repository")
    base_sha, head_sha = _commit(repository, base_sha), _commit(repository, head_sha)
    if base_sha == head_sha:
        raise ValueError("Base and head revisions must differ")
    policy = load_policy(Path(policy_path).resolve(strict=True))
    # Use the same entrypoints as the gated analysis so both sides report the same flows.
    entrypoints = manifest_entrypoints(load_manifest(Path(manifest_path).resolve(strict=True))) if manifest_path else None
    started = datetime.now(timezone.utc).replace(microsecond=0)
    with tempfile.TemporaryDirectory(prefix="unspool-diff-") as temporary:
        root = Path(temporary)
        base_root, head_root = root / "base", root / "head"
        base_root.mkdir(); head_root.mkdir()
        _extract_revision(repository, base_sha, base_root)
        _extract_revision(repository, head_sha, head_root)
        base_target, head_target = base_root.joinpath(*target.parts), head_root.joinpath(*target.parts)
        if not base_target.is_dir() or not head_target.is_dir():
            raise ValueError("Target directory is missing from one of the requested revisions")
        base = analyze_project(base_target, policy, entrypoints=entrypoints)
        head = analyze_project(head_target, policy, entrypoints=entrypoints)
    changes = compare_findings(base["findings"], head["findings"])
    ended = datetime.now(timezone.utc).replace(microsecond=0)
    result = {"version": 1, "base_sha": base_sha, "head_sha": head_sha,
              "policy_sha256": policy.digest,
              "base_findings": base["findings"], "head_findings": head["findings"],
              "changes": changes, "sast_report": sast_report(changes, started=started, ended=ended)}
    if output:
        output = Path(output)
        output.mkdir(parents=True, exist_ok=True)
        (output / "exposure-diff.json").write_text(json.dumps({key: value for key, value in result.items()
                                                               if key != "sast_report"}, sort_keys=True) + "\n",
                                                    encoding="utf-8")
        (output / "gl-sast-report.json").write_text(json.dumps(result["sast_report"], sort_keys=True) + "\n",
                                                    encoding="utf-8")
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repository", type=Path, default=Path.cwd())
    parser.add_argument("--target-directory", default=".")
    parser.add_argument("--policy", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, help="Runtime manifest whose entrypoints the gate analyzes")
    parser.add_argument("--base", required=True)
    parser.add_argument("--head", required=True)
    parser.add_argument("--output", type=Path, default=Path("."))
    args = parser.parse_args(argv)
    result = diff_revisions(args.repository, args.policy, args.base, args.head,
                            output=args.output, target_directory=args.target_directory,
                            manifest_path=args.manifest)
    print(json.dumps({"base_sha": result["base_sha"], "head_sha": result["head_sha"],
                      "changes": len(result["changes"]),
                      "reported": len(result["sast_report"]["vulnerabilities"])}))


if __name__ == "__main__":
    main()
