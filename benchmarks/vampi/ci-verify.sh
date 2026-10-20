#!/bin/sh
# Trusted harness for this known vulnerable lab, not a hostile-code worker service.
set -eu
root=$(pwd)
harness=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
work="$root/.unspool-work"
rm -rf "$work"
mkdir -p "$work/source" "$root/acceptance"
rm -f "$root/acceptance/evidence.json" "$root/acceptance/health.json"
# Export source without .git credentials, runner files or inherited workspace state.
git archive "$CI_COMMIT_SHA" | tar -x -C "$work/source"
docker build -f "$harness/Dockerfile" -t vampi-acceptance-dependencies "$work/source"
image=$(docker image inspect --format '{{.Id}}' vampi-acceptance-dependencies)
if ! docker run --rm --pull=never --network=none --read-only \
  --cap-drop=ALL --security-opt=no-new-privileges \
  --memory=256m --cpus=1 --pids-limit=64 \
  --tmpfs=/tmp:rw,nosuid,noexec,size=32m,uid=10001,gid=10001 \
  --tmpfs=/vampi/database:rw,nosuid,noexec,size=16m,uid=10001,gid=10001 \
  --mount="type=bind,source=$work/source,target=/vampi,readonly" \
  --mount="type=bind,source=$harness/probe.py,target=/harness/probe.py,readonly" \
  "$image" python /harness/probe.py --expect-fixed \
  > "$work/probe-result.json" 2> "$work/probe-stderr.log"; then
  rm -f "$work/probe-result.json" "$work/probe-stderr.log"
  echo 'HTTP acceptance failed or could not execute; no successful evidence produced.'
  exit 1
fi
python3 "$harness/report.py" --probe-result "$work/probe-result.json" \
  --commit "$CI_COMMIT_SHA" --image "$image" --output "$root/acceptance"
rm -f "$work/probe-result.json" "$work/probe-stderr.log"
