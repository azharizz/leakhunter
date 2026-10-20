# Unspool on Cloud Run

Public service: https://unspool-398376578726.us-central1.run.app

GitLab Pages remains the fallback at https://unspool-site-1032c3.gitlab.io.
Both deployments serve a sanitized immutable graph report. Local CRUD, repository
execution, credentials, SQLite state and the handoff controller are not hosted.

## Delivery

The `deploy-cloud-run` job requires the `verify-exposure` artifact and runs
`bash deploy/cloudrun/deploy.sh`. It verifies `health.json` against `CI_COMMIT_SHA`,
builds only the public files using Cloud Build, deploys the revision, and runs the
same exact-revision smoke check as Pages. Failed deployment checks fail the
pipeline and prevent the controller from reporting completion.

Configuration is intentionally fixed to the dedicated hackathon deployment:

| Resource | Value |
| --- | --- |
| GCP project | `project-df38a01c-6abb-4bc3-9c1` |
| Project number | `398376578726` |
| Region | `us-central1` |
| Cloud Run service | `unspool` |
| Artifact Registry | `unspool` (Docker) |
| Build staging bucket | `project-df38a01c-6abb-4bc3-9c1-unspool-build` |
| Workload identity pool / provider | `unspool-gitlab` / `gitlab` |

## Authentication and permissions

No service account keys or GCP access tokens are stored in GitLab. GitLab issues
a temporary OIDC token with audience `https://gitlab.com`. The provider uses
issuer `https://gitlab.com`, subject `assertion.sub`, and project attribute
`assertion.project_id`. Its condition is:

```text
assertion.project_id=='87860005' && assertion.ref=='main' && assertion.ref_type=='branch' && assertion.ref_protected=='true'
```

The principal set for project `87860005` can impersonate `unspool-deploy` through
`roles/iam.workloadIdentityUser`. All service accounts belong to the GCP project:

| Identity | Permissions |
| --- | --- |
| `unspool-deploy` | Cloud Build Editor and Service Usage Consumer on the project; Run Developer on this service; Artifact Registry Reader on this repository; Storage Object Admin and Legacy Bucket Reader on the staging bucket; Service Account User on the builder and runtime only |
| `unspool-build` | Artifact Registry Writer on this repository; Storage Object Viewer on staging; Logs Writer on the project |
| `unspool-web` | No project roles; runs the static server as UID 101 |
| `allUsers` | Run Invoker on this public read-only service only |

Enabled APIs: Cloud Run, Cloud Build, Artifact Registry, IAM Credentials and STS.
The staging bucket has uniform access and public-access prevention. The initial
service and IAM bindings are provisioned by the authorized GCP user; subsequent
deployment jobs cannot change service IAM or create unrelated Cloud Run services.

## Cost and availability

The service uses request-based billing, 1 vCPU, 256 MiB, minimum zero and maximum
one instance, concurrency 80, and a 30-second request timeout. It has no database,
load balancer, custom domain or persistent VM. This keeps the demo small but does
not impose a spending cap. Cloud Build, image storage, logs and network transfer
can incur charges beyond applicable free quotas. Trial balance and expiry are
account-specific; keep billing valid through judging.

The workflow still starts locally with an authenticated `glab` session:

```sh
python3 -m unspool.handoff --project 87860005 --issue <iid>
```

Cloud Run hosts the public report only. Keep the local controller running until
the full workflow returns `DEPLOYED_AND_VERIFIED`.

## Fresh workflow evidence

Before adding Google Cloud, [issue #2](https://gitlab.com/gitlab-ai-hackathon/transcend-october-2026/43244671/unspool/-/work_items/2)
completed the full workflow without intervention: the controller triggered Duo,
Duo created [MR !3](https://gitlab.com/gitlab-ai-hackathon/transcend-october-2026/43244671/unspool/-/merge_requests/3),
the fixed CI gates passed, the controller merged it, and
[pipeline 2967534949](https://gitlab.com/gitlab-ai-hackathon/transcend-october-2026/43244671/unspool/-/pipelines/2967534949)
deployed and verified revision `ff1264c4f0f38faa498ab496e6cab7ab70292066`.
This demonstrates the bounded synthetic workflow, not unrestricted repair safety.
