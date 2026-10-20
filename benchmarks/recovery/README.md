# Real GitLab review-controller interruption drill

`observe.py` wraps the installed controller's GitLab client without substituting
any response. It permits GET only: POST, PUT and DELETE stop locally before they
can reach GitLab. It requires an operator-owned review-mode configuration and an
existing MR on the issue's stable branch. It cannot create an MR, trigger an
agent or merge. Run the script with an installed Unspool virtual-environment
interpreter from outside the target checkout.

The controlled [issue #2](https://gitlab.com/gitlab-ai-hackathon/transcend-october-2026/43244671/unspool-vampi-delivery/-/work_items/2)
and [MR !2](https://gitlab.com/gitlab-ai-hackathon/transcend-october-2026/43244671/unspool-vampi-delivery/-/merge_requests/2)
contain only a comment clarification in `api_views/users.py`. No application
behavior or verifier contract changed. This is a restart test, not a new security
repair, discovery result or Duo automation success. Candidate SHA:
`951960c9d85ea874a5f9e0248c42b83f9751d499`; real candidate pipeline
`2968122599` passed independent HTTP acceptance and syntax checks.

## Procedure

Using the same configuration and private state directory for every invocation:

```sh
/path/to/installed/python /path/to/unspool/benchmarks/recovery/observe.py \
  --config /operator/handoff.vampi-delivery.json --issue 2 \
  --state-dir /operator/private-recovery-state --fault after-mr
```

The process prints the reached boundary and sends SIGKILL to itself after the
actual server response. This deliberately skips context-manager cleanup, testing
the OS lock release and the production controller's previously persisted state.
Read the journal without changing it. Repeat with `--fault after-evidence`, then
with `--fault none` to finish. Do not delete state between runs or change config.
While a normal run is active, start a second command with the same state directory
to verify that competing delivery fails on the target lock before making API calls.

Expected final result is `READY_FOR_REVIEW` for the exact original MR SHA and
pipeline, with zero writes. Confirm the MR count, source branch, target SHA and
issue notes in GitLab after the exercise. Do not merge the test MR as part of the
drill. This checks recovery around existing-MR reads; trigger delivery, remote
merge/deployment interruption and production rollback require separate exercises.

## Observations

On 21 October the fresh installed 0.4.3 wheel repeated `--fault none` against the
same existing issue/MR, using isolated imports from `/tmp` and a new private state
directory. It returned READY_FOR_REVIEW for the same SHA, pipeline and config
digest after 23 GET requests and zero writes. The added reads check the current
MR/pipeline and target before returning readiness. Wheel SHA-256 was
`1b6f162d6b2e76d1b3ea044780f10908cce9674252629e355a159aaae15eda70`.
This replay qualifies the live read-only path for that version; it does not repeat
the killed-process exercise or inject a live revision race.

Initial `after-mr` run reached 14 real reads and exited 137/SIGKILL. Its journal
remained `VERIFYING`, `merge_request: 2`, with configuration digest
`888b3d9f4b78d985b3cfde7bea3f9550f06119c0116af3779065b6a18dedae5b`.
The resumed `after-evidence` run reached 17 actual reads, retrieved the real
evidence artifact, then also exited 137/SIGKILL. The journal still retained the
original intent. A normal resume then returned `READY_FOR_REVIEW` for MR !2,
SHA `951960c9d85ea874a5f9e0248c42b83f9751d499` and pipeline `2968122599`,
after 21 read requests and zero writes. A duplicate invocation launched while
that resume held the target lock failed with `BlockingIOError` before any API
request. The journal ended `READY_FOR_REVIEW`.

Afterward GitLab still showed exactly one MR for `unspool/repair-2`, open at the
same SHA; target master remained `c146bd1b9ee9fbe2730c316675de1fa7e55f0fa1`.
Issue notes remained the two preexisting system notes (IDs `4051206346` and
`4051194316`), with no agent trigger. An additional unwrapped installed CLI replay
using `unspool-handoff --config ... --issue 2 --state-dir ...` also returned
`READY_FOR_REVIEW` for that same SHA/pipeline. The durable journal ended with that
status, source SHA, MR IID and pipeline ID. The configuration and state directory
were unchanged throughout both killed runs, the successful resume and CLI replay.

The interpreter used the separately installed 0.4.0 wheel, not target-checkout
imports. Installed module SHA-256 identities were:

- `unspool/handoff.py`: `360310679e4279e577b21f65f0dd21254a59abd55e4caa1cad67d05455836785`.
- `unspool/handoff_state.py`: `db55e7b5368a91eb7375146feb7717a78a57a8a7524af057f36ec889b1d7245e`.

The current source has additional file-read hardening; this older artifact drill
does not qualify later controller changes without rerunning them. All 97 local
regression tests passed, including two wrapper tests proving server responses
are preserved, mutations never dispatch and faults occur after actual reads.
The mock wrapper tests are not the real GitLab observations recorded above.
