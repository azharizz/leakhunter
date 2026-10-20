# Executable synthetic customer-service example

Everything specific to this target lives here: `fixtures/`, `runtime.yaml`, policy,
case generator, model selections, and launcher. The dependency is
`example → leakhunter`; the portable production package never imports this tree.
All records and markers are invented. Do not replace them with customer data.

## Run the customer application independently

From the project root:

```sh
python3 example/fixtures/server.py --route /catalog
python3 example/fixtures/server.py --route /customers/profile
python3 example/fixtures/server.py --route /tenant/export --customer-id cust-bob --tenant tenant-a
python3 example/fixtures/server.py --serve --port 8790
```

The server binds only to `127.0.0.1`. For example:

```sh
curl http://127.0.0.1:8790/catalog
curl -H 'X-Tenant: tenant-a' 'http://127.0.0.1:8790/tenant/export?customer_id=cust-bob'
```

This is an intentionally vulnerable teaching app, **not authentication software**:
`X-Tenant` is a synthetic request identity, not an authenticated production claim.
Its modules separate customer records, tenant-aware storage, service behavior,
analytics adapter, and HTTP/CLI routing. Routes exercise these paired flows:

| Flow | Deliberately unsafe route | Safe route |
| --- | --- | --- |
| Response serialization | `/customers/unsafe-response` includes secret hash/token | `/customers/profile` allowlists public profile fields |
| Operator logs | `/audit/unsafe` writes email | `/audit` writes only internal customer ID |
| Vendor analytics | `/analytics/unsafe` hands email/token to SDK | `/analytics` emits aggregate page event |
| Tenant authorization | `/tenant/unsafe-export` ignores request tenant | `/tenant/export` denies another tenant |
| Public functionality | — | `/catalog` returns products and prices |

Analytics uses an explicit synthetic SDK adapter with an in-memory outbox. No
external vendor is contacted and nothing is persisted. Runtime instrumentation
captures actual calls to `analytics.track` (the egress boundary), including their
arguments; it does not pretend a vendor delivered or accepted an event.

The independent functional regression command, runnable **from the target root**:

```sh
(cd example/fixtures && python3 regression.py)
```

It pins legitimate product/profile/audit behavior and authorization denials,
without requiring vulnerable extra response fields to survive a repair.

## Run Unspool against the target

```sh
python3 -m pip install -r requirements.txt
docker pull python:3.12-slim
python3 -m example.run --offline --port 8787
```

Open http://127.0.0.1:8787 and select **Run analysis**. The launcher passes
`example/fixtures`, `example/leakhunter-policy.yaml`, `example/runtime.yaml`, and
`example/data`. Docker is the default runtime backend: isolated execution uses
no network and does not inherit host credentials. Docker and the pre-pulled image
must be available; missing prerequisites are execution errors, not local fallbacks.

For this trusted synthetic repository only, explicitly opt into host execution:

```sh
python3 -m example.run --offline --trusted-local --port 8787
# Equivalent explicit backend selection, still requiring the trust flag:
python3 -m example.run --offline --runtime-backend local --trusted-local
```

`--runtime-manifest PATH` selects another manifest. The bundled manifest invokes
real service functions for ten positive/safe cases, records synthetic markers,
sets tenant/recipient/contract context, and runs `regression.py`. The policy
permits authenticated-self profile access, prohibits secrets in responses and
PII in logs, requires aggregate-only analytics contracts, and denies unauthorized
cross-tenant data. Positive cases intentionally violate policy; a correct
baseline therefore has passing functional checks but a failing security gate.
Expected labels are for evaluation, not exemptions from enforcement.

Static candidates are not runtime proof. Runtime case observations and policy
violations come from executed responses/log records/adapter arguments, and
persisted evidence is sanitized. A repair must remove violations while retaining
functional contracts; model advice alone is never a successful repair.

## OpenRouter and the simulated Duo role

```sh
python3 -m example.run --port 8787
```

Only this example launcher reads the root `.env`; override with `--env-file`.
It defaults to OpenRouter, `openai/gpt-6-luna-decisions` for typed decisions, and
`deepseek/deepseek-v4.1-flash` for the repair-model role that simulates Duo.
Luna uses `/api/alpha/decisions` with source-backed `state` and three typed `noul`
questions, not chat messages. Production builds connected code/graph review units
even when no static finding exists, with declared policy, scoped runtime evidence
and explicit unknowns. Configuring a remote provider authorizes bounded source
disclosure; runtime inputs/results/markers and raw tenant identities are excluded
from runtime context. Credential filtering is heuristic, not a complete secret
scanner. Probability answers remain unresolved advice, never release approval.
Flash uses the configured chat-completions endpoint. These are configurable model IDs, not a claim that
GitLab Duo was connected. Set `AGENT_PROVIDER_API_KEY`, optionally
`AGENT_PROVIDER_URL`, `AGENT_PROVIDER_MODEL`, and `DUO_PROVIDER_MODEL`.
Existing environment values take precedence over the env file and defaults.
Provider errors remain errors; neither model is replaced with a fallback.
`--offline` suppresses all model requests even if credentials exist. Repairs
produce local artifacts; there is no remote push, merge, or deployment.

## Generate and measure executable cases

```sh
# Metadata exploration only; this does not create or run applications:
python3 -m example.generator --sample 20

# Empty destination required. Eight programs cover four positive/safe pairs:
python3 -m example.generator --materialize /tmp/leakhunter-cases --count 8 --seed 17
# Default isolated execution:
python3 -m example.generator --evaluate /tmp/leakhunter-cases --output /tmp/leakhunter-evaluation.json
# Explicit opt-in for these trusted generated programs:
python3 -m example.generator --evaluate /tmp/leakhunter-cases --trusted-local
```

Materialization creates a pinned `policy.yaml`, labeled `catalog.json`, and one
independent `repository/` plus `runtime.yaml` per case. Each target contains actual
source-to-sink code, a safe or unsafe implementation, a unique synthetic marker,
and a runnable functional regression. The four implemented families are secret
response, PII logging, analytics SDK egress, and unauthorized tenant response.
A count above eight repeats these concrete families with different markers; it
does **not** increase semantic coverage to the metadata Cartesian space.

Evaluation executes each target and computes separate static-candidate and runtime
confusion matrices, precision, recall, and accuracy against labels. Unexecuted or
failed-functional cases are excluded from runtime metrics and reported as
incomplete, never silently labeled safe. The command exits nonzero on incomplete
execution or a runtime label mismatch. The metadata heuristic `evaluate(case)`
remains available but explicitly labels its output as unexecuted metadata.

Focused repository checks (not a claim they have already run):

```sh
python3 -m unittest discover -s tests -p test_example.py
```

These execute the realistic fixture and generated programs, verify marker
observations match labels, and deliberately turn a safe generated program into a
leak to ensure labels are checked against real behavior rather than list lengths.
`example/data/` is created on demand and is not required to start.

## Observed integration results

The live Docker run analyzed six Python files, generated 1,238 graph nodes and
1,445 edges, and reported 16 static candidates. Five candidates were confirmed
by actual synthetic observations. All ten functional cases completed; four cases
violated policy, so the vulnerable baseline correctly remained blocked.

Labeled runtime evaluation measured TP=4, TN=6, FP=0, FN=0. Static evaluation
measured TP=3, FP=4, FN=1, with two unmapped cases; do not interpret static output
as complete security coverage.

The corrected integration returned actual typed Luna answers through
`/api/alpha/decisions`. `deepseek/deepseek-v4.1-flash` repaired a generated
response-leak target and passed independent before/after Docker execution,
functional regressions, static/policy checks, and all repair gates. The real
local Git commit is `13e62198ac2a79d34c68f7948fe2788175c32abf`; its artifact is
`example/data/repairs/25d4e3c164344b0cae636f21ef6bfb2b/merge-request.json`
in the verification workspace. Earlier incomplete proposals against the larger
application were blocked and produced no MR. These are observed synthetic
results, not guarantees of model repair success.
