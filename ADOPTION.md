# Install Unspool for another GitLab project

Version 0.4.7 includes the operator-configured controller for GitLab.com, file
boundary hardening and an operator STOP flag (introduced after 0.4.0).
It also rechecks candidate/pipeline/target freshness before review readiness.
The CLI rejects `evaluate --gate` before configuration or execution: detection
accuracy cannot authorize release. Ungated evaluation remains available.
The current execution hosts are Linux/macOS with Python 3.10+ and authenticated
`glab`. These are supported interfaces, not a claim of production certification.
Other language analyzers remain experimental; this controller initially accepts
existing, explicitly allowlisted Python application files only.
Qualification targets CPython 3.10, 3.11 and 3.12; newer interpreters are unverified.
The CI installation matrix is evidence for the checked revisions, not every
framework/dependency combination or a production-certification claim.
The pipeline builds one wheel with pinned tools and a source-commit timestamp,
then passes that exact artifact and checksum to both Python installation jobs.
Each job checks its checksum before and after qualification. `wheel-build.json`
records the source SHA, timestamp, builder interpreter and build tool versions.
CI artifacts have 90-day retention. The [frozen release](RELEASE.md) retains its
wheel, checksums and verification records separately in the package registry.

## Local analysis input limits

Version 0.4.4 bounds source ingestion before parsing or recording an analysis:
at most 1 MiB per source file, 32 MiB of source bytes in total, 2,000 selected
source files, 20,000 visited directory entries and 64 nested directories. These
are enforced input budgets, not measured throughput or CPU/memory guarantees.
An over-budget repository raises an error; no truncated successful result is
returned. Use a deliberately scoped regular-file snapshot for larger inputs.

Internal symlinks, hardlinked source files and special source files are refused.
Directory and file opens use anchored directory descriptors and no-follow flags;
special-file reads are nonblocking and byte limits also apply after opening.
The scanner prunes `.git`, `__pycache__`, `.venv`, `venv` and `node_modules`.
Python also excludes `data`; other adapters exclude `vendor` and `target`.
Excluded content is outside the analysis scope. Revision hashing now uses the
same exclusions, so an old snapshot that included ignored dependency files may
have a different revision identifier after upgrading; rerun analysis and retain
old snapshots as historical records.

This does not sandbox runtime execution, bound all parser/AST computation, or
prevent same-process callable evidence tampering. Keep the worker and reviewed
source snapshot immutable and preserve the runtime restrictions below.

## Independent HTTP acceptance (0.4.5)

`python -m unspool.http_acceptance --base-url http://target:8080 --plan plan.json`
executes an operator-owned JSON plan from a different process/container. Run it
only against an authorized disposable application with synthetic records; the
plan can include mutating requests. It imports no application code and is not an
application launcher or sandbox. Provision a trusted probe image and isolated
app separately, with no target source mount in the probe. Do not expose the local
mutable Unspool server as a remote execution service.

See `benchmarks/vampi/http-plan.json` for an example. Ordered cases specify an
ID, method, origin-relative path, expected status, expected JSON subset and
optional JSON body/headers. Expected objects match their specified fields;
nonempty expected arrays require each specified record to occur, and empty
expected arrays require an empty result. `${nonce}` and `${secret}` are distinct
fresh random values shared across the plan. Response bodies/headers are checked
for configured literal canaries; configured forbidden JSON keys are checked at
every depth. This is not arbitrary taint analysis or proof of all app behavior.

The client rejects redirects, inherited proxies, credential-bearing base URLs,
duplicate/nonfinite JSON, oversized responses and unbounded contract comparison.
Plans are capped at 64 KiB/64 cases; responses at 1 MiB. Startup waits only for
TCP readiness; requests are not retried, including mutations. A failed contract
stops later requests with explicit NOT_RUN records. Output retains hashes and
check outcomes, never raw target bodies, credentials or exception messages.
Exit 0 requires functional and security success. Use a worker/job deadline too;
HTTP request deadlines alone do not bound every DNS/parser/OS operation.

Freeze the probe, plan, application revision/image and CI adapter outside the
repair allowlist. This command reports its plan hash but cannot itself attest
which Git commit/image serves a URL. Before using its result for handoff, a
trusted pinned CI adapter must bind the report to the exact candidate artifact
and produce the configured health evidence. The existing callable runtime still
shares an interpreter with target code; this command does not silently replace it
or make hostile callable execution trustworthy. Logs and outbound application
requests need separate independent observers.

## Bind HTTP reports for handoff (0.4.6)

Enable `http_contract` in the operator handoff JSON to require the independent
HTTP evidence format. For the frozen VAmPI plan, the additional object is:

```json
"http_contract": {
  "plan_sha256": "7defd18b6503b7b33fc73dc0030b506229541d6ce4667011acba863145ca2a24",
  "probe_sha256": "38128a56c844797acf646bca912057f718dd21a4f6521381e5b4a840bac0ea50",
  "probe_image_id": "sha256:541096ae9b05d3b850341b78790e2ed31e94d5aa0ea086933c6ff0c09ffa2e63",
  "application_image_id": "sha256:d4202d21bf6d511c0bdccc180b437c33f2e4db28092435d6e503a23f9ce82a18",
  "host_filter_image_id": "sha256:d2dc198f7d839eae26b5a9cb0e7cdc4e2c97d9cb4ea66dbeb0a4c0c7f0b165f8",
  "case_ids": ["initialize-disposable-db", "register-canary", "public-list", "lookup", "debug"]
}
```

This is a fragment to add to an existing configuration, not a standalone JSON
file. Use the hashes, ordered case IDs and Linux image ID for your reviewed plan
and probe. The plan hash uses `json.dumps(plan, allow_nan=False)` before random
placeholder replacement, not the raw JSON file's bytes. The controller requires
the exact source SHA, expected plan/probe/image pins, all cases passing, separate
container IDs, snapshot identity and a recorded host-isolation check. A true
health flag alone is insufficient. Old configurations without this object retain
their existing journal digest and behavior; they do not gain this protection.
Adding/changing it deliberately creates a new configuration identity. Retain and
reconcile prior runs instead of editing their journals to force a match.

The trusted CI job runs `python -m unspool.http_evidence --help` for the binding
interface. It verifies the report against the plan and projects only known safe
metadata, then atomically writes `evidence.json` and `health.json`. It removes
previous successful artifacts before validation. Its image/source/isolation
arguments must come from trusted orchestration, not application output or an
issue. These records are trusted-job evidence, not cryptographic attestations.

`benchmarks/vampi/ci-independent.sh` is a VAmPI orchestration example for a
**dedicated disposable Docker daemon**. It exports the exact checked-out Git SHA,
uses pre-provisioned immutable local image IDs in `UNSPOOL_APP_IMAGE`,
`UNSPOOL_PROBE_IMAGE` and `UNSPOOL_FILTER_IMAGE`, and performs no target dependency
installation. Provision/review those images separately. The trusted filter image
must provide `iptables`; the trusted probe image must provide Python 3.11+.
Both application and probe run without host credentials/socket, source in the
probe, public ports, writable roots or capabilities. Only the operator-controlled
filter helper gets host networking and NET_ADMIN/NET_RAW to install a temporary
host INPUT rule. Do not run that example on a shared or production Docker daemon.

Before application startup, a synthetic host listener is reachable from a trusted
host-network control, unreachable from the workload network after filtering, and
still reachable from the control. Internal DNS aliases remain available while
external forwarding is pointed at container loopback. This tests a host-service
boundary, not every egress mechanism or kernel escape. Failed verification or
cleanup removes successful artifacts and stops the job. A cleanup-failure unit
test exercises the real shell script with a stub Docker client; real Cloud Build
runs separately qualify the network/HTTP behavior.

For another application, provide operator-owned startup/storage/image settings,
an appropriate frozen HTTP plan and pinned CI orchestration. The generic probe,
adapter and controller require no Unspool source edits. Protect that CI code,
plan and dependency contracts outside the agent's write allowlist. The existing
GitLab VAmPI project still requires migration from its earlier CI harness; the
Cloud Build qualification alone does not claim that migration is complete.

## Install outside the analyzed repository

Install the reviewed wheel in a dedicated virtual environment. Do not execute
the controller from an agent-writable or third-party repository checkout.

```sh
python3 -m venv ~/.venvs/unspool
~/.venvs/unspool/bin/python -m pip install --upgrade -r /path/to/reviewed/requirements.build.lock
~/.venvs/unspool/bin/pip install -c /path/to/reviewed/requirements.lock /path/to/reviewed/unspool-0.4.7-py3-none-any.whl
~/.venvs/unspool/bin/unspool-handoff --help
glab auth status --hostname gitlab.com
```

`unspool` and the previous `leakhunter` CLI/imports remain compatible. Create
an operator-owned configuration outside the target repository. Start with
`config/handoff.demo.json` as a schema example, replacing the project ID/path,
target branch, trigger identity, allowed application paths, actual verification
job names, artifact paths and deployment jobs. Do not leave the demo project ID.
`config/handoff.vampi-review.json` is an external-fork preflight example, not
evidence that its trigger, pipeline or repair integration is already ready.

The schema rejects unknown fields, credentials, duplicate keys, non-normalized
paths, wildcards, source-path escapes and group/world-writable config files.
Configuration must be an operator-owned regular file of at most 64 KiB; symbolic
links, hard links and special files are rejected. Copy the example as an ordinary
file into the operator's private configuration directory.
No configuration key can execute shell commands. There is no automatic discovery
of configuration from issue text or an untrusted repository.

## Required verifier contract

The target's trusted verification setup must produce actual executed evidence,
not a model's self-assessment. Configure mandatory CI jobs with failure blocking
the pipeline. The evidence job must retain:

- `evidence.json` with `gate.passed: true`, `runtime.status: COMPLETED`,
  `runtime.passed: true`, and a nonempty list of cases with `passed: true`.
- `public/health.json` equal to `{"status":"ok","commit":"<full source SHA>","verified":true}`.

Paths/job names can differ when specified in the operator configuration. Pin
the policy and executable runtime manifest under `protected_files` as exact
repository-relative paths mapped to SHA-256 content digests. Calculate these
from the independently reviewed baseline, not from the proposed repair:

```sh
sha256sum policy.yaml runtime.yaml
```

The controller checks pinned contracts on the target during preflight and on
the candidate before declaring it ready. The server's project ID and full path
must both match configuration, and the observed diff must match the MR SHA.

This does not make an arbitrary repository's CI trustworthy. Keep verification
and promotion code pinned and outside the repair agent's write scope. Do not
run unfamiliar application code with deployment credentials or use a laptop
subprocess as a sandbox. See SECURITY.md and the remaining roadmap gates.

## Read-only preflight and review mode

```sh
~/.venvs/unspool/bin/unspool-handoff --config /operator/handoff.json --preflight
~/.venvs/unspool/bin/unspool-handoff --config /operator/handoff.json --merge-request 12
```

Preflight only reads project, target branch, allowlisted files and pinned
contracts. It does not trigger Duo, create state, merge, or deploy. Passing it
does not prove trigger availability, worker isolation, CI correctness or effective
deployment permissions; those need a complete execution test.

Omitting `mode` selects `review`. A passing candidate returns `READY_FOR_REVIEW`
and never merges. An already merged MR returns `ALREADY_MERGED`, which is an
observation, not a new verification result. Review mode is the default for adopters.
Before returning readiness, the controller rereads the MR and target branch. A
changed source, pipeline, base or target stops verification; rebase/retest and
rerun rather than treating the earlier result as current. Readiness describes
the observed revision only and cannot reserve a branch against later changes.

The controller can trigger an issue with `--issue <iid>`. It uses the configured
trigger username and stable `<branch_prefix>repair-<iid>` branch. The operator must
have authorized that issue and configured an actually available Duo flow. Source
comments and issue instructions cannot enlarge the allowlist or pinned contracts.

## Automatic mode is explicit and restricted

`mode: auto` requires at least two pinned contracts, mandatory deployment/smoke
jobs, and a protected **fast-forward-only** target project. Immediately before
merge, the MR's tested base must still equal the target. The merge is pinned to
the verified source SHA; fast-forward-only enforcement prevents a target update
from being silently incorporated in an untested merge. Rebase and reverify when
the target moves. If the group cannot provide these guarantees, retain review mode.

Auto mode is not a bypass for required approvals or missing permission. The
controller stops when GitLab refuses a merge. Do not grant the repair agent a
different identity or more privileges to defeat a boundary. Configure promotion
under the team's approved identity and target-project permissions.

The legacy `--project 87860005` command remains restricted to the original
synthetic demo. It is not the portable adopter path and does not enforce all
new configuration guarantees. Use `--config` for real repositories.

## Recovery and concurrent controllers

The CLI stores private atomic records under
`$XDG_STATE_HOME/unspool/handoff`, or `~/.local/state/unspool/handoff`.
An optional `--state-dir` must be a real private operator-owned directory (0700),
outside the target checkout. Records contain project/intent identifiers, config
digest, stages and observed SHAs/job IDs, not tokens or application payloads.
State and lock files must be private regular files owned by the operator; links,
shared permissions and special files are rejected without blocking on reads.

One controller holds a lock for each project/target. A second controller fails
explicitly instead of racing a promotion; other projects can run independently.
Resume the same command with the same configuration and state directory. Do not
delete state to get past an uncertain trigger or a configuration mismatch.

Before dispatch, the controller durably records intent and includes a stable
marker in its GitLab note. If the POST response is lost, a resume reconciles the
marker against GitLab. It does not blindly repeat a mutation. Unresolved delivery
stops for operator investigation rather than starting duplicate Duo work.
Transient GET failures receive three bounded attempts; mutations are never
automatically replayed. GitLab remains authoritative for MR and pipeline state.

Keep the controller running until it returns a terminal result. A stopped local
process does not cancel a Duo session or remote deployment already running.
Remote cancellation, rollback drills, full crash/concurrency validation and
operational alerting remain tracked in ROADMAP.md.

## Operator stop and cancellation

Create an entry named `STOP` in the controller's private state directory to stop
all handoff controllers using that directory:

```sh
touch ~/.local/state/unspool/handoff/STOP
```

Use your configured `--state-dir`/`XDG_STATE_HOME` location when different. Any
entry with that name, including a broken symlink, means stop; no content is read.
The controller checks before API calls and read retries, and before recording a
successful outcome. It records `CANCELED` and exits 130. Ctrl-C also records
cancellation when it reaches the CLI's handler. Cancellation preserves the intent,
source and configuration records; it never deletes state or creates permission.
Read-only `--preflight` does not use run state and is not affected by this flag.

An already dispatched API request, Duo session, merge or deployment may complete.
The flag cannot undo it, cancel a remote pipeline, or stop controllers on other
machines/state directories. Inspect GitLab and cloud state, cancel remote work
through their authorized controls if necessary, and keep the flag until you have
reconciled the result. The operator owns escalation; no automatic alert service
is configured. In-flight requests and current polling sleeps can delay observation.

To resume, deliberately remove only that `STOP` entry after review, then run the
original command with the original state directory/configuration. The controller
re-observes GitLab and reuses existing work. Do not delete its journal to restart.

## Upgrade, removal, and credentials

Upgrade by installing a reviewed wheel into a new virtual environment and checking
its version and preflight before switching. Preserve the old environment and state
for rollback. A configuration change requires deliberate reconciliation of an
existing intent; it must not silently change the scope of running work.

To uninstall, stop the local controller and review/cancel any live GitLab sessions
and pipelines through GitLab. Remove only this integration's triggers/configuration
and cloud identity bindings. Retain run evidence under the team's retention policy;
do not delete shared credentials or projects. The controller creates no credentials.
