"""Bounded non-Python execution; local execution requires explicitly trusted code."""
from __future__ import annotations

import hashlib
import json
import math
import os
from pathlib import Path
import re
import shutil
import signal
import subprocess
import tempfile
import time

from leakhunter.languages import entrypoint, runtime_image


_JS_RUNNER = r'''import fs from "node:fs";
import path from "node:path";
import {pathToFileURL} from "node:url";
import {createHash} from "node:crypto";
import {inspect} from "node:util";

const input = JSON.parse(fs.readFileSync(process.argv[2], "utf8"));
const observations = [];
const captured = new Set();
const stringify = (value) => {
  if (typeof value === "string") return value;
  try { return JSON.stringify(value) ?? String(value); }
  catch { return inspect(value, {depth: null, customInspect: false, getters: false}); }
};
const observe = (sink, value) => {
  captured.add(sink);
  const text = stringify(value);
  for (const source of input.case.sensitive) {
    if (!text.includes(source.marker)) continue;
    const item = {sink, symbol: source.symbol,
      marker_hash: createHash("sha256").update(source.marker).digest("hex")};
    if (!observations.some((current) => JSON.stringify(current) === JSON.stringify(item))) observations.push(item);
  }
};
for (const name of ["log", "info", "warn", "error", "debug", "trace", "dir", "table"]) {
  console[name] = (...args) => observe("APPLICATION_LOG", args.map(stringify).join(" "));
}
const streamBuffers = [];
for (const stream of [process.stdout, process.stderr]) {
  const chunks = [];
  streamBuffers.push(chunks);
  stream.write = (value, encoding, callback) => {
    chunks.push(typeof value === "string" ? Buffer.from(value, typeof encoding === "string" ? encoding : "utf8") : Buffer.from(value));
    const done = typeof encoding === "function" ? encoding : callback;
    if (typeof done === "function") queueMicrotask(done);
    return true;
  };
}
globalThis.fetch = async (url, options = {}) => {
  const address = typeof url === "object" && url !== null && "url" in url ? url.url : String(url);
  const model = [...(input.case.capture_http ?? [])].sort((a, b) => b.url_prefix.length - a.url_prefix.length)
    .find((item) => address.startsWith(item.url_prefix));
  let body = "";
  if (typeof url === "object" && typeof url?.clone === "function") body = await url.clone().text();
  observe(model?.sink ?? "THIRD_PARTY_ANALYTICS", [address, stringify(options), body].join(" "));
  return new Response(JSON.stringify({ok: true}), {status: 200, headers: {"content-type": "application/json"}});
};
const subset = (actual, expected) => {
  if (expected === null || typeof expected !== "object") return Object.is(actual, expected);
  if (Array.isArray(expected)) return Array.isArray(actual) && actual.length === expected.length && expected.every((item, index) => subset(actual[index], item));
  return actual !== null && typeof actual === "object" && Object.entries(expected).every(([key, value]) => Object.hasOwn(actual, key) && subset(actual[key], value));
};
const output = {id: input.case.id, passed: false, observations, captured_sinks: [], call_events: [], executed_lines: []};
try {
  const target = await import(pathToFileURL(path.resolve(input.repository, input.entrypoint.file)).href);
  const parts = input.entrypoint.callable.split(".");
  const owner = parts.slice(0, -1).reduce((value, key) => value?.[key], target);
  const callable = owner?.[parts.at(-1)];
  if (typeof callable !== "function") throw new Error("entrypoint_not_callable");
  const returned = await callable.apply(owner, input.case.args ?? []);
  observe("HTTP_RESPONSE", returned);
  output.passed = subset(returned, input.case.expect);
} catch { output.error = "fixture_execution_failed"; }
for (const chunks of streamBuffers) {
  if (chunks.length) observe("APPLICATION_LOG", Buffer.concat(chunks).toString("utf8"));
}
output.captured_sinks = [...captured].sort();
fs.writeFileSync(process.argv[3], JSON.stringify(output));
'''

_TOOLS = ("node", "bun", "go", "rustc", "cargo", "python", "python3")
_COPY_IGNORE = shutil.ignore_patterns(".git", "__pycache__", ".env", ".env.*", "*.pem", "*.key", "credentials", ".aws", ".ssh")


def _sha_marker(marker: str) -> str:
    return hashlib.sha256(marker.encode()).hexdigest()


def _contains(value, marker: str) -> bool:
    if isinstance(value, bytes):
        return marker.encode() in value
    if isinstance(value, str):
        return marker in value
    if isinstance(value, dict):
        return any(_contains(key, marker) or _contains(item, marker) for key, item in value.items())
    if isinstance(value, list):
        return any(_contains(item, marker) for item in value)
    return False


def _observations(case: dict, sink: str, value, observations: list[dict], captured: set[str]) -> None:
    captured.add(sink)
    for source in case["sensitive"]:
        if _contains(value, source["marker"]):
            item = {"sink": sink, "symbol": source["symbol"], "marker_hash": _sha_marker(source["marker"])}
            if item not in observations:
                observations.append(item)


def _subset(actual, expected) -> bool:
    if isinstance(expected, dict):
        return isinstance(actual, dict) and all(key in actual and _subset(actual[key], value) for key, value in expected.items())
    if isinstance(expected, list):
        return isinstance(actual, list) and len(actual) == len(expected) and all(_subset(a, b) for a, b in zip(actual, expected))
    return type(actual) is type(expected) and actual == expected


def _environment(work: Path, *, docker: bool) -> dict[str, str]:
    directories = ["/usr/local/go/bin", "/usr/local/cargo/bin", "/usr/local/bin", "/usr/bin", "/bin"] if docker else [os.path.dirname(tool) for name in _TOOLS if (tool := shutil.which(name))]
    env = {"PATH": os.pathsep.join(dict.fromkeys(directories + [os.defpath])), "LANG": "C.UTF-8",
           "HOME": str(work / "home"), "TMPDIR": str(work / "tmp"), "GOCACHE": str(work / "go-cache"),
           "GOMODCACHE": str(work / "go-mod-cache"), "CARGO_HOME": str(work / "cargo-home"),
           "CARGO_TARGET_DIR": str(work / "cargo-target"), "GOTOOLCHAIN": "local", "GOPROXY": "off", "GOSUMDB": "off"}
    # rustup proxies need the installed toolchain, not an empty synthetic HOME.
    env["RUSTUP_HOME"] = "/usr/local/rustup" if docker else os.environ.get("RUSTUP_HOME", str(Path.home() / ".rustup"))
    if docker:
        env["CARGO_NET_OFFLINE"] = "true"
    return env


def _command(spec, repository: Path, *, docker: bool, regression: bool = False) -> list[str]:
    if not spec:
        raise RuntimeError("entrypoint_command_required")
    command = list(spec)
    name = command[0]
    candidate = repository / name
    if "/" in name or candidate.is_file():
        if Path(name).is_absolute() or ".." in Path(name).parts or not candidate.is_file() or not candidate.resolve().is_relative_to(repository.resolve()):
            raise RuntimeError("command_not_repository_local")
        command[0] = str(candidate)
    elif name in (_TOOLS if regression else ("go", "rustc", "cargo")):
        if not docker:
            tool = shutil.which(name)
            if not tool:
                raise RuntimeError("toolchain_unavailable:" + name)
            command[0] = tool
    else:
        raise RuntimeError("unsupported_entrypoint_command")
    return command


def _run_process(command, *, cwd: Path, input_data: str, env: dict[str, str], timeout: float) -> tuple[bytes, bytes, int]:
    process = subprocess.Popen(command, cwd=cwd, env=env, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                               stderr=subprocess.PIPE, start_new_session=True)
    try:
        stdout, stderr = process.communicate(input_data.encode(), timeout=timeout)
    except subprocess.TimeoutExpired:
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        stdout, stderr = process.communicate()
        raise subprocess.TimeoutExpired(command, timeout, output=stdout, stderr=stderr) from None
    return stdout, stderr, process.returncode


class _Executor:
    """One subprocess path for both trusted host commands and pinned containers."""

    def __init__(self, backend: str, manifest: dict, language: str, work: Path, result: dict, timeout: float):
        self.backend, self.work, self.timeout = backend, work, timeout
        self.js_tool = "bun" if language == "typescript" or any(case["entrypoint"]["file"].endswith(".jsx") for case in manifest["cases"]) else "node"
        self.docker = None
        self.image_id = None
        self.env = _environment(work, docker=False)
        if backend == "docker":
            self.docker = shutil.which("docker")
            if not self.docker:
                raise RuntimeError("docker_unavailable")
            image = runtime_image(manifest)
            check = subprocess.run([self.docker, "image", "inspect", "--format", "{{.Id}}", image], env=self.env,
                                   stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=min(timeout, 10))
            if check.returncode:
                if b"No such image" in check.stderr or b"No such object" in check.stderr:
                    raise RuntimeError("docker_image_unavailable")
                raise RuntimeError("docker_inspection_failed")
            self.image_id = check.stdout.decode().strip()
            if not re.fullmatch(r"sha256:[0-9a-f]{64}", self.image_id):
                raise RuntimeError("docker_inspection_failed")
            result.update(docker_image=image, image_id=self.image_id)

    def run(self, command: list[str], repository: Path, workspace: Path, *, input_data: str = ""):
        for name in ("home", "tmp", "go-cache", "go-mod-cache", "cargo-home", "cargo-target"):
            (workspace / name).mkdir(exist_ok=True)
        if self.backend == "local":
            return _run_process(command, cwd=repository, input_data=input_data,
                                env=_environment(workspace, docker=False), timeout=self.timeout)
        container = "leakhunter-" + os.urandom(12).hex()
        # The image needs only env, sh, cp and its native toolchain, never Python.
        argv = [self.docker, "run", "--rm", "--pull=never", "--name", container, "--interactive",
                "--entrypoint=/usr/bin/env", "--network=none", "--read-only", "--memory=512m", "--cpus=1",
                "--pids-limit=128", "--cap-drop=ALL", "--security-opt=no-new-privileges", "--user", f"{os.getuid()}:{os.getgid()}",
                "--tmpfs", "/tmp:rw,noexec,nosuid,size=32m",
                "--mount", f"type=bind,source={repository},target=/repository,readonly",
                "--mount", f"type=bind,source={self.work / 'harness'},target=/harness,readonly",
                "--mount", f"type=bind,source={workspace.with_suffix('.json')},target=/input.json,readonly",
                "--mount", f"type=bind,source={workspace},target=/work", "--workdir", "/work", self.image_id, "-i"]
        argv.extend(f"{key}={value}" for key, value in _environment(Path("/work"), docker=True).items())
        argv.extend(["/bin/sh", "-c", 'cp -R /repository/. /work/repository/ && cd /work/repository && exec "$@"', "leakhunter", *command])
        try:
            return _run_process(argv, cwd=workspace, input_data=input_data, env=self.env, timeout=self.timeout)
        finally:
            try:
                subprocess.run([self.docker, "rm", "-f", container], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                               env=self.env, timeout=5)
            except (OSError, subprocess.TimeoutExpired):
                pass


def _case(repository: Path, case: dict, language: str, workspace: Path, executor: _Executor) -> dict:
    observations: list[dict] = []
    captured: set[str] = set()
    result = {"id": case["id"], "passed": False, "observations": observations, "captured_sinks": [],
              "call_events": [], "executed_lines": []}
    try:
        for option in ("observe_calls", "capture_calls", "trace"):
            if case.get(option):
                raise RuntimeError("unsupported_instrumentation:" + option)
        js = language in {"javascript", "typescript"}
        if js and case.get("kwargs"):
            raise RuntimeError("unsupported_javascript_kwargs")
        if not js and case.get("capture_http"):
            raise RuntimeError("unsupported_instrumentation:capture_http")
        spec = entrypoint(case, language)
        docker = executor.backend == "docker"
        isolated = workspace / "repository"
        if docker:
            isolated.mkdir()
        else:
            shutil.copytree(repository, isolated, symlinks=True, ignore=_COPY_IGNORE)
        target_root = Path("/work/repository") if docker else isolated
        payload = {"repository": str(target_root), "entrypoint": {"file": spec.file, "callable": spec.callable}, "case": case}
        input_path = workspace.with_suffix(".json")
        input_path.write_text(json.dumps(payload, allow_nan=False), encoding="utf-8")
        if js:
            tool = executor.js_tool if docker else ("bun" if language == "typescript" or spec.file.endswith(".jsx") else "node")
            binary = tool if docker else shutil.which(tool)
            if not binary:
                raise RuntimeError("toolchain_unavailable:" + tool)
            command = [binary, "/harness/runner.mjs" if docker else str(executor.work / "harness" / "runner.mjs"),
                       "/input.json" if docker else str(input_path),
                       "/work/result.json" if docker else str(workspace / "result.json")]
        else:
            # Validate the host copy, then rewrite only the executable path for the container.
            command = _command(spec.command, repository if docker else isolated, docker=docker)
            if docker and Path(command[0]).is_absolute():
                command[0] = str(target_root / Path(command[0]).relative_to(repository))
        stdout, stderr, code = executor.run(command, repository if docker else isolated, workspace,
                                          input_data="" if js else json.dumps({"args": case.get("args", []), "kwargs": case.get("kwargs", {})}, allow_nan=False))
        # Native stderr and anything bypassing JS stream wrappers are application logs.
        if stderr:
            _observations(case, "APPLICATION_LOG", stderr, observations, captured)
        if js and stdout:
            _observations(case, "APPLICATION_LOG", stdout, observations, captured)
        if code:
            if code == 127:
                missing = tool if js else spec.command[0]
                raise RuntimeError("toolchain_unavailable:" + missing if missing in _TOOLS else "entrypoint_command_unavailable")
            raise RuntimeError("fixture_exit_nonzero")
        if js:
            output = workspace / "result.json"
            if output.is_symlink() or not output.is_file() or output.stat().st_size > 4 * 1024 * 1024:
                raise RuntimeError("worker_result_missing_or_invalid")
            actual = json.loads(output.read_text(encoding="utf-8"))
            if not isinstance(actual, dict) or actual.get("id") != case["id"] or type(actual.get("passed")) is not bool or not isinstance(actual.get("observations"), list) or not isinstance(actual.get("captured_sinks"), list):
                raise RuntimeError("worker_case_invalid")
            observations.extend(actual["observations"])
            if any(not isinstance(sink, str) for sink in actual["captured_sinks"]):
                raise RuntimeError("worker_case_invalid")
            captured.update(actual["captured_sinks"])
            result["passed"] = actual["passed"]
            if actual.get("error"):
                result["error"] = "fixture_execution_failed"
        else:
            actual = json.loads(stdout)
            if not isinstance(actual, dict):
                raise RuntimeError("runner_protocol_invalid")
            _observations(case, "HTTP_RESPONSE", actual, observations, captured)
            result["passed"] = _subset(actual, case["expect"])
        for artifact in case.get("artifacts", []):
            path = isolated / artifact["path"]
            if path.is_symlink() or not path.resolve().is_relative_to(isolated.resolve()) or not path.is_file():
                raise RuntimeError("artifact_missing_or_escaped")
            _observations(case, artifact["sink"], path.read_bytes(), observations, captured)
    except subprocess.TimeoutExpired:
        result["error"] = "runtime_timeout"
    except RuntimeError as exc:
        result["error"] = str(exc)
    except (OSError, TypeError, ValueError, KeyError):
        result["error"] = "fixture_execution_failed"
    result["captured_sinks"] = sorted(captured)
    return result


def _safe_case(case: dict, captured: dict, policy) -> dict:
    safe = {"id": case["id"], "passed": captured["passed"], "observations": [], "captured_sinks": [],
            "call_events": [], "executed_lines": [], "violations": [], "observed": False}
    if "finding" in case:
        safe["finding"] = dict(case["finding"])
    if captured.get("error"):
        safe["error"] = captured["error"]
    sources = {(item["symbol"], _sha_marker(item["marker"])): item for item in case["sensitive"]}
    required = {"HTTP_RESPONSE"} | {item["sink"] for key in ("capture_http", "capture_calls", "artifacts") for item in case.get(key, [])}
    if case.get("finding"):
        required.add(case["finding"]["sink"])
    sinks = required | {"APPLICATION_LOG", "THIRD_PARTY_ANALYTICS"}
    for observation in captured["observations"]:
        if not isinstance(observation, dict) or set(observation) != {"sink", "symbol", "marker_hash"} or any(not isinstance(value, str) for value in observation.values()):
            safe["error"] = "worker_observation_invalid"
            continue
        source = sources.get((observation["symbol"], observation["marker_hash"]))
        if source is None or observation["sink"] not in sinks:
            safe["error"] = "worker_marker_invalid"
            continue
        clean = dict(observation)
        if clean in safe["observations"]:
            continue
        safe["observations"].append(clean)
        decision = policy.evaluate(source["class"], clean["sink"], symbol=source["symbol"], context=case["context"])
        if not decision["allowed"]:
            safe["violations"].append({"sink": clean["sink"], "symbol": source["symbol"],
                                       "classification": source["class"], "reasons": decision["reasons"]})
    if any(sink not in sinks for sink in captured["captured_sinks"]):
        safe["error"] = "worker_capture_invalid"
    safe["captured_sinks"] = sorted(set(captured["captured_sinks"]) & sinks)
    safe["observed"] = bool(safe["observations"])
    if required - set(safe["captured_sinks"]) and not safe.get("error"):
        safe["error"] = "required_capture_missing"
    return safe


def _regression(repository: Path, command, workspace: Path, executor: _Executor) -> dict:
    stdout = stderr = b""
    passed = False
    error = None
    try:
        docker = executor.backend == "docker"
        isolated = workspace / "repository"
        if docker:
            isolated.mkdir()
        else:
            shutil.copytree(repository, isolated, symlinks=True, ignore=_COPY_IGNORE)
        workspace.with_suffix(".json").write_text("{}", encoding="utf-8")
        argv = _command(command, repository if docker else isolated, docker=docker, regression=True)
        if docker and Path(argv[0]).is_absolute():
            argv[0] = str(Path("/work/repository") / Path(argv[0]).relative_to(repository))
        stdout, stderr, code = executor.run(argv, repository if docker else isolated, workspace)
        passed = code == 0
    except subprocess.TimeoutExpired as exc:
        stdout, stderr = exc.output or b"", exc.stderr or b""
        error = "runtime_timeout"
    except (OSError, RuntimeError, ValueError, TypeError):
        error = "regression_execution_failed"
    result = {"passed": passed, "stdout_hash": hashlib.sha256(stdout).hexdigest(), "stderr_hash": hashlib.sha256(stderr).hexdigest()}
    if error:
        result["error"] = error
    return result


def run_external_suite(repository: Path, manifest: dict, policy, *, language: str, backend: str, timeout: float) -> dict:
    started = time.monotonic()
    result = {"status": "ERROR", "cases": [], "passed": False, "functional_passed": False,
              "backend": backend, "duration_ms": 0}
    try:
        if backend not in {"local", "docker"} or language not in {"javascript", "typescript", "go", "rust"}:
            raise ValueError("invalid backend or language")
        if isinstance(timeout, bool) or not isinstance(timeout, (int, float)) or not math.isfinite(timeout) or timeout <= 0:
            raise ValueError("invalid timeout")
        repository = Path(repository).resolve(strict=True)
        with tempfile.TemporaryDirectory(prefix="leakhunter-runtime-") as temporary:
            work = Path(temporary)
            (work / "harness").mkdir()
            (work / "harness" / "runner.mjs").write_text(_JS_RUNNER, encoding="utf-8")
            # Docker receives only the credential-scrubbed, read-only input copy.
            isolated = work / "repository"
            shutil.copytree(repository, isolated, symlinks=True, ignore=_COPY_IGNORE)
            executor = _Executor(backend, manifest, language, work, result, float(timeout))
            for index, case in enumerate(manifest["cases"]):
                workspace = work / f"case-{index}"
                workspace.mkdir()
                captured = _case(isolated, case, language, workspace, executor)
                result["cases"].append(_safe_case(case, captured, policy))
            regression = None
            if "regression_command" in manifest:
                workspace = work / "regression"
                workspace.mkdir()
                regression = _regression(isolated, manifest["regression_command"], workspace, executor)
                result["regression"] = regression
                if not regression["passed"]:
                    result["error"] = "regression_failed"
            result["status"] = "ERROR" if result.get("error") or any(case.get("error") for case in result["cases"]) else "COMPLETED"
            result["functional_passed"] = all(case["passed"] for case in result["cases"]) and (regression is None or regression["passed"])
            result["passed"] = result["status"] == "COMPLETED" and result["functional_passed"] and not any(case["violations"] for case in result["cases"])
    except subprocess.TimeoutExpired:
        result["error"] = "runtime_timeout"
    except RuntimeError as exc:
        result["error"] = str(exc)
    except (OSError, ValueError, TypeError, KeyError):
        result["error"] = "runtime_input_or_execution_error"
    finally:
        result["duration_ms"] = round((time.monotonic() - started) * 1000, 2)
    return result
