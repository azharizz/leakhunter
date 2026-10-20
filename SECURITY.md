# Security scope and reporting

Unspool is currently an evaluated prototype, not a certified security boundary.
The portable handoff initially supports explicit Python application-file scopes
on GitLab.com, with review-only behavior by default. The public Cloud Run/Pages
service serves immutable sanitized reports and accepts no repository-execution
or repair requests. Never expose the mutable local API as a shared public service.

## Trust boundaries

See [THREAT_MODEL.md](THREAT_MODEL.md) for the control/evidence matrix and known
gaps, including same-process runtime tampering and dependency-build privilege.
The [controlled isolation drill](benchmarks/isolation/README.md) records tested
container settings and a credential-exposure negative control, with its limits.
See [SECURITY_REVIEW.md](SECURITY_REVIEW.md) for source/dependency scan results,
concrete fixes, remaining warnings and the CI audit policy.

- Operators own and review configuration, policy, runtime manifests, verification
  logic, credentials and promotion authorization. Repository/issue/model content
  is untrusted data; it cannot grant permissions or expand a repair scope.
- Install the verifier/controller outside the repair checkout. A versioned
  allowlist and content pins protect specific contracts, not arbitrary code semantics.
- Analyze unfamiliar application/build/dependency code only inside appropriate
  disposable isolation without host credentials or privileged mounts. The explicit
  `local` runtime backend is for trusted targets only. A separate process is not
  containment, and a shared container is not sufficient for hostile tenants.
- Keep execution, dependency installation, verification and promotion privileges
  separate. Do not expose cloud metadata, host Docker sockets or deployment tokens
  to code under test. Restrict network access and resource use.
- A passing canary test establishes behavior only for exercised paths. Missing,
  unsupported or failed execution is not safe. Do not claim whole-program proof.
- Provider-backed reviews may transmit selected source/context to the configured
  model endpoint. Review provider behavior and repository-owner authorization
  before enabling it for private code. Model advice cannot replace runtime evidence.
- Private controller state prevents duplicate dispatch within its recorded scope;
  it is not a distributed job scheduler or a guarantee that remote work was canceled.

## Vulnerability reports

Do not post secrets, private customer code or unpatched findings in public issues.
For a flaw in Unspool, open a **confidential** issue in the Unspool GitLab project
and verify confidentiality is enabled before sending sensitive details. If that
option is unavailable, request a private reporting route without disclosing the
vulnerability publicly. No response-time SLA or security certification is claimed.
Findings in third-party targets belong in that owner's authorized private process.

Include the affected release/commit, prerequisite permissions, minimal synthetic
reproduction, expected/actual behavior and impact. Omit real credentials and data.

Production adoption is gated by the threat-model, isolation, independent review,
evaluation and operational work in ROADMAP.md. This document does not mark those
gates complete or authorize security testing against unrelated live services.
