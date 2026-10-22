# Real-advisory benchmark

**Question:** for real, published Python information-exposure advisories, does Unspool flag the leak
at the vulnerable commit and stop flagging it at the fix commit?

## Cases

`cases.json` holds 8 GitHub-reviewed pip advisories. They were selected from the 397 advisories with
CWE-200/201/209/359/532 on 21 October 2026:

1. Keep only advisories where a secret field reaches a response, log or outbound payload in Python code,
   and a fix commit is linked.
2. From those, choose 8 that cover different leak shapes. All 8 were chosen before any Unspool run.

| Advisory | Leak shape |
| --- | --- |
| GHSA-635v-pc42-fr74 (sagemaker-training) | Token from an API response field logged in a pip command |
| GHSA-2wx6-wc87-rmjm / CVE-2020-5262 (easybuild) | `headers` argument with `Authorization` logged |
| GHSA-7rcj-2493-83x3 / CVE-2026-9073 (foreman-mcp-server) | Header deny-list misses credential headers |
| GHSA-r297-p3v4-wp8m / CVE-2026-32633 (glances) | Server list with passwords returned by the API |
| GHSA-cvwp-r2g2-j824 / CVE-2026-32609 (glances) | `vars(self.args)` with the password hash returned |
| GHSA-xmfj-7pp5-fxr6 / CVE-2026-25211 (llama-stack) | Config with password interpolated into a log |
| GHSA-v853-p72q-4cfw (quart) | Raw request body printed |
| GHSA-gh7p-78x6-jw6m / CVE-2026-59222 (open-webui) | Full user model with OAuth/SCIM fields returned |

**Labels come from each advisory:** the fix commit's first parent leaks, and the fix commit does not.
Each case names the functions the fix changed, and a policy that marks the advisory's secret fields.

## Run

```sh
python3 -m benchmarks.cves.run                      # static analysis only, free
AGENT_PROVIDER_API_KEY=... python3 -m benchmarks.cves.run --decision-model openai/gpt-6-luna-decisions
```

**What the runner does:**
- Fetches only the two commits per repository, never a full clone.
- Exports only the files the fix changed.
- Analyzes the named functions as entrypoints.
- Writes `results/<timestamp>/results.json` and `RESULTS.md`. Publish every run.

**Outcomes, per detector (static and Luna):**

| Outcome | Meaning |
| --- | --- |
| `HIT` | Flagged at the vulnerable commit only |
| `FALSE_ALARM_ON_FIX` | Flagged at both commits |
| `MISS` | Flagged at neither |
| `INVERTED` | Flagged at the fix only |
| `NOT_REPRODUCED` | The case could not be fetched or analyzed (the error is kept) |

## Limits

- **No runtime probes:** these projects need their own dependencies and credentials to run, so runtime
  probes were not attempted. Only static analysis and Luna review are measured.
- **One file per case:** only the changed file is analyzed, so calls into the rest of each project
  are unresolved.
- **Small set:** 8 cases cannot estimate production accuracy. They show which real leak shapes Unspool
  does and does not model.
