#!/bin/sh
# Dedicated disposable worker only. No application source is mounted in the probe.
set -eu
expected=$1
case "$expected" in --expect-fixed|--expect-vulnerable) ;; *) exit 2 ;; esac
network=unspool-generic-http
app=unspool-generic-target
cleanup() {
  docker rm -f "$app" >/dev/null 2>&1 || true
  docker network rm "$network" >/dev/null 2>&1 || true
}
trap cleanup EXIT INT TERM
docker network create --internal "$network" >/dev/null
image=$(docker image inspect --format '{{.Id}}' vampi-validation-dependencies)
probe_image=$(docker image inspect --format '{{.Id}}' python:3.11-slim)
docker run -d --name "$app" --pull=never --network="$network" --network-alias=vampi \
  --read-only --cap-drop=ALL --security-opt=no-new-privileges \
  --memory=256m --cpus=1 --pids-limit=64 --log-driver=none \
  --tmpfs=/tmp:rw,nosuid,noexec,size=32m,uid=10001,gid=10001 \
  --tmpfs=/vampi/database:rw,nosuid,noexec,size=16m,uid=10001,gid=10001 \
  --mount=type=bind,source=/workspace/upstream,target=/vampi,readonly \
  "$image" python -c 'from config import vuln_app; from werkzeug.serving import run_simple; run_simple("0.0.0.0", 8080, vuln_app.app)' >/dev/null
docker run --rm --pull=never --network="$network" --user=10001:10001 \
  --read-only --cap-drop=ALL --security-opt=no-new-privileges \
  --memory=128m --cpus=1 --pids-limit=32 --env=PYTHONDONTWRITEBYTECODE=1 \
  --mount=type=bind,source=/workspace/acceptance.py,target=/acceptance.py,readonly \
  --mount=type=bind,source=/workspace/http-plan.json,target=/plan.json,readonly \
  --mount=type=bind,source=/workspace/generic_probe.py,target=/probe.py,readonly \
  "$probe_image" python -I -B /probe.py "$expected"
printf 'Application image: %s\nProbe image: %s\n' "$image" "$probe_image"
sha256sum /workspace/acceptance.py /workspace/http-plan.json
