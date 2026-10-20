# Unspool delivery and hackathon handoff

Unspool is the renamed LeakHunter project. Existing Python imports and the old
CLI remain compatible. The original MIT-licensed project is
[azharizz/leakhunter](https://github.com/azharizz/leakhunter); its history is retained
in the [public GitLab project](https://gitlab.com/gitlab-ai-hackathon/transcend-october-2026/43244671/unspool).

## Delivery

GitLab CI runs Python regression tests, dashboard checks, and a real synthetic
exposure probe. Only a passing probe can produce the immutable Pages report.
Default-branch pipelines trigger the public deployment project and verify the exact commit through
`health.json`. The live report is read-only; local graph CRUD remains available
through `python -m unspool`. The mutable local analysis server is not published.

The demo uses synthetic customer data only. `demo/policy.yaml` and
`demo/runtime.yaml` define the fixed security and public response contracts.
Returning the complete record fails the exposure gate even though the public
response fields still work. Never merge that deliberately failing fixture.

## Repair handoff

The existing GitLab Duo Developer flow writes the change. Project access
is Developer, so custom-flow management cannot be assumed. Start a narrowly scoped
issue workflow using the local controller with your existing authenticated glab login.
The agent must obey `AGENTS.md`, change only `demo/target/service.py`, and create
a real MR on an `unspool/` branch.

Start from one initial intent:

```sh
python3 -m unspool.handoff --project 87860005 --issue <iid>
```

The controller triggers Duo when no MR exists, otherwise reuses the existing MR.
The Duo runtime token cannot merge into main; the local controller uses the
user's existing authorized glab login without sharing it with Duo. It checks
the complete diff, exact revision, mandatory CI jobs, runtime
evidence, and report revision before merging. It waits for the merged revision's
Pages deployment and production smoke check, then records the pipeline on the
MR. Failed, missing, skipped, manual, or timed-out checks stop the workflow.
It does not change permissions or branch protection.

The hackathon group's Pages site is restricted to members and Developer access
cannot change it. Public delivery therefore uses
[azharizz/unspool-site](https://gitlab.com/azharizz/unspool-site), owned by the same
user. The main pipeline passes its exact SHA to that downstream pipeline, which
rebuilds the public source, reruns the fixed exposure gate, publishes the report,
and checks the live revision. No personal token is stored in CI; the trigger uses
GitLab's temporary job token. The public report is
[Unspool](https://unspool-site-1032c3.gitlab.io). The enterprise Jamf policy on this
Mac blocks browser access to GitLab Pages; remote CI performs the live check.

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
