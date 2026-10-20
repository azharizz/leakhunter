# Unspool delivery and hackathon handoff

Unspool is the renamed LeakHunter project. Existing Python imports and the old
CLI remain compatible. The original MIT-licensed project is
[azharizz/leakhunter](https://github.com/azharizz/leakhunter); its history is retained
in the [public GitLab project](https://gitlab.com/gitlab-ai-hackathon/transcend-october-2026/43244671/unspool).

## Delivery

GitLab CI runs Python regression tests, dashboard checks, and a real synthetic
exposure probe. Only a passing probe can produce the immutable Pages report.
Default-branch pipelines publish that report and verify its exact commit through
`health.json`. The live report is read-only; local graph CRUD remains available
through `python -m unspool`. The mutable local analysis server is not published.

The demo uses synthetic customer data only. `demo/policy.yaml` and
`demo/runtime.yaml` define the fixed security and public response contracts.
Returning the complete record fails the exposure gate even though the public
response fields still work. Never merge that deliberately failing fixture.

## Repair handoff

The existing GitLab Duo Developer flow is the intended runtime. Project access
is Developer, so custom-flow management cannot be assumed. Launch an available
Developer flow from a GitLab issue or MR with a narrowly scoped repair goal.
The agent must obey `AGENTS.md`, change only `demo/target/service.py`, and create
a real MR on an `unspool/` branch.

After opening a non-draft MR, the agent can run:

```sh
python3 -m unspool.handoff --project 87860005 --merge-request <iid>
```

The controller uses the flow's existing `GITLAB_TOKEN`, or authenticated `glab`
locally. It checks the complete diff, exact revision, mandatory CI jobs, runtime
evidence, and report revision before merging. It waits for the merged revision's
Pages deployment and production smoke check, then records the pipeline on the
MR. Failed, missing, skipped, manual, or timed-out checks stop the workflow.
It does not change permissions or branch protection.

An implementation and passing unit tests are not proof of a hands-off run.
Claim hands-off only after a real Duo session creates the repair and completes
merge, deployment, and smoke verification without intermediate human approval.
Retain the session, MR, pipeline, and live revision links as evidence.

## Path B submission

The current event is [Life After Code](https://gitlab-transcend.devpost.com/).
The earlier gitlab.devpost.com event has ended. The current deadline is
27 October 2026, 13:00 UTC / 20:00 WIB. Check the event's current rules before
submitting. Link the original project and explain the new GitLab automation.
Keep the live deployment available through judging, and record a public YouTube
demo under three minutes using real session, CI, MR, and deployment results.
No hackathon entry or video has been submitted by this repository workflow.
