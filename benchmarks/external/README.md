# Frozen external static feasibility cases

`cases.json` freezes ten case-level expectations across three independently
authored MIT security labs before the first Unspool evaluation run. We inspected
source and authors' descriptions to label specific policy flows. These are
solo labels, selected after knowledge of Unspool's design, not a blind/held-out
benchmark, unknown-vulnerability discovery or independent human ground truth.
No third-party code is copied into this repository or executed by this evaluation.
Original MIT notices remain in the pinned upstream checkouts.

Sources: [VAmPI](https://github.com/erev0s/VAmPI),
[DVGA](https://github.com/dolevf/Damn-Vulnerable-GraphQL-Application),
[PyGoat](https://github.com/adeyosemanputra/pygoat). Their intentional security-lab
design is not representative of customer repositories. Exact revisions, source
paths, callable boundaries, labels and rationale are in the manifest. Safe labels
mean only no selected secret in the bounded source behavior; unknown cases stay
outside the binary denominator and remain visible in coverage.

There are five positive policy-flow cases, three negative cases and two explicitly
unknown cases. They are correlated within repositories; do not describe them as
ten independent production vulnerabilities. This falls short of the roadmap's
20-positive/20-negative target. GraphQL/admin and authenticated-user cases are
evaluated under the explicitly declared no-secret-return policy, not reclassified
as authentication bypasses. Only VAmPI currently has recorded real HTTP evidence.

The analyzer must parse, not import/execute, the target source. Results must include
every case, misses, false positives, unknowns, coverage diagnostics, exact package
and manifest identities, latency and any setup failures. Do not tune the policy or
labels after a result and call the rerun held-out. No model calls/repair runs are
part of this static comparison; a syntax-only baseline is not a competing security
agent. Application runtime and ungated-agent comparisons remain separate work.

## Observed results — 21 October 2026 (Asia/Jakarta)

The manifest was frozen in commit `f0ed588` before execution; SHA-256
`8e49a7cca7b3d55af760d507a0780ec0d4d7ea3e80195a2263a483d590d2ceb4`.
`results.initial.json` retains the first source-import run. A second run used
the installed 0.4.2 wheel, isolated Python imports and `/tmp` as cwd; its full
case records are `results.installed.json`. The analyzer module hash was
`ebc5180498b8080f74aca5cc43879946b5dc00e9144db841d2e334931bee028a`.
Both runs produced TP 5, FP 0, TN 3, FN 0, unknown labels 2, execution errors 0.
`results.validated-targets.json` retains a further installed repeat after adding
qualified-callable existence checks; it produced the same outcomes with no label
or analyzer changes. Missing/mistyped callable targets now fail setup instead of
silently becoming negative predictions.
`results.bounded-ingestion.json` repeats the unchanged manifest with a clean
installed 0.4.4 wheel and isolated imports after source-ingestion hardening.
It retained TP 5 / TN 3 / unknown 2, with no false positives, misses, execution
errors or parse errors. The report now records the source-reader module hash as
well as the analyzer hash; labels and upstream source revisions were unchanged.
This checks regression on the same selected set, not a new held-out evaluation
or evidence that larger/malicious repositories meet production operating limits.
These are predictions on **eight selected labeled cases**, not ten runtime tests.
Conditional precision/recall are 5/5 for this selected set only. They are too
small, correlated and selection-biased to estimate production accuracy.

| Pinned repository | Python files parsed | Analysis time, installed run | Unresolved calls | Unsupported constructs | Case outcomes |
| --- | ---: | ---: | ---: | ---: | --- |
| VAmPI | 11 | 83.01 ms | 129 | 0 | 2 TP, 1 TN |
| DVGA | 35 | 219.71 ms | 362 | 7 | 1 TP, 1 TN, 1 unknown |
| PyGoat | 80 | 930.95 ms | 869 | 1 | 2 TP, 1 TN, 1 unknown |

No parse errors were reported. Unresolved calls include framework/library/model
behavior that the analyzer does not resolve. Parsing 126 files is not equivalent
to verifying their functions, authorization, templates or execution paths. The
two unknown labels represent 2/10 unscored cases, not an analyzer-derived proof
that exactly 80% of application behavior is covered. No-match on an unlabeled
callable remains unknown. The time values measure analyzer work only, excluding
clone/source export, setup, runtime, CI and repair. No model was called or charged;
compute cost was not separately metered. No repairs were proposed/evaluated here.

Reproduce with authorized local clones containing the exact manifest commits:

```sh
cd /tmp
/path/to/installed/python -I /path/to/unspool/benchmarks/external/evaluate.py \
  --manifest /path/to/unspool/benchmarks/external/cases.json \
  --checkout vampi=/path/to/VAmPI \
  --checkout dvga=/path/to/Damn-Vulnerable-GraphQL-Application \
  --checkout pygoat=/path/to/pygoat \
  --output /path/to/results.json
```

The runner reads pinned Git blobs, so working-tree edits do not change inputs.
Each repository is analyzed in its own subprocess with a 90-second timeout;
timeout/setup failures retain every affected case as execution error. It never
imports a target module or installs target requirements. The test checks that
misses, unknowns and execution failures cannot become true negatives. The report
contains hashes and counts rather than full source or private filesystem paths.

The 20-positive/20-negative target, representative non-lab repositories, runtime
checks for DVGA/PyGoat, repair/regression comparison, ungated-agent baseline,
independent labels and uncertainty estimation remain open. Do not mark the full
roadmap evaluation gate complete from this feasibility result.
