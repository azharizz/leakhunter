# Unspool: evidence-driven roadmap to submission and production

Prepared 20 October 2026, Asia/Jakarta. This is a plan, not a claim that the work
below is complete. No checklist item is satisfied merely because code exists,
a test count increased, a cloud URL works, or an agent says it succeeded.

## Decision and intended first product

### CLI safety correction — 21 October

A wider branch audit found three old commits outside GitLab main. Their alternate
integration is not needed by the current handoff. Ported the missing CLI safety
fix: evaluation accuracy, even perfect detection of an exposed secret, must not
authorize release. `evaluate --gate` and serving with `--gate` now exit 2 before
configuration, state creation or target execution. Ungated evaluation remains.
The regression failed on the old code and passed after the fix. All 127 local
Python tests and dashboard checks passed. Installed-wheel verification now checks
the rejection through both `unspool` and compatible `leakhunter` commands.
The 0.4.7 package source is `722f3955bb44c270b24f248b9046f0f26df93a76`.
Pipeline `2969187062` passed all checks. The identical CI-built wheel passed
Linux Python 3.10/3.12 and fresh macOS 3.11 installation, including the new
pre-execution refusal. [RELEASE.md](RELEASE.md) and the judge guide pin its
source/checksum; retained submission checks identify the final main/report SHA.

The previously local checklist audit below is reconciled and included in this
change. Production gaps remain unchecked; video, submission, personal eligibility
declarations and continuing hosting ownership remain author responsibilities.

### Submission freeze — user scope amendment, 21 October

The user explicitly narrowed the immediate work to the five submission essentials.
The unfinished production gates below remain future qualification work; they are
not prerequisites for presenting this release as an evaluated prototype.

- MR !22 was reviewed and merged at `05bbefc6e936d7efab8f0a7b10aeb04e77742ee3`.
  Release pipeline `2969101179` passed all checks and report delivery.
- Package 0.4.6 is frozen at that source with its canonical CI wheel, retained
  package-registry downloads, verification bundle and release tag. The same wheel
  passed clean Linux 3.10/3.12 and macOS 3.11 installation checks, including
  40 file matches, three commands, persisted STOP cancellation and the synthetic
  exposure gate. The fresh local regression run passed 126 tests.
- README, the judge guide, submission text and [release record](RELEASE.md) identify
  that package and separate it from historical evidence. The historical external
  GitLab verifier has not silently gained the new opt-in HTTP contract.
- Public GitLab project and MIT detection were checked without credentials.
  Cloud Run served the release SHA; remote CI job `17328074132` verified Pages for
  that SHA. Local Jamf redirection is not counted as fallback health.
- Path B was reviewed against Section 4 of the current official rules: an original
  project date before October 5 is not required. The actual October 19 source,
  October 20 MIT/import/automation and October 21 publication chronology are
  disclosed in [SUBMISSION.md](SUBMISSION.md). Path B / Supervised is the
  recommended classification, not a claimed organizer ruling.

The author owns the public video, personal attestations and Devpost submission.
The maintainer owns ongoing availability through the expected November 16
announcement. Billing is enabled now; future trial credits/expiry and uptime are
not guaranteed, and no automated billing monitor is claimed. Catalog, more
hosting, broad accuracy evaluation and production qualification are deferred.
Older execution logs/checklists below describe their recorded revision and date;
this amendment records the current submission scope and handoff.

Current verdict: working prototype with real GitLab Duo, CI, bounded automatic
promotion, and public static-report delivery. Not established as a production
security product or a general repair service. The synthetic delivery runs
normalized display names; the later external VAmPI run repaired an instructed,
published exposure. Neither discovered an unknown real-world vulnerability.
Regression test counts are not counts of independent vulnerability cases.

First production candidate: a versioned, self-hosted GitLab integration for
selected Python repositories. Each adopting team owns its workers, repository
credentials, policies, and evidence. Start in report/MR-only mode with human
approval. Gradually enable narrowly defined automatic changes in disposable
staging applications. Preserve `leakhunter` import compatibility.

Do not start by building a shared SaaS that clones arbitrary customer code.
Multiple people can use a packaged integration in separate projects without
sharing code, credentials, or mutable state. Shared SaaS is a later product with
additional authorization, isolation, privacy, tenancy, and operating obligations.

Production readiness must always name a scope: supported languages/frameworks,
repository sizes, policy semantics, deployment targets, users, and permitted
automatic changes. Passing a scoped release gate never proves all code safe.

### Solo validation amendment — user instruction, 20 October

The project is built solo. Recruiting two independent teams is no longer a
prerequisite for this goal. Replace installer/pilot requirements with the solo
qualification gates below. Preserve the distinction between independent evidence
sources and an independent person: automated review or a second environment is
not external customer acceptance. Do not claim a human-reviewed certification.

Use fresh installations in separate environments and projects; upstream-owned
test suites and published vulnerability provenance; acceptance cases frozen
before repair; held-out checks unavailable to the repair runtime; recorded
baseline comparisons; static/dependency/security checks; and reproducible
recovery/isolation/load drills. Evaluate all outcomes and retain failed runs.
External pilot feedback remains valuable future evidence, not a dependency that
stops the solo engineering work.

## Established evidence and remaining uncertainty

### Execution log — source-bound HTTP CI and host boundary, 21 October

Classification: **progress**, production qualification incomplete. MR !21 passed
pipeline `2968954866`, then merged at `8de167220454824c8e9ee59260c7660d53eaf2f7`.
Both installed Linux jobs qualified the same 0.4.5 wheel, SHA-256
`605bc5530897ccd8e3679791fd12cd70a73f2fd9dea17a5bfcddd2410a30baaf`.

Added a 0.4.6 evidence adapter and optional operator `http_contract`: exact plan,
probe, all three application/probe/privileged-filter image IDs and ordered case
IDs are checked against the candidate SHA and complete safe case records.
Source snapshot and distinct container identities are retained. Older config
journal digests remain unchanged when the optional contract is absent; they do
not silently gain this stronger evidence mode. Trusted pinned orchestration is
still required; the records are not cryptographic attestations.

The VAmPI CI example now uses pre-provisioned immutable images and performs no
target dependency installation. App/probe containers receive no host credentials,
socket, writable root or capabilities. A trusted privileged network helper installs
a temporary host INPUT filter. A live host listener is reachable from a trusted
host-network control, unreachable from the workload network, and still reachable
from the control afterward. Both participants retain internal service DNS while
external forwarding is pointed at loopback. Cleanup failure revokes success.

Initial worker builds `54f7ca79-0867-4540-ae2d-48f1016f4328` and
`77a73b22-adb4-4a38-913e-35fb7b6102c5` succeeded. After explicit image-pin
validation changes, current build `8c5a61ad-eb7d-4c57-a726-e196f5ec05a8`
also succeeded with all five repaired-app requests passing and source-bound
health. Vulnerable revision build `7d80c7cf-19ee-4629-a329-8b1ce12bd7af`
failed as intended: HTTP functionality completed, a canary was observed and
security was false. Full sanitized evidence is in benchmarks/vampi/results.independent.json.
These were deliberate code-revision qualifications, not restarted observations.

All 126 local tests passed, including recorded-leak refusal, wrong revision/image/
probe/plan/case refusal, compatibility and a real-shell cleanup-failure test with
a stub Docker client. A clean installed macOS Python 3.11.9 0.4.6 wheel verified
40 files, commands/cancellation/synthetic exposure outside the checkout. Its SHA-256
is `51d67f00aedbd616e3c8bb2784309f4b04cb06876dec1cfb4363755d227b72f2`.
The installed validator accepted the current real Cloud Build evidence against
explicit expected pins and rejected a different candidate revision. The source
audit remained at 14 LOW/6 MEDIUM, no HIGH/errors; selected dependency pins had
no reported advisories. Linux 0.4.6 qualification and actual GitLab project CI
migration remain open. So do broader runtime/evaluation/recovery/operating gates.
Initial MR !22 pipeline `2969066322` stopped on the compatibility test because
the checked-in configuration template had shared-write permissions in the CI
checkout. The secure loader correctly refused it. Updated only the test setup
to copy that template into an owned mode-0600 operator file before checking the
historical digest; the loader and permission policy are unchanged. Its six
evidence tests pass locally; the replacement CI pipeline must still pass.

### Execution log — shared wheel and reusable HTTP verification, 21 October

Classification: **progress**, production qualification incomplete. MR !20 passed
pipeline `2968892353` and merged at `28b76baadf62f39fd0bc3e382cf040020ed212a4`.
Build job `17326418809` produced wheel SHA-256
`09190410380e87f8918c8726d37abe3057bb188b4b803de7a40c9fc8bd9d0965`.
Python 3.10.22 job `17326418813` and Python 3.12.15 job `17326418814`
qualified that same artifact outside the checkout, verified all 38 files and
retained identical checksum/build metadata. Its source was `2406e510`, epoch
`1792520080`, builder Python 3.12.15 and pinned pip/setuptools/wheel/packaging.
This closes the separately-built-wheel ambiguity, not permanent release or all
cross-platform reproducible builds.

Implemented 0.4.5 with a reusable declarative JSON HTTP probe. Unlike the callable
worker, it imports no target code; isolation/source binding must be supplied by
trusted CI. Added an independently mounted VAmPI plan/benchmark adapter so the
new packaged probe can be exercised against both pinned real revisions without
changing the earlier benchmark or application. All 120 tests passed, including
the retained original HTTP tests and new separate-client-process cases. The
loader-specific FIFO check passes after interpreter startup; the initial host
process launch with a preexisting FIFO argument timed out without interpreter
diagnostics, so that observation is not a successful CLI-loader test.

Froze probe/plan in commit `d3e801b` before new Cloud Build executions. Baseline
build `cf3e8c15-8d7a-4ebb-af2b-becaa8e038e3` reproduced the canary in the debug
HTTP response and forbidden password/admin keys: functional checks passed but
the security gate remained false. Repaired build
`7cde97e2-61cd-4b14-9e3b-6a2c1e2a2ec7` passed all five functional requests and
security checks with the same frozen plan/probe, on a separate internal-network
container. Both build jobs succeeded because their benchmark expectations were
reproduced; the baseline did not become a passing security result. Full sanitized
reports and source/app/probe identities are in benchmarks/vampi/results.generic.json.
The five requests are one known-exposure application exercise, not five independent
vulnerabilities. Logs were retrieved with `gcloud builds log` after one direct
Cloud Logging observation timed out; neither build was restarted.

A clean macOS Python 3.11.9 installation of 0.4.5 verified 39 files, three
commands, STOP cancellation and synthetic exposure checks outside the checkout.
Wheel SHA-256: `d5093e979fb275e1f28a17f9de573e3f6f034967ed2d455a1f2aa89e2f8c58d9`.
Local source/dependency audit retained 14 LOW/6 MEDIUM warnings, no HIGH/errors
and no reported advisories in selected pins. Linux qualification and integration
of this new probe into portable handoff CI remain required.
General callable evidence tampering, trusted dependency build, broader evaluation,
full remote recovery and operating qualification remain open gates.

### Execution log — bounded repository source ingestion, 21 October

Classification: **progress**, production qualification incomplete. MR !18 passed
pipeline `2968840400` and merged at `d45e521d1b6290f8f70e28c6efc614f44ae8edf5`.
Reproduced blocking reads in both Python and JavaScript analysis using real
source-named FIFOs; each pre-fix child exceeded two seconds and was killed.
Version 0.4.4 replaces analyzer and local revision-hash traversal with one bounded
source scanner. Directory descriptors/no-follow opens refuse source and
directory link swaps; nonblocking file opens and descriptor checks refuse special
files and hardlinks. Reads remain bounded when a file grows after stat.

Declared/enforced input budgets are 1 MiB/file, 32 MiB source total, 2,000 source
files, 20,000 visited entries and depth 64; excluded dependency trees are pruned
before descent. Over-budget or unsupported input stops the whole analysis,
rather than yielding a truncated successful result. Revision hashing now uses
the same language-specific exclusions as analysis; ADOPTION.md documents the
effect on historical identities. These input budgets were chosen before their
tests, and are not parser CPU/memory or throughput guarantees.

All 117 regression tests passed, including timeout-bounded FIFO refusal across
all five adapters/revision hashing, file/directory replacement, hardlinks,
quota boundaries and post-stat growth. A clean macOS Python 3.11.9 installation
of 0.4.4 verified 38 installed files, three commands, STOP cancellation and the
synthetic exposure gate outside the checkout. Wheel SHA-256:
`236655a773f08b7c2d60f275e3149b97d5d55af0abe7755a11414eca089c9ca6`.
The installed CLI refused a real source FIFO in 0.133 seconds, exited 2 with no
success output and left zero analysis snapshots in its database. This single
timing is not a latency guarantee. Local audit still reports zero advisories in
the selected dependency pins, 14 LOW/6 MEDIUM source warnings and no HIGH/errors.

The installed wheel reran the original ten-case, three-repository static manifest
without relabeling: TP 5 / TN 3 / unknown 2 / FP 0 / FN 0 / execution errors 0,
with zero parse errors. `benchmarks/external/results.bounded-ingestion.json`
retains exact analyzer/source-reader/manifest identities and case outcomes. This
is a repeated selected feasibility set, not new independent accuracy evidence.
MR !19 passed pipeline `2968875317` and merged at
`9a656c7e1578ac0c7bc735d7e1f7981186ccebe0`. Both Linux jobs passed the 38-file
installed checks: Python 3.10.22 job `17326283669`, wheel
`a76914eb1775c11d2efdede7c9efeef29816d7912a8e7b642dbb2ea129977ad4`;
Python 3.12.15 job `17326283670`, wheel
`5398f609836188cf88a06197e6ecb384d0102c8e733262a6f1031fbb9329b03c`.
Their 44 ZIP members had identical payloads but six differing ZIP timestamps;
they were separately built artifacts, not one wheel qualified twice. Preparing
a single CI build artifact, checksummed before/after each installation and shared
by both matrix jobs; its build timestamp is anchored to the source commit and
build metadata is retained. This pipeline change still requires remote validation.
GitLab's project CI lint accepted it with zero errors/warnings. Two local builds
with pinned tools, build isolation disabled and the same fixed timestamp
(`1792515600`) produced identical wheel bytes, SHA-256
`48171ffeb46846f5803904e8e3ee2caa7ddbebe102b07f57765f47c924951208`.
That is repeatability in one environment, not a cross-platform reproducible-build
claim or a permanent published release.

Separately exercised the installed scanner with unpatched release limits: 2,000
empty source files, 32 files totaling exactly 32 MiB, 20,000 non-source entries
and a directory at depth 64 were accepted; adding one file/byte/entry/directory
respectively raised the expected quota error. These are ingestion fixtures,
not representative parsing/application-load or concurrency qualification.
General callable/runtime evidence
tampering, dependency execution, parser resource isolation, full recovery,
broader evaluation and declared operational qualification remain open.

### Execution log — review revision freshness, 21 October

Classification: **progress**, production qualification incomplete. MR !16 passed
pipeline `2968817064` and merged at `bc9a965fbc21edef8b9a3fbf1d7f6a5d53809505`.
Found that configured review mode could return READY_FOR_REVIEW after its target
had advanced: only automatic mode rechecked the target. Version 0.4.3 now rereads
the MR after contract/evidence checks and refuses changed source/base/pipeline
identity or status. Both modes then require the current target to equal the
verified base; automatic mode also rechecks protection. These are observations,
not a branch reservation; GitLab's fast-forward/SHA enforcement remains required
for automatic merge. The legacy synthetic path is unchanged.

The 110-test suite passed before one additional protection-removal test; all nine
configuration tests then passed, including fourteen revision-race subcases and
protection removal after preflight. A fresh macOS Python 3.11.9 installation of
0.4.3 verified 37 installed files, three commands, STOP cancellation and synthetic
exposure checks outside the checkout. Wheel SHA-256:
`1b6f162d6b2e76d1b3ea044780f10908cce9674252629e355a159aaae15eda70`.
The installed controller then read the real existing VAmPI issue 2/MR 2 through
the mutation-blocking observation wrapper: 23 real GET requests, zero writes,
READY_FOR_REVIEW at source `951960c9d85ea874a5f9e0248c42b83f9751d499`,
pipeline `2968122599`, unchanged operator configuration digest
`888b3d9f4b78d985b3cfde7bea3f9550f06119c0116af3779065b6a18dedae5b`.
This is one live read-only replay, not a new repair or live race injection.
MR !17 passed pipeline `2968830722` with 111 tests, dashboard/security/exposure
checks and both Linux installed-wheel jobs, then merged at
`faeb5010fb279018ecd208cec454894f1f25ab84`. Jobs `17325971078` (Python
3.10.22) and `17325971079` (Python 3.12.15) each verified the same 37-file,
three-command, cancellation/exposure contract outside the source checkout. Both
built wheel SHA-256
`c359959500b3f0f1cdac518905549a4c263f7934edf5d2df99252f78341e98f0`.
The complete remaining roadmap is still required. Judge instructions now pin
that reviewed 0.4.3 source; older 0.4.2 evaluation results remain labeled as such.

### Execution log — submission draft and public-access audit, 21 October

Classification: **progress**, submission/production readiness not established.
MR !15 passed pipeline `2968792097` and merged at
`a93bbda29a480b66b9a43024f924d15ee66c634b`. Prepared SUBMISSION.md with the
description, exact claim/evidence links, dependencies, honest provenance,
supervised versus synthetic hands-off distinction, author video outline and
remaining decisions. JUDGE_GUIDE.md provides pinned installed-wheel/local-demo
steps without triggering remote automation.

Unauthenticated HTTP checks returned public GitLab project/MR/pipeline/license
data and a healthy Cloud Run revision `7d36585ff1c7d19872c119c131ba1577424b79bd`.
Gitleaks 8.30.1 (official release checksum verified) scanned the two original
commits with zero findings; manual review of credential-related code found
environment-variable handling, detection patterns and synthetic fixtures. Both
original commits are retained in GitLab main.
The history starts 19 October, with MIT added 20 October. Path B classification
remains unresolved; publication alone does not establish eligibility. No history
was altered. Pages redirected to the local
Jamf block page, so that request does not establish judge availability. The
production/evaluation/security gates remain in force; the draft does not narrow
the active goal. Official submission requirements were rechecked on 21 October.

### Execution log — initial frozen external static evaluation, 21 October

Classification: **progress**, evaluation gate incomplete. MR !14 passed pipeline
`2968297644` (including security audit and installed 0.4.2 Python 3.10/3.12 jobs)
and merged at `7d36585ff1c7d19872c119c131ba1577424b79bd`. Main delivery
pipeline `2968309102` also passed. The installed Linux artifacts each verified
37 files, three commands, durable cancellation and synthetic exposure checks.

Froze ten source-labeled cases across three independently authored MIT security
labs (VAmPI, DVGA, PyGoat) in commit `f0ed588`, before the first analyzer run.
Eight cases have binary policy-flow labels; two are explicitly unknown. The first
run and the repeated installed-wheel 0.4.2 run both yielded TP 5 / FP 0 / TN 3 /
FN 0 / unknown 2 / execution errors 0. No target code was executed or imported.
All 126 Python files parsed, but unresolved calls were 129/362/869 respectively;
DVGA/PyGoat also had 7/1 unsupported constructs. Those limits remain visible.
The labels are solo/source-derived and selected with knowledge of the analyzer;
this is not held-out, customer-representative, runtime vulnerability proof or a
production precision/recall estimate. No repairs or model calls occurred here.
Full case records, exact upstream revisions, file hashes, analysis times and
reproduction are in benchmarks/external/. A further installed repeat after
qualified-callable existence validation retained the same outcomes without label
changes; typo/missing callables cannot become false safe results. The full suite
passed 108 tests, then both evaluation-specific tests passed after that additional
target-validation test. The 20-positive/20-negative floor,
runtime/repair/ungated-agent comparisons and broad accuracy gate remain open.

### Execution log — source/dependency security audit and fixes

Classification: **progress**, further qualification required. MR !13 passed
pipeline `2968216148` and merged at `637ccae42d7d869ad14514a81ca5a62105354cc9`.
Both installed 0.4.1 Linux checks passed outside the checkout: Python 3.10.22
job `17321131582`, wheel hash `52a1e63b4390dc8bcfa410c6c03a2fd400ed46ddecbff67177bb8738238fedb1`;
Python 3.12.15 job `17321131583`, wheel hash
`3046e839c220ff839b8a0d0a5083f56f71b1c9dba2743060b64f25eecb2f3c9f`.
Each verified 37 installed files, all console commands, cancellation and exposure.

Pinned pip-audit 2.10.1 and Bandit 1.9.4 found no reported advisories in six
runtime pins, but auditing the actual installed environment found vulnerable
bootstrap pip/setuptools versions. Added reviewed bootstrap/build pins and
installation/CI upgrade steps; all ten selected runtime/build versions then
audited without reported advisories. The upgraded installed environment had no
reported advisories among registry packages, while Unspool itself was explicitly
not found on PyPI and unassessed by that tool.

Bandit initially reported 14 LOW/8 MEDIUM/0 HIGH, with no scan errors. Fixed
arbitrary URL/redirect acceptance in smoke checks, bounded health/API JSON reads,
refused token-backed GitLab redirects, and required a real boolean verification
flag before accepting health evidence. Retained/triaged 14 LOW and 6 MEDIUM
warnings with no source suppression. Added CI security auditing that blocks
advisories, scan errors and HIGH/unknown-severity results while retaining complete
JSON reports. Version 0.4.2 captures these fixes. The 106-test suite passed,
and the subsequently added SQL allowlist/parameterization regression also passed
with all four knowledge tests. A fresh Python 3.11.9 environment installed the
0.4.2 wheel outside the checkout and passed all 37-file/CLI/cancellation/exposure
checks. Wheel hash:
`bdcfa568a40932883fa2101baba27653a985d9d3ea3c0ec837d22cd2ea8c7a15`.
Linux matrix/CI qualification for 0.4.2 is still required.
See SECURITY_REVIEW.md for findings, limitations and reproduction.

### Execution log — installed wheel version and Python boundaries

Classification: **progress**, qualification pending. MR !12 passed pipeline
`2968181565` and merged at `b100d7cc74cbc2a7b726924aed9ce99eebea1db0`.
Prepared version 0.4.1 to distinguish file-boundary/cancellation hardening from
the earlier installed 0.4.0 artifact. Added blocking CI matrix jobs for
Python 3.10/3.12 slim Linux images. Each builds/installs a wheel, checks dependency
consistency, runs outside the checkout with isolated imports, compares installed
Python/UI assets byte-for-byte, exercises all console commands, verifies durable
STOP cancellation and executes the trusted synthetic exposure workflow. Jobs
retain the wheel/hash, dependency inventory and installation result. Both jobs
later passed pipeline `2968216148`, as recorded above. A fresh macOS Python 3.11.9 virtual environment passed the
same installed check from `/tmp`: 37 Python/UI files matched, all three console
commands worked, STOP cancellation persisted and the synthetic exposure gate
passed. Local wheel SHA-256:
`eb9f22aef32ff0e9c1e1a1d7a63c218843a8ab5402e50d24957b09d4979c2a23`.
This is solo installation evidence, not independent adoption or external
application accuracy. CI-built wheel identities may differ and must be recorded.

### Execution log — operator kill switch and distinct cancellation

Classification: **progress**. MR !11 passed pipeline `2968150405` and merged at
`77c6c3126c56980a419d98800949b611eabc8f21`.
Added the operator-controlled `STOP` entry in the private state directory. The
default CLI checks it before API requests/retries and successful terminal state
writes, prevents new trigger/merge/completion requests, records `CANCELED` and
exits 130. Ctrl-C is recorded as cancellation rather than a generic stopped
failure. Tests verify zero requests at startup, stop between read and mutation,
blocked trigger/success writes, stop between retry attempts, and a broken-symlink
flag without following its target. The full 101-test suite passed; the final
additional Ctrl-C regression also passed with all five cancellation tests.
A real CLI invocation with the STOP flag returned CANCELED/exit 130 and
persisted CANCELED in its private journal without entering remote observation.
ADOPTION.md documents operator ownership, reconciliation and deliberate resumption.
This cannot recall an in-flight operation or cancel remote work; remote
cancellation/alerting and the remaining failure drills are still open.

### Execution log — real GitLab controller interruption

Classification: **progress**. MR !10 passed pipeline `2968113480`
and merged at `2b779cd176643dd13f2ea2b6dd10b07f3d99a338`.
Created an explicitly labeled comment-only recovery MR !2 in the isolated VAmPI
project, with stable branch `unspool/repair-2`, source
`951960c9d85ea874a5f9e0248c42b83f9751d499` and passing real pipeline
`2968122599`. A read-only wrapper invokes the installed 0.4.0 controller against
real GitLab responses; all writes are refused locally. The first run reached
the MR-read boundary, then was actually SIGKILLed (exit 137). Its private journal
retained `VERIFYING`, MR 2 and the pinned configuration digest. A second actual
SIGKILL after the evidence artifact read retained the same intent. A normal
resume returned `READY_FOR_REVIEW` for the same SHA/pipeline after 21 real reads,
zero writes, and a competing duplicate invocation was rejected by the target
lock before API dispatch. GitLab still showed one open MR, the original target
SHA and unchanged issue system-note IDs, with no new Duo trigger. All 97 local
tests pass. The unwrapped installed CLI replay also returned `READY_FOR_REVIEW`
for the same SHA/pipeline and retained that final state in the original journal.
This is a controlled restart exercise, not another security repair or Duo run.
See benchmarks/recovery/README.md.

### Execution log — disposable application staging and rollback

Classification: **progress**. MR !9 passed pipeline
`2968097344` and merged at `2d8c784200fe68c5777d657934c5b8d61a35e89b`.
Added a staging drill that builds the repaired VAmPI source into an immutable
application image (rather than mounting a checkout), retains it in the private
Artifact Registry, and runs only on an internal Docker network without public
ports or passed credentials. It verifies the healthy app, rejects an intentionally
broken startup configuration before touching the healthy container, rechecks that
healthy container, then deliberately removes it and recreates it from the retained
digest before repeating HTTP acceptance. Database state is synthetic/ephemeral;
this does not claim data backup/restore or a production Cloud Run rollback.
Cloud Build `ff4898a1-6efe-427d-85ba-b91747d35202` completed successfully.
All three independent HTTP checks passed: initial healthy deployment, healthy
deployment after candidate rejection, and recreation after intentional removal.
The failed candidate exited 17; the original healthy container ID stayed unchanged
until the deliberate outage, and the restored container had a new ID. The retained
application artifact is
`unspool/vampi-staging@sha256:2b779dff0e4ff46af33966c4ae8372c9d8cbe7f440145cdf846cb6d8be3267dd`
in the authorized GCP project's private us-central1 Artifact Registry. Its source
label is the repaired `c146bd1b9ee9fbe2730c316675de1fa7e55f0fa1`; its digest
was separately confirmed through the registry API. See benchmarks/vampi/README.md.
This closes the real target's disposable staging exercise, not the controller's
full remote fault/recovery or production data restoration requirements.

### Execution log — controlled isolation drill

Classification: **progress**. MR !8 passed pipeline `2968079417` and merged at
`9dce9999d423885d9940ad2fc72316ac86ba1cb5`.
Cloud Build `07483223-985b-423b-805c-c6892f0c17d6` ran a controlled attack
script inside disposable workload containers with network-none and internal-only
networking. All 15 initial checks passed in both cases: non-root/capability/
privilege settings, write denial, hidden host canary/credential paths/socket and
environment, blocked tested metadata/external TCP, and observed cgroup limits.
Follow-up Cloud Build `b99654ca-27aa-4fa1-9411-d8b500637029` passed all 16
checks in both modes, including bounded temporary disk. A deliberately passed
synthetic credential caused failure specifically on credential environment
exposure, and an external inspector confirmed the expected rejection and other
positive checks. Runtime image ID:
`sha256:541096ae9b05d3b850341b78790e2ed31e94d5aa0ea086933c6ff0c09ffa2e63`.
See benchmarks/isolation/README.md. The hostile-code isolation gate remains open:
this is no kernel escape audit or exhaustive egress/dependency-build test, and
does not fix the general callable runtime's same-process measurement risk.

### Execution log — separate HTTP observation boundary

Classification: **progress**, incomplete isolation qualification. MR !7 passed
final pipeline `2968058406` and merged at
`e65463a150dcb88bd79598736fe8f4ac3c1474b4`.
Added a second VAmPI acceptance client that imports no target code. The target
and HTTP client run in different containers with separate filesystems/processes,
an internal-only Docker network, no published ports, no passed credentials,
resource limits and read-only source/probe mounts. Only the application receives
the source; only the probe receives its measurement code. This aims to close the
same-process monkeypatch path for this benchmark, not the general runtime.
Two HTTP client tests passed: safe/leaking behavior distinguished, and leak,
empty result, forbidden admin field, redirect and oversized response rejected.
Cloud Build `3493cb5f-f753-4b19-8a0e-7e9c6ef538fe` passed the repaired
application HTTP checks at `c146bd1b9ee9fbe2730c316675de1fa7e55f0fa1`, with
`security_passed: true`. Baseline build `be497e7b-d0d2-4c3d-b181-54fc4edfb220`
reproduced the original exposure at `f16052dce83f05847133ec98f01c5193a41de7d8`,
with `security_passed: false`. Both preserved the tested public identity behavior
and used the same probe image ID. See benchmarks/vampi/README.md for identities
and reproduction. All 95 local tests pass. These are separate-container executions
of one security-lab application; in-worker malicious-fixture/network isolation
checks and general-runtime tamper resistance remain unproven.

### Execution log — local recovery and file boundary hardening

Classification: **progress**. Closed unsafe configuration/state reads: symlinks,
hard links, special files, shared permissions and wrong ownership are rejected
using the opened descriptor; reads are nonblocking and bounded. State remains
private and atomic. Added regression cases and an actual child-process kill test:
while a child holds the project/target lock a competing intent is rejected;
after SIGKILL the lock can be acquired and the saved trigger intent survives.
All 21 handoff/config/state tests and the full 93-test local suite pass.
Remote pipeline `2968050565` passed the hardening revision
`4e9fba9aedc19c2a5d6d4278501a934699f8c42b`; a subsequent two-line change
also enforces the 64 KiB configuration limit before UTF-8 decoding, with its
configuration tests passing locally and final remote CI still required.
This proves the local OS-lock/intent
case, not remote crash recovery or a distributed lock. Added THREAT_MODEL.md with
explicit unresolved worker-evidence tampering, dependency execution and provider
privacy risks. The full adversarial isolation and remote recovery gates remain open.

### Execution log — external acceptance integration

Classification: **progress**, incomplete qualification. Created a second isolated
validation project, `87865932` (`unspool-vampi-delivery`), with original VAmPI
history at `f16052dce83f05847133ec98f01c5193a41de7d8`, a protected `master`,
and fast-forward merges. Added a pinned HTTP acceptance
CI harness and strict evidence adapter with a regression test. It exports source
without Git credentials, runs the application without passed CI credentials or
external network, and keeps verification outside the permitted repair diff.
The external repair now has direct evidence:

- Duo session `9754951` produced [VAmPI MR !1](https://gitlab.com/gitlab-ai-hackathon/transcend-october-2026/43244671/unspool-vampi-delivery/-/merge_requests/1).
  Its complete diff changes only `api_views/users.py`, projecting username/email
  instead of returning password/admin fields. Candidate SHA:
  `c146bd1b9ee9fbe2730c316675de1fa7e55f0fa1`.
- [Candidate pipeline 2968003131](https://gitlab.com/gitlab-ai-hackathon/transcend-october-2026/43244671/unspool-vampi-delivery/-/pipelines/2968003131)
  passed application syntax and the frozen loopback HTTP acceptance probe. Job
  `17319543552` recorded image ID
  `sha256:49bcaf51146af53baa498a2c0bce009f9957f4f074257c3be9502a5bbf03177d`.
- The separately installed 0.4.0 CLI, run outside the checkout from `/tmp`,
  returned `READY_FOR_REVIEW` for this exact SHA and pipeline. Configuration
  digest: `888b3d9f4b78d985b3cfde7bea3f9550f06119c0116af3779065b6a18dedae5b`.
  It verified the full diff, mandatory jobs, exact health evidence and pinned
  CI/agent instructions; it performed no merge. See config/handoff.vampi-delivery.json.
- Baseline GitLab pipeline `2967877801` failed acceptance and produced no success
  evidence. Its raw diagnostics were discarded, so the exact failure cause is
  unknown; do not count it as a confirmed leak detection. The separate Cloud Build
  baseline below is the confirmed HTTP leak reproduction.

This establishes one instructed known-exposure repair and review handoff, not an
analyzer discovery, broad accuracy measurement or completed isolation audit.
After review, the operator merged the external MR using the existing authorized
GitLab login. Protected `master` now points to the tested candidate SHA without a
new merge commit. [Post-merge pipeline 2968031105](https://gitlab.com/gitlab-ai-hackathon/transcend-october-2026/43244671/unspool-vampi-delivery/-/pipelines/2968031105)
passed syntax and fixed-behavior HTTP acceptance at that same SHA; no public
deployment is claimed. The full local suite passes 90 tests. Staging/rollback and broader
evaluation remain pending.

### Execution log — 20 October, first implementation goal turn

Classification: **progress**. The goal remains active; production readiness is
not established. These are partial gate results, not a replacement for the full
objective or the solo qualification requirements below.

- Added 0.4.0 operator-owned JSON configuration and read-only preflight for
  GitLab.com. Project ID/path binding, exact application paths, pinned contracts,
  strict schema and review-only defaults are implemented. Automatic mode requires
  a protected fast-forward-only target and stops on a changed base.
- Added private atomic intent records, a per-project/target lock, bounded retries
  for transient reads, and marker reconciliation for a lost trigger response.
  Mutations are not automatically replayed. Unit failure/restart tests pass;
  real remote crash/concurrency drills are still pending.
- The full local suite passes **89 Python tests**, plus dashboard checks. Counts
  remain regression tests, not independently labeled vulnerability examples.
- MR !6 merged at `f67ed2a6d4514554d677dd7979d6095a9857b421`.
  [Pipeline 2967835951](https://gitlab.com/gitlab-ai-hackathon/transcend-october-2026/43244671/unspool/-/pipelines/2967835951)
  passed Python tests, dashboard checks, exposure verification, Cloud Run delivery
  and the production smoke job. This validates that revision's report delivery;
  it does not establish repair accuracy on external applications.
- Built a 0.4.0 wheel and installed it into a fresh Python 3.11 virtual environment.
  Its installed console command, run from `/tmp` outside the source checkout,
  passed live preflight against `azharizz/unspool-vampi-validation` without editing
  Unspool source. This is maintainer-run portability evidence, not an independent
  installer or pilot. Other declared Python-version boundaries remain unverified.
- Imported the MIT-licensed external VAmPI project into that dedicated validation
  repository, preserving upstream revision
  `f16052dce83f05847133ec98f01c5193a41de7d8`. Added a no-public-listener HTTP probe
  for its author-documented exposure. It is an intentionally vulnerable external
  security lab, not a production customer deployment or unknown-vulnerability claim.
- The isolated VAmPI HTTP baseline now reproduces the published debug exposure:
  public lookup/list functionality passes, the debug HTTP response leaks the
  synthetic canary, and the report explicitly says `security_passed: false`.
  Cloud Build `d4c0faaf-67f6-444a-b9d6-7a33cff8ee12` is the execution record.
  Two earlier harness-startup failures are retained as setup errors; no upstream
  code changed. See benchmarks/vampi/README.md. Integration into Unspool's detector,
  candidate repair and comparative evaluation are not yet complete.
- Added ADOPTION.md, SECURITY.md, sample configurations and a pinned known
  dependency set. Threat-model verification, independent review, worker isolation
  evidence, full recovery drills, deployment/rollback proof for a repaired target,
  real-world evaluation, baseline comparison and pilot acceptance remain open.

Next: extend external application verification and real repair evidence, then
complete the remaining clean-environment and failure drills. Do not mark an
entire gate complete from these partial checks.

| Area | Established | Not established |
| --- | --- | --- |
| Platform integration | Actual Duo sessions, real MRs, verified merge, Cloud Run and Pages delivery | Reliable operation across other GitLab groups and permission models |
| Security checks | Synthetic marker capture, safe/leaking fixture checks, bounded verification machinery | Independent accuracy on representative applications and unseen vulnerabilities |
| Deployment | Public sanitized report with exact-revision smoke checks | Deployment and functional verification of a repaired real application |
| Autonomy | Fresh bounded issue-to-report runs without intermediate intervention | General autonomous remediation or safe execution of adversarial repositories |
| Product access | Local CLI/UI, local CRUD, public read-only report | Hosted multi-user CRUD or cross-tenant access controls |
| Operations | Working deployment jobs and local polling controller | Durable recovery, concurrency guarantees, rollback drills, sustained service objectives |

## Checklist audit — 21 October 2026

Reconciled the checklist with the execution records, current source, adoption and
security documents, retained benchmark results, and read-only GitLab/public URL
checks. `[x]` means the stated scoped deliverable has evidence; it does not mean
the entire gate or production qualification is complete. Compound items are split
where implementation is finished but broader validation is still missing. Earlier
execution logs retain the status at their execution time; use this checklist for
current remaining work.

Accepted baseline before the CLI safety patch: release 0.4.6, source
`05bbefc6e936d7efab8f0a7b10aeb04e77742ee3`, qualified in Linux Python
3.10/3.12 and macOS 3.11 with 40 installed files and the same retained wheel.
Final documentation/report delivery at `2ae0687dbd78d1d145a42a4342ded90c94d96070`
passed pipeline `2969146642`. The retained
[0.4.6 submission checks](https://gitlab.com/api/v4/projects/87860005/packages/generic/unspool/0.4.6/submission-checks.json)
record 18 successful anonymous checks, actual graph CRUD with unchanged snapshot,
and an installed external-controller replay with 23 GETs / zero writes.
The optional HTTP binding exists; migration of the historical external GitLab
verifier remains future production work.

These are point-in-time checks, not availability guarantees through judging.
Path B / Supervised is recommended on the disclosed chronology and current rules;
organizers decide eligibility. The session page and raw job-trace API are not
anonymous evidence sources; public pipeline metadata and retained records are.

| Area | Completed evidence | Still required |
| --- | --- | --- |
| Installation and portability | Retained versioned wheel, validated configuration/preflight, clean macOS/Linux installs, real external review-controller run, optional HTTP binding | Reusable adopter CI migration, complete permissions matrix, qualification across more frameworks/projects |
| Security value | Real external Duo MR, HTTP baseline/fix, staging failure/recreation drill, ten-case static set across three repositories | Upstream regressions, inaccessible held-out checks, 20-positive/20-negative floor, ungated-agent comparison |
| Trust boundaries | Pinned contracts, diff/SHA checks, source bounds, controlled isolation drill, separate HTTP probe | General callable tamper resistance, dependency-build containment, complete identity/privacy/adversarial qualification |
| Recovery | Durable intent, local target lock, bounded reads, STOP/Ctrl-C, real MR/evidence-read crash recovery | Remaining remote crash points, full concurrency/failure matrix, remote cancellation and alerting |
| Submission material | Public source/original, live static report, pinned judge guide, submission text/evidence map, verified patch package, public retained records and documented Path B basis | Video, personal attestations, submission and ongoing hosting belong to the author |

No complete production gate is inferred from this audit. Shared SaaS and Catalog
publication remain optional; neither is required for a self-hosted integration or
an honest submission.

## Gate 0 — confirm the claims and submission basis

- [x] Write the supported-use statement: initially selected Python services,
  specified sinks and policy semantics, report/MR mode, no universal security claim.
- [x] Label other language adapters experimental until each has its own execution,
  detection, and repair evidence. Parsing a language is not equivalent to securing it.
- [x] Preserve original source history, MIT notices and attribution. The original
  project commit was dated 19 October 2026; do not imply an older project history.
- [x] Review Path B against the actual history and current rules; disclose source,
  MIT/import/automation and publication dates. Evidence: [SUBMISSION.md](SUBMISSION.md).
  The rules do not require a source date before October 5. Path B / Supervised is
  recommended; no organizer ruling or guaranteed eligibility is claimed.
- [x] Record actual additions, dates, model/provider dependencies, local controller
  requirements, and what the live public URL does and does not run.
  Evidence: [submission draft/evidence map](SUBMISSION.md), [handoff](HANDOFF.md)
  and [adoption guide](ADOPTION.md); unknown underlying Duo model version is disclosed.

Exit: every public claim maps to evidence or is marked planned/experimental.
Owner: product maintainer. For solo qualification, retain the frozen inputs,
unmodified upstream expectations, automated review results and reproducible logs.
External human review is not yet obtained and must not be implied.

## Gate 1 — make a second repository work without source edits to Unspool

- [x] Replace demo-specific controller assumptions with a validated operator-owned
  project configuration: project/namespace, protected target, branch convention,
  issue trigger identity, required jobs, allowed paths, policy/manifest identities,
  polling/time limits and required deployment jobs. Evidence: `HandoffConfig`,
  read-only preflight, configuration tests and `config/handoff.*.json`.
- [ ] Add the remaining operator cost budgets and explicit deployment/rollback
  configuration; declaring required job names alone does not implement these.
- [x] Bind that configuration to a version and authorized project. An issue,
  model output, repository file, or supplied URL must not enlarge permissions.
  Keep the current synthetic repair boundary until an explicitly reviewed change
  introduces the reusable mechanism; never relax it to make a repair pass.
  Evidence: project ID/path checks, configuration digest, exact diff allowlist and
  target/candidate contract pins; the external VAmPI configuration is separate.
- [x] Build/install a versioned wheel with pinned runtime/bootstrap dependencies,
  sample configuration, uninstall/upgrade instructions and non-mutating preflight.
  Evidence: [ADOPTION.md](ADOPTION.md), lockfiles and successful installed-wheel CI.
- [x] Retain the release wheel, checksums and verification records in the package
  registry with a release link, independently of 90-day CI artifact expiry.
  Evidence: [release record](RELEASE.md); hosting still needs maintainer ownership.
- [ ] Finish reusable adopter CI templates/migration and the complete permission
  matrix. The working project and benchmark CI do not establish this full deliverable.
- [x] Verify the installed artifact from a clean environment, not PYTHONPATH into
  the development checkout. Record exact dependency and container identities.
  Evidence: macOS Python 3.11 and Linux 3.10/3.12 installation records; MR !20/!21
  qualify one checksummed wheel across both Linux versions and retain inventories.
- [x] Exercise an installed controller on a different authorized repository without
  editing Unspool source. Evidence: VAmPI MR !1 review acceptance with installed
  0.4.0, and installed 0.4.3 MR !2 replay with 23 GETs / zero writes; see
  [recovery records](benchmarks/recovery/README.md).
- [x] Exercise declared Python interpreter boundaries in clean installations:
  macOS 3.11, Linux 3.10/3.12. This establishes those installation checks only.
- [ ] Qualify the final released artifact across the intended external framework/
  dependency combinations and projects. Historical controller replays, interpreter
  checks and a static three-repository set do not cover arbitrary applications.
- [ ] Confirm a separate project's identity cannot trigger work, read private evidence or deploy changes
  in the original project. Do not copy the maintainer's credentials into their setup.

Exit: repeatable clean installations in at least two environments/projects, with installation notes,
observed duration, permission checks, and a complete evidence bundle.

## Gate 2 — establish real security value independently

- [x] Select an authorized, realistically structured application with a confirmed
  exposure defect and an independently defined expected safe behavior. Prefer a
  maintained MIT project or a consented internal application in an isolated copy.
  Record upstream revision, license, dependencies, vulnerability provenance and scope.
  Evidence: [VAmPI records](benchmarks/vampi/README.md), upstream `f16052dc`,
  MIT notices and published debug exposure. It is a security lab, not a maintained
  production customer deployment or representative proof for every repository.
- [x] Reproduce the defect before repair using a harmless canary and a real
  application boundary such as HTTP. Never probe unrelated live systems or use
  customer secrets. Disclose sensitive new findings privately to the owner.
- [x] Separate configured-source tests, detection of known vulnerabilities, and
  discovery of previously unknown vulnerabilities. A supplied secret-field selector
  or explicit repair instruction is not evidence of independent discovery.
  Evidence: [SUBMISSION.md](SUBMISSION.md) and benchmark limitations explicitly
  distinguish the synthetic run, instructed VAmPI repair and selected static set.
- [x] Freeze the original VAmPI security/functional acceptance contract before its
  Duo repair. Candidate CI uses the pinned harness; baseline and repaired source
  revisions and outcomes are retained. The later generic plan was frozen before
  its own before/after replays, not before the earlier agent repair.
- [ ] Add genuinely held-out checks inaccessible to the repair agent. A public
  pinned probe protects write scope but does not prove test secrecy. Do not tune
  policy/labels after failures and still call the result held-out.
- [x] Produce the bounded real Duo repair MR and independently reproduce the
  vulnerable/fixed HTTP behavior. Evidence: VAmPI session `9754951`, MR !1,
  candidate/post-merge CI and separate-container results, including
  [generic probe records](benchmarks/vampi/results.generic.json).
- [x] Analyze the pinned external source revisions and retain static coverage and
  findings. Evidence: [three-repository evaluation](benchmarks/external/README.md).
  This later static analysis is not evidence that the analyzer discovered the
  earlier instructed repair before the agent ran.
- [ ] Run the application's own unmodified regression suite, in addition to the
  independent HTTP cases, and retain baseline/candidate regression comparisons.
- [x] Exercise a disposable staging deployment of the actual repaired application.
  Demonstrate the vulnerable request is now blocked/redacted and legitimate
  requests still work. The graph report is supporting evidence, not that application.
- [x] Build an initial static evaluation across three independently authored MIT
  repositories, including safe and unknown cases. Evidence: VAmPI/DVGA/PyGoat,
  ten frozen cases, TP 5 / TN 3 / unknown 2 / FP 0 / FN 0 / errors 0.
  This is a selected feasibility set, not representative runtime accuracy.
- [ ] Reach at least 20 vulnerable and 20 safe cases across the declared scope;
  retain unsupported/unknown cases separately. This is an initial
  evaluation floor, not a production certification or statistical guarantee.
- [x] Report the static set's case/repository counts, exact revisions, TP/FP/TN/FN,
  unknowns, execution errors, coverage diagnostics, analysis times and limitations.
  Static model calls are zero; compute cost was not metered. Unknown labels are
  retained and excluded explicitly from binary metrics, not converted to negatives.
- [ ] Complete aggregate repair acceptance/rejection, upstream-regression,
  end-to-end latency and model/compute cost measurements for the broader evaluation.
  Report conditional executed-case metrics and coverage separately.
- [x] Keep case-level results and uncertainty visible. Correlated variants of one
  fixture are not independent real-world samples; balanced test-set precision does
  not predict production precision at a different vulnerability prevalence.
  Evidence: frozen case manifest, retained per-case JSON and benchmark README.
- [ ] Compare the same cases with the project's existing checks and with a
  repair agent without Unspool's gate. Record additional correct detections and
  incorrect repairs prevented, along with cost and false blocks. Freeze inputs and
  versions, repeat stochastic runs, and publish failures as well as successful runs.

Exit: reproducible before/after application evidence against independently sourced expectations and an honest
evaluation report. One successful application supports a pilot story, not a claim
that arbitrary repositories are supported. If this gate fails, narrow the product.

## Gate 3 — enforce security boundaries outside the model

- [x] Write a threat model covering repository code/build scripts, dependencies,
  issue/MR prompt injection, CI artifacts, GitLab identities, model providers,
  credentials, public reports, and deployment privileges.
- [x] Execute the controlled isolation drill in network-none and internal-network
  modes, including a deliberately injected synthetic credential negative control.
  Evidence: [16-check drill](benchmarks/isolation/README.md), Cloud Build
  `b99654ca-27aa-4fa1-9411-d8b500637029`; this is scoped control evidence only.
- [ ] Execute unfamiliar code in disposable isolated workers with no host Docker
  socket, no host credentials, no cloud metadata access, bounded CPU/memory/disk/
  processes/time, and controlled egress. Select stronger worker/VM isolation for
  hostile multi-tenant workloads; a subprocess or container alone is not a complete
  trust boundary. Test the isolation from inside a malicious fixture.
- [ ] Treat dependency installation as code execution too. Separate dependency
  fetch/build steps from credentialed promotion and restrict dependency sources.
- [x] Run the recorded configured workflows with installed/pinned controller and
  verification logic. Repository
  tests can supply useful checks but cannot certify their own trustworthiness.
  Keep independent policy, tests and deployment logic outside the agent's write scope.
  Evidence: installed controller replays, protected-file content pins and the
  external CI's fixed harness revision. This does not fix runtime monkeypatching.
- [x] Add a reusable HTTP probe that imports no target code, and exercise the same
  frozen plan/probe against vulnerable and repaired VAmPI in separate containers.
  Evidence: [0.4.5 reports](benchmarks/vampi/results.generic.json), MR !21.
- [ ] Integrate that independent HTTP report into reusable handoff CI with trusted
  source/image/plan/probe binding. The CLI does not attest which commit serves a URL.
- [ ] Pin source/base/target SHAs, policy hash, manifest hash, runtime image digest,
  verifier version, test results, artifact hashes, model/version, actor and run ID.
  Bind evidence to the exact artifact promoted, not just a self-reported health SHA.
- [x] Revalidate or stop when the configured target branch changes. An MR tested on an old
  base does not prove its integration with a new target branch is correct.
  Evidence: MR !17's source/base/pipeline/target freshness tests in review/auto
  modes and protection recheck. The legacy synthetic path has fewer guarantees;
  the full live remote race/failure matrix remains open under Gate 4.
- [x] Keep Duo's repair identity separate from the operator's promotion identity;
  preserve protected-branch/approval refusals and never give Duo the operator login.
  Evidence: the real Duo MR required the separately authorized operator to merge.
- [ ] Complete least-privilege scoping of every read/analyze/propose/verify/deploy
  identity to its project and operation, including live cross-project refusal tests.
  An operator's existing broad `glab` login is not proof of least privilege.
- [ ] Specify what code/context leaves the worker for model inference, and make
  provider choice, redaction, retention and opt-out explicit. Test canary secrets
  against logs, artifacts, prompts and public reports.
- [x] Test exact diff allowlists, forbidden test/CI paths, project/config confusion,
  path escapes, linked/special files, stale SHA/pipeline/health evidence and forged
  verification booleans. Evidence: handoff/config/state/smoke/source-boundary tests
  and passing CI; these are implemented negative checks, not a full attack audit.
- [ ] Execute the remaining prompt-injection cases through issues, source comments
  and tool outputs; complete unauthorized-trigger and wrong-project-deployment
  drills, plus forged-artifact/adversarial workflow coverage beyond unit tests.

Exit: a recorded security review of the trust boundaries using automated checks
and adversarial execution tests, no unresolved critical/high
risk in the declared use, and regression tests proving the negative cases stop
promotion. A clean review is evidence within scope, not a guarantee of no flaws.

## Gate 4 — survive interruptions and concurrent work

- [x] Persist private atomic versioned run records, intent/configuration identity,
  observed MR/source/pipeline identities and controller stages/outcomes. Evidence:
  `RunJournal`, installed cancellation checks and real recovery journals. GitLab
  remains authoritative for remote agent/pipeline state.
- [ ] Complete the run-wide transition/recovery model across requested, analyzing,
  proposed, verifying, blocked, merged, deploying, healthy, failed and recovery-required
  phases. A local STOPPED/error-type record is not a fully qualified remote lifecycle.
- [x] Use stable project/target/intent plus configuration identity; durably record
  trigger intent before dispatch, reconcile its marker on retry, reuse the existing
  MR and lock the target against concurrent local controllers. Evidence:
  [ADOPTION.md](ADOPTION.md), journal tests and real MR !2 replay with zero writes.
  This is one operator state directory's OS lock, not a distributed lock.
- [x] Bound transient GET retries, refuse blind mutation replay, retain stop/error
  details and distinguish cancellation from success. Missing/failed/unknown checks
  stop the workflow. Evidence: 429/503/403 regression cases, STOP/Ctrl-C tests and
  exact required-job/health checks. Full remote fault drills remain below.
- [x] Demonstrate local lock recovery after SIGKILL and real existing-MR recovery
  after MR reads and evidence reads. Evidence: [recovery record](benchmarks/recovery/README.md),
  exits 137, preserved journal, same MR/SHA/pipeline and successful read-only resume.
- [ ] Demonstrate the remaining remote restart points: trigger dispatch, push,
  merge, deployment and successful deployment before the completion note.
- [x] Exercise duplicate local delivery/competing intent locks and unit checks for
  stale candidates/targets and transient/permanent API errors. Do not describe
  these as the complete live concurrency matrix.
- [ ] Complete live two-issue concurrency, duplicate delivery, stale MR/changed
  target, 429/5xx, revoked-credential and unavailable-provider workflow drills.
- [x] Preserve the healthy disposable VAmPI staging container when a candidate
  fails, then separately recreate the healthy app from its retained image digest.
  Evidence: build `ff4898a1-6efe-427d-85ba-b91747d35202`, rejected exit-17
  candidate, unchanged healthy container, retained image digest and restored app
  passing HTTP checks. This proves candidate rejection and artifact recreation,
  not production traffic rollback or persistent data restoration.
- [x] Implement/document local STOP and Ctrl-C cancellation, persist CANCELED/exit
  130, assign reconciliation/escalation to the operator and retain resume guidance.
  Evidence: [operator instructions](ADOPTION.md) and installed cancellation checks.
- [x] Post the successful verified synthetic workflow's outcome/evidence to its MR.
  Evidence: the recorded complete handoff; this does not prove every failure path
  posts a final notification.
- [ ] Add stuck-run alerts, remote cancellation and complete success/failure/unknown
  outcome notification coverage; qualify controller-coordinated production rollback
  and any required persistent-data backup/restore.

Exit: fault-injection records show no duplicate promotion, unauthorized merge or
false success; interrupted runs can be safely resumed from a fresh operator
environment using only the documented procedure. External operator usability
remains unverified until someone else tries it.

## Gate 5 — solo release qualification and future supervised adoption

- [x] Qualify packaged installations in fresh macOS/Linux environments, including
  one exact wheel across the Linux Python matrix. Evidence: Gate 1 installation
  records and 0.4.5 jobs above; this is solo evidence, not independent adoption.
- [ ] Exercise the released artifact in two clean environments and separate
  projects, without source-checkout imports or inherited development state.
  Start with report/MR-only mode and tested rollback instructions. Record this
  as solo qualification, not adoption by independent teams.
- [x] Declare/enforce source-ingestion budgets and test their actual installed
  boundaries: 1 MiB/file, 32 MiB total, 2,000 source files, 20,000 visited entries,
  depth 64. Over-budget input errors instead of producing a truncated success.
  Evidence: 0.4.4 source scanner tests and installed quota exercises above.
- [ ] Declare the remaining qualification's repository/framework workload sizes,
  concurrent jobs, acceptable latency/cost,
  support hours, data retention and service objectives before testing them.
  Choose thresholds from the declared supported use before execution, not from
  whichever results pass. External customer needs remain unvalidated.
- [ ] Measure those limits on representative repositories and queue pressure.
  Reject/defer work beyond quotas with an explicit status, not silent truncation.
- [ ] Keep tenant/project state and credentials isolated; define deletion/export
  and verify public reports never disclose private code or repository metadata.
- [x] Provide security scope/reporting guidance, supported interpreter versions,
  dependency inventories/source audit, upgrade/removal/state-preservation guidance
  and operator ownership. Evidence: [SECURITY.md](SECURITY.md),
  [SECURITY_REVIEW.md](SECURITY_REVIEW.md), [ADOPTION.md](ADOPTION.md) and CI artifacts.
- [ ] Verify the confidential/private reporting route works for intended reporters;
  complete dependency/license review, operational migration/rollback rehearsal,
  comprehensive diagnostic redaction, billing alerts and availability ownership.
  Documenting a confidential-issue option does not verify access or configure alerts.
- [ ] Run a recorded soak/repeated-workflow exercise for a declared observation window; track every failure and
  required intervention. Publish the denominator and unresolved limitations.
- [x] Restrict current external configurations to human review by default and
  require explicit auto mode, protected fast-forward target, pinned contracts and
  exact diff/jobs/revision checks. The recorded hands-off demo is a bounded
  synthetic display-name change, not general autonomous security repair.
- [ ] Qualify any further autonomy expansion only for approved low-risk change classes with explicit
  policy and independent acceptance checks. Unknown/high-impact cases remain
  human-reviewed. Never advertise general automatic security repair from this pilot.

Exit: the solo release qualification meets the declared operational/security
criteria with all failures reviewed. Describe it as qualified for the explicit
tested use, with external adoption/security-review limitations disclosed. Do not
claim independent-team acceptance, certification, or universal production safety.

## Gate 6 — optional shared hosted product

This is not necessary for many teams to use the self-hosted integration. If the
product later accepts customer repositories through a shared website, additionally
require login/SSO, server-side project membership and per-action authorization,
tenant isolation tests, short-lived per-project credentials, isolated execution,
durable queues, shared-state design, fair-use quotas, audit logs, deletion/retention,
backup restoration, abuse response and ongoing operational ownership.

Public CRUD must never call the existing mutable local server without that design.
Do not expose host paths or execute arbitrary repositories in the report service.
Independent security review and customer data-handling approval precede this launch.

## GitLab AI Catalog: a distribution gate, not certification

- [ ] First prove Gate 1 through clean-environment installation and Gate 2 with an external application.
- [ ] Package a genuine versioned custom agent/flow with an explicit external
  controller dependency if retained. Do not rename the existing foundational
  Developer flow and imply it is a new Unspool agent implementation.
- [ ] Publish experimental report/MR-only behavior first; disclose permissions,
  data transmission, supported cases, costs, limitations and uninstall steps.
- [ ] Test enablement in a separate namespace, version pinning, upgrade and removal.
- [ ] Use a managing project where the user actually has Maintainer/Owner rights.
  The hackathon project's Developer access is not sufficient to create custom
  agents there; Catalog publication does not remove group enablement constraints.

Do not make Catalog listing a prerequisite for an honest hackathon submission.

## Submission schedule and scope cuts

The current deadline is 27 October 2026 at 20:00 WIB (13:00 UTC). The following
is a proposed schedule, not an effort estimate or promise of production readiness.
Parallel engineering cannot substitute for independent evaluation or a pilot.

| Date (WIB) | Highest-value work | Decision at the end |
| --- | --- | --- |
| 20–21 October | Supported scope, VAmPI repair, portable configuration, clean installs, retained release and disclosed Path B basis completed | Finish CLI safety patch; preserve explicit prototype scope and organizer authority |
| 21–22 October | Clean installation on a second repository; reproduce confirmed defect and pin acceptance cases | If unsuccessful, keep explicit prototype status |
| 22–24 October | Real repair/staging demonstration, safe cases, baseline comparison, highest-risk isolation and negative tests | Report measured results; reduce unsupported claims |
| 24–25 October | Remaining restart/concurrency/failed-deployment drills and fresh solo installation rehearsal | Freeze supported behavior; disable unvalidated autonomy |
| 25–26 October | Release candidate, clean-room reproduction, public evidence bundle and demo recording | Fix blockers only; no late architecture or marketplace expansion |
| 26 October | Prepare and validate submission fields, public links and video | Aim to submit with a day's buffer |
| 27 October, before 20:00 | Final availability/visibility checks and submission | Do not submit inflated claims to compensate for unfinished work |
| After submission | Larger held-out evaluation, supervised pilots, security review and operations gates | Decide whether a scoped production release is justified |

If time is short: keep Python only; keep the controller local and documented;
retain human approval for external/customer code; skip shared SaaS, public mutable
CRUD, extra cloud services and Catalog publication. Do not skip a truthful scope,
independent verification or required submission material.

## Submission go/no-go checklist

- [x] Public MIT GitLab repository, public original project URL and honest provenance.
  Evidence: preserved original history/licensing, credential review before its
  authorized publication and current unauthenticated HTTP 200 checks. This does
  not resolve Path B eligibility.
- [x] Retain actual Duo/session/diff/CI/deployment/outcome references for the
  successful synthetic handoff and supervised external repair; retain deliberate
  failing HTTP/credential-control evidence. Evidence: [SUBMISSION.md](SUBMISSION.md),
  VAmPI generic baseline `gate.passed: false` and the isolation negative control.
- [x] Validate the installed trusted demo, graph/annotation CRUD and persisted STOP
  cancellation; retain vulnerable/repaired HTTP results and public MR/pipeline
  metadata. Evidence: [judge guide](JUDGE_GUIDE.md), [release records](RELEASE.md).
  This is not an end-to-end failed remote promotion; session pages and raw
  job-trace APIs require authorized access and are not required reproduction links.
- [x] Deploy a public live GCP static report and keep its deployment code public;
  publish the Pages fallback. Current Cloud Run health is verified above.
- [x] Check Pages from remote GitLab CI with an exact-revision smoke test; check
  Cloud Run directly and retain the served revision. See release verification.
  Local Jamf redirects are not counted as health evidence.
- [ ] Maintain both delivery targets through judging; this is the maintainer's
  ongoing obligation, not a completed point-in-time availability test.
- [x] Confirm what the live project actually executes. If it remains a static
  report, say so; demonstrate any repaired target separately and explain the
  deployment boundary rather than implying a full hosted service.
  Evidence: [HANDOFF.md](HANDOFF.md), [SUBMISSION.md](SUBMISSION.md), judge guide
  and separate repaired-app staging records. Hosted report is read-only; controller
  and annotation CRUD remain local.
- [x] Provide pinned clean-install/demo instructions and their committed
  inputs/configuration. Evidence: [JUDGE_GUIDE.md](JUDGE_GUIDE.md) and the
  exact source, checksum and installation records in [RELEASE.md](RELEASE.md).
- [x] Retain a frozen release wheel, checksums and verification records separately
  from expiring CI artifacts; identify its exact source in the judge guide.
  Code changes require a new patch release and renewed verification, not a moved tag.
- [ ] Public YouTube video under three minutes showing actual operation; explain
  time cuts and local-controller requirements without staging fake outcomes.
  **Author action**, excluded from the delegated engineering/preparation work;
  Devpost submission itself also belongs to the author. The outline is prepared.
- [x] Prepare submission text stating the problem, additions, actual autonomy, measured
  benefits, failure behavior, limitations and model/service dependencies.
  Evidence: [SUBMISSION.md](SUBMISSION.md); no invented adoption, time-saved,
  unknown-vulnerability or production-certification claim.
- [x] Align the description with the pinned release and disclosed Path B basis.
  Organizer eligibility decisions and the author's personal attestations remain external.
- [x] Review source/history and retained artifacts for credentials and private
  material; preserve licenses and the synthetic/lab scope. Evidence: release
  audit records and original history review; scanner findings are disclosed.
- [ ] Review the author's final video for credentials/private material and asset
  permissions before upload. The video is not created by this engineering workflow.
- [x] Designate the maintainer as availability owner and verify billing is enabled.
- [ ] Keep billing/trial availability valid through judging/winner announcement,
  expected around 16 November. A current enabled-billing check does not establish
  future credit balance, expiry or uptime, and no automatic billing monitor is claimed.
- [x] Check the public source, MIT detection, release downloads, evidence metadata,
  judge instructions and Cloud Run without credentials; record access limitations.
  Pages is verified through remote CI. See retained submission checks in the release.

Shipping as a prototype or evaluated beta is acceptable if described accurately.
Do not declare production readiness because the submission deadline arrived.

## Evidence record for each gate

Use the same record format: claim; exact release/commit; configuration and dataset
versions; prerequisite permissions; procedure; expected result; observed result;
all failures/unknowns; logs/artifact hashes; independent reviewer; date; limitations;
decision (pass, fail, blocked). Keep a claim-evidence table in the release notes.
Screenshots and demo videos supplement reproducible evidence; they do not replace it.

## Official references checked 20 October 2026

- [Event overview and requirements](https://gitlab-transcend.devpost.com/)
- [Official rules: timing, Path B, functionality, submission and availability](https://gitlab-transcend.devpost.com/rules)
- [GitLab AI Catalog and version management](https://docs.gitlab.com/user/duo_agent_platform/ai_catalog/)
- [Custom agent creation and required roles](https://docs.gitlab.com/user/duo_agent_platform/agents/custom/)

The roadmap's engineering gates and sample targets are our proposals, not extra
hackathon rules or a security certification standard. Organizer decisions govern
eligibility; recheck requirements before submission.
