#!/bin/sh
# Dedicated disposable Docker worker only: this installs a temporary host INPUT rule.
set -eu
root=$(pwd)
harness=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
framework=$(CDPATH= cd -- "$harness/../.." && pwd)
work="$root/.unspool-http-work"
case "$CI_JOB_ID" in ''|*[!0-9]*) exit 2 ;; esac
network="unspool-http-$CI_JOB_ID"
app="unspool-http-app-$CI_JOB_ID"
probe="unspool-http-probe-$CI_JOB_ID"
listener="unspool-http-listener-$CI_JOB_ID"
subnet=''
filter_image=''
cleanup() {
  docker rm -f "$app" "$probe" "$listener" >/dev/null 2>&1 || true
  if [ -n "$subnet" ] && [ -n "$filter_image" ]; then
    docker run --rm --pull=never --network=host --cap-drop=ALL --cap-add=NET_ADMIN --cap-add=NET_RAW --entrypoint=iptables \
      "$filter_image" -D INPUT -s "$subnet" -j DROP >/dev/null 2>&1 || true
  fi
  docker network rm "$network" >/dev/null 2>&1 || true
  rm -f "$work/report.json"
}
mkdir -p "$root/acceptance"
rm -f "$root/acceptance/evidence.json" "$root/acceptance/health.json"
actual=$(git rev-parse --verify HEAD)
[ "$actual" = "$CI_COMMIT_SHA" ] || exit 1
rm -rf "$work"
mkdir -p "$work/source"
git archive "$actual" > "$work/source.tar"
tar -xf "$work/source.tar" -C "$work/source"
rm "$work/source.tar"
trap cleanup EXIT INT TERM
# Provision/pull reviewed images separately. Candidate verification installs no dependencies.
for image in "$UNSPOOL_APP_IMAGE" "$UNSPOOL_PROBE_IMAGE" "$UNSPOOL_FILTER_IMAGE"; do
  python3 -I -c 'import re,sys;sys.exit(0 if re.fullmatch(r"sha256:[0-9a-f]{64}",sys.argv[1]) else 1)' "$image"
  [ "$(docker image inspect --format '{{.Id}}' "$image")" = "$image" ] || exit 1
done
app_image=$UNSPOOL_APP_IMAGE
probe_image=$UNSPOOL_PROBE_IMAGE
filter_image=$UNSPOOL_FILTER_IMAGE
docker network create --internal "$network" >/dev/null
subnet=$(docker network inspect --format '{{(index .IPAM.Config 0).Subnet}}' "$network")
gateway=$(docker network inspect --format '{{(index .IPAM.Config 0).Gateway}}' "$network")
docker run -d --name "$listener" --pull=never --network=host --user=10001:10001 \
  --read-only --cap-drop=ALL --security-opt=no-new-privileges --log-driver=none \
  --memory=64m --cpus=1 --pids-limit=32 --workdir=/tmp \
  "$probe_image" python -I -B -m http.server 19375 --bind 0.0.0.0 >/dev/null
check_host() {
  docker run --rm --pull=never --network="$1" --dns=127.0.0.1 --user=10001:10001 \
    --read-only --cap-drop=ALL --security-opt=no-new-privileges --memory=64m --cpus=1 --pids-limit=32 \
    "$probe_image" python -I -B -c 'import socket,sys,time
deadline=time.monotonic()+5
reachable=False
while time.monotonic()<deadline:
 try:
  with socket.create_connection((sys.argv[1],19375),timeout=0.5): reachable=True
  break
 except OSError: time.sleep(0.1)
sys.exit(0 if reachable == (sys.argv[2]=="reachable") else 1)' "$2" "$3"
}
check_host host 127.0.0.1 reachable
[ "$(docker inspect --format '{{.State.Running}}' "$listener")" = true ] || exit 1
docker run --rm --pull=never --network=host --cap-drop=ALL --cap-add=NET_ADMIN --cap-add=NET_RAW --entrypoint=iptables \
  "$filter_image" -I INPUT -s "$subnet" -j DROP
check_host "$network" "$gateway" blocked
check_host host 127.0.0.1 reachable
[ "$(docker inspect --format '{{.State.Running}}' "$listener")" = true ] || exit 1
docker rm -f "$listener" >/dev/null
app_id=$(docker run -d --name "$app" --pull=never --network="$network" --network-alias=target \
  --dns=127.0.0.1 \
  --user=10001:10001 --read-only --cap-drop=ALL --security-opt=no-new-privileges \
  --memory=256m --cpus=1 --pids-limit=64 --log-driver=none \
  --tmpfs=/tmp:rw,nosuid,noexec,size=32m,uid=10001,gid=10001 \
  --tmpfs=/vampi/database:rw,nosuid,noexec,size=16m,uid=10001,gid=10001 \
  --mount="type=bind,source=$work/source,target=/vampi,readonly" \
  "$app_image" python -c 'from config import vuln_app; from werkzeug.serving import run_simple; run_simple("0.0.0.0", 8080, vuln_app.app)')
probe_id=$(docker create --name "$probe" --pull=never --network="$network" \
  --dns=127.0.0.1 \
  --user=10001:10001 --read-only --cap-drop=ALL --security-opt=no-new-privileges \
  --memory=128m --cpus=1 --pids-limit=32 --env=PYTHONDONTWRITEBYTECODE=1 \
  --tmpfs=/tmp:rw,nosuid,noexec,size=16m,uid=10001,gid=10001 \
  --mount="type=bind,source=$framework/unspool/http_acceptance.py,target=/probe.py,readonly" \
  --mount="type=bind,source=$harness/http-plan.json,target=/plan.json,readonly" \
  "$probe_image" python -I -B /probe.py --base-url http://target:8080 --plan /plan.json)
attach_status=0
docker start --attach "$probe" > "$work/report.json" || attach_status=$?
if [ "$attach_status" != 0 ] || [ "$(docker inspect --format '{{.State.ExitCode}}' "$probe")" != 0 ]; then
  python3 -I -c 'import json,sys
with open(sys.argv[1]) as source: result=json.load(source)
runtime=result.get("runtime",{})
print(json.dumps({"status":"STOPPED","runtime_status":runtime.get("status"),"functional_passed":runtime.get("functional_passed"),"security_passed":runtime.get("security_passed"),"secret_observed":any(c.get("observations") for c in runtime.get("cases",[]))}))' "$work/report.json"
  exit 1
fi
python3 -I -c 'import sys;sys.path.insert(0,sys.argv.pop(1));from unspool.http_evidence import main;main()' "$framework" \
  --report "$work/report.json" --plan "$harness/http-plan.json" \
  --probe "$framework/unspool/http_acceptance.py" --snapshot "$work/source" --source "$actual" \
  --app-image "$app_image" --probe-image "$probe_image" \
  --filter-image "$filter_image" --host-isolation-verified \
  --app-container "$app_id" --probe-container "$probe_id" --output "$root/acceptance"
