# Test Verification

Updated: 21 October 2026 (Asia/Jakarta)

This log records evidence for the referenced test plan against MR !25. The
product code under test is unchanged from `a6bad192a7471aa98572521f62fc51dc1d9bca52`;
verification results are published at commit `4b73736a10013eb4188fe92212d93182e9d1b38a`.
A fixture, unit test,
or successful build does not count as a live workflow result.

## Completed checks

| Step | Result | Evidence |
| --- | --- | --- |
| Read the referenced plan and inspect the current MR | Done | The plan requires live checks for Tracks A–H, then separate production-readiness checks. It recommends separating core, workflow, component, and benchmark changes. |
| Review current MR pipeline | **Blocked** | [Latest MR !25 pipeline](https://gitlab.com/gitlab-ai-hackathon/transcend-october-2026/43244671/unspool/-/pipelines/2971063495) on `4b73736a10013eb4188fe92212d93182e9d1b38a`: `python-tests`, `dashboard-tests`, `security-audit`, and `build-wheel` passed. Both `installed-wheel` jobs (Python 3.10 and 3.12) failed with `Installed synthetic workflow failed`; `verify-exposure`, `sign-evidence`, and `verify-attestation` were skipped. |
| Run the exact CI Python test command locally | **Passed** | `python3 -m unittest discover -s tests -v`: 143 tests passed in 22.039 seconds. This includes unit-level evidence tamper rejection with Cosign mocked, plus handoff fail-closed/recovery tests. |
| Try repository-wide pytest collection | **Failed to collect** | `python3 -m pytest -q` imports the three benchmark app modules as the same `tests.test_service` name and stops with import-file-mismatch errors for billing and support. The GitLab job uses `unittest discover -s tests`, which passed; benchmark tasks are run by their dedicated harness. |
| Run exact CI dashboard checks locally | **Passed** | `node --check leakhunter/static/app.js && node tests/test_dashboard.cjs`: dashboard checks passed for inspector, selection, snapshot locks, filters, zoom, and compact layout. |
| Run dependency and Bandit audit locally | **Passed under configured policy** | `python3 ci/security_audit.py`: 0 dependency advisories; Bandit reported 22 LOW and 6 MEDIUM findings, which this repository retains for review and does not block. No HIGH findings or audit errors. |
| Check the current MR's built wheel and console commands | **Packaging passed** | Installed the wheel from build job `17341249523` into a clean temporary virtual environment using `requirements.lock`; `pip check` and `--help` for all eight installed commands passed. This does not replace the failed synthetic workflow gate in the two GitLab installed-wheel jobs. |
| Parse reusable component template | **Static syntax passed** | PyYAML parsed both GitLab component documents and found `unspool-verify`, `unspool-sign-evidence`, and `unspool-verify-attestation`. This does not prove installation or job success in a second project. |
| Check model ID | Done | OpenRouter lists `openai/gpt-6-luna-decisions`; its listed input price is $0.10 per million tokens and output is free. [OpenRouter model page](https://openrouter.ai/openai/gpt-6-luna-decisions). This confirms catalog availability, not request access or an inference result. |
| Check test credentials | **Missing** | `OPENROUTER_API_KEY` and `AGENT_PROVIDER_API_KEY` are unset locally. GitLab API metadata returned zero project variables and zero group variables. No live Luna or repair-model request can run from the available credentials. |
| Reproduce the installed-wheel failure | **Confirmed cause on latest artifact** | Installed the exact current-pipeline wheel from build job `17341771340` into a temporary Python 3.11 environment and ran `ci/verify_install.py`; it fails at the synthetic workflow gate. The same direct analysis completed its runtime probe successfully, but Luna was `INCOMPLETE` (`0 of 1 boundaries decided`) and the release gate failed. The local provider keys are unset and GitLab project/group variable lists were empty. GitLab reproduced the verifier failure on Python 3.10 and 3.12. |
| Check published frontend copy | **Expected generated difference** | `unspool/publish.py` reads `leakhunter/static/index.html`, adds `data-mode="published"`, and writes `public/index.html`; differing hashes are expected. `tests/test_publish.py` passed in the 143-test suite. |
| Initial PII-to-LLM static check | **Invalid setup; not counted** | A first local analysis without the fixture's runtime manifest found zero findings for both leaky and repaired inputs. Because it omitted the manifest that binds sources and probes, it does not demonstrate absence of a leak; it must be rerun with the planned fixture setup. |
| Closed-loop PII-to-LLM fixture with bound manifest | **Static/runtime pass** | In isolated temporary repositories with synthetic canaries, the intentionally leaky account and support-summary baseline returned gate `BLOCKED` (exit 1), with HTTP_RESPONSE secret violations and an AI_PROMPT PII violation. The reference account/support projection returned gate `PASSED` (exit 0), no findings, and runtime passed. The test explicitly forced the on-demand case in a temporary manifest, so it proves the probe detects the leak but does not prove Luna selected it. |
| Regenerate Track B fixtures | Done | `python3 benchmarks/gate_experiment/build_tasks.py` reported 12 tasks, 4 held out, and 9 leak tasks; generated files matched the committed fixture tree. |
| Freeze Track B task/probe set | Done; committed | `benchmarks/gate_experiment/FROZEN.json` is committed in MR !25: case set SHA-256 `09143bdc326100ea65d5ebffed6aac867a9a105960a627d30594b723f6ab1954`; probe set SHA-256 `df3f36d5c7993472a1e5e7d5f793931015f825928f6c9ff1cff56ef0bff5bd59`. The reference, shallow, and no-repair runs are recorded below and included in the current verification update. |
| Audit frozen Track B result integrity | Done | All three run/result pairs contain 36 runs, match both frozen hashes, and match their aggregate report counts. Each includes all 4 held-out tasks. All runs used `decision_mode=advisory` with no decision model; verdicts are probe/runtime evidence or `UNREVIEWED`, not live Luna results. |
| Track B free reference run | Done | `benchmarks/gate_experiment/results/reference-20261021T083306Z/`: 36/36 app tests passed, 0/36 leaked, 36/36 gates passed, 0 errors; all 4 held-out tasks included. Luna verdict was `UNREVIEWED` in all 36 runs (advisory mode, no key), so this is reference-fixture validation, not a Luna effectiveness result. |
| Track B free shallow run | Done; advisory only | `benchmarks/gate_experiment/results/shallow-20261021T083404Z/`: 36/36 app tests passed; 27/36 patches still leaked; the deterministic/runtime gate blocked 21 and passed 6 leaking patches. All 9 safe-task runs passed; no false blocks or harness errors. Misses are T02 (second endpoint) and T10 (PII-to-LLM), three runs each; every missed run had `luna_verdict=UNREVIEWED` and empty gate reasons. This does not measure Luna because `decision_model` was unset and mode was `advisory`. |
| Track B free no-repair run | Done; advisory only | `benchmarks/gate_experiment/results/none-20261021T083503Z/`: all 27 leaky baseline runs passed the app's own tests; deterministic/runtime gate blocked 24 and passed 3 T10 leaks. The 9 safe tasks failed their own tests because no requested feature was applied. No false blocks or harness errors. All three misses had `luna_verdict=UNREVIEWED` and empty gate reasons; no Luna model was called. |
| Track G static advisory benchmark | Done | `benchmarks/cves/results/20261021T083707Z/`: fetched and analyzed all 8 pinned vulnerable/fixed commit pairs; 1 `HIT`, 3 `FALSE_ALARM_ON_FIX`, 4 `MISS`, 0 `NOT_REPRODUCED`. Luna was `NOT_RUN`. This is a small, one-file-per-case static benchmark, not an accuracy estimate. |
| Track E local MR-diff/SAST flow | **Local pass only** | In an isolated temporary Git repository, the leak-introducing commit produced 1 added finding and 1 GitLab SAST vulnerability; the repair commit produced 1 removed flow and 0 current vulnerabilities. This validates local diff/report generation, not a GitLab security widget. |

## Live verification tracks

| Track | Required evidence | Status |
| --- | --- | --- |
| A. Closed loop | Real analysis and issue draft; Duo-created MR changes only the intended repair; base leaks/head is clean; controller verifies and promotes; deployment smoke passes. | **Partial local evidence only.** The bound synthetic fixture detected both HTTP and AI prompt leaks and the reference repair passed. No real GitLab issue, Duo MR, controller promotion, or deployment smoke was run. |
| B. Gate experiment | Freeze the 12-task suite; free reference/shallow/none runs; 36 paid repair runs; publish every result, including failures. | **Free portion complete.** All three agents have 36 runs each. Reference fixed all leaks; shallow blocked 21/27 and missed T02/T10; no-repair blocked 24/27 and missed T10. The 36 paid model runs remain unavailable without credentials. |
| C. PII to LLM | Leaky support-summary case is detected, Luna selects the on-demand probe, probe confirms the leak, reference repair passes. | **Partial.** Static/runtime detection and reference repair pass locally; Luna selection was not tested because the required API key is unavailable. |
| D. Luna | Report actual verdict counts and probe-truth confusion; at least one Luna-selected probe confirms T10. | Not run. T10 is a repeatable miss in no-key advisory runs; no real Luna decision/probe selection was observed. |
| E. MR diff and SAST | A real leak-introducing MR shows a new finding; fixing MR resolves it in the report/widget or documented fallback. | **Partial local pass.** Synthetic Git commits show 1 finding added then 1 removed in the SAST output. No real GitLab leak/fix MRs or widget were tested; MR !25 does not change `demo/target`. |
| F. Signed evidence | Real keyless sign/verify succeeds; tampered evidence is rejected; controller confirms signer identity. | **Partial unit evidence.** The suite's tamper test rejects evidence changed after statement creation, but it mocks Cosign. No real keyless sign/verify or controller signer-identity check ran; the MR jobs were skipped. |
| G. CVE benchmark | Run all eight pinned advisory cases, publish hits/misses/false alarms/unknowns; optional Luna run separately labeled. | **Static run complete:** 1 hit, 3 false alarms on fixes, 4 misses, 0 unreproduced. Luna run remains unavailable without API credentials. |
| H. Reusable CI component | Install the component in a second authorized project and observe its jobs pass. | **Static check only.** The template parses and has all three expected jobs; second-project installation and live job pass remain untested. |

## Production-readiness checks

The 143-test unit suite covers simulated provider failures, timeouts, cancellation,
restart recovery, duplicate-trigger avoidance, and concurrent promotion locks.
Those tests passed, but they do not replace live Duo/GitLab outage, restart, or
two-issue tests. The CI-built wheel installed cleanly and all eight console
commands started, but an independent README-only installation was not observed.
The static security audit found zero dependency advisories and no HIGH Bandit
findings; live hostile-issue testing and a full external security review remain
open. Luna cost and latency remain unmeasured without a real provider request.
Submission-document consistency has not been audited in this test pass.

## Execution entries

New checks will be appended here with the command or live artifact, commit SHA,
result, and any limitation. Failed and blocked outcomes remain in this log.
