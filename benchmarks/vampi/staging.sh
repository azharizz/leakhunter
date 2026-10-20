#!/bin/sh
# Disposable synthetic database only. Never point this at customer storage.
set -eu
release=$1
network=unspool-staging-drill
live=unspool-staging-live
candidate=unspool-staging-candidate
cleanup() {
  docker rm -f "$live" "$candidate" >/dev/null 2>&1 || true
  docker network rm "$network" >/dev/null 2>&1 || true
}
trap cleanup EXIT INT TERM
docker network create --internal "$network" >/dev/null
probe_image=$(docker image inspect --format '{{.Id}}' python:3.11-slim)
docker pull "$release" >/dev/null
artifact=$(docker image inspect --format '{{index .RepoDigests 0}}' "$release")
revision=$(docker image inspect --format '{{index .Config.Labels "org.opencontainers.image.revision"}}' "$artifact")
test "$revision" = c146bd1b9ee9fbe2730c316675de1fa7e55f0fa1

start_live() {
  docker run -d --name "$live" --pull=never --network="$network" --network-alias=vampi \
    --read-only --cap-drop=ALL --security-opt=no-new-privileges \
    --memory=256m --cpus=1 --pids-limit=64 --log-driver=none \
    --tmpfs=/tmp:rw,nosuid,noexec,size=32m,uid=10001,gid=10001 \
    --tmpfs=/vampi/database:rw,nosuid,noexec,size=16m,uid=10001,gid=10001 \
    "$artifact" python -c 'from config import vuln_app; from werkzeug.serving import run_simple; run_simple("0.0.0.0", 8080, vuln_app.app)' >/dev/null
}
probe_live() {
  docker run --rm --pull=never --network="$network" --user=10001:10001 \
    --read-only --cap-drop=ALL --security-opt=no-new-privileges \
    --memory=128m --cpus=1 --pids-limit=32 \
    --mount=type=bind,source=/workspace/http_probe.py,target=/probe.py,readonly \
    "$probe_image" python -I -B /probe.py --expect-fixed
}
fail_candidate() {
  docker run -d --name "$candidate" --pull=never --network="$network" \
    --read-only --cap-drop=ALL --security-opt=no-new-privileges \
    --memory=128m --cpus=1 --pids-limit=32 --log-driver=none \
    "$artifact" python -I -B -c 'raise SystemExit(17)' >/dev/null
  test "$(docker wait "$candidate")" = 17
  test "$(docker inspect --format '{{.State.Running}}' "$candidate")" = false
}

start_live
healthy_id=$(docker inspect --format '{{.Id}}' "$live")
probe_live
echo 'Stage: healthy application verified'
# Reject a broken startup candidate before touching the healthy container.
fail_candidate
test "$(docker inspect --format '{{.Id}}' "$live")" = "$healthy_id"
test "$(docker inspect --format '{{.State.Running}}' "$live")" = true
probe_live
echo 'Stage: failing candidate rejected; healthy application preserved'

# Intentional staging outage: remove healthy deployment and restore the retained
# immutable application image. This tests configuration rollback, not data restore.
docker rm -f "$live" >/dev/null
test "$(docker inspect --format '{{.State.Running}}' "$candidate")" = false
start_live
test "$(docker inspect --format '{{.Id}}' "$live")" != "$healthy_id"
probe_live
printf 'Rollback artifact: %s\nSource revision: %s\nProbe image: %s\n' "$artifact" "$revision" "$probe_image"
echo '{"kind":"disposable-application-staging-rollback","passed":true,"failed_candidate_rejected":true,"healthy_preserved":true,"rollback_reverified":true,"ephemeral_database_only":true}'
