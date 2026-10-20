# Security review record — 20 October 2026

Scope: Unspool's own Python packages and selected runtime/bootstrap dependency
pins. This review is solo and tool-assisted. It is not a penetration test,
independent human review, container escape audit or proof of no vulnerabilities.
The deliberately vulnerable VAmPI dependencies are a separate lab and are not
included in these clean-dependency claims.

## Dependency findings and changes

Used [pip-audit 2.10.1](https://github.com/pypa/pip-audit) against the six entries
in `requirements.lock`: no reported advisories. Auditing the actual fresh 0.4.1
venv additionally found advisories in inherited `pip 24.0` and `setuptools 65.5.0`.
The runtime-only result did not cover those bootstrap packages.

Updated the documented/CI bootstrap tools to `pip 26.2.1`, `setuptools 83.0.0`,
`wheel 0.48.0` and `packaging 26.3` in `requirements.build.lock`, and pinned the
build backend. Auditing all ten selected runtime/build versions returned no
reported advisories. Re-auditing the upgraded local environment returned no
reported advisories for its registry packages; Unspool itself was explicitly
skipped because its local 0.4.1 distribution was not found on PyPI. That skip is
not a security assessment of Unspool. Advisory data can change after this run.

## Source scan and triage

[Bandit 1.9.4](https://bandit.readthedocs.io/en/latest/start.html) scanned
`leakhunter/` and `unspool/` with zero scan errors. Initially 22 findings:
14 LOW, 8 MEDIUM, zero HIGH. One MEDIUM finding prompted a concrete fix:

- The deployment smoke checker accepted arbitrary urllib URL schemes and followed
  redirects. It now requires HTTPS, rejects credentials/query/fragment and bad
  ports, requires a full source SHA, refuses redirects, ignores inherited proxy
  settings and bounds health response size. Regression tests preserve stale-SHA
  rejection and cover unsafe URLs, redirects and oversized/forged responses.
- Health verification now also requires the actual JSON boolean `true` in both
  smoke and handoff checks. Python equality alone treats numeric `1` as equal to
  `True`; tests now reject numeric/string/null/false verification before merge.
- A real check passed against the live Cloud Run revision
  `637ccae42d7d869ad14514a81ca5a62105354cc9`. An invocation expecting an older
  revision failed, as it should; no deployment outage was inferred from it.

The token-backed GitLab client now also refuses redirects (rather than forwarding
its authorization header to a redirected service), ignores inherited proxies and
bounds JSON response size at 4 MiB. A redirect or oversized response stops the
workflow; it is not silently accepted. Tests cover both stopped outcomes.

The subsequent scan retains 20 findings: 14 LOW and 6 MEDIUM, zero HIGH/errors.
No findings are hidden with `nosec` or removed from the full JSON output.

| Remaining warning group | Review disposition | Limits |
| --- | --- | --- |
| 14 LOW subprocess import/call warnings (B404/B603) | The runtime/controller intentionally use subprocesses. Commands use argv, and runtime/dependency execution remains an explicit trust boundary. | Do not treat these warnings as proof that subprocess execution is safe; hostile-code/runtime gaps remain in THREAT_MODEL.md. |
| Four MEDIUM fixed `/tmp` warnings (B108) | These occurrences configure explicit container tmpfs/work directories or a regression child's HOME, rather than opening a predictable host temporary file. Actual scratch directories use private temporary-directory helpers. | Local runtime execution is still trusted-only; the documented container drill is scoped control evidence. |
| Two MEDIUM SQL string-format warnings (B608) | Collection names are checked against the fixed set `metrics`, `repairs`, `evaluations` before table-name interpolation; values are parameterized. An actual SQLite regression rejects injection names and preserves quoted payloads without dropping the snapshots table. | Preserve that allowlist. Arbitrary caller-selected table names are not supported. |

## CI policy and reproduction

`security-audit` retains the complete dependency and Bandit JSON reports. It
fails on any reported selected-dependency advisory, auditor error, incomplete
static scan, unknown severity or HIGH Bandit finding. LOW/MEDIUM warnings remain
visible for review; the job does not claim they are universally harmless. This
is a new additional check, not a weakened existing test/exposure policy.

```sh
python -m pip install -c requirements.build.lock -r requirements.audit.lock
python ci/security_audit.py
```

Tool versions are selected explicitly; their transitive environments are not a
complete hash lock. CI reports are bound to the job's exact source revision and
expire after 90 days. Audit failure and unknown execution remain stopped outcomes.
Operating-system images/native dependency code, all provider traffic, secret
history and cross-project authorization are not qualified by this scan. Keep
the remaining roadmap security gates open and do not call this certification.
