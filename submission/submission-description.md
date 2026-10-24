<p align="center">
  <img src="https://gitlab.com/gitlab-ai-hackathon/transcend-october-2026/43244671/unspool/-/raw/main/submission/assets/unspool-readme-banner.png" alt="Unspool: pull the thread before it unravels" width="100%">
</p>

# UNSPOOL

## Open a merge request. If it leaks, GitLab Duo fixes it, and Unspool ships it verified. Nobody in the middle.

**Unspool** is a hands-off exposure gate for GitLab. On every merge request it proves whether a sensitive value (a password hash, a card number, a token) leaves the code where it should not. When it does, Unspool hands the evidence to GitLab Duo, Duo fixes the same merge request on the same branch, and Unspool's controller re-verifies the exact revision, merges it, deploys it to Google Cloud Run and confirms the live revision. The developer's `git push` is the only human step.

<p align="center">
  <a href="https://gitlab.com/gitlab-ai-hackathon/transcend-october-2026/43244671/unspool"><img src="https://img.shields.io/badge/SOURCE%20ON%20GITLAB-0E110D?style=for-the-badge&logo=gitlab&logoColor=white" alt="Source on GitLab"></a>
  <a href="https://unspool-398376578726.us-central1.run.app"><img src="https://img.shields.io/badge/LIVE%20ON%20GOOGLE%20CLOUD%20RUN-28765A?style=for-the-badge&logo=googlecloud&logoColor=white" alt="Live on Google Cloud Run"></a>
  <a href="https://unspool-demo-398376578726.us-central1.run.app"><img src="https://img.shields.io/badge/TRY%20THE%20UI-3DDC97?style=for-the-badge" alt="Read-only demo of the Unspool UI"></a>
  <a href="https://github.com/azharizz/leakhunter"><img src="https://img.shields.io/badge/ORIGINAL%20MIT%20PROJECT-EEF3EA?style=for-the-badge&logo=github&logoColor=0E110D" alt="Original MIT project, LeakHunter"></a>
</p>

<p align="center"><strong>Path B · Bring Your Own</strong> &nbsp;·&nbsp; <strong>Autonomy: Hands-off</strong> &nbsp;·&nbsp; <strong>All nine DevSecOps stages</strong> &nbsp;·&nbsp; <strong>Deployed on Google Cloud</strong></p>

## Inspiration

Somewhere in your API, a field is leaving that never should. Not a breach: one `password_hash` riding along in a public response.

We kept seeing the same pattern. A one-line change, `fields = record.get("columns", fields)`, so legacy CSV imports can show a customer handle. Static analysis finds nothing. Every test passes. Review approves it. Only a legacy import row that carries its own column list turns the public profile into the whole record.

AI coding agents sharpen the problem. In our benchmark, **14 of 36 agent-written fixes passed every test and still leaked.** But agents are also fast at fixing a leak once something proves it, and as long as their fix is checked by something other than the agent. That became the product: prove the leak, let GitLab Duo fix it, verify independently, ship it. On every merge request, without a person in the middle.

## What it does

<p align="center">
  <img src="https://gitlab.com/gitlab-ai-hackathon/transcend-october-2026/43244671/unspool/-/raw/main/submission/assets/unspool-loop.gif" alt="One push. Everything after it is automatic: tests and the Unspool gate, the controller starts GitLab Duo through the Agent Platform API, Duo pushes the fix, the gate re-runs, the controller merges, deploys and checks the live revision." width="100%">
</p>

| Unspool capability | What it does | Why it matters |
| --- | --- | --- |
| **Exposure tracing** | Follows every classified field from where it is born to where it leaves: API responses, logs, webhooks, analytics calls, AI prompts. Works with a policy file or a built-in catalogue. | The leak is a path, not a line. |
| **Proven, not guessed** | A typed decision model reads only the changed boundaries and says what to test; operator-written canary probes run in isolation and catch the canary at a forbidden sink. | A merge request is blocked only by evidence it can show. |
| **GitLab Duo fixes the same MR** | The controller starts GitLab Duo's Developer flow through the Duo Agent Platform API, on the MR's own branch, with the verdict: boundary, probe, field, sink. | No new MR, no copy-paste, no comment ping-pong. |
| **Hands-off promotion** | After Duo's fix passes, the controller checks the complete diff, the exact revision, every required job and the signed evidence, merges, waits for Cloud Run and confirms the live revision. | Missing, failed or unknown is a stopped workflow, never a "successful" deployment. |
| **Signed evidence** | `verify-exposure` evidence is signed and attested with Sigstore `cosign` on protected `main`. | Anyone can check what was verified, and for which commit. |
| **A graph you can read** | The Unspool UI shows the data flow, findings, probes and decisions; a read-only demo runs on Cloud Run. | Reviewers see the whole thread in one place. |

## The proof run: one push, 8.5 minutes, untouched

On 23 October 2026 a developer pushed the leaky change and opened [MR !44](https://gitlab.com/gitlab-ai-hackathon/transcend-october-2026/43244671/unspool/-/merge_requests/44). Nobody touched it again.

| UTC | Step | Who |
| --- | --- | --- |
| 18:44 | `git push` opens MR !44 | **You** |
| 18:44 | `verify-exposure` blocks: decision model LEAK (0.73), probe `csv-import-row-probe` observed `customer.password_hash` in the HTTP response | GitLab CI |
| 18:45 | Controller starts GitLab Duo Developer session 9981901 through the Agent Platform API | Controller |
| 18:48 | Duo Developer pushes "Stop imported rows from choosing profile response columns" to the same branch | GitLab Duo |
| 18:48 | Gate re-runs: UNCERTAIN (0.43), all five probes run again, nothing leaks, gate passed | GitLab CI |
| 18:49 | Controller verifies the exact revision and merges | Controller |
| 18:52 | `main`: signed evidence, attestation, Cloud Run + Pages deploy, smoke check → `DEPLOYED_AND_VERIFIED` | CI + controller |

<table>
  <tr>
    <td width="50%"><img src="https://gitlab.com/gitlab-ai-hackathon/transcend-october-2026/43244671/unspool/-/raw/main/submission/assets/gate-blocks-the-leak.gif" alt="Every test passes, verify-exposure is red, the job log explains the block"><br><sub><strong>Every test passes. One check doesn't.</strong> The boundary, the probe, the field and where it left.</sub></td>
    <td width="50%"><img src="https://gitlab.com/gitlab-ai-hackathon/transcend-october-2026/43244671/unspool/-/raw/main/submission/assets/duo-fixes-the-mr.gif" alt="The controller's record of the Duo session it started, then Duo's commit on the same branch"><br><sub><strong>Duo fixes the same merge request.</strong> Started through the Agent Platform API; the commit lands on the developer's branch.</sub></td>
  </tr>
  <tr>
    <td width="50%"><img src="https://gitlab.com/gitlab-ai-hackathon/transcend-october-2026/43244671/unspool/-/raw/main/submission/assets/verified-and-live.gif" alt="Gate passed, merged by the controller, Production serves verified revision"><br><sub><strong>Verified and live.</strong> Cloud Run serves exactly the merged commit.</sub></td>
    <td width="50%"><img src="https://gitlab.com/gitlab-ai-hackathon/transcend-october-2026/43244671/unspool/-/raw/main/submission/assets/canary-proves-the-leak.gif" alt="A legacy import row carries a canary; it comes back in the response; leak proven"><br><sub><strong>Probes written before the bug.</strong> The canary comes back in the response: proven, not guessed.</sub></td>
  </tr>
</table>

An issue works the same way: [issue #6](https://gitlab.com/gitlab-ai-hackathon/transcend-october-2026/43244671/unspool/-/work_items/6), labelled `unspool`, became [MR !39](https://gitlab.com/gitlab-ai-hackathon/transcend-october-2026/43244671/unspool/-/merge_requests/39) written by Duo and reached a verified deployment in about 7 minutes.

## Path B: before and after

Unspool is **LeakHunter**, an MIT-licensed open-source project ([github.com/azharizz/leakhunter](https://github.com/azharizz/leakhunter)), imported to GitLab with its history and rebuilt around GitLab's full lifecycle during the hackathon.

| | Before: LeakHunter | After: Unspool on GitLab |
| --- | --- | --- |
| **Finding a leak** | A local CLI you remember to run. | Every merge request runs the exposure gate in GitLab CI. |
| **Proving it** | Static findings and judgement. | A typed decision model picks what to test; canary probes prove it; evidence is attached. |
| **Fixing it** | A developer reads a report and patches by hand. | GitLab Duo fixes it on the same branch, started automatically with the evidence. |
| **Shipping it** | Manual merge and deploy. | Verified merge, signed evidence, Cloud Run deploy, live-revision check. |

## Nine DevSecOps stages

| Stage | Unspool on GitLab |
| --- | --- |
| **Plan** | An issue labelled `unspool` becomes a bounded task for Duo. |
| **Create** | GitLab Duo's Developer flow writes the fix on the merge request's branch. |
| **Verify** | 162 tests, dashboard and installed-wheel checks, and the `verify-exposure` gate with canary probes. |
| **Package** | `build-wheel`; a GitLab release keeps the wheel and its verification bundle. |
| **Secure** | The exposure gate, `security-audit` (bandit + pip-audit), signed evidence and attestation. |
| **Release** | Exact-revision verified merge by the controller into protected `main`. |
| **Configure** | Cloud Build + Cloud Run and Pages delivery with keyless Workload Identity Federation; operator-owned controller configuration. |
| **Monitor** | `production-smoke` and the controller's live `health.json` check of the deployed revision. |
| **Govern** | File allowlist, required jobs, stop-on-unknown, at most two Duo attempts, a resumable private run journal. |

## How we built it

<p align="center">
  <img src="https://gitlab.com/gitlab-ai-hackathon/transcend-october-2026/43244671/unspool/-/raw/main/submission/assets/unspool-architecture.png" alt="Unspool architecture: GitLab CI and the verify-exposure gate, the controller starting GitLab Duo through the Agent Platform API, and delivery to Google Cloud Run through Workload Identity Federation, Secret Manager, Cloud Build and Artifact Registry, with GitLab Pages as fallback" width="100%">
</p>

| Technology | Role in Unspool |
| --- | --- |
| **GitLab Duo Agent Platform** | The Developer flow (`developer/v1`) writes every fix; the controller starts it through the Agent Platform API on the MR's branch. A Duo agent configuration prepares the runner. |
| **GitLab CI/CD** | Tests, wheel build, security audit, `verify-exposure`, signing, attestation, Cloud Run and Pages delivery, production smoke. |
| **Unspool controller** (`python3 -m unspool.handoff --watch`) | Watches merge requests and labelled issues; starts Duo when the gate blocks; promotes only verified, allowlisted, exact revisions. |
| **Analyzer + runtime probes** | Data-flow tracing for Python (AST) and JavaScript, TypeScript, Go and Rust (Tree-sitter) with policy or catalogue classification; isolated probes with synthetic canaries. |
| **Typed decision model** (third-party API) | One call per boundary, typed answers with probabilities, no chat: from 180 ms (provider page), 1.11–1.38 s measured here, about $1 per 1,000 decisions. It chooses what to test; probes decide. |
| **Google Cloud** | Cloud Run (report, demo UI), Cloud Build, Secret Manager, Workload Identity Federation: no service-account keys in CI. |
| **Sigstore cosign** | Signs and verifies the protected-`main` evidence before the controller reports a deployment. |

## Challenges we ran into

- **Hands-off without handing over the keys.** Duo's runtime cannot merge into `main`, and we did not want it to. The controller holds the only merge identity and promotes only what it can verify.
- **Starting Duo without a comment.** Our first version triggered Duo with an @-mention. We moved to the Duo Agent Platform API so the hand-off is a real API start on the MR's own branch, recorded on the MR.
- **Not fixing leaks that were never found.** A real run showed the evidence job failing before the gate ran (a secret was unavailable on a new branch). The controller now stops when there is no evidence instead of asking Duo for a fix.
- **Real runs find real gaps.** The first hands-off issue merged and deployed, then stopped because `cosign` was missing locally; the controller now refuses to merge without the verifier, instead of stopping after the merge.
- **Proving instead of guessing.** Scores alone flip; canary probes are what make a block defensible, so the model only decides what to test.

## Accomplishments that we're proud of

- A real, untouched loop from one `git push` to a verified Cloud Run deployment ([MR !44](https://gitlab.com/gitlab-ai-hackathon/transcend-october-2026/43244671/unspool/-/merge_requests/44)), and the same from a labelled issue ([issue #6](https://gitlab.com/gitlab-ai-hackathon/transcend-october-2026/43244671/unspool/-/work_items/6)).
- **14/14** leaking agent-written fixes blocked and **22/22** clean fixes passed in a 36-patch benchmark; the same verdict across 10 runs per revision.
- Every stop condition we hit in real runs is now a test: 162 tests, including the controller's hands-off paths against a fake GitLab.
- All nine DevSecOps stages, deployed on Google Cloud with keyless authentication.

## What we learned

An agent that writes code is only as trustworthy as the thing that checks it. The useful split is narrow: a gate that can prove a leak, an agent that fixes it, and a controller that refuses to ship anything it cannot verify. The hard engineering was in the stop conditions, not the happy path.

## What's next

- Running the controller as a GitLab-hosted service, once a merge identity can be scoped as tightly as it is today.
- Parallel decision-model calls for large merge requests (today one boundary at a time).
- Real-project validation for JavaScript, TypeScript, Go and Rust. Analysis and runtime probes already work in all five languages on synthetic holdouts (runtime 10/10 each); automatic repair promotion turns on per language once it is validated on real code.
- Publishing Unspool's repair flow to the GitLab AI Catalog.

## Honest limits

- The controller runs on the operator's machine with their `glab` login; "walk away" means the watcher keeps running. GitLab records the Duo start under the operator's account, because that is the identity making the API call.
- The gate's decision model is a third-party API; GitLab Duo writes every fix.
- The demo target is a small synthetic service, and automatic promotion is limited to allowlisted files; it is enabled for Python while the other four languages are validated on real projects.
- A passing gate means the configured probes saw nothing at a forbidden sink, not that every path is safe.
- The 36-patch benchmark is synthetic; "about one second in parallel" is a projection.

## Try it

- **Source (GitLab):** [gitlab.com/gitlab-ai-hackathon/transcend-october-2026/43244671/unspool](https://gitlab.com/gitlab-ai-hackathon/transcend-october-2026/43244671/unspool)
- **Original MIT project:** [github.com/azharizz/leakhunter](https://github.com/azharizz/leakhunter)
- **Live on Google Cloud Run:** [unspool-398376578726.us-central1.run.app](https://unspool-398376578726.us-central1.run.app)
- **Read-only UI demo:** [unspool-demo-398376578726.us-central1.run.app](https://unspool-demo-398376578726.us-central1.run.app)
- **The proof run:** [MR !44](https://gitlab.com/gitlab-ai-hackathon/transcend-october-2026/43244671/unspool/-/merge_requests/44)
- **Technical notes:** [submission/technical-notes.md](https://gitlab.com/gitlab-ai-hackathon/transcend-october-2026/43244671/unspool/-/blob/main/submission/technical-notes.md)
