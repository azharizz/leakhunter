# Unspool trust model and unresolved risks

Scope: self-hosted GitLab.com controller, explicitly allowed Python application
files, operator-owned credentials/configuration, review mode by default. This
document describes current controls and residual risks, not a certification.

## Assets and authority

The operator's GitLab identity can trigger work and may merge protected targets.
The configured Duo identity proposes a repair under its own permissions. GitLab
decides whether each operation is authorized. The Cloud Run deployment identity
is separate and bound by OIDC to the original project's protected main branch.
The public service serves static reports; the local mutable API is not a shared
tenant service. Policy, verifier, runtime manifest and operator configuration are
trusted inputs. Target source, dependencies, issue text, model output and runtime
output are untrusted inputs and never grant authorization.

## Boundaries and verification

| Boundary / attack | Current control | Evidence / remaining risk |
| --- | --- | --- |
| Issue/model instructions expand the repair | Exact project ID/path binding; full diff allowlist; add/delete/rename and overflow rejection | `test_handoff_config.py`, `test_handoff.py`; semantic malicious code inside an allowed file is still possible |
| Repair changes its own gate | Operator content pins; candidate and baseline pin checks; verifier installed outside checkout | Config tests and VAmPI recorded run; operator must pin every executable verification dependency, including CI includes |
| Wrong/stale revision promoted | Exact MR/diff/pipeline/health SHA; auto mode requires protected fast-forward target and rechecks base | Config tests; review-mode readiness is an observation at a point in time, not permission for a later unchecked merge |
| Missing/failed/unknown jobs treated as success | Mandatory non-optional jobs and positive runtime/case evidence | Handoff tests; the controller trusts the configured CI's evidence contract, not an arbitrary artifact |
| Host file redirection or blocking recovery reads | No-follow, nonblocking opens; descriptor ownership/type/permission checks; regular files only; bounded reads; links rejected | Config/state regression tests; same-user compromise and writable ancestor directories remain outside this file check |
| Duplicate dispatch after lost response | Durable intent before POST; stable marker reconciliation; no mutation replay | State tests; remote journal deletion or a forged marker can cause a stopped/misdirected observation; marker is not a signature |
| Competing local controllers | Nonblocking per-project/target OS lock; private atomic journal | Subprocess kill/restart test; different state directories or machines do not share the lock |
| Application reads worker credentials or reaches services | Docker backend: read-only exported source, no passed secrets, network none, resource limits, dropped capabilities | Controlled Cloud Build drill passed 16 checks under network-none/internal modes and rejected a synthetic credential negative control; see benchmarks/isolation/README.md. Not exhaustive egress/kernel testing; local backend provides no containment |
| Dependency installation executes arbitrary code | Separate dependency build from application execution in external benchmark | Dependency build retains network and Docker builder privilege; it is not a hostile-code sandbox or supply-chain guarantee |
| Application forges worker evidence | Trusted host validates schema and known markers; VAmPI also has a separate-container HTTP probe with no target code/source imports | VAmPI before/after runs recorded in benchmarks/vampi/README.md. General callable runtime still shares a process with target code; hostile code can tamper with it. Do not use it as an adversarial security boundary |
| Public report leaks private source/secrets | Sanitized report publisher; static hosting; synthetic markers only for demos | Publisher tests; full canary audit of prompts/logs/artifacts remains pending |
| Provider receives private code | Provider is explicitly configured, no automatic `.env` loading | Selected source/context can leave the worker. Provider retention/redaction/opt-out qualification is pending; obtain repository-owner authorization |
| Promotion/deploy credentials reused by Duo | Separate identities; controller uses operator login outside flow; GitLab access checks retained | Actual Duo MR creation and operator promotion; cross-project negative authorization drills remain pending |
| Remote interruption falsely reported healthy | GitLab state re-observed; exact deployment revision and mandatory jobs required; operator STOP blocks subsequent API calls and success records | Real MR/evidence-read SIGKILL/resume and scoped staging rollback recorded; local cancellation regression tests pass. In-flight remote cancellation, full merge/deploy crash drills and alerting remain pending |

## Release decisions

The 0.4.6 optional HTTP handoff contract requires source-bound safe case results
and exact plan/probe/app/probe-image/filter-image pins from the operator. Its CI
example uses prebuilt images and a dedicated disposable daemon. Only trusted
operator code can run the host-network NET_ADMIN/NET_RAW filter helper; the app
and probe have neither capability. A live host-listener control and blocked
workload connection are required before app execution. This closes a tested
host-service access path rather than assuming an internal Docker network proves
host isolation. It is not every DNS/egress channel, kernel escape, image-builder
or hostile shared-worker qualification. A cleanup-failure regression with a stub
Docker client proves the actual shell removes success artifacts and exits nonzero;
real Cloud Build records separately qualify the network and HTTP execution.

The separate 0.4.5 JSON HTTP probe observes requests/responses without importing
target code and can run in a separately provisioned probe container. Its canary,
field and functional assertions are declarative and bounded. Actual VAmPI
before/after runs with the same frozen plan/probe are retained in
`benchmarks/vampi/results.generic.json`. This protects that measurement process
from application monkeypatching, given the trusted probe image, host and isolation
configuration. It is not an application launcher, artifact attestation, log/egress
observer or a fix to same-process callable instrumentation. Portable handoff use
still requires a pinned CI adapter binding source/image identity to its report.

Static source ingestion in 0.4.4 uses no-follow, directory-relative opens,
single-link regular files and bounded reads; excluded trees are pruned before
descent. Limits are 1 MiB/file, 32 MiB source total, 2,000 source files, 20,000
visited entries and depth 64. Reproduced pre-fix FIFO hangs in Python and
JavaScript; timeout-bounded regression checks now refuse FIFOs in all five
adapters and revision hashing. Other tests cover source/directory symlink swaps,
hardlinks, post-stat growth and quota refusal. This closes those ingestion paths,
not arbitrary parser CPU/memory denial of service or concurrently hostile host
control. A trusted immutable source snapshot and isolated worker remain required.

Keep external repositories in review mode. A reviewer must inspect both the
application diff and the evidence-producing CI before merge, and recheck the
target/source if time has passed. Existing tests do not establish safety for
actively hostile repositories, private customer data or shared multi-tenant work.
The Python subprocess worker and dependency builder need stronger isolation and
out-of-process measurement before supporting that threat model. A Docker
container alone does not establish it.

The operator controls the host, state directory ancestry, package installation,
GitLab credentials and configuration. An attacker with that same OS identity or
an administrative GitLab role can defeat those controls; Unspool does not claim
to protect against a compromised operator host or project administrator.

Unknown execution, incomplete capture, missing artifacts, permission refusal and
timeout must remain stopped outcomes. Never change policy, tests, permissions or
classification after a repair to make evidence look successful. Publish failures
and separate this document's control descriptions from executed attack results.
