# Unspool 0.4.7 — submission freeze

This is an evaluated prototype release for bounded Python repair workflows.
It is not a production security certification. Follow [JUDGE_GUIDE.md](JUDGE_GUIDE.md)
for installation and [SUBMISSION.md](SUBMISSION.md) for the submission handoff.

## Frozen package

- Source: `722f3955bb44c270b24f248b9046f0f26df93a76`, tag `v0.4.7`.
- [Release and retained downloads](https://gitlab.com/gitlab-ai-hackathon/transcend-october-2026/43244671/unspool/-/releases/v0.4.7).
- Wheel: `unspool-0.4.7-py3-none-any.whl`.
- SHA-256: `7ebd8f69f93679ff7b4f2c095c528f76d79609e9d6da39fac9cb30fd21ae5963`.
- [Canonical CI build](https://gitlab.com/gitlab-ai-hackathon/transcend-october-2026/43244671/unspool/-/jobs/17328758135):
  CPython 3.12.15; pip 26.2.1, setuptools 83.0.0, wheel 0.48.0,
  packaging 26.3; `SOURCE_DATE_EPOCH=1792526114`.
- [Package verification pipeline 2969187062](https://gitlab.com/gitlab-ai-hackathon/transcend-october-2026/43244671/unspool/-/pipelines/2969187062)
  passed regression, dashboard, audit, installed-wheel and exposure checks.
  Main-branch delivery is checked separately in the retained `submission-checks.json`.

## Safety correction

`--once evaluate --gate` could exit successfully when the detector correctly
recognized a real leak. Version 0.4.7 rejects this combination, and serving with
`--gate`, with exit 2 before configuration, state creation or execution. Ungated
evaluation remains available. The regression failed before the fix and passed
after it. The published project CI uses `analyze --gate`; its earlier successful
delivery records are not invalidated by this separate CLI correction.

The old alternate GitLab integration is not imported. The relevant safety behavior
is ported and the previously local roadmap audit is reconciled. Older release
0.4.6 files/tags remain unchanged; use 0.4.7 for the submission instructions.

The generic package registry retains the wheel and `verification.zip` independently
of the CI jobs' 90-day artifact expiry. The bundle also retains this freeze's
judge guide and submission instructions. These are retained files, not a promise of
permanent hosting or a cryptographic third-party attestation. Do not replace this
version's files or move its tag; publish a new version for package changes.
Later documentation commits can deploy a newer report SHA without changing this
package. Read `/health.json` to identify the currently served report revision.

## Verification on 21 October 2026, WIB

| Check | Observed result | Evidence |
| --- | --- | --- |
| Python regressions | 127 passed on the frozen source | CI job 17328758136; fresh local run also passed |
| Dashboard | Inspector, selection, snapshot locks, filters, zoom and compact-layout checks passed | CI job 17328758137; local Node run |
| Linux installation | Python 3.10.22 and 3.12.15 passed against the same wheel checksum | Jobs 17328758139 / 17328758140; retained installation/dependency records |
| macOS installation | Fresh Python 3.11.9 virtual environment passed against that CI wheel | Retained `macos-installation.json` |
| Installed behavior | 40 module/static files matched source; three commands passed; no checkout imports; STOP persisted cancellation; synthetic exposure gate passed | All three installation records |
| Evaluation gate refusal | Both installed command names exit 2 without creating state when evaluation is paired with `--gate` | All three installation records; new counterexample regression |
| Independent HTTP checks | Original known VAmPI exposure stopped; repaired revision passed, with separate app/probe containers and source/image pins | `benchmarks/vampi/results.independent.json` |
| Dependency audit | No reported advisories among 10 installed packages | Retained audit report; database coverage is limited |
| Source audit | 14 LOW, 6 MEDIUM, 0 HIGH Bandit findings; no scan errors | Retained audit report; warnings have not been erased |
| History credential review | Gitleaks 8.30.1 scanned all local Git refs; one documentation-prose false positive was manually reviewed | Retained review summary; not a claim that a scanner proves absence of secrets |
| Public report delivery | Exact current report revision and final main pipeline are retained separately from the frozen package SHA | Release `submission-checks.json`; Cloud Run and remote CI Pages smoke |

The history finding is `generic-api-key` at `ADOPTION.md:61` in
`d3e801b798a13e5c9f03efb91d358edecbb705e9`: prose about rejecting
credential-bearing URLs and malformed JSON, not an issued credential. No scanner
rule was disabled.
Scanning the retained bundle reports the same prose false positive in its
`ADOPTION.md:64–65`; that finding was also reviewed and remains disclosed.

Tests, HTTP requests and repeated environments are not independent vulnerability
counts or external customer acceptance. The generic HTTP contract is opt-in;
the historical VAmPI GitLab repair pipeline still uses its earlier verifier.
The separate Cloud Build HTTP runs do not retroactively change that pipeline.
No new external agent repair is claimed for this CLI patch. Raw GitLab job-trace
APIs and session pages are not anonymous evidence sources; public pipeline
metadata, retained verification records and package downloads are provided.

## Hosting ownership

The maintainer, Azhar Izzannada, owns availability through the expected winner
announcement around 16 November 2026. GCP billing was enabled at the freeze check;
the report has a service maximum of one instance, 256 MiB and scale-to-zero.
Trial-credit balance/expiry and future availability are not guaranteed by this
check. Keep billing valid and do not delete either deployment during judging.
No automated billing monitor is claimed. GitLab Pages is the fallback; the local
network blocks that domain, so its exact-revision check is performed by remote CI.

The live service is a read-only sanitized graph report. The controller and mutable
graph annotations run locally. Keep unfamiliar code out of the trusted-local demo.
