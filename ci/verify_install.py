"""Qualify the installed wheel from an empty cwd, never importing checkout code."""
import argparse
import hashlib
from importlib.metadata import distributions, version
import json
import os
from pathlib import Path
import platform
import subprocess
import sys
import sysconfig
import tempfile

import leakhunter
import unspool


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    source = args.source.resolve(strict=True)
    output = args.output.resolve()
    checked = 0
    for package in (leakhunter, unspool):
        installed = Path(package.__file__).resolve().parent
        if installed.is_relative_to(source):
            raise RuntimeError("Qualification imported the source checkout")
        origin = source / package.__name__
        for file in origin.rglob("*"):
            if file.is_file() and file.suffix in {".py", ".html", ".css", ".js"}:
                target = installed / file.relative_to(origin)
                if not target.is_file() or hashlib.sha256(target.read_bytes()).digest() != hashlib.sha256(file.read_bytes()).digest():
                    raise RuntimeError("Installed module or static asset differs from source: " + str(file.relative_to(source)))
                checked += 1
    with tempfile.TemporaryDirectory(prefix="unspool-installed-") as directory:
        work = Path(directory)
        env = {"PATH": sysconfig.get_path("scripts") + os.pathsep + os.defpath,
               "HOME": directory, "LANG": "C.UTF-8", "PYTHONDONTWRITEBYTECODE": "1"}
        for command in ("unspool", "leakhunter", "unspool-handoff"):
            result = subprocess.run([str(Path(sysconfig.get_path("scripts")) / command), "--help"],
                                    cwd=work, env=env, capture_output=True, timeout=30)
            if result.returncode:
                raise RuntimeError("Installed console command failed: " + command)
        rejected_state = work / "rejected-evaluation"
        for command in ("unspool", "leakhunter"):
            rejected = subprocess.run([str(Path(sysconfig.get_path("scripts")) / command),
                                       "--repository", str(source / "demo/target"),
                                       "--policy", str(source / "demo/policy.yaml"),
                                       "--data-dir", str(rejected_state), "--once", "evaluate", "--gate"],
                                      cwd=work, env=env, capture_output=True, timeout=10)
            if rejected.returncode != 2 or rejected_state.exists():
                raise RuntimeError("Installed evaluation was allowed to act as a release gate")
        state = work / "state"
        state.mkdir(mode=0o700)
        (state / "STOP").touch()
        canceled = subprocess.run([str(Path(sysconfig.get_path("scripts")) / "unspool-handoff"),
                                   "--project", "87860005", "--issue", "1", "--state-dir", str(state)],
                                  cwd=work, env=env, capture_output=True, text=True, timeout=10)
        if canceled.returncode != 130 or json.loads(canceled.stdout).get("status") != "CANCELED":
            raise RuntimeError("Installed controller did not honor the STOP flag")
        records = list(state.glob("*.json"))
        if len(records) != 1 or json.loads(records[0].read_text()).get("state") != "CANCELED":
            raise RuntimeError("Installed controller did not persist cancellation")
        command = [sys.executable, "-I", "-m", "unspool", "--repository", str(source / "demo/target"),
                   "--policy", str(source / "demo/policy.yaml"), "--runtime-manifest", str(source / "demo/runtime.yaml"),
                   "--runtime-backend", "local", "--provider-url", "", "--data-dir", str(work / "data"),
                   "--once", "analyze", "--gate"]
        result = subprocess.run(command, cwd=work, env=env, capture_output=True, text=True, timeout=60)
        if result.returncode:
            raise RuntimeError("Installed synthetic workflow failed")
        evidence = json.loads(result.stdout)
        if evidence.get("gate", {}).get("passed") is not True or evidence.get("runtime", {}).get("passed") is not True:
            raise RuntimeError("Installed synthetic workflow did not pass exposure verification")
    record = {"status": "PASSED", "version": version("unspool"), "python": platform.python_version(),
              "platform": platform.system(), "installed_files_verified": checked,
              "source_checkout_imported": False, "console_commands_passed": 3,
              "evaluation_release_gate_rejected": True,
              "stop_flag_canceled": True,
              "synthetic_exposure_gate_passed": True,
              "dependencies": sorted(f"{d.metadata['Name']}=={d.version}" for d in distributions())}
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(record, indent=2) + "\n")
    print(json.dumps({k: v for k, v in record.items() if k != "dependencies"}))


if __name__ == "__main__":
    main()
