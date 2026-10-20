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
