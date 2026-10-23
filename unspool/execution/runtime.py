"""Execute synthetic fixtures; local execution is for explicitly trusted repositories only."""
from __future__ import annotations

import hashlib
import json
import math
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import signal
import subprocess
import sys
import tempfile
import time

import yaml

from unspool.execution.external import run_external_suite
from unspool.languages import entrypoint as language_entrypoint, manifest_language, runtime_image


_NAME = re.compile(r"^[A-Za-z_]\w*(?:\.[A-Za-z_]\w*)*$")
_CASE_KEYS = {"id", "module", "callable", "entrypoint", "args", "kwargs", "sensitive", "context", "expect",
              "expected_violation", "finding", "capture_http", "capture_calls", "observe_calls", "trace", "artifacts",
              "on_demand"}
_CONTEXT_KEYS = {"audience", "recipient", "tenant", "source_tenant", "authorized", "contract", "synthetic",
                 "boundary_kind", "applicable_questions", "security_contexts"}
_BOOTSTRAP = "import sys;sys.path.insert(0,sys.argv.pop(1));from unspool.runtime_worker import main;main()"
_REGRESSION_TOOLS = {"python": {"python", "python3"}, "javascript": {"node", "bun"},
                     "typescript": {"node", "bun"}, "go": {"go"}, "rust": {"cargo", "rustc"}}


def _keys(value, allowed, required, where):
    if not isinstance(value, dict) or set(value) - allowed or required - set(value):
        raise ValueError(f"invalid {where} fields")


def _path(value):
    if not isinstance(value, str) or not value or "\\" in value:
        raise ValueError("invalid relative path")
    path = PurePosixPath(value)
    if path.is_absolute() or any(part in ("", ".", "..") for part in value.split("/")):
        raise ValueError("invalid relative path")
    return value


def _json(value):
    # Reject non-JSON YAML objects, non-string keys, and NaN at the trust boundary.
    if value is None or isinstance(value, (str, bool, int)):
        return
    if isinstance(value, float) and math.isfinite(value):
        return
    if isinstance(value, list):
        for item in value:
            _json(item)
        return
    if isinstance(value, dict) and all(isinstance(key, str) for key in value):
        for item in value.values():
            _json(item)
        return
    raise ValueError("manifest values must be finite JSON values")


def _validate(manifest):
    _keys(manifest, {"version", "language", "cases", "regression_command", "docker_image"},
          {"version", "cases"}, "manifest")
    _json(manifest)
    if type(manifest["version"]) is not int or manifest["version"] != 1:
        raise ValueError("unsupported runtime manifest version")
    language = manifest_language(manifest)
    image = runtime_image(manifest)
    if not isinstance(image, str) or len(image) > 512 or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_./:@-]*", image):
        raise ValueError("invalid Docker image reference")
    if not isinstance(manifest["cases"], list) or not manifest["cases"]:
        raise ValueError("manifest requires cases")
    ids = set()
    for case in manifest["cases"]:
        required = {"id", "args", "kwargs", "sensitive", "context", "expect"}
        required |= {"module", "callable"} if language == "python" else {"entrypoint"}
        _keys(case, _CASE_KEYS, required, "case")
        if not isinstance(case["id"], str) or not re.fullmatch(r"[A-Za-z0-9_.-]+", case["id"]) or case["id"] in ids:
            raise ValueError("invalid or duplicate case id")
        ids.add(case["id"])
        if "on_demand" in case and not isinstance(case["on_demand"], bool):
            raise ValueError("case on_demand must be boolean")
        if language == "python":
            if "entrypoint" in case:
                raise ValueError("Python cases use module/callable, not entrypoint")
            for key in ("module", "callable"):
                if not isinstance(case[key], str) or not _NAME.fullmatch(case[key]) or any(p.startswith("__") for p in case[key].split(".")):
                    raise ValueError(f"invalid case {key}")
        else:
            if "module" in case or "callable" in case:
                raise ValueError("non-Python cases use entrypoint, not module/callable")
            language_entrypoint(case, language)
        if not isinstance(case["args"], list) or not isinstance(case["kwargs"], dict):
            raise ValueError("case args/kwargs have invalid types")
        if not isinstance(case["sensitive"], list) or not case["sensitive"]:
            raise ValueError("case requires synthetic sensitive markers")
        markers = set()
        for source in case["sensitive"]:
            _keys(source, {"marker", "class", "symbol"}, {"marker", "class", "symbol"}, "sensitive source")
            if any(not isinstance(v, str) or not v for v in source.values()) or source["marker"] in markers:
                raise ValueError("invalid or duplicate sensitive marker")
            markers.add(source["marker"])
        _keys(case["context"], _CONTEXT_KEYS, set(), "context")
        for key, value in case["context"].items():
            if key in {"authorized", "synthetic"}:
                if type(value) is not bool:
                    raise ValueError("context flags must be booleans")
            elif key == "contract":
                if not isinstance(value, (str, bool)):
                    raise ValueError("context contract must be a string or boolean")
            elif key == "boundary_kind":
                if value not in {"HTTP_RESPONSE", "APPLICATION_LOG", "THIRD_PARTY_ANALYTICS", "WEBHOOK"}:
                    raise ValueError("invalid context boundary kind")
            elif key == "applicable_questions":
                if (not isinstance(value, list) or not value
                        or any(not isinstance(item, str) or not item for item in value)
                        or len(set(value)) != len(value)):
                    raise ValueError("context applicable_questions must be a nonempty list of unique strings")
            elif key == "security_contexts":
                if (not isinstance(value, list) or not value
                        or any(not isinstance(item, str) or not item for item in value)
                        or len(set(value)) != len(value)):
                    raise ValueError("context security_contexts must be a nonempty list of unique strings")
            elif not isinstance(value, str):
                raise ValueError("context identities must be strings")
        if "expected_violation" in case and type(case["expected_violation"]) is not bool:
            raise ValueError("expected_violation must be boolean")
        if "finding" in case:
            _keys(case["finding"], {"file", "function", "sink", "symbol"}, {"file", "function", "sink"}, "finding")
            _path(case["finding"]["file"])
            if any(not isinstance(v, str) or not v for v in case["finding"].values()):
                raise ValueError("invalid finding mapping")
        for key in ("capture_http", "capture_calls", "observe_calls", "artifacts"):
            if key in case and not isinstance(case[key], list):
                raise ValueError(f"{key} must be a list")
        for model in case.get("capture_http", []):
            _keys(model, {"url_prefix", "sink"}, {"url_prefix", "sink"}, "HTTP capture")
            if not isinstance(model["url_prefix"], str) or not model["url_prefix"].startswith(("http://", "https://")) or not isinstance(model["sink"], str) or not model["sink"]:
                raise ValueError("invalid HTTP capture")
        for model in case.get("capture_calls", []):
            _keys(model, {"module", "callable", "sink", "return_value"}, {"module", "callable", "sink"}, "SDK capture")
            if any(not isinstance(model[key], str) or not _NAME.fullmatch(model[key]) for key in ("module", "callable")) or not isinstance(model["sink"], str) or not model["sink"]:
                raise ValueError("invalid SDK capture")
        for model in case.get("observe_calls", []):
            _keys(model, {"module", "callable", "role"}, {"module", "callable", "role"}, "call observation")
            if (any(not isinstance(model[key], str) or not _NAME.fullmatch(model[key])
                    for key in ("module", "callable"))
                    or not isinstance(model["role"], str) or not model["role"] or len(model["role"]) > 128):
                raise ValueError("invalid call observation")
        if "trace" in case and type(case["trace"]) is not bool:
            raise ValueError("trace must be boolean")
        for artifact in case.get("artifacts", []):
            _keys(artifact, {"path", "sink"}, {"path", "sink"}, "artifact capture")
            _path(artifact["path"])
            if not isinstance(artifact["sink"], str) or not artifact["sink"]:
                raise ValueError("invalid artifact sink")
    if "regression_command" in manifest:
        command = manifest["regression_command"]
        if not isinstance(command, list) or not command or any(not isinstance(a, str) or not a or "\x00" in a for a in command):
            raise ValueError("regression_command must be nonempty argv")
        if command[0] not in _REGRESSION_TOOLS[language]:
            _path(command[0])
    return manifest


def load_manifest(path: Path) -> dict:
    return _validate(yaml.safe_load(Path(path).read_text(encoding="utf-8")))


def _repository_paths(repository, manifest):
    if not repository.is_dir():
        raise ValueError("repository is not a directory")
    # Reject all links, including imports/transitive resources that could escape a mount.
    for root, dirs, files in os.walk(repository, followlinks=False):
        dirs[:] = [name for name in dirs if name not in {".git", "__pycache__"}]
        for name in dirs + files:
            if (Path(root) / name).is_symlink():
                raise ValueError("repository symlinks are not supported")
    language = manifest_language(manifest)
    for case in manifest["cases"]:
        if language == "python":
            module = repository.joinpath(*case["module"].split("."))
            if not module.with_suffix(".py").is_file() and not (module / "__init__.py").is_file():
                raise ValueError("fixture module does not exist inside repository")
        else:
            target = repository / language_entrypoint(case, language).file
            if not target.is_file():
                raise ValueError("fixture entrypoint does not exist inside repository")
    command = manifest.get("regression_command")
    if command and command[0] not in _REGRESSION_TOOLS[language] and not (repository / command[0]).is_file():
        raise ValueError("regression executable must be repository-local")
    if command and command[0] in {"python", "python3"} and len(command) > 1 and not command[1].startswith("-"):
        _path(command[1])
        if not (repository / command[1]).is_file():
            raise ValueError("regression script does not exist")


def _execute(command, cwd, env, timeout):
    process = subprocess.Popen(command, cwd=cwd, env=env, stdout=subprocess.DEVNULL,
                               stderr=subprocess.DEVNULL, start_new_session=True)
    try:
        return process.wait(timeout=timeout)
    except subprocess.TimeoutExpired:
        os.killpg(process.pid, signal.SIGKILL)
        process.wait()
        raise


def run_suite(repository: Path, manifest: dict, policy, *, backend="docker", timeout=30) -> dict:
    start = time.monotonic()
    result = {"status": "ERROR", "cases": [], "passed": False, "functional_passed": False,
              "backend": backend, "duration_ms": 0}
    container, docker = None, None
    try:
        _validate(manifest)
        if backend not in {"docker", "local"}:
            raise ValueError("backend must be docker or explicitly trusted local")
        if isinstance(timeout, bool) or not isinstance(timeout, (int, float)) or not math.isfinite(timeout) or timeout <= 0:
            raise ValueError("timeout must be positive")
        repository = Path(repository).resolve(strict=True)
        _repository_paths(repository, manifest)
        for case in manifest["cases"]:
            for source in case["sensitive"]:
                if source["class"] not in policy.classifications:
                    raise ValueError("unknown sensitive classification")
        if manifest_language(manifest) != "python":
            return run_external_suite(repository, manifest, policy, language=manifest_language(manifest),
                                      backend=backend, timeout=float(timeout))
        with tempfile.TemporaryDirectory(prefix="unspool-runtime-") as temporary:
            work = Path(temporary)
            harness = work / "harness" / "unspool"
            harness.mkdir(parents=True)
            (harness / "__init__.py").write_text("")
            shutil.copyfile(Path(__file__).with_name("runtime_worker.py"), harness / "runtime_worker.py")
            (work / "output").mkdir()
            isolated_repository = work / "repository"
            shutil.copytree(repository, isolated_repository, symlinks=True,
                            ignore=shutil.ignore_patterns(".git", "__pycache__", ".env", ".env.*",
                                                        "*.pem", "*.key", "credentials", ".aws", ".ssh"))
            _repository_paths(isolated_repository, manifest)
            (work / "input.json").write_text(json.dumps(manifest, allow_nan=False), encoding="utf-8")
            env = {"PATH": os.defpath, "LANG": "C.UTF-8", "PYTHONDONTWRITEBYTECODE": "1"}
            if backend == "local":
                # This is not a sandbox. The caller explicitly trusts repository code.
                local_repo = isolated_repository
                command = [sys.executable, "-I", "-B", "-c", _BOOTSTRAP, str(harness.parent),
                           str(local_repo), str(work / "input.json"), str(work / "output" / "result.json"), str(timeout)]
            else:
                docker = shutil.which("docker")
                if not docker:
                    raise RuntimeError("docker_unavailable")
                # Pin the runtime dependency deliberately; no implicit pull or host credentials.
                image = manifest.get("docker_image", "python:3.12-slim")
                check = subprocess.run([docker, "image", "inspect", "--format", "{{.Id}}", image], env=env,
                                       stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=min(timeout, 10))
                if check.returncode:
                    if b"No such image" in check.stderr or b"No such object" in check.stderr:
                        raise RuntimeError("docker_image_unavailable:" + image)
                    raise RuntimeError("docker_inspection_failed")
                image_id = check.stdout.decode().strip()
                if not re.fullmatch(r"sha256:[0-9a-f]{64}", image_id):
                    raise RuntimeError("docker_inspection_failed")
                result.update(docker_image=image, image_id=image_id)
                container = "unspool-" + hashlib.sha256(os.urandom(32)).hexdigest()[:20]
                command = [docker, "run", "--rm", "--pull=never", "--name", container, "--entrypoint=python",
                           "--network=none", "--read-only", "--memory=256m", "--cpus=1", "--pids-limit=64",
                           "--cap-drop=ALL", "--security-opt=no-new-privileges", "--user", f"{os.getuid()}:{os.getgid()}",
                           "--tmpfs", "/tmp:rw,noexec,nosuid,size=32m", "--env", "HOME=/tmp", "--env", "PYTHONDONTWRITEBYTECODE=1",
                           "--mount", f"type=bind,source={isolated_repository},target=/repository,readonly",
                           "--mount", f"type=bind,source={harness.parent},target=/harness,readonly",
                           "--mount", f"type=bind,source={work / 'input.json'},target=/input.json,readonly",
                           "--mount", f"type=bind,source={work / 'output'},target=/output",
                           "--workdir", "/tmp", image_id, "-I", "-B", "-c", _BOOTSTRAP,
                           "/harness", "/repository", "/input.json", "/output/result.json", str(timeout)]
            code = _execute(command, work, env, timeout)
            if code:
                raise RuntimeError("worker_exit_nonzero")
            output = work / "output" / "result.json"
            if not output.is_file() or output.is_symlink() or output.stat().st_size > 4 * 1024 * 1024:
                raise RuntimeError("worker_result_missing_or_invalid")
            evidence = json.loads(output.read_text(encoding="utf-8"))
            if not isinstance(evidence, dict) or not isinstance(evidence.get("cases"), list) or len(evidence["cases"]) != len(manifest["cases"]):
                raise RuntimeError("worker_result_invalid")
            for case, captured in zip(manifest["cases"], evidence["cases"]):
                if captured.get("id") != case["id"] or type(captured.get("passed")) is not bool or not isinstance(captured.get("observations"), list) or not isinstance(captured.get("captured_sinks"), list):
                    raise RuntimeError("worker_case_invalid")
                safe = {"id": case["id"], "passed": captured["passed"], "observed": False,
                        "observations": [], "violations": [], "call_events": [], "executed_lines": []}
                if "finding" in case:
                    safe["finding"] = dict(case["finding"])
                for event in captured.get("call_events", []):
                    if (not isinstance(event, dict)
                            or set(event) - {"module", "callable", "role", "order", "returned_type", "returned_bool", "raised"}
                            or not all(isinstance(event.get(key), str) and event[key] for key in ("module", "callable", "role"))
                            or type(event.get("order")) is not int):
                        raise RuntimeError("worker_call_event_invalid")
                    if "returned_bool" in event and type(event["returned_bool"]) is not bool:
                        raise RuntimeError("worker_call_event_invalid")
                    if "raised" in event and type(event["raised"]) is not bool:
                        raise RuntimeError("worker_call_event_invalid")
                    safe["call_events"].append({key: event[key] for key in event})
                for line in captured.get("executed_lines", []):
                    if (not isinstance(line, dict) or set(line) != {"file", "line"}
                            or not isinstance(line["file"], str) or not isinstance(line["line"], int)):
                        raise RuntimeError("worker_trace_invalid")
                    _path(line["file"])
                    safe["executed_lines"].append(dict(line))
                sources = {(s["symbol"], hashlib.sha256(s["marker"].encode()).hexdigest()): s for s in case["sensitive"]}
                for observation in captured["observations"]:
                    if not isinstance(observation, dict) or set(observation) != {"sink", "symbol", "marker_hash"} or not isinstance(observation["sink"], str):
                        raise RuntimeError("worker_observation_invalid")
                    source = sources.get((observation["symbol"], observation["marker_hash"]))
                    if source is None:
                        raise RuntimeError("worker_marker_invalid")
                    safe["observations"].append(observation)
                    decision = policy.evaluate(source["class"], observation["sink"], symbol=source["symbol"],
                                               context=case["context"])
                    if not decision["allowed"]:
                        violation = {"sink": observation["sink"], "symbol": source["symbol"],
                                     "classification": source["class"], "reasons": decision["reasons"]}
                        if violation not in safe["violations"]:
                            safe["violations"].append(violation)
                safe["observed"] = bool(safe["observations"])
                if captured.get("error"):
                    safe["error"] = "fixture_execution_failed"
                required = {"HTTP_RESPONSE"} | {m["sink"] for key in ("capture_http", "capture_calls", "artifacts") for m in case.get(key, [])}
                if case.get("finding"):
                    required.add(case["finding"]["sink"])
                if required - set(captured["captured_sinks"]):
                    safe["error"] = "required_capture_missing"
                result["cases"].append(safe)
            regression = evidence.get("regression")
            if "regression_command" in manifest:
                if not isinstance(regression, dict) or type(regression.get("passed")) is not bool:
                    raise RuntimeError("regression_result_missing")
                result["regression"] = {key: regression[key] for key in ("passed", "stdout_hash", "stderr_hash") if key in regression}
                if not regression["passed"]:
                    result["error"] = "regression_failed"
            result["status"] = "ERROR" if result.get("error") or any(c.get("error") for c in result["cases"]) else "COMPLETED"
            result["functional_passed"] = all(c["passed"] for c in result["cases"]) and (not regression or regression["passed"])
            result["passed"] = result["status"] == "COMPLETED" and result["functional_passed"] and not any(c["violations"] for c in result["cases"])
    except subprocess.TimeoutExpired:
        result["error"] = "runtime_timeout"
    except (ValueError, TypeError, OSError, RuntimeError, KeyError) as exc:
        # Never expose target exception text, payloads, stdout, or marker strings.
        result["error"] = str(exc) if isinstance(exc, RuntimeError) else "runtime_input_or_execution_error"
    finally:
        if container:
            try:
                subprocess.run([docker, "rm", "-f", container], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                               env={"PATH": os.defpath}, timeout=5)
            except (OSError, subprocess.TimeoutExpired):
                pass
        result["duration_ms"] = round((time.monotonic() - start) * 1000, 2)
    return result
