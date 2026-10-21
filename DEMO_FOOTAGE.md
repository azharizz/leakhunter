# Unspool demo footage guide

Prepared 21 October 2026, WIB. Final cut: **2:00**, using release **0.4.7**.
This is a recording plan, not a new execution record. No app, tests, agent workflow
or deployment was run to create this guide. Commands below are for later use.

## The story to show

**Unspool makes an agent's proposed change reviewable: inspect the graph, check
the bounded MR, inspect verification, then confirm the delivered revision.**

Use the external VAmPI repair as the main **supervised** example. Show the bounded
synthetic hands-off delivery separately. Record actual UI interactions and browse
the retained historical workflow evidence; a new agent run is not necessary.

Keep these distinctions visible in captions:

| Footage | Accurate caption |
| --- | --- |
| Local graph and annotation editing | `Local app · trusted synthetic fixture · Unspool 0.4.7` |
| External issue, MR and pipelines | `Recorded external lab repair · operator approval` |
| Vulnerable/repaired HTTP records | `Retained before/after evidence · one known exposure` |
| Original synthetic delivery | `Separate bounded hands-off demo · historical run` |
| Public Cloud Run page | `Live read-only report · controller runs locally` |

The local graph is the bundled synthetic fixture. It is **not** the VAmPI
application's graph. The external HTTP replays and the older GitLab repair
pipeline are also separate records; do not edit them into one continuous run.

## 1. Prepare the recording workspace

- [ ] Use the pinned installation in [JUDGE_GUIDE.md](JUDGE_GUIDE.md). Avoid an
  unrelated development installation when presenting release 0.4.7.
- [ ] Record one app/browser window at 1920×1080 if available. Use readable browser
  zoom and terminal text; check the exported video at normal playback size.
- [ ] Hide notifications, unrelated tabs, bookmarks and personal account details.
  Keep terminal environment dumps, credentials and cloud account settings off screen.
- [ ] Record screen footage without narration. Keep a few seconds before and
  after every interaction so clips are easy to trim.
- [ ] Keep an untouched original of each recording. Put annotations/captions in
  the edit; do not alter a result, log, timestamp or commit identifier.
- [ ] Preload the public pages below. If one needs login, use the public retained
  evidence instead. The Duo session page is not available anonymously, and raw
  GitLab job-trace APIs require authorized access.

Suggested local folder structure; create it yourself when recording:

```text
unspool-demo/
  raw/
    01-local-graph.mov
    02-annotation-crud.mov
    03-snapshot.mov
    04-external-issue-mr.mov
    05-external-pipeline.mov
    06-http-before-after.mov
    07-synthetic-delivery.mov
    08-cloud-report-health.mov
    09-release-proof.mov
  audio/
    narration.wav
  export/
    unspool-demo.mp4
```

## 2. Open the evidence tabs

These references come from the verified release handoff. Check what actually
loads when you record; this guide does not assert fresh availability.

| Tab | Open | Focus the camera on |
| --- | --- | --- |
| Local app | `http://127.0.0.1:8080` after starting it | Graph, inspector, annotation CRUD and snapshots |
| External intent | [VAmPI issue #1](https://gitlab.com/gitlab-ai-hackathon/transcend-october-2026/43244671/unspool-vampi-delivery/-/work_items/1) | The bounded repair request |
| External change | [VAmPI MR !1](https://gitlab.com/gitlab-ai-hackathon/transcend-october-2026/43244671/unspool-vampi-delivery/-/merge_requests/1) | One-file diff in `api_views/users.py`; public fields preserved, password/admin fields excluded |
| Candidate verification | [Pipeline 2968003131](https://gitlab.com/gitlab-ai-hackathon/transcend-october-2026/43244671/unspool-vampi-delivery/-/pipelines/2968003131) | Actual job names, successful status and candidate revision |
| External delivery | [Pipeline 2968031105](https://gitlab.com/gitlab-ai-hackathon/transcend-october-2026/43244671/unspool-vampi-delivery/-/pipelines/2968031105) | Successful checks after operator promotion |
| HTTP before/after | [Independent HTTP record](https://gitlab.com/gitlab-ai-hackathon/transcend-october-2026/43244671/unspool/-/blob/main/benchmarks/vampi/results.independent.json) | `negative_run.diagnostic`, then positive `evidence.gate` and `health` |
| Separate hands-off demo | [Synthetic issue #3](https://gitlab.com/gitlab-ai-hackathon/transcend-october-2026/43244671/unspool/-/work_items/3), [MR !5](https://gitlab.com/gitlab-ai-hackathon/transcend-october-2026/43244671/unspool/-/merge_requests/5), [pipeline 2967584891](https://gitlab.com/gitlab-ai-hackathon/transcend-october-2026/43244671/unspool/-/pipelines/2967584891) | The actual bounded issue-to-report chain |
| Public output | [Cloud Run report](https://unspool-398376578726.us-central1.run.app) | Read-only graph report |
| Output identity | [Cloud Run health](https://unspool-398376578726.us-central1.run.app/health.json) | `status`, `verified` and exact `commit` |
| Final main verification | [Pipeline 2969209430](https://gitlab.com/gitlab-ai-hackathon/transcend-october-2026/43244671/unspool/-/pipelines/2969209430) | Regression, installed-wheel, exposure and deployment checks |
| Release | [Unspool 0.4.7](https://gitlab.com/gitlab-ai-hackathon/transcend-october-2026/43244671/unspool/-/releases/v0.4.7) | Wheel, checksums, verification bundle and final checks |
| Retained final proof | [submission-checks.json](https://gitlab.com/api/v4/projects/87860005/packages/generic/unspool/0.4.7/submission-checks.json) | Version, successful pipeline, clean main, live revision and access checks |

## 3. Capture the local graph and CRUD

If the pinned app is not already installed, follow the judge guide first. Keep
dependency installation out of the main video unless it communicates something
essential. The commands here assume its installed virtual environment and source.

For later use only, in a terminal:

```sh
# Replace this with the absolute path of the pinned checkout from JUDGE_GUIDE.md.
UNSPOOL_SOURCE_DIR=/absolute/path/to/unspool

# Use a fresh directory outside the source and target repositories for this take.
UNSPOOL_FOOTAGE_STATE=$(mktemp -d /tmp/unspool-footage.XXXXXX)

"$UNSPOOL_SOURCE_DIR/.venv/bin/python" -I -m unspool \
  --repository "$UNSPOOL_SOURCE_DIR/demo/target" \
  --policy "$UNSPOOL_SOURCE_DIR/demo/policy.yaml" \
  --runtime-manifest "$UNSPOOL_SOURCE_DIR/demo/runtime.yaml" \
  --runtime-backend local --provider-url '' \
  --data-dir "$UNSPOOL_FOOTAGE_STATE" --port 8080
```

Use `--runtime-backend local` only for this committed trusted synthetic fixture.
It is not a sandbox for unfamiliar code. If port 8080 is occupied, choose another
unused port and use its matching browser URL. Stop the server with Ctrl-C after
recording. No remote issue command, repair trigger, merge or deployment is needed.

Capture these takes independently, then keep the clearest moments:

| Take | Exact actions | What to retain |
| --- | --- | --- |
| Graph, 20–30 seconds | Open the local URL. Click **Analyze**. Wait for the actual result. Click a node and inspect its record. Use **Fit** or a filter if needed. | A readable graph and a selected node; preserve real loading behavior in the raw take |
| Node CRUD, 30–45 seconds | In **Nodes**, click **Add node**. Set ID `demo-note-a`, Label `Review required`, Kind `transform`. Click **Create node**. Select the new annotation, change its Label to `Reviewed by maintainer`, and save. | Create, read and update in the inspector; use the selector/search if the graph filter hides the annotation |
| Relationship CRUD, 30–45 seconds | Create another annotation: ID `demo-note-b`, Label `Evidence checked`, Kind `sink`. Switch to **Edges**, choose **Add edge**, set ID `demo-link`, relationship `DATA_FLOW`, and endpoints to the two demo annotations. Create/select the edge, then delete it. | A real relationship created, inspected and removed |
| Cleanup, 10–15 seconds | Return to **Nodes**. Select and delete only `demo-note-a` and `demo-note-b`. | Successful deletion of your annotations; do not delete analyzer-generated records |
| Snapshot, 15–20 seconds | Open **Workspace settings & snapshots**, select the saved analysis, click **Inspect snapshot**, then **Return to live knowledge**. | The saved analysis view and read-only editing state |

For the final edit, node create/update/delete plus a short graph inspection is
enough. Relationship CRUD and snapshot navigation are useful spare footage; use
them only if they fit. Annotation changes do not repair application code or
establish that a release passed a security check.

## 4. Capture the GitLab workflow and verification

### External supervised repair — essential

1. Record the issue title/request, then cut to MR !1. Caption the transition
   **“Historical run — opening retained results.”**
2. Open the MR diff and frame the actual change in `api_views/users.py`. Explain
   that Duo projected public user fields and excluded password/admin fields.
3. Record the successful candidate pipeline and then the post-merge pipeline.
   Show identifiers legibly, rather than rapidly scrolling long logs.
4. State that operator review preceded promotion. Do not click merge buttons or
   imply that viewing these records reruns the agent.

The fixed external source is
`c146bd1b9ee9fbe2730c316675de1fa7e55f0fa1`. The external repair and its
verification predate patch 0.4.7; the patch is not a new external repair.

### One clear failure/success comparison — essential

Open the independent HTTP JSON record and capture two close crops:

- **Before:** `negative_run.source_sha` is the original vulnerable revision;
  `diagnostic.status` is `STOPPED`, `functional_passed` is `true`,
  `security_passed` is `false`, and `secret_observed` is `true`.
- **After:** positive `evidence.gate.passed` is `true`, runtime status is
  `COMPLETED`, and `health.commit` identifies the repaired source.

Suggested caption: **“Functional success alone is insufficient. The configured
security check must also pass.”** This is a recorded worker verification failure,
not footage of a fresh end-to-end failed agent promotion. The five positive HTTP
cases exercise one known lab exposure; they are not five vulnerability repairs.

### Delivery and release — essential

1. Briefly show the separate synthetic hands-off pipeline. Say explicitly that
   its task normalized display names while preserving a secret-field restriction.
2. Open Cloud Run and its health JSON. Pair the **currently observed** commit with
   its own pipeline, not automatically with the older hands-off run.
3. Show release 0.4.7 and final retained checks. If showing test counts, say
   **“127 regression tests at the verified revision,”** not “127 vulnerabilities.”

Recorded reference identities:

| Record | Identity |
| --- | --- |
| Frozen 0.4.7 package source | `722f3955bb44c270b24f248b9046f0f26df93a76` |
| Verified main/report at handoff | `3cdce65268d28ef58c3f9aa45edc46f8b9d98b8d` |
| Final main pipeline | `2969209430` |
| Earlier synthetic hands-off delivery | `834f456623421a6150f16c2b82fd950910e0cb9a`, pipeline `2967584891` |

Different SHAs here are expected: package source, documentation/report delivery,
external repair and historical hands-off delivery are different revisions.
If hosting now serves another SHA, show its actual matching evidence or use the
retained record labeled with its date. Never substitute an expected health result.

## 5. Final silent edit — 2:00

The exported file is `demo-footage/unspool-demo.mp4`. It keeps the original UI
recording and adds a short animated evidence walkthrough between the issue and
repair footage. It has no voice track.

| Final time | Footage | Message |
| --- | --- | --- |
| 0:00–0:12 | Product framing and the actual VAmPI issue | A bounded, known exposure is the example |
| 0:12–0:16 | Evidence-walkthrough title | Isolated copy; synthetic canary; no secret value shown |
| 0:16–0:27 | Five-step HTTP request path from the checked-in plan | Disposable database, synthetic canary, public list/lookup, then debug route |
| 0:27–0:38 | Retained negative-run fields | HTTP/function checks completed; security failed; canary observed; worker result stopped |
| 0:38–0:48 | Retained positive evidence and tested revision | Same gate passed after the bounded repair |
| 0:48–0:55 | Separate synthetic issue #3 → MR !5 → pipeline #2967584891 | A different historical task, clearly separated from VAmPI |
| 0:55–1:09 | Four steps for a different repository | Define behavior, restrict scope, set independent checks, start in review mode |
| 1:09–1:21 | Before/after summary and actual MR diff | Public fields stay; password/admin fields are removed from the debug response |
| 1:21–1:29 | Candidate pipeline | Inspect the recorded candidate checks |
| 1:29–1:33 | Before/after summary | Read the worker result separately from promotion evidence |
| 1:33–1:41 | Post-promotion pipeline | Confirm the recorded post-promotion checks |
| 1:41–1:45 | Read-only Cloud Run report | The public report is not the local controller |
| 1:45–1:49 | Local graph and annotation controls | Inspect the trusted fixture; annotations do not repair code |
| 1:49–1:57 | Task-boundary card | Scope the task, checks, and human decision |
| 1:57–2:00 | Scope and limitation card | One known lab exposure; arbitrary-repository safety is unproven |

Cursor movement, click pulses and focused highlights are visual guidance. The
negative-run panel is a retained worker verification result, not a newly staged
failed promotion. The five configured HTTP cases cover one known exposure. The
synthetic workflow is historical and separate. Keep those labels and the final
limitations card visible; do not imply a fresh end-to-end run or unknown-leak
discovery.

## 6. Final recording checklist

- [ ] Show actual application interaction, the real external MR, verification and
  the deployment boundary; avoid making the video only slides or static JSON.
- [ ] Clearly label local synthetic UI, historical external repair, independent
  HTTP checks, and the separate hands-off demo.
- [ ] Keep all values, outcomes, dates and revision identifiers faithful to the
  source shown. If a check fails during recording, retain the failure honestly.
- [ ] Do not claim production readiness, independent customer adoption, unknown
  vulnerability discovery, measured time savings or guaranteed event eligibility.
- [ ] No tokens, private source, account settings, customer data or unlicensed
  audio/assets appear in the final export.
- [ ] Watch the full export at ordinary playback size. Confirm it has no audio
  track, the evidence labels match the visible record, and text remains readable.
- [ ] Upload the finished video publicly to YouTube and check it signed out.
  Add the actual URL to the submission. This guide does not upload or submit it.

Fastest recording route: capture local graph/node CRUD, external MR/pipelines,
the retained HTTP comparison, Cloud Run health and release proof. Skip a new
agent trigger, full installation recording, additional cloud runs and long logs.
