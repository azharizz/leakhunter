# Test Verification

Updated: 21 October 2026 (Asia/Jakarta)

This log records evidence for the referenced test plan, against MR
!25 at commit `0eaff7be4565dd357f45f447a6552963ed64b80c`. A fixture, unit test,
or successful build does not count as a live workflow result.

## Completed checks

| Step | Result | Evidence |
| --- | --- | --- |
| Read the referenced plan and inspect the current MR | Done | The plan requires live checks for Tracks A–H, then separate production-readiness checks. It recommends separating core, workflow, component, and benchmark changes. |
| Review current MR pipeline | **Blocked** | [MR !25 pipeline](https://gitlab.com/gitlab-ai-hackathon/transcend-october-2026/43244671/unspool/-/pipelines/2970948465): `python-tests`, `dashboard-tests`, `security-audit`, and `build-wheel` passed. Both `installed-wheel` jobs (Python 3.10 and 3.12) failed with `Installed synthetic workflow failed`; evidence and signing jobs were skipped. |
| Check model ID | Done | OpenRouter lists `openai/gpt-6-luna-decisions`; its listed input price is $0.10 per million tokens and output is free. [OpenRouter model page](https://openrouter.ai/openai/gpt-6-luna-decisions). This confirms catalog availability, not request access or an inference result. |
| Check test credentials | **Missing** | `OPENROUTER_API_KEY` and `AGENT_PROVIDER_API_KEY` are unset locally. GitLab API metadata returned zero project variables and zero group variables. No live Luna or repair-model request can run from the available credentials. |
| Reproduce the installed-wheel failure | **Confirmed cause** | Installed the exact CI wheel from build job `17340862886` into a temporary Python 3.11 environment and ran `ci/verify_install.py`; it fails at the synthetic analyze gate. Direct output reports Luna `INCOMPLETE` (`0 of 1 boundaries decided`, skipped), because no provider key is available to this local process. GitLab independently reproduced the same failed gate on Python 3.10 and 3.12. |
| Check published frontend copy | **Mismatch** | `public/index.html` exists but its SHA-256 differs from `leakhunter/static/index.html`; the published copy is stale or generated from another source. No asset was changed during this verification. |
| Initial PII-to-LLM static check | **Invalid setup; not counted** | A first local analysis without the fixture's runtime manifest found zero findings for both leaky and repaired inputs. Because it omitted the manifest that binds sources and probes, it does not demonstrate absence of a leak; it must be rerun with the planned fixture setup. |
| Closed-loop PII-to-LLM fixture with bound manifest | **Static/runtime pass** | In isolated temporary repositories with synthetic canaries, the intentionally leaky account and support-summary baseline returned gate `BLOCKED` (exit 1), with HTTP_RESPONSE secret violations and an AI_PROMPT PII violation. The reference account/support projection returned gate `PASSED` (exit 0), no findings, and runtime passed. The test explicitly forced the on-demand case in a temporary manifest, so it proves the probe detects the leak but does not prove Luna selected it. |
| Regenerate Track B fixtures | Done | `python3 benchmarks/gate_experiment/build_tasks.py` reported 12 tasks, 4 held out, and 9 leak tasks; generated files matched the committed fixture tree. |
| Freeze Track B task/probe set | Done; commit next | `benchmarks/gate_experiment/FROZEN.json`: case set SHA-256 `09143bdc326100ea65d5ebffed6aac867a9a105960a627d30594b723f6ab1954`; probe set SHA-256 `df3f36d5c7993472a1e5e7d5f793931015f825928f6c9ff1cff56ef0bff5bd59`. No Track B runs have started. |

## Live verification tracks

| Track | Required evidence | Status |
| --- | --- | --- |
| A. Closed loop | Real analysis and issue draft; Duo-created MR changes only the intended repair; base leaks/head is clean; controller verifies and promotes; deployment smoke passes. | **Partial local evidence only.** The bound synthetic fixture detected both HTTP and AI prompt leaks and the reference repair passed. No real GitLab issue, Duo MR, controller promotion, or deployment smoke was run. |
| B. Gate experiment | Freeze the 12-task suite; free reference/shallow/none runs; 36 paid repair runs; publish every result, including failures. | **Frozen.** Free runs are next. Paid repair runs are unavailable without `AGENT_PROVIDER_API_KEY` and a selected repair model. |
| C. PII to LLM | Leaky support-summary case is detected, Luna selects the on-demand probe, probe confirms the leak, reference repair passes. | **Partial.** Static/runtime detection and reference repair pass locally; Luna selection was not tested because the required API key is unavailable. |
| D. Luna | Report actual verdict counts and probe-truth confusion; at least one Luna-selected probe confirms T10. | Not run. |
| E. MR diff and SAST | A real leak-introducing MR shows a new finding; fixing MR resolves it in the report/widget or documented fallback. | Not run. MR !25 does not change `demo/target`. |
| F. Signed evidence | Real keyless sign/verify succeeds; tampered evidence is rejected; controller confirms signer identity. | Not run. Jobs were skipped in MR !25. |
| G. CVE benchmark | Run all eight pinned advisory cases, publish hits/misses/false alarms/unknowns; optional Luna run separately labeled. | Not run. |
| H. Reusable CI component | Install the component in a second authorized project and observe its jobs pass. | Not run. |

## Production-readiness checks

Fail-closed outages/timeouts, controller restart recovery, concurrent issues,
clean installation from the README, prompt-injection/security review, measured
Luna cost/latency, and evidence-aligned submission docs remain unverified.

## Execution entries

New checks will be appended here with the command or live artifact, commit SHA,
result, and any limitation. Failed and blocked outcomes remain in this log.
