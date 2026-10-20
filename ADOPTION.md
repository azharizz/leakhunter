# Install Unspool for another GitLab project

Version 0.4.0 introduces an operator-configured controller for GitLab.com.
The current execution hosts are Linux/macOS with Python 3.10+ and authenticated
`glab`. These are supported interfaces, not a claim of production certification.
Other language analyzers remain experimental; this controller initially accepts
existing, explicitly allowlisted Python application files only.

## Install outside the analyzed repository

Install the reviewed wheel in a dedicated virtual environment. Do not execute
the controller from an agent-writable or third-party repository checkout.

```sh
python3 -m venv ~/.venvs/unspool
~/.venvs/unspool/bin/pip install -c /path/to/reviewed/requirements.lock /path/to/reviewed/unspool-0.4.0-py3-none-any.whl
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
