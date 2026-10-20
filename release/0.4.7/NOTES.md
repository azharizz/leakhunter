# Unspool 0.4.7 — evaluated prototype

Source: `722f3955bb44c270b24f248b9046f0f26df93a76`.

The CLI previously allowed `--once evaluate --gate` to exit successfully when
detection accuracy was perfect, including a correctly detected leak. This patch
rejects evaluation or serving with `--gate` before configuration or execution.
Ungated evaluation remains supported. The new regression failed before the fix;
the installed-wheel check also proves both command names reject the combination
without creating state.

Package verification pipeline 2969187062 passed 127 Python regressions, dashboard,
audit, both Linux installation jobs and the synthetic exposure gate. The same CI
wheel passed a fresh macOS Python 3.11.9 installation. All three environments
verified 40 files, three commands, persisted STOP cancellation, evaluation-gate
rejection and the trusted synthetic gate without source-checkout imports.
A real installed local HTTP check also passed graph annotation CRUD while keeping
the saved snapshot unchanged.

Wheel SHA-256: `7ebd8f69f93679ff7b4f2c095c528f76d79609e9d6da39fac9cb30fd21ae5963`.
Retained downloads include the wheel, verification records and SHA256SUMS.
Dependency auditing reported no advisories; Bandit still reports 14 LOW and
6 MEDIUM findings. This is not production qualification or security certification.

- [Judge installation and demo guide](https://gitlab.com/gitlab-ai-hackathon/transcend-october-2026/43244671/unspool/-/blob/main/JUDGE_GUIDE.md)
- [Release record and limits](https://gitlab.com/gitlab-ai-hackathon/transcend-october-2026/43244671/unspool/-/blob/main/RELEASE.md)
- [Package verification pipeline](https://gitlab.com/gitlab-ai-hackathon/transcend-october-2026/43244671/unspool/-/pipelines/2969187062)
- [Live read-only Cloud Run report](https://unspool-398376578726.us-central1.run.app)

Final main/report revision and deployment checks are retained separately in
`submission-checks.json`. Public pipeline metadata and retained records are
available anonymously; raw GitLab job-trace APIs and session pages require access.
The controller and graph annotation CRUD remain local. Historical external repair
records are not a new agent repair for this patch. Older 0.4.6 assets/tags are unchanged.
