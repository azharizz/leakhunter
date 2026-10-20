# Judge reproduction guide

This guide exercises the trusted synthetic demonstration locally. It does not
execute arbitrary customer repositories, require a model API key, trigger Duo,
merge an MR or deploy anything. Allow about a few minutes for dependency download;
that is not a measured setup-time guarantee. Use CPython 3.10, 3.11 or 3.12 on
Linux/macOS. Docker is not needed for this deliberately trusted synthetic case.

## Inspect without installing

- [Live Cloud Run graph](https://unspool-398376578726.us-central1.run.app) is a
  sanitized read-only report. Its `/health.json` identifies the currently served
  revision. It is not the local mutable application or a hosted scanning service.
- [External Duo repair diff](https://gitlab.com/gitlab-ai-hackathon/transcend-october-2026/43244671/unspool-vampi-delivery/-/merge_requests/1)
  and [candidate pipeline](https://gitlab.com/gitlab-ai-hackathon/transcend-october-2026/43244671/unspool-vampi-delivery/-/pipelines/2968003131)
  show the actual instructed known-exposure repair. Operator review preceded merge.
- [Synthetic delivery pipeline](https://gitlab.com/gitlab-ai-hackathon/transcend-october-2026/43244671/unspool/-/pipelines/2967584891)
  records the separate bounded hands-off run. Newer deployments may serve newer SHAs.
- [Submission claim/evidence map](SUBMISSION.md), [security review](SECURITY_REVIEW.md)
  and [roadmap](ROADMAP.md) distinguish completed evidence from remaining work.

## Install a pinned reviewed source revision

Choose a new empty working directory. The following revision contains version
0.4.2; this guide's later documentation changes do not affect that package.

```sh
git clone https://gitlab.com/gitlab-ai-hackathon/transcend-october-2026/43244671/unspool.git
cd unspool
git checkout --detach a93bbda29a480b66b9a43024f924d15ee66c634b
python3 -m venv .venv
.venv/bin/python -m pip install --upgrade -r requirements.build.lock
.venv/bin/python -m pip wheel --no-deps --wheel-dir dist .
.venv/bin/python -m pip install -c requirements.lock dist/unspool-0.4.2-py3-none-any.whl
.venv/bin/python -m pip check
```

Retain the source path so the trusted synthetic inputs can be found from an
empty working directory; use the installed interpreter with isolated imports:

```sh
UNSPOOL_SOURCE_DIR="$PWD"
cd /tmp
"$UNSPOOL_SOURCE_DIR/.venv/bin/python" -I \
  "$UNSPOOL_SOURCE_DIR/ci/verify_install.py" \
  --source "$UNSPOOL_SOURCE_DIR" --output /tmp/unspool-judge-installation.json
```

Expected output: `status: PASSED`, version 0.4.2, 37 installed files verified,
three console commands passed, no source-checkout imports, persisted STOP
cancellation and a passing synthetic exposure gate. The JSON also records the
installed dependency inventory. This command was separately exercised in fresh
macOS Python 3.11 and Linux CI Python 3.10/3.12 environments; judge environment
differences can still expose untested issues.

## Inspect the local app and its scope

With the same source-path variable, run the installed app using the committed
trusted synthetic fixture and a fresh data directory:

```sh
"$UNSPOOL_SOURCE_DIR/.venv/bin/python" -I -m unspool \
  --repository "$UNSPOOL_SOURCE_DIR/demo/target" \
  --policy "$UNSPOOL_SOURCE_DIR/demo/policy.yaml" \
  --runtime-manifest "$UNSPOOL_SOURCE_DIR/demo/runtime.yaml" \
  --runtime-backend local --provider-url '' \
  --data-dir /tmp/unspool-judge-demo --port 8080
```

Open `http://127.0.0.1:8080`. The graph and annotation CRUD are local; analysis
snapshots are immutable. Use a different port/data directory if already in use.
Stop with Ctrl-C. This is an explicitly trusted demo: `--runtime-backend local`
provides no sandbox and must not be used for unfamiliar repository code.
No real credentials or customer secrets are needed. Do not expose this local
mutable API publicly or connect it to arbitrary repository URLs.

## Verify failure handling and external evidence

The version's regression suite includes leaking/safe synthetic fixtures,
scope/configuration checks, false health evidence, stale deployment checks,
target locking and cancellation. Run it only against this reviewed source:

```sh
cd "$UNSPOOL_SOURCE_DIR"
.venv/bin/python -m unittest discover -s tests -v
node tests/test_dashboard.cjs
```

Node is required only for the last dashboard check. Tests are regression evidence,
not independent vulnerability counts. The CI test count belongs to its exact SHA.
For actual external HTTP before/after and rollback reproduction, use
[the VAmPI record](benchmarks/vampi/README.md) on a disposable authorized worker.
Those commands require GCP access and can incur usage; public GitLab MR/pipeline
links are available separately. Never deploy the deliberately vulnerable app
publicly or use its database-reset endpoint on persistent/customer storage.

## Real Duo integration prerequisites

Read [ADOPTION.md](ADOPTION.md) for operator configuration, permission boundaries,
review mode, STOP flag, recovery and removal. An existing authorized `glab` login,
an enabled GitLab Duo flow and matching project permissions are required. Do not
reuse the author's credentials or trigger the demo issues merely to browse this
submission. No credential, custom-agent entitlement or unrestricted merge right
is bundled in the package. The public Cloud Run URL does not run this controller.

This guide does not close the incomplete production gates in ROADMAP.md.
