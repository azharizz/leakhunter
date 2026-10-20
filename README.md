# Unspool

Evidence before agent promotion: bounded GitLab Duo repairs, explicit release
gates, and a graph that shows what was verified.

Start with [JUDGE_GUIDE.md](JUDGE_GUIDE.md) for the pinned local demonstration.
[Release 0.4.7](https://gitlab.com/gitlab-ai-hackathon/transcend-october-2026/43244671/unspool/-/releases/v0.4.7)
retains the CI-built wheel and verification bundle; [RELEASE.md](RELEASE.md)
records its source and checksum. [SUBMISSION.md](SUBMISSION.md) contains the
submission text, evidence map, Path B basis and author handoff.

For installation on another GitLab.com repository, read [ADOPTION.md](ADOPTION.md).
The 0.4.7 package accepts operator-owned project configuration, defaults to
review-only behavior, and records private durable intent for safe resumption.
Portable repair promotion currently allows explicitly configured Python application
files only. JavaScript, TypeScript, Go and Rust analysis remains experimental;
language parsing alone does not establish reliable security detection or repairs.
Use [ROADMAP.md](ROADMAP.md) for the current evidence gates and outstanding work;
[SECURITY.md](SECURITY.md) defines the trust boundaries and reporting route.

The [GitLab project](https://gitlab.com/gitlab-ai-hackathon/transcend-october-2026/43244671/unspool)
contains the redesign, MIT history, actual GitLab Duo integration, and CI delivery.
The [Cloud Run report](https://unspool-398376578726.us-central1.run.app) and
[Pages fallback](https://unspool-site-1032c3.gitlab.io) are read-only; graph CRUD runs locally.
See [HANDOFF.md](HANDOFF.md) for the one-command issue workflow, deployment project,
verification boundaries, and required local glab authentication. The older local
repair engine described below remains a separate simulation of remote MR creation.

Unspool is the new product name for the original LeakHunter project. Install with
`pip install .` and run `unspool --help` or `python -m unspool --help`. The
`leakhunter` Python imports and command remain compatible with existing callers.

The GitLab pipeline verifies the Python suite, dashboard, and a committed
synthetic exposure case before publishing an immutable, read-only graph to
Cloud Run and GitLab Pages. The full local app retains annotation CRUD. A
published report does not expose repository execution or repair endpoints.

## Verified workflow and evidence

On 20 October 2026, a fresh run completed without intermediate human edits,
retries, or approvals:

1. The local controller triggered the real GitLab Duo Developer flow from
   [issue #3](https://gitlab.com/gitlab-ai-hackathon/transcend-october-2026/43244671/unspool/-/work_items/3).
2. Duo session `9749019` changed only the allowlisted synthetic service and created
   [MR !5](https://gitlab.com/gitlab-ai-hackathon/transcend-october-2026/43244671/unspool/-/merge_requests/5).
   The session page is unavailable anonymously; the MR and pipeline are public.
3. The controller checked the complete diff, exact source revision, required CI
   jobs, and independent runtime evidence before merging through the user's
   existing authorized `glab` login. The Duo runtime's permissions were unchanged.
4. [Pipeline 2967584891](https://gitlab.com/gitlab-ai-hackathon/transcend-october-2026/43244671/unspool/-/pipelines/2967584891)
   passed all 77 Python tests, dashboard checks, the exposure gate, Cloud Run
   delivery, Pages delivery, and live exact-revision smoke checks. Both hosts
   served commit `834f456623421a6150f16c2b82fd950910e0cb9a`.
5. The controller returned `DEPLOYED_AND_VERIFIED` and recorded the pipeline and
   merged revision on the MR. These links describe that observed run; later
   deployments can serve newer commits, identified by their `health.json`.

To start a bounded issue workflow:

```sh
python3 -m unspool.handoff --project 87860005 --issue <iid>
```

The controller must remain running locally with an authenticated `glab` session.
Cloud Run hosts only the public report, not the controller or a multi-user CRUD
backend. GCP deployment uses short-lived GitLab OIDC credentials restricted to
this project's protected `main` branch; no service account keys are stored in CI.
See [deployment code, permissions, and cost settings](deploy/cloudrun/README.md).

## What these results establish

A separate external application experiment now has a real instructed repair:
[VAmPI MR !1](https://gitlab.com/gitlab-ai-hackathon/transcend-october-2026/43244671/unspool-vampi-delivery/-/merge_requests/1)
removes password/admin fields from its published debug exposure while the frozen
HTTP acceptance checks preserve public identity behavior. Candidate pipeline
`2968003131` passed, and the installed 0.4.0 controller independently returned
`READY_FOR_REVIEW` for its exact revision before operator promotion. See the
[reproduction record and limitations](benchmarks/vampi/README.md).
VAmPI is an intentionally vulnerable external security lab; this result is not
unknown-vulnerability discovery or proof of general repair accuracy.

**This is a working hackathon prototype with real platform integration and
controlled synthetic validation. It is not a production-grade security product.**
Synthetic means the application, sensitive markers, labels, and expected behavior
were deliberately constructed. The execution, captured observations, GitLab Duo
session, MR, CI jobs, merge, cloud deployment, and HTTP smoke checks were real.

| Evidence | What it establishes | What it does not establish |
| --- | --- | --- |
| 127 Python regression tests, dashboard checks and installed-wheel CI for 0.4.7 | The checked behavior passed at the frozen release; see [release records](RELEASE.md) | Absence of bugs, production load capacity, or compatibility with every repository |
| Fixed synthetic exposure probe | The exercised response preserved its public contract and did not return the configured secret marker | Safety of unexecuted inputs, paths, sinks, dependencies, or business rules |
| Fresh Duo-to-production run | The bounded workflow completed on actual GitLab and GCP infrastructure without an intermediate human action | Reliability across arbitrary tasks, adversarial repositories, permission models, or service outages |
| Deployed revision smoke checks | Public HTTP endpoints served the exact verified report revision | A deployed customer backend, online scanning service, or hosted CRUD application |
| Synthetic precision/recall measurements below | Performance on the stated executed labeled fixtures | Real-world detection accuracy or a representative independent benchmark |

The latest fresh Duo tasks changed display-name normalization while preserving
the secret-field restriction. They demonstrate delivery and verification of a
bounded change; they are **not evidence of discovering and repairing an unknown
vulnerability in a real production application**. Earlier generated-target repair
tests are separate synthetic experiments described below.

Before considering production adoption, evaluate consented real applications
with independently established findings, project-specific policy and executable
regressions, safe execution isolation, and a reviewable repair process. Measure
misses, false positives, blocked/unknown outcomes, and repair regressions on
previously unseen cases. Authentication and authorization for hosted mutations,
concurrent-user/load behavior, recovery and rollback, adversarial inputs, and
operational monitoring also need dedicated validation. Do not use a passing demo
gate as a general authorization to release customer code.

Policy-aware exposure analysis for Python, JavaScript, TypeScript, Go, and Rust, executed synthetic evidence, and independently verified local repairs.

`leakhunter/` is the installable application. It does not import `example/`, bundle a target repository, load `.env` automatically, or create state on import. `example/` owns its vulnerable application, policy, executable cases, generator, and launcher.

## Architecture status

The engine experiments below are historical observations from the earlier local
workflow; the GitLab/GCP results above were verified on 20 October 2026. Neither
establishes universal production readiness. `leakhunter/` remains configurable for
external repositories; executable fixtures and scenario generation remain in `example/`.

Production layout is grouped by responsibility: `leakhunter/app.py` is the composition root; `api/` owns HTTP transport; `application/` owns orchestration and operation decorators; `providers/` owns model factories/clients; `execution/` owns runtime and worker code; `repairs/` owns repair verification; `storage/` owns the knowledge bank; `analyzers/`, `policy/`, and `static/` remain focused packages/assets. The package root contains only the composition entrypoints: `app.py`, `__init__.py`, and `__main__.py`.

Pattern boundaries are intentional: `application.decorators.exclusive` decorates long-running operations with the shared concurrency guard, while `providers.openrouter.ProviderFactory.create` is the Factory Method for provider transport selection. Stable value objects and pure analyzers do not receive artificial pattern wrappers.

| Architecture area | Current status | Actual implementation and verification |
| --- | --- | --- |
| Knowledge graph UI | Implemented; browser-verified | `leakhunter/static/index.html` renders the Python code-property graph with node/edge filtering, inspection, and immutable snapshot selection. |
| Knowledge CRUD | Implemented; browser-verified | Node and edge create/read/update/delete through the API and UI. Updates preserve analyzer metadata; live annotations survive scans without rewriting historical snapshots. |
| Findings dashboard | Implemented with scoped runtime evidence | Displays source/sink paths, policy reasons, static `POSSIBLE` candidates, and `CONFIRMED_IN_TEST` evidence only for matching executed observations. Provider advice cannot confirm findings. |
| Complex leak example | Implemented; executable synthetic application | `example/fixtures/` contains a multi-module customer application with HTTP/CLI entrypoints, repository access, logging, analytics, tenant checks, and functional regressions. Ten runtime cases cover leaking and permitted behavior. |
| Synthetic case generation | Implemented; executable targets measured | `example/generator.py` materializes runnable repositories, manifests, policies, and labels for four flow families with positive/safe pairs. Eight generated targets were executed in Docker. The separate 137,200-combination metadata space is not claimed as executed coverage. |
| Runtime evidence simulation | Replaced with actual execution/capture | `leakhunter/execution/runtime.py` and `leakhunter/execution/runtime_worker.py` invoke target callables and inspect returns, logs, configured HTTP/call boundaries, and artifacts. Captured synthetic marker hashes establish scoped observations; marker-print output is not used as proof. |
| Metrics | Implemented; measured synthetic results | Stores duration, findings, provider status/latency, policy version, labeled TP/FP/TN/FN/unknown counts, precision, recall, false-safe rate, and repair success. The ten-case example measured runtime TP=4, TN=6, FP=0, FN=0; static misses and false positives remain documented. |
| OpenRouter Decision API | Source-backed typed Luna reviews; live response verified | Uses `openai/gpt-6-luna-decisions` through `/api/alpha/decisions`. Reviews source/graph boundaries even with zero static findings, with scoped runtime evidence and explicit unknowns. A real source-backed Luna request succeeded; the HTTP/Docker/snapshot/dashboard path also passed with a loopback typed-provider fixture. Advice never opens a deterministic gate. |
| GitLab Duo simulation | Implemented through OpenRouter; Flash repair verified on a generated target | Uses `deepseek/deepseek-v4.1-flash` for bounded structured patch proposals through chat completions. A generated-target proposal passed independent checks and created a local Git commit/MR artifact. This simulates the Duo role, not GitLab integration or guaranteed model success. |
| Policy schema | Implemented with validation and lifecycle | `leakhunter/policy/engine.py` validates classifications, selectors, sink constraints, invariants, types, and unknown keys. The knowledge bank enforces immutable version content, named approval, draft/approved/retired states, and no reapproval of retired versions. |
| Policy engine | Implemented for declared semantics | Enforces classification allowances, denied fields, audience, recipient, contracts, authorization, tenant constraints, and supported invariants. Required missing context fails closed; static analysis does not invent runtime identity or consent. |
| Static source/sink analyzer | Implemented; bounded Python data-flow analysis | `leakhunter/analyzers/python_ast.py` propagates classified values through assignments, containers, returns, and resolved calls, with explicit manifest entrypoints. Coverage reports parse errors, unsupported constructs, unresolved calls, and limitations; this is not a sound whole-program taint proof. |
| CPG generation | Implemented for supported Python constructs | Produces AST, control-flow, call, and data-flow nodes/edges with source/sink paths. Reflection, dynamic dispatch, implicit control taint, native extensions, and framework/ORM semantics are not fully modeled. |
| Incremental MR analysis | Implemented as local branch/snapshot overlays | Caches AST/per-file outputs and invalidates affected import/call components after changes/deletions. Installed-CLI verification exercised a changed-file branch from a pinned snapshot without moving `main`. No remote GitLab MR event integration is provided. |
| Knowledge Bank data model | Implemented with SQLite | `leakhunter/storage/knowledge.py` stores policy versions, immutable snapshots and relational facts, branch pointers, annotation overlays, metrics, evaluations, and repairs. Snapshot integrity hashes and database triggers protect historical records. |
| Evidence contract | Implemented; persisted with immutable snapshots | Records repository-relative locations, source revision, policy identity, executed case scope, sanitized observations, marker hashes, and runtime status. Missing or failed execution remains distinct from confirmed evidence; raw captured sensitive payloads are not persisted. |
| Runtime verification | Implemented; Docker and dependency-image execution verified | Docker runs sanitized copies with network disabled, read-only repository mounts, resource limits, and minimized credentials/environment. Configured dependency images are supported and recorded by immutable image ID. Explicit trusted-local execution is available, never an automatic fallback or host sandbox. |
| Duo repair branch/MR | Implemented; real local Git artifacts verified | `leakhunter/repairs/engine.py` applies allowlisted edits in an isolated copied repository and creates a real branch/commit plus `merge-request.json` only after passing gates. Artifacts explicitly declare `simulation: true`; no remote push, MR publication, merge, or deployment occurs. |
| Independent differential verification | Implemented; passing and blocked outcomes exercised | Independently reproduces the baseline, reruns static/runtime/functional checks, pins policy/manifest/runtime image, protects original source and test scope, and blocks unresolved findings. Context-only discharge requires exact passing runtime evidence. A generated-target repair passed; leaking complex-example proposals failed without an MR. |

Earlier verification included 41 passing regression tests, dashboard CRUD/history/approval interactions, and installed-wheel execution against external safe and unsafe targets. The original delivery pipeline passed 77 Python tests; the frozen 0.4.7 release has 127. These counts describe different revisions, not independent real-world benchmark cases. See [verification and limits](#verification-and-limits) and the [example's observed integration results](example/README.md#observed-integration-results) for scope and caveats.

## Install and run against another repository

Requires Python 3.10+, Git for repair workspaces, and Docker for isolated runtime execution:

```sh
python3 -m pip install .
docker pull python:3.12-slim

leakhunter \
  --repository "$TARGET_REPOSITORY" \
  --policy "$POLICY_FILE" \
  --runtime-manifest "$RUNTIME_MANIFEST" \
  --data-dir "$STATE_DIRECTORY"
```

Open `http://127.0.0.1:8787`; `--port` changes the port. Use a separate state directory per target, outside both the application package and target repository. No changes inside `leakhunter/` are required to select another target. The installed wheel contains the application and dashboard, not the example package.

Without a runtime manifest, static analysis and knowledge editing still work, but runtime status is `NOT_RUN` and the release gate cannot pass. Without a model provider, analysis, execution, evaluation, and storage still work; model requests report `skipped`.

For the bundled target, see [example/README.md](example/README.md).

## Language contract

`leakhunter/languages.py` defines language selection, entrypoints, source extensions, and normalized analyzer results. `leakhunter/analyzers/registry.py` keeps Python on its original AST analyzer and dispatches other languages to Tree-sitter. Every adapter returns `nodes`, `edges`, `findings`, `coverage`, `index`, and `incremental`; coverage and unresolved calls remain explicit.

One repository scan/runtime manifest selects one language. Set top-level `language` in the manifest; omitted means `python`. `--language` can select static-only analysis and must match a supplied manifest. Python's `module`/`callable` fixtures and worker remain unchanged.

| Language | Source extensions | Runtime | Default Docker image |
| --- | --- | --- | --- |
| Python | `.py` | Existing Python worker | `python:3.12-slim` |
| JavaScript | `.js`, `.jsx`, `.mjs`, `.cjs` | Node; Bun for JSX | `node:22-bookworm-slim`; `oven/bun:1` for JSX |
| TypeScript | `.ts`, `.tsx` | Bun | `oven/bun:1` |
| Go | `.go` | Explicit native protocol command | `golang:1.23-bookworm` |
| Rust | `.rs` | Explicit native protocol command | `rust:1.82-bookworm` |

Non-Python cases use a repository-relative `entrypoint` instead of Python `module`/`callable`:

```yaml
version: 1
language: javascript
cases:
  - id: response-check
    entrypoint: {file: service.js, callable: run}
    args: [{password_hash: SYNTHETIC_SECRET_48291}]
    kwargs: {}
    sensitive:
      - {marker: SYNTHETIC_SECRET_48291, class: SECRET, symbol: record.password_hash}
    context: {synthetic: true, boundary_kind: HTTP_RESPONSE}
    expect: {ok: true}
```

JavaScript/TypeScript invokes an exported callable, awaits its result, and captures returns, console/stdout/stderr, modeled `fetch`, and configured artifacts. Arguments are positional; nonempty `kwargs` or entrypoint commands are rejected rather than ignored.

Go/Rust must supply an argv command, for example `entrypoint: {file: service.go, callable: run, command: [go, run, service.go]}` or `entrypoint: {file: src/main.rs, callable: run, command: [cargo, run, --quiet, --offline]}`. The command runs from the copied repository root, reads one JSON object `{"args": [...], "kwargs": {...}}` from stdin, and writes exactly one JSON result object to stdout. Stderr is captured as `APPLICATION_LOG`; the result is `HTTP_RESPONSE`. The wrapper is responsible for invoking the declared callable. Native HTTP interception is unsupported. Dependency-bearing targets need an image with their offline dependencies.

External runners reject `capture_calls`, `observe_calls`, and `trace`; missing required captures and unavailable toolchains/images fail closed. Docker remains the default: images must exist locally, execution pins their immutable IDs, network is disabled, and there is no fallback to local execution. `--runtime-backend local` is only for trusted code, not a host security sandbox.

The new static adapter is intraprocedural: classified fields, aliases, assignments, branches, returns, and common sinks are modeled; calls without a model retain argument taint and are recorded as unresolved. A helper that discards a secret can therefore produce a false positive. It does not establish receiver types or whole-program/framework semantics. Use wildcard field selectors such as `*.password_hash` for portable untyped-field policies. This is language support, not a claim of Python analysis or model-inference parity.

`example/language_holdouts.py` materializes and executes five safe/leaking pairs per language (response, logging, overwrite, branch, helper), saving source, policy, manifests, scans, runtime evidence, and metrics:

```sh
PYTHONPATH=. python3 -m example.language_holdouts --output /tmp/leakhunter-language-local --backend local
```

Use `--backend docker` after installing all five language images. These 50 correlated synthetic checks measure static/runtime contracts only; they do not call Luna or estimate production accuracy.

Measured on that corpus:

| Language | Static correct | Precision | Recall | Runtime correct, local / Docker |
| --- | --- | --- | --- | --- |
| Python | 10/10 | 100% | 100% | 10/10 / 10/10 |
| JavaScript | 9/10 | 83.3% | 100% | 10/10 / 10/10 |
| TypeScript | 9/10 | 83.3% | 100% | 10/10 / 10/10 |
| Go | 9/10 | 83.3% | 100% | 10/10 / 10/10 |
| Rust | 9/10 | 83.3% | 100% | 10/10 / 10/10 |

All four static errors are false positives on helpers that discard their sensitive argument; there are no false negatives in this corpus. Evidence: `example/data/five-language-local-v2/results.json` and `example/data/five-language-docker/results.json`. Actual CLI analysis and source-backed review contexts were exercised for all five languages; controlled local repair verification was exercised for JS/TS/Go/Rust, and Docker timeout cleanup for JavaScript.

## Runtime manifest

The Python harness invokes real callables with synthetic fixtures; other language entrypoints follow the contract above. Supply JSON-compatible YAML values and invented, unique markers—not production records or credentials. Even safe cases declare the markers whose absence is checked.

```yaml
version: 1
docker_image: python:3.12-slim
regression_command: [python, regression.py]
cases:
  - id: profile-response
    module: service
    callable: customer_profile
    args: [synthetic-customer]
    kwargs: {}
    sensitive:
      - marker: SYNTHETIC_PRIVATE_8be71d
        class: SECRET
        symbol: customer.password_hash
    context:
      audience: authenticated_self
      tenant: tenant-a
      source_tenant: tenant-a
      authorized: true
      synthetic: true
    expect: {ok: true}
    expected_violation: false
    finding:
      file: service.py
      function: customer_profile
      sink: HTTP_RESPONSE
```

- `module` and `callable` select the target entrypoint; dotted callable names are supported. `args` and `kwargs` are passed to it. `expect` is a recursive subset of the returned JSON-compatible value, not a replacement implementation.
- Actual return values are inspected as `HTTP_RESPONSE`; log records are inspected as `APPLICATION_LOG`.
- `sensitive` declares marker, classification from the configured policy, and source symbol. Persisted observations contain the symbol and SHA-256 marker hash, never raw captured payloads.
- Optional `finding` maps runtime evidence to an exact repository-relative file, function, and sink. `symbol` is optional. A passing unrelated case cannot discharge another function's candidate.
- Optional `expected_violation` is an independent evaluation label. It never exempts a leak from policy enforcement.
- `regression_command` is an argv list, run from the copied target root. Python commands use the worker interpreter. Its success is required; output is represented by hashes, not copied into evidence.

Additional capture declarations belong to each case:

```yaml
capture_http:
  - url_prefix: https://synthetic.invalid/events
    sink: THIRD_PARTY_ANALYTICS
capture_calls:
  - module: analytics
    callable: track
    sink: THIRD_PARTY_ANALYTICS
    return_value: {accepted: true}
artifacts:
  - path: export.txt
    sink: TEST_ARTIFACT
```

HTTP capture supports `urllib` and a bounded common `requests` transport interface. These adapters intercept calls without contacting recipients. `capture_calls` intercepts a configured callable boundary before importing the fixture; it proves arguments reached that boundary, not vendor delivery. Artifacts are read from a writable per-case temporary working directory; the repository stays read-only in Docker. Missing required captures, unsupported networking, execution errors, and timeouts do not establish safety.
Optional guard and branch evidence can be captured without changing the target repository:

```yaml
observe_calls:
  - module: authorization
    callable: owns
    role: ownership
trace: true
```

`observe_calls` records only the configured callable role, call order, return type, and boolean result; arguments and return payloads are never persisted. `trace: true` records bounded repository-relative executed lines. These observations establish only the declared execution, not universal control-flow coverage.

`case.passed` measures functional expectations only. Suite `functional_passed` also requires the pinned regression command. Suite `passed` additionally requires completed execution and zero observed policy violations. A deliberately vulnerable baseline can pass functionality while failing security.

### Dependencies and isolation

The default image must already exist locally; execution uses `--pull=never`. For dependencies, build a trusted Python image with those dependencies installed, then set `docker_image` in the manifest. Unspool does not run package installation from target instructions. Each execution resolves and records an immutable image ID; repair before/after runs must use the same image ID.

Docker execution disables networking, mounts sanitized target/harness/input read-only, drops capabilities, prohibits privilege escalation, runs as a non-root host UID where available, and limits memory, CPU, processes, and temporary storage. Common credential files are excluded and host credentials are not inherited. Docker is a dependency: unavailable daemon/image or execution failure is reported, never silently replaced with host execution.

`--runtime-backend local` explicitly selects **trusted target execution on the host, not a security sandbox**. The target is copied and the child environment is minimized, but code still runs with the user's host privileges. Use Docker for untrusted targets. Instrumentation is not cryptographic attestation against a deliberately hostile process that tampers with its own Python runtime.

## Policy and approval

The validated schema includes:

- Positive integer `version`; lifecycle `draft`, `approved`, or `retired`.
- Ranked `classifications` including `PUBLIC: 0`; source selector/class records.
- Unique sink kinds with `allow`, optional `deny_fields`, `audience`, `recipient`, `require_contract`, `require_authorization`, and `same_tenant` constraints.
- Supported invariants: `secret_fields_never_in_external_payloads`, `cross_tenant_reads_must_be_authorized`, and `no_real_secrets_in_test_artifacts`.

See [the example policy](example/leakhunter-policy.yaml) for complete syntax. Unknown fields/classes/invariants and invalid types are rejected. Required audience, recipient, contract, tenant, and authorization context fails closed when absent or mismatched; the engine does not invent identity or consent.

The knowledge bank treats policies without an explicit lifecycle as drafts. Approval requires a named `approved_by` operator and exact configured semantic policy content. Content cannot change under an existing version; configure a higher version instead. Retired versions cannot be approved again. A version explicitly supplied as approved must name its approving operator. These are local operator records, not external identity authentication or a multi-user approval service. Models cannot approve policy.

Static analysis cannot establish runtime recipient or tenant context. A context-only `POSSIBLE` candidate may be discharged only for an exact mapped, successfully executed case with a real matching sensitive observation and reevaluation against the pinned policy/context. Raw findings remain available; this is scoped evidence, not universal safety.

## Analysis, graph, and knowledge bank

The analyzer builds a bounded Python code-property graph with AST, control-flow, call, and data-flow edges. It propagates classified values through assignments, returns, containers, and resolved interprocedural calls. Manifest callables are explicit response entrypoints. Findings include source/sink paths, locations, policy reasons, source revision, and evidence state.

Incremental analysis caches serialized AST/per-file outputs keyed by source, analyzer, policy, and entrypoint identity. Changes/deletions invalidate affected import/call components. Named branch snapshots can start from an immutable baseline without moving `main`; this is a local MR overlay, not a GitLab webhook integration.

State is stored in `knowledge.sqlite3`: policy versions, immutable snapshots and relational facts, branch pointers, mutable annotation overlays, metrics, evaluations, and repairs. Snapshot hashes are checked on read; SQLite triggers reject snapshot/fact updates and deletes. Node/edge updates retain analyzer metadata. Annotation deletion never rewrites historical snapshots.

The dashboard supports graph filtering/inspection, full node and edge CRUD, findings, runtime evidence, source-backed security reviews, measured evaluations, immutable history, repair gates, and explicit policy approval. Reviews show connected code/graph context, evidence references, typed assessments, missing evidence and suggested checks. Historical inspection disables mutations.

## OpenRouter and local repair/MR workflow

Set the key through the environment; the application never returns it through APIs:

```sh
export AGENT_PROVIDER_API_KEY='your-key'
export AGENT_PROVIDER_URL='https://openrouter.ai/api/v1/chat/completions'
export AGENT_PROVIDER_MODEL='openai/gpt-6-luna-decisions'
export DUO_PROVIDER_MODEL='deepseek/deepseek-v4.1-flash'
```

Equivalent nonsecret flags: `--provider-url`, `--decision-model`, and `--repair-model`. The example launcher alone can load a root `.env`. Provider errors and invalid model IDs remain errors; configuration is not proof of access. **Both decision and repair requests can disclose source to the configured provider.** Only bounded, revision-checked source is used for reviews; repair source remains allowlisted. Credential-like, binary, oversized, changed or symlinked review source is withheld. The shared credential guard is heuristic, not a complete secret scanner: authorize source disclosure before configuring a remote model.

Luna is a **decision-output model**, not a chat-completion model. Each review sends source-backed `state` and three typed `noul` questions to `/api/alpha/decisions` on the configured provider origin: `unauthorized_disclosure_plausible`, `additional_context_required`, and `targeted_runtime_test_required`. Repair sends chat messages to `AGENT_PROVIDER_URL`. Responses retain structured `answers`, probabilities, model and usage. Missing answers, wrong answer types and invalid probabilities are provider errors, never approvals or text-model fallbacks. See the [Decisions request contract](https://openrouter.ai/docs/api/api-reference/alphadecisions/submit-a-decisions-request).

Model discovery must include the output modality: the [decision catalog](https://openrouter.ai/api/v1/models?output_modalities=decisions&q=luna) lists Luna, while the default catalog lists text-output models. The requested Flash model is [`deepseek/deepseek-v4.1-flash`](https://openrouter.ai/deepseek/deepseek-v4.1-flash); neither role silently substitutes another model.

`providers/context.py` groups sink and unresolved-call boundaries independently of existing findings, then follows resolved caller/callee connections. Context includes exact source spans with file/line/SHA references, scoped AST/CFG/call/data-flow edges, relevant findings, configured policy origin/constraints and matched synthetic runtime observations. Default `PUBLIC` or no finding is not disclosure approval. Unknown external database, authentication, recipient and tenant semantics stay unknown; configured policy is not replaced with invented ownership requirements. Runtime arguments, keyword arguments, expected/results payloads, sensitive markers and raw tenant identifiers are not forwarded as runtime evidence.
Each review boundary now also carries a discovered or declared entrypoint, input parameter names, direct callers and callees, connected-function scope, output recipient kinds, and source locations. `flow_paths` preserves each static source-to-sink route with node IDs, source references, candidate branch predicates, and `POSSIBLE_FLOW` status. A route decorator, explicit analysis entrypoint, or runtime-manifest entrypoint can create a review unit even when no classified finding exists.
Provider answers are accompanied by `deterministic_evidence`: a conservative, provider-independent tri-state overlay. It uses only configured policy requirements, static flow paths, observed sink markers, and explicitly configured runtime guard roles; it never infers authorization from function names. `UNPROVEN` and `UNKNOWN` are abstentions, not safe results. An observed violation or possible response path produces an effective `BLOCKED` status without rewriting the model probability.

Disclosure is bounded to 24 review units, 12 connected function/module owners, 256 graph nodes and 768 edges per unit, 64 KiB source files and a 128 KiB serialized typed request envelope. Whole excerpts or units are omitted rather than truncated; omitted coverage and unavailable source/provider results remain visible. Each review remains `verification: UNRESOLVED` and `safe_to_release: false`, regardless of probability. Missing evidence and next checks are context-derived prompts, not model-written explanations or automatically executed tests. Immutable snapshots retain each context and response. These bounded reviews can identify hypotheses missed by classification rules; they do not establish whole-program understanding, exploit confirmation or release safety.

A repair requires an approved policy, unchanged source revision, and an executed baseline with observed violations. It then:

1. Copies the target into an isolated local Git worktree and independently reproduces the baseline.
2. Requests bounded exact source edits. Policy, manifest, tests, regression scripts, credentials, and paths outside the allowlist are protected.
3. Applies edits only in the copy and independently reruns static analysis, runtime security, and pinned functional regressions.
4. Rejects unsupported/failed analysis, new violations, unresolved candidates, changed policy/manifest, changed runtime image, out-of-scope edits, or modification of original source.
5. Only after every gate passes, creates a real local branch/commit and `repairs/<id>/merge-request.json` with `simulation: true` and independent verification results.

Incomplete model proposals are stored as rejected/failed, not successful repairs. This local repair engine does not push, create GitLab MRs, merge, or deploy. OpenRouter simulates its Duo repair role. The separate `unspool.handoff` workflow uses the real GitLab Duo Developer flow and GitLab CI.

## CLI and HTTP interfaces

```sh
# Add the same repository/policy/manifest/data-dir flags shown above:
leakhunter ... --once analyze --gate
leakhunter ... --once evaluate
leakhunter ... --once repair --gate
leakhunter ... --once analyze --branch mr-42 --base-snapshot-id "$SNAPSHOT_ID"
```

Replace `...` with configuration flags; it is not a literal argument. One-shot commands print JSON. `analyze --gate` requires approved policy, supported analyzed Python, resolved candidates, and passing runtime security/functionality. `repair --gate` requires independent verification. Evaluation reports detection accuracy and cannot authorize release: `evaluate --gate` is rejected with exit 2 before configuration or execution. Failing supported gates exit with status 1. Parse, execution, provider, and unsupported-analysis states remain inspectable.

| Endpoint | Purpose |
| --- | --- |
| `GET /api/knowledge`, `/api/config` | Live graph, latest evidence/evaluation, and prerequisites |
| `POST /api/analyze` | Analyze; optional `branch` and `base_snapshot_id` |
| `POST /api/repair` | Propose/verify; optional repository-relative `allowed_paths` |
| `POST /api/evaluate` | Execute independently labeled cases and save metrics |
| `GET /api/snapshots`, `/api/snapshots/<id>` | Immutable history and full snapshot |
| `GET /api/metrics`, `/api/repairs`, `/api/evaluations`, `/api/policies` | Stored run records |
| `POST /api/knowledge/nodes`, `/api/knowledge/edges` | Create annotations |
| `PUT /api/knowledge/nodes/<id>`, `/api/knowledge/edges/<id>` | Update annotations |
| `DELETE /api/knowledge/nodes/<id>`, `/api/knowledge/edges/<id>` | Delete live annotations |
| `POST /api/policies/approve` | Exact configured `policy` plus named `approved_by` |

The server is loopback-only with Host/Origin checks and bounded JSON requests. It has no multi-user authentication: do not expose it publicly as an organizational security service.

## Verification and limits

```sh
python3 -B -m unittest discover -s tests
python3 -m example.generator --materialize /tmp/leakhunter-cases --count 8 --seed 17
python3 -m example.generator --evaluate /tmp/leakhunter-cases --runtime-backend docker
```

The generator requires an empty destination. Measured synthetic precision/recall applies only to the executed labeled cases, not arbitrary repositories. The current ten-case customer example detects all four runtime-positive cases and leaves six safe cases unflagged; static analysis has documented misses and false positives. A live OpenRouter-generated repair has passed independent Docker verification on a generated target; larger-example proposals that retained leaks were correctly blocked.

The contextual-review smoke used a separate external invoice repository with **zero static findings**: Docker captured authorization and tenant violations, the review included connected endpoint/repository source and matched sanitized evidence, and the context/response survived an immutable snapshot roundtrip and browser rendering. A real Luna request using that synthetic source-backed context returned all three typed answers; verification remained `UNRESOLVED` and release safety remained false. This checks the review pipeline, not general model detection accuracy.

Metrics use `precision = TP/(TP+FP)`, `recall = TP/(TP+FN)`, and `false_safe_rate = FN/(TP+FN)` (missed-positive rate, not false-omission probability). Unknown/unexecuted cases are excluded rather than counted safe; undefined ratios are `null`. Repair success is verified successful attempts divided by all recorded attempts for that target.

This is bounded, language-specific static analysis plus configured runtime evidence—not a sound whole-program proof. Python and the newer intraprocedural Tree-sitter adapters have different coverage and precision. Reflection, dynamic dispatch, implicit control taint, native extensions, framework/ORM semantics, and unconfigured sink transports are not fully modeled. Coverage reports include parse errors, unsupported constructs, unresolved calls, and limitations. Unsupported/failed analysis blocks automatic release; successfully exercised cases do not prove untested paths safe. Adapt fixtures/capture boundaries and build a dependency image for each real target. Existing production tests and human security review remain necessary.
