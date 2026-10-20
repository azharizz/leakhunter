# External VAmPI validation — known intentional exposure

Upstream: [erev0s/VAmPI](https://github.com/erev0s/VAmPI), MIT, copyright 2020 erev0s.
Validation fork: [azharizz/unspool-vampi-validation](https://gitlab.com/azharizz/unspool-vampi-validation).
Pinned upstream source: `f16052dce83f05847133ec98f01c5193a41de7d8`.
The upstream MIT notice is preserved in the imported repository.

The author documents excessive exposure at `/users/v1/_debug`. This benchmark
tests that published behavior with a synthetic canary over actual HTTP. It is
an externally authored intentional security lab, not a customer production system,
an independent human evaluation, a new vulnerability discovery, or a measured
Unspool detection/repair result yet.

## Observed baseline, 20 October 2026

[Cloud Build d4c0faaf-67f6-444a-b9d6-7a33cff8ee12](https://console.cloud.google.com/cloud-build/builds;region=us-central1/d4c0faaf-67f6-444a-b9d6-7a33cff8ee12?project=398376578726)
successfully reproduced the expected vulnerability:

- Create a disposable dummy database and register a canary user: HTTP 200.
- Public user list preserves that username and excludes its canary password.
- Public user lookup preserves that username and excludes its canary password.
- Debug user response includes that canary password: **security failed**.

The probe reports `http_functionality_passed: true`,
`secret_observed_at_http_response: true`, `security_passed: false`, and
`expected_behavior_reproduced: true`. The successful benchmark job means the
vulnerability was reproduced, not that the application passed security validation.

The application container runs as UID/GID 10001, with no network, no published
ports, read-only source/root filesystem, dropped capabilities, no privilege
escalation, bounded CPU/memory/processes, and ephemeral database storage. Only
loopback HTTP inside that container is used. Cloud build/dependency download
stages require network access; they are separate from application execution.
The application receives no mounted credentials, host Docker socket or deployment
token. This is evidence for these execution settings, not a complete isolation audit.

Two earlier runs failed during harness startup, before security evaluation:
`673b82f6-d6eb-4568-b270-578e783fea08` (Python import path) and
`c1ffcf22-1850-4ae7-9f0d-c3ba255b34f1` (upstream circular-import bootstrap).
Those failures remain setup errors/unknown security outcomes, not false negatives.
Only the harness import/bootstrap changed; the pinned upstream application did not.

## Reproduce

With an authorized GCP account and the documented dedicated build service account:

```sh
gcloud builds submit benchmarks/vampi \
  --config=benchmarks/vampi/cloudbuild.yaml \
  --project=project-df38a01c-6abb-4bc3-9c1 --region=us-central1 \
  --service-account=projects/project-df38a01c-6abb-4bc3-9c1/serviceAccounts/unspool-build@project-df38a01c-6abb-4bc3-9c1.iam.gserviceaccount.com \
  --gcs-source-staging-dir=gs://project-df38a01c-6abb-4bc3-9c1-unspool-build/source
```

`cloudbuild.yaml` contains the isolation options and exact upstream checkout.
Do not expose the deliberately vulnerable application to the public internet.
`probe.py --expect-fixed` defines the candidate acceptance check: public identity
behavior must remain, and debug responses must exclude passwords/admin flags.
That candidate run is not yet completed. The upstream dependency tree includes
intentionally old packages and has not been claimed safe for production.

Next work: wire this real HTTP observation into Unspool's independently pinned
runtime evidence, produce a bounded real repair MR, test the candidate with the
fixed expectation, retain negative controls, and compare with the ungated agent.
Keep this baseline distinct from those later outcomes in all metrics.

## Pinned repair acceptance harness

`ci-verify.sh` exports the exact candidate revision without Git metadata, builds
dependencies separately, and runs the frozen fixed-behavior HTTP probe with the
same container restrictions. It passes no CI variables or credentials into the
application container. `report.py` runs outside that container and only adapts
an exact positive result into the handoff evidence contract, recording the source
SHA and resolved image ID. This is HTTP acceptance of a known exposure; it does
not represent an Unspool analyzer discovery.

The validation repository must fetch these files from a pinned Unspool commit,
and pin its CI/agent instructions in the operator configuration. Its repair may
change only `api_views/users.py`. GitLab's hosted runner/Docker service and the
probe's application process are not a verified sandbox for actively malicious
repositories. This experiment does not close the hostile-code isolation gate.
No raw application output, database or source archive is published as an artifact.
