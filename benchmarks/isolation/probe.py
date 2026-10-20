"""Controlled attack attempts inside a disposable container; never run on the host."""
import json
import os
from pathlib import Path
import secrets
import socket


def writable(path):
    target = Path(path) / (".unspool-write-" + secrets.token_hex(8))
    try:
        target.write_text("synthetic")
    except OSError:
        return False
    target.unlink()
    return True


def reachable(host, port):
    try:
        with socket.create_connection((host, port), timeout=1):
            return True
    except OSError:
        return False


def readable(path):
    try:
        with open(path, "rb") as source:
            source.read(1)
        return True
    except OSError:
        return False


def limit(v2, v1):
    for path in (v2, v1):
        try:
            return Path(path).read_text().strip()
        except OSError:
            pass
    return "unknown"


def main():
    status = dict(line.split(":", 1) for line in Path("/proc/self/status").read_text().splitlines() if ":" in line)
    memory = limit("/sys/fs/cgroup/memory.max", "/sys/fs/cgroup/memory/memory.limit_in_bytes")
    pids = limit("/sys/fs/cgroup/pids.max", "/sys/fs/cgroup/pids/pids.max")
    cpu = limit("/sys/fs/cgroup/cpu.max", "/sys/fs/cgroup/cpu/cpu.cfs_quota_us")
    checks = {
        "non_root": os.getuid() == 10001,
        "capabilities_dropped": status.get("CapEff", "").strip() == "0000000000000000",
        "no_new_privileges": status.get("NoNewPrivs", "").strip() == "1",
        "root_read_only": not writable("/"),
        "source_read_only": not writable("/repository"),
        "temporary_storage_available": writable("/tmp"),
        "temporary_disk_bounded": os.statvfs("/tmp").f_blocks * os.statvfs("/tmp").f_frsize <= 32 * 1024 * 1024,
        "host_canary_not_readable": not readable("/workspace/host-canary"),
        "docker_socket_absent": not Path("/var/run/docker.sock").exists(),
        "credentials_not_readable": not any(readable(p) for p in (
            "/root/.config/gcloud/application_default_credentials.json", "/root/.aws/credentials",
            "/root/.git-credentials", "/root/.ssh/id_rsa", "/probe.py")),
        "credential_environment_absent": not any(k in os.environ for k in (
            "GITLAB_TOKEN", "CI_JOB_TOKEN", "GCP_ID_TOKEN", "GOOGLE_APPLICATION_CREDENTIALS")),
        "metadata_tcp_blocked": not reachable("169.254.169.254", 80),
        "external_tcp_blocked": not reachable("1.1.1.1", 443),
        "memory_bounded": memory.isdecimal() and 0 < int(memory) <= 256 * 1024 * 1024,
        "processes_bounded": pids.isdecimal() and 0 < int(pids) <= 64,
    }
    if " " in cpu:
        quota, period = cpu.split()
        checks["cpu_bounded"] = quota.isdecimal() and period.isdecimal() and 0 < int(quota) <= int(period)
    else:
        checks["cpu_bounded"] = cpu.isdecimal() and 0 < int(cpu) <= 100000
    print(json.dumps({"kind": "controlled-container-isolation-drill", "passed": all(checks.values()),
                      "checks": checks, "limits": {"memory": memory, "pids": pids, "cpu": cpu}}))
    raise SystemExit(0 if all(checks.values()) else 1)


if __name__ == "__main__":
    main()
