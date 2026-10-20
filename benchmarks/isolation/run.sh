#!/bin/sh
set -eu
network=unspool-isolation-drill
cleanup() { docker network rm "$network" >/dev/null 2>&1 || true; }
trap cleanup EXIT INT TERM
docker network create --internal "$network" >/dev/null
# This synthetic host file must never be mounted into either workload.
printf 'UNSPOOL_SYNTHETIC_HOST_CANARY' > /workspace/host-canary
image=$(docker image inspect --format '{{.Id}}' python:3.11-slim)
printf 'Drill image: %s\n' "$image"
for mode in none "$network"; do
  echo "Network case: $mode"
  docker run --rm --pull=never --network="$mode" --user=10001:10001 \
    --read-only --cap-drop=ALL --security-opt=no-new-privileges \
    --memory=256m --cpus=1 --pids-limit=64 \
    --tmpfs=/tmp:rw,nosuid,noexec,size=32m,uid=10001,gid=10001 \
    --mount=type=bind,source=/workspace/probe.py,target=/repository/attack.py,readonly \
    "$image" python -I -B /repository/attack.py
done
# Deliberately expose only a harmless synthetic value; the probe must reject it.
set +e
docker run --rm --pull=never --network=none --user=10001:10001 \
  --read-only --cap-drop=ALL --security-opt=no-new-privileges \
  --memory=256m --cpus=1 --pids-limit=64 \
  --tmpfs=/tmp:rw,nosuid,noexec,size=32m,uid=10001,gid=10001 \
  --env=GITLAB_TOKEN=UNSPOOL_SYNTHETIC_NEGATIVE_CONTROL \
  --mount=type=bind,source=/workspace/probe.py,target=/repository/attack.py,readonly \
  "$image" python -I -B /repository/attack.py > /workspace/negative.json
code=$?
set -e
test "$code" -eq 1
docker run --rm --pull=never --network=none --user=10001:10001 --read-only \
  --cap-drop=ALL --security-opt=no-new-privileges --memory=64m --cpus=1 --pids-limit=32 \
  --mount=type=bind,source=/workspace/negative.json,target=/negative.json,readonly \
  "$image" python -I -B -c '
import json
from pathlib import Path
result = json.loads(Path("/negative.json").read_text())
checks = result["checks"]
if result["passed"] is not False or checks.pop("credential_environment_absent") is not False or not all(v is True for v in checks.values()):
    raise SystemExit("Unexpected negative-control result")
print(json.dumps({"kind": "isolation-negative-control", "synthetic_credential_rejected": True}))
'
