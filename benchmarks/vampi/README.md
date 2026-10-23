# External VAmPI validation — known intentional exposure

Upstream: [erev0s/VAmPI](https://github.com/erev0s/VAmPI), MIT, copyright 2020 erev0s.
Validation fork: [azharizz/unspool-vampi-validation](https://gitlab.com/azharizz/unspool-vampi-validation).
Pinned upstream source: `f16052dce83f05847133ec98f01c5193a41de7d8`.
The upstream MIT notice is preserved in the imported repository.

The author documents excessive exposure at `/users/v1/_debug`. This benchmark
tests that published behavior with a synthetic canary over actual HTTP. It is
an externally authored intentional security lab, not a customer production system,
an independent human evaluation or a new vulnerability discovery. The later
instructed repair and controller verification are recorded separately below.

## Observed baseline, 20 October 2026

[Cloud Build d4c0faaf-67f6-444a-b9d6-7a33cff8ee12](https://console.cloud.google.com/cloud-build/builds;region=us-central1/d4c0faaf-67f6-444a-b9d6-7a33cff8ee12?project=398376578726)
successfully reproduced the expected vulnerability:

- Create a disposable dummy database and register a canary user: HTTP 200.
- Public user list preserves that username and excludes its canary password.
- Public user lookup preserves that username and excludes its canary password.
- Debug user response includes that canary password: **security failed**.

The probe reports `http_functionality_passed: true`,
`secret_observed_at_http_response: true`, `security_passed: false`, and
`expected_behavior_reproduced: true`. The successful benchmark job means the
vulnerability was reproduced, not that the application passed security validation.

The application container runs as UID/GID 10001, with no network, no published
ports, read-only source/root filesystem, dropped capabilities, no privilege
escalation, bounded CPU/memory/processes, and ephemeral database storage. Only
loopback HTTP inside that container is used. Cloud build/dependency download
stages require network access; they are separate from application execution.
The application receives no mounted credentials, host Docker socket or deployment
token. This is evidence for these execution settings, not a complete isolation audit.

Two earlier runs failed during harness startup, before security evaluation:
`673b82f6-d6eb-4568-b270-578e783fea08` (Python import path) and
`c1ffcf22-1850-4ae7-9f0d-c3ba255b34f1` (upstream circular-import bootstrap).
Those failures remain setup errors/unknown security outcomes, not false negatives.
Only the harness import/bootstrap changed; the pinned upstream application did not.

## Reproduce

With an authorized GCP account and the documented dedicated build service account:

```sh
gcloud builds submit benchmarks/vampi \
  --config=benchmarks/vampi/cloudbuild.yaml \
  --project=project-df38a01c-6abb-4bc3-9c1 --region=us-central1 \
  --service-account=projects/project-df38a01c-6abb-4bc3-9c1/serviceAccounts/unspool-build@project-df38a01c-6abb-4bc3-9c1.iam.gserviceaccount.com \
  --gcs-source-staging-dir=gs://project-df38a01c-6abb-4bc3-9c1-unspool-build/source
```

`cloudbuild.yaml` contains the isolation options and exact upstream checkout.
Do not expose the deliberately vulnerable application to the public internet.
`probe.py --expect-fixed` defines the candidate acceptance check: public identity
behavior must remain, and debug responses must exclude passwords/admin flags.
The candidate run is recorded below. The upstream dependency tree includes
intentionally old packages and has not been claimed safe for production.

## Observed instructed repair

Duo session `9754951` created [MR !1](https://gitlab.com/gitlab-ai-hackathon/transcend-october-2026/43244671/unspool-vampi-delivery/-/merge_requests/1)
at `c146bd1b9ee9fbe2730c316675de1fa7e55f0fa1`. Its only changed file is
`api_views/users.py`; the debug response now projects username/email.
[Pipeline 2968003131](https://gitlab.com/gitlab-ai-hackathon/transcend-october-2026/43244671/unspool-vampi-delivery/-/pipelines/2968003131)
passed syntax and the fixed-behavior HTTP acceptance. The harness was pinned at
Unspool `61b884e723012c8ede7308a4aa49f5e5cd512e56`, before the repair ran.

The installed Unspool 0.4.0 console command, run from `/tmp` outside the checkout,
returned `READY_FOR_REVIEW` after checking the diff, exact source/pipeline,
mandatory jobs, artifacts and pinned CI/instructions with
`config/handoff.vampi-delivery.json`. No automatic merge was performed.
This is one instructed known-exposure repair, not independent discovery or a
measured general repair success rate. After operator review and fast-forward
promotion, [post-merge pipeline 2968031105](https://gitlab.com/gitlab-ai-hackathon/transcend-october-2026/43244671/unspool-vampi-delivery/-/pipelines/2968031105)
passed both checks on the same repaired SHA. The upstream has no automated Python test
suite in the pinned tree; syntax and our frozen HTTP acceptance do not prove all
other application behavior correct. Staging and rollback checks remain open.

The earlier GitLab baseline pipeline `2967877801` blocked on acceptance and
produced no success evidence, but discarded diagnostics make its exact cause
unknown. Only the separate Cloud Build baseline above confirms the actual leak.
Comparison with an ungated agent and wider cases remains pending.

## Pinned repair acceptance harness

`ci-verify.sh` exports the exact candidate revision without Git metadata, builds
dependencies separately, and runs the frozen fixed-behavior HTTP probe with the
same container restrictions. It passes no CI variables or credentials into the
application container. `report.py` runs outside that container and only adapts
an exact positive result into the handoff evidence contract, recording the source
SHA and resolved image ID. This is HTTP acceptance of a known exposure; it does
not represent an Unspool analyzer discovery.

The validation repository must fetch these files from a pinned Unspool commit,
and pin its CI/agent instructions in the operator configuration. Its repair may
change only `api_views/users.py`. GitLab's hosted runner/Docker service and the
probe's application process are not a verified sandbox for actively malicious
repositories. This experiment does not close the hostile-code isolation gate.
No raw application output, database or source archive is published as an artifact.

## Separate-container HTTP verification

### Source-bound CI runner (0.4.6)

`ci-independent.sh` binds the independent report to the exact checked-out commit,
all archived file content, plan/probe and app/probe/filter image identities, and
distinct container IDs. Verification uses preloaded image IDs and installs no
application dependencies. A temporary host INPUT filter and a live host-listener
control test the workload-to-host boundary before the application starts. Only
the trusted filter helper has NET_ADMIN/NET_RAW with host networking. This example
requires a dedicated disposable Docker daemon, not a shared developer/production
host. Cleanup failure removes successful artifacts and fails the job.

| Run | Outcome |
| --- | --- |
| [Current fixed-source worker](https://console.cloud.google.com/cloud-build/builds;region=us-central1/8c5a61ad-eb7d-4c57-a726-e196f5ec05a8?project=398376578726) | SUCCESS; host controls and five HTTP requests passed; exact-source evidence/health produced |
| [Vulnerable-source worker](https://console.cloud.google.com/cloud-build/builds;region=us-central1/7d80c7cf-19ee-4629-a329-8b1ce12bd7af?project=398376578726) | FAILURE as intended; HTTP functionality completed, canary observed, security false |

`results.independent.json` retains the actual evidence and stopped-run diagnostic;
both were compared directly with completed logs. Earlier positive qualifications
are also listed rather than discarded. The installed 0.4.6 validator accepted
the current real record against explicit expected pins and refused a different
candidate SHA. This is one known lab, not broad accuracy or kernel/egress proof.
The existing GitLab project's older CI has not yet been migrated to this runner.

For a clean Cloud Build context, copy these framework files and directories
without Git metadata or credentials:

```sh
UNSPOOL_BOUND_CONTEXT="$(mktemp -d)"
mkdir -p "$UNSPOOL_BOUND_CONTEXT/framework/unspool" \
  "$UNSPOOL_BOUND_CONTEXT/framework/unspool/analyzers" \
  "$UNSPOOL_BOUND_CONTEXT/framework/benchmarks/vampi"
cp unspool/__init__.py unspool/http_acceptance.py unspool/http_evidence.py \
  "$UNSPOOL_BOUND_CONTEXT/framework/unspool/"
cp unspool/analyzers/sources.py "$UNSPOOL_BOUND_CONTEXT/framework/unspool/analyzers/"
cp benchmarks/vampi/ci-independent.sh benchmarks/vampi/http-plan.json \
  "$UNSPOOL_BOUND_CONTEXT/framework/benchmarks/vampi/"
cp benchmarks/vampi/independent.cloudbuild.yaml "$UNSPOOL_BOUND_CONTEXT/"
```

Submit that directory with `independent.cloudbuild.yaml` and the earlier documented
project/region/service-account/staging-bucket flags. The example pulls the retained
private staging artifact through the authorized build identity; other projects
must provision their own reviewed runtime image and access. Its source is hidden
by the read-only exact-candidate source mount. For the vulnerable run add
`--substitutions=_SOURCE_SHA=f16052dce83f05847133ec98f01c5193a41de7d8` and expect
a failed job with the stopped diagnostic, not a green security gate. The generic
adapter/controller contract and dedicated-worker requirements are in ADOPTION.md.

### Original independent probe and generic plan replay

The original standalone probe remains unchanged below. Version 0.4.5 adds a
packaged reusable probe, `python -m unspool.http_acceptance`, plus the frozen
`http-plan.json` for this application. `generic_probe.py` is a benchmark adapter
that checks the expected vulnerable/fixed outcome; it never rewrites a failed
baseline gate to true. `results.generic.json` retains exact reports from both
new runs and was compared directly with the completed build logs.

| Generic-probe run | Application revision | Result |
| --- | --- | --- |
| [Baseline build](https://console.cloud.google.com/cloud-build/builds;region=us-central1/cf3e8c15-8d7a-4ebb-af2b-becaa8e038e3?project=398376578726) | `f16052dce83f05847133ec98f01c5193a41de7d8` | Five HTTP requests functionally pass; debug leaks the canary/password/admin; security gate is false |
| [Repaired build](https://console.cloud.google.com/cloud-build/builds;region=us-central1/7cde97e2-61cd-4b14-9e3b-6a2c1e2a2ec7?project=398376578726) | `c146bd1b9ee9fbe2730c316675de1fa7e55f0fa1` | Same five functional requests and security assertions pass |

These are one known-exposure lab's before/after checks, not five vulnerabilities,
another agent repair or broad accuracy evidence. Cloud logs require authorized
GCP access; the retained sanitized JSON and source are public. Probe SHA-256:
`38128a56c844797acf646bca912057f718dd21a4f6521381e5b4a840bac0ea50`;
raw plan SHA-256:
`78857c2283281879c0fe605bbc1783834121b720e9bbdd7ea07efbd9441b2a87`.
The report's `plan_sha256` hashes the normalized JSON, so it differs from the raw
file hash. Both runs used probe image
`sha256:541096ae9b05d3b850341b78790e2ed31e94d5aa0ea086933c6ff0c09ffa2e63`.

To reproduce, from the Unspool repository root create a clean upload context
containing only these six trusted public files:

```sh
UNSPOOL_HTTP_CONTEXT="$(mktemp -d)"
cp unspool/http_acceptance.py "$UNSPOOL_HTTP_CONTEXT/acceptance.py"
cp benchmarks/vampi/Dockerfile benchmarks/vampi/generic.sh \
  benchmarks/vampi/generic_probe.py benchmarks/vampi/http-plan.json \
  benchmarks/vampi/generic.cloudbuild.yaml "$UNSPOOL_HTTP_CONTEXT/"
```

Use the earlier documented `gcloud builds submit` project/region/service-account
and staging-bucket settings, but submit that directory with its
`generic.cloudbuild.yaml`. Defaults check the fixed revision. For the baseline
add `--substitutions=_SOURCE_SHA=f16052dce83f05847133ec98f01c5193a41de7d8,_EXPECT=--expect-vulnerable`.
The dedicated disposable worker runs app and probe in separate containers, with
only the application receiving its source. The application has no public port,
passed credentials or Docker socket. Dependency-image construction still uses
network and builder privileges; this is not a qualification of hostile dependency
installation. A generic HTTP report alone cannot attest which commit serves a URL;
retain the trusted orchestration/image/source binding as this benchmark does.

`http_probe.py` uses only the standard library and imports no target code.
`sidecar.sh` runs the app and probe in separate containers/filesystems on an
internal-only network, without a public port, shared process namespace, passed
credentials or Docker socket. Only the app receives the source mount; only the
probe receives its read-only measurement code. Both have read-only roots,
non-root users, dropped capabilities, process/memory/CPU limits and no privilege
escalation. The app cannot monkeypatch the probe's Python interpreter. Redirects
and oversized responses are rejected. Each execution registers a fresh random
synthetic username/password and checks username/email preservation, rather than
allowing an empty debug response to pass.

| Execution | Source SHA | Observed HTTP result | Application image ID |
| --- | --- | --- | --- |
| [Baseline Cloud Build](https://console.cloud.google.com/cloud-build/builds;region=us-central1/be497e7b-d0d2-4c3d-b181-54fc4edfb220?project=398376578726) | `f16052dce83f05847133ec98f01c5193a41de7d8` | Public functionality passes; canary leaks; security fails as expected | `sha256:b786e7522cf11d4cab78104ad68a44a9e168b7b5a085fbee88fa019f12596cf0` |
| [Repaired Cloud Build](https://console.cloud.google.com/cloud-build/builds;region=us-central1/3493cb5f-f753-4b19-8a0e-7e9c6ef538fe?project=398376578726) | `c146bd1b9ee9fbe2730c316675de1fa7e55f0fa1` | Public functionality passes; canary absent; password/admin fields absent | `sha256:89e2a47f9c51c47bffcc1dcb507c5264c5a0acaae46742a9e730e31a6006814f` |

Both used probe image
`sha256:541096ae9b05d3b850341b78790e2ed31e94d5aa0ea086933c6ff0c09ffa2e63`.
They fetched dependencies separately; mutable image tags/transitive package
resolution mean these IDs identify the observed runs, not a reproducible build
guarantee. Cloud console logs require authorized project access; the public
GitLab candidate/post-merge CI links above are separate evidence for judges.
No customer data or public vulnerable service was involved.

Reproduce with the earlier `gcloud builds submit` command, replacing its config
with `benchmarks/vampi/sidecar.cloudbuild.yaml`. Its defaults check the repaired
SHA. For the baseline add
`--substitutions=_SOURCE_SHA=f16052dce83f05847133ec98f01c5193a41de7d8,_EXPECT=--expect-vulnerable`.
The script assumes Cloud Build's `/workspace` and a disposable dedicated Docker
daemon per build; its container names are not for concurrent use on a shared
daemon. Runtime output is bounded/sanitized in the probe; app logs are disabled.

These runs improve the measurement boundary for this benchmark. They do not
replace the general callable runtime, prove a container/daemon is secure against
hostile code, or establish detection/repair accuracy across other applications.
Active malicious-fixture, metadata/egress and dependency-build isolation tests
remain outstanding; do not close those roadmap gates from Docker flags alone.

## Disposable staging and rollback evidence

[Cloud Build ff4898a1-6efe-427d-85ba-b91747d35202](https://console.cloud.google.com/cloud-build/builds;region=us-central1/ff4898a1-6efe-427d-85ba-b91747d35202?project=398376578726)
successfully exercised `staging.cloudbuild.yaml` and `staging.sh`:

1. Export the exact repaired source without Git metadata and build it into an
   application image containing its MIT notice and source revision label.
2. Push/retain the image in the private registry and resolve its immutable digest.
3. Start a deployment on an internal-only Docker network and pass the separate
   HTTP probe with a fresh synthetic user and canary.
4. Start an intentionally broken candidate configuration that exits 17. Verify
   it has stopped, the original healthy container is unchanged/running, and the
   original deployment still passes HTTP acceptance.
5. Intentionally remove that healthy deployment, restore a new container from
   the retained digest, and repeat HTTP acceptance successfully.

Retained artifact (also confirmed by the Artifact Registry API):

```text
us-central1-docker.pkg.dev/project-df38a01c-6abb-4bc3-9c1/unspool/vampi-staging@sha256:2b779dff0e4ff46af33966c4ae8372c9d8cbe7f440145cdf846cb6d8be3267dd
```

Source label: `c146bd1b9ee9fbe2730c316675de1fa7e55f0fa1`.
Probe image: `sha256:541096ae9b05d3b850341b78790e2ed31e94d5aa0ea086933c6ff0c09ffa2e63`.
The three HTTP checks each passed public identity and secret-exposure acceptance.
The build's final record reports failed-candidate rejection, healthy preservation
and rollback verification. No public vulnerable application was deployed; cleanup
removed all workload containers/network. The private image remains retained for
reproduction/rollback, accessible only through authorized registry permissions.

Reproduce with the earlier Cloud Build command using config
`benchmarks/vampi/staging.cloudbuild.yaml`. The fixed source SHA is explicit in
that file; a new release requires an intentionally reviewed source/label update.
Use a dedicated disposable worker, not a shared daemon. The current script is
specific to this validation application and is not a generic production deployer.

This tests rollback of a startup configuration failure and recreation of the
application artifact. It does **not** test database restoration/migrations,
zero-downtime routing, distributed rollback, Cloud Run application traffic shifts
or the local handoff controller crashing during deployment. The synthetic
database is intentionally ephemeral and recreated by the acceptance probe.
Do not use `/createdb` on any non-disposable storage. Dependency build isolation,
broader regression coverage and general runtime tamper resistance remain open.
