# Unspool — submission text and evidence handoff

Prepared 21 October 2026, Asia/Jakarta, for frozen release **0.4.7**.
Engineering/reproduction records are in [RELEASE.md](RELEASE.md). The author
records/uploads the video, completes personal eligibility declarations and
submits on Devpost. Production qualification remains future work.

Recommended entry: **Path B / Supervised**. This matches the external repair's
operator approval boundary. Present the bounded hands-off synthetic run as
separate evidence. Neither this document nor a working demo grants event approval.

## Suggested title and tagline

**Unspool — evidence before agent promotion**

A GitLab Duo handoff that turns bounded Python repair intent into a reviewable
MR, executed exposure checks and revision-linked delivery evidence.

## Project description — copy-ready

Unspool is for maintainers of selected Python services who want agent-written
changes to pass explicit project-owned checks before release. An agent's
proposed fix is only the beginning of a release decision. Someone
still has to check its scope, preserve the public API, verify the exact revision,
and determine whether deployment actually passed. Unspool makes those boundaries
explicit and leaves a record when a check fails or cannot execute.

The existing GitLab Duo Developer flow writes a bounded change and opens an MR.
A separately installed local controller uses operator-owned configuration to
check the complete diff, required CI jobs, pinned verification contracts and
exact-revision evidence. External repositories default to review mode: the
controller returns `READY_FOR_REVIEW` and a person decides whether to merge.
The agent does not receive the operator's merge credentials or expanded access.
The local graph presents source/sink evidence and supports annotation CRUD;
snapshots retain the evidence for a specific analysis.

For the original synthetic demonstration, a fresh issue-to-MR-to-merge-to-report
run completed without intermediate edits or approvals. That run changed display
name normalization while preserving a fixed secret-field restriction. Its public
Cloud Run/Pages output is an immutable sanitized graph report. The controller
and annotation CRUD remain local; the public URL is not a hosted scanning backend.

We also exercised an external application: an authorized isolated MIT VAmPI copy.
Duo repaired its published debug-response exposure by projecting public user
fields. A pinned HTTP acceptance check passed before operator review/merge and
again afterward. Separate app/probe containers reproduced the upstream canary
leak and verified its absence in the repaired revision. Disposable staging then
rejected a failing startup candidate, preserved the healthy deployment and
restored the app from a retained immutable image, passing HTTP acceptance again.

Unspool is currently an evaluated prototype. The external repair was instructed
and supervised; VAmPI is an intentionally vulnerable lab. A small static set on
three external MIT labs flagged five selected positive policy flows, left three
negatives unflagged and retained two unknown cases. These are not production
accuracy estimates, unknown-vulnerability discoveries or ten runtime tests.
General callable-runtime tamper resistance, representative evaluation, complete
remote recovery and operating limits remain open work.

## Before and after: scope of the additions

Original project: LeakHunter, renamed Unspool with compatible Python imports.
Its original Git history starts on 19 October 2026; MIT licensing was committed
on 20 October. It is not a long-established pre-hackathon project.
Its first two commits were scanned with Gitleaks 8.30.1 and reviewed; no
credentials were found. Both commits remain in GitLab history.

### Path B basis and provenance

| Event | Exact evidence |
| --- | --- |
| Original source, 19 October | Commit `3e8c0afffabe2388a1d87db582b3ad641f19cf92` |
| MIT license, 20 October | Commit `c6ab65f251576790255902c70f2ead497168fb1d` |
| GitLab automation/delivery additions, 20 October onward | First delivery commit `d327259`; issue/MR/pipeline evidence below |
| Original made public after credential review, 21 October | Public original URL and preserved two-commit history |
| Frozen package, 21 October WIB | `722f3955bb44c270b24f248b9046f0f26df93a76`, release `v0.4.7` |

Section 4 of the [official rules](https://gitlab-transcend.devpost.com/rules)
permits Path B projects that may predate the submission period; it does not
require an original project date before October 5. The
[event overview](https://gitlab-transcend.devpost.com/)
requires an original MIT project, new automation/deployment and a live URL.
On that reading, Path B is the recommended classification for this preserved
original and its new GitLab lifecycle integration. The private-to-public timing
is disclosed above; no organizer ruling or guaranteed eligibility is claimed.

The GitLab additions include real Duo issue/MR orchestration, independently pinned
verification, mandatory pipeline checks, exact-revision delivery on Cloud Run,
portable review configuration, durable intent/target locking, restart checks,
operator cancellation, clean wheel installation checks, security auditing and
external-application evidence. The earlier local repair engine still simulates
remote MR creation and must not be used as evidence that a GitLab MR was created.

No measured developer time saved, customer adoption rate or monetary savings
has been established. The measured benefit is the recorded workflow behavior:
specific gates passed, stopped runs stayed stopped, and exact revisions/evidence
can be inspected. Do not invent baseline productivity numbers.

## Claim-to-evidence map

| Claim | Inspectable evidence | What it does not establish |
| --- | --- | --- |
| Real bounded hands-off synthetic delivery | [Issue #3](https://gitlab.com/gitlab-ai-hackathon/transcend-october-2026/43244671/unspool/-/work_items/3), Duo session ID `9749019`, [MR !5](https://gitlab.com/gitlab-ai-hackathon/transcend-october-2026/43244671/unspool/-/merge_requests/5), [delivery pipeline](https://gitlab.com/gitlab-ai-hackathon/transcend-october-2026/43244671/unspool/-/pipelines/2967584891) | General hands-off security remediation or a hosted mutable backend; the session page is unavailable anonymously, so use the public MR/pipeline |
| Real external instructed repair with operator promotion | [VAmPI issue #1](https://gitlab.com/gitlab-ai-hackathon/transcend-october-2026/43244671/unspool-vampi-delivery/-/work_items/1), [MR !1](https://gitlab.com/gitlab-ai-hackathon/transcend-october-2026/43244671/unspool-vampi-delivery/-/merge_requests/1), [candidate pipeline](https://gitlab.com/gitlab-ai-hackathon/transcend-october-2026/43244671/unspool-vampi-delivery/-/pipelines/2968003131), [post-merge pipeline](https://gitlab.com/gitlab-ai-hackathon/transcend-october-2026/43244671/unspool-vampi-delivery/-/pipelines/2968031105) | Autonomous discovery, arbitrary application safety or independent customer acceptance |
| Before/after HTTP and retained-artifact staging rollback | [Reproduction and exact source/image records](benchmarks/vampi/README.md) | Publicly hosted repaired VAmPI or database restoration; Cloud Build logs/private image require GCP access |
| Real review-controller interruption/resumption | [Recovery procedure and results](benchmarks/recovery/README.md), [controlled MR !2](https://gitlab.com/gitlab-ai-hackathon/transcend-october-2026/43244671/unspool-vampi-delivery/-/merge_requests/2) | Recovery around all trigger/merge/deployment crash points or distributed locking |
| Tested container controls with negative control | [Isolation drill](benchmarks/isolation/README.md) | Kernel escape resistance, all egress channels or hostile multi-tenant qualification |
| Frozen 0.4.7 package, 127 regressions and clean installation | [Package verification pipeline 2969187062](https://gitlab.com/gitlab-ai-hackathon/transcend-october-2026/43244671/unspool/-/pipelines/2969187062), [retained wheel and records](https://gitlab.com/gitlab-ai-hackathon/transcend-october-2026/43244671/unspool/-/releases/v0.4.7), [reproduction guide](JUDGE_GUIDE.md) | Compatibility with arbitrary dependencies/frameworks, live race injection or independent-team installation |
| Small frozen external static feasibility set | [All case labels/results and limitations](benchmarks/external/README.md) | Representative production precision/recall, runtime proof or ungated-agent comparison |
| Source/dependency audit with concrete fixes | [Review record](SECURITY_REVIEW.md), security-audit CI artifacts | Certification or absence of vulnerabilities; LOW/MEDIUM warnings remain visible |

## URLs and dependencies to disclose

- Public code: [Unspool GitLab](https://gitlab.com/gitlab-ai-hackathon/transcend-october-2026/43244671/unspool).
- Live GCP report: [Cloud Run](https://unspool-398376578726.us-central1.run.app).
- Fallback report: [GitLab Pages](https://unspool-site-1032c3.gitlab.io). Remote
  CI verifies the served SHA; [release records](RELEASE.md) identify the delivery
  revision. Raw job-trace APIs require
  login; public pipeline metadata and retained verification records are provided.
- Local execution: CPython 3.10–3.12 qualification, authenticated `glab` for GitLab
  operations, GitLab runner/Duo group enablement and appropriate project roles.
- Model: GitLab's existing foundational Developer flow performs the remote repair;
  its underlying model/version was not independently pinned by Unspool. Optional
  provider-backed local reviews are separate and may transmit selected source.
- Cloud: Cloud Run static report, Artifact Registry, Cloud Build, GitLab OIDC
  workload identity for report delivery. No persistent GCP key is stored in CI.
- Demo runtime/HTTP fixtures use synthetic canaries only. External application
  dependencies remain intentionally vulnerable/old and are not recommended for production.
- No custom Catalog listing is claimed; Developer access in the hackathon project
  is insufficient to manage custom agents there. Catalog is optional distribution.

## Video outline for the author (target 2:40)

| Time | Show actual evidence | Narration boundary |
| --- | --- | --- |
| 0:00–0:20 | Graph report and local graph CRUD | Explain public report versus local controller/CRUD |
| 0:20–0:55 | Real issue, Duo-created external MR and one-file diff | Known-exposure supervised repair; do not imply discovery |
| 0:55–1:25 | Exact candidate pipeline, HTTP gate and controller result | Explain contract/scope checks; label time cuts |
| 1:25–1:50 | Recorded failing gate and successful post-merge evidence | A failed/unknown check stops; baseline GitLab failure's exact cause is unknown |
| 1:50–2:15 | Synthetic hands-off delivery pipeline and Cloud Run health SHA | This is the bounded hands-off run; the deployed object is a static report |
| 2:15–2:40 | Installation evidence, recovery/rollback records and limitations | No general production claim; show reproduction links |

Use real screen recordings and retained results. Do not recreate logs or fake
waiting times. Mark cuts/time compression. Do not show account tokens, private
cloud logs, customer code, copyrighted music or unlicensed assets. The author
records/uploads the public YouTube video and submits; this workflow does neither.

## Author handoff

1. Record the actual functionality using the outline above; upload a public
   YouTube video under three minutes and paste its actual URL into Devpost.
2. Copy the title, description, public code, original and Cloud Run URLs. Select
   Path B / Supervised on the stated basis; personally review the event's entrant
   eligibility and attestations. The organizers retain the final decision.
3. Keep both reports and their billing/accounts available through judging and
   the expected announcement around 16 November. Billing is currently enabled;
   future trial-credit balance/expiry is not established by that check. The
   maintainer owns this ongoing obligation; no automatic billing monitor is claimed.
4. Check that the recorded video matches this scope, contains no credentials or
   private material, then submit before the deadline. The production roadmap,
   additional hosting and Catalog listing are not prerequisites for this
   evaluated-prototype submission.

Rules rechecked 21 October 2026: [official rules](https://gitlab-transcend.devpost.com/rules).
Submission deadline is 27 October 2026, 13:00 UTC / 20:00 WIB; video should be
under three minutes and publicly visible on YouTube. Keep the project available
through the winner announcement, expected around 16 November. Recheck the rules
and all timestamps before final submission.
