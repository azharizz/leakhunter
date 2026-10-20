# Unspool 0.4.6 — evaluated prototype

Source: `05bbefc6e936d7efab8f0a7b10aeb04e77742ee3`.
The source-bound HTTP evidence adapter adds optional operator-owned plan, probe,
image and case pins to the existing review controller. The Docker worker remains
a dedicated disposable-worker demonstration; the historical external GitLab
pipeline has not been migrated to it.

The release pipeline passed 126 Python regressions, dashboard checks, the
synthetic exposure gate, auditing, both Linux wheel-installation jobs and public
report delivery. The same CI wheel passed fresh macOS Python 3.11.9 installation.
All three environments verified 40 packaged files, three commands, STOP
cancellation and the trusted synthetic gate without source-checkout imports.

Wheel SHA-256: `9be68ac05bfb256a63d9bb6fe55a8fe1f3d69eb591f13aa9e280a3fb756b9d87`.
Retained downloads include the wheel, verification records and SHA256SUMS.
Dependency auditing reported no advisories; Bandit still reports 14 LOW and
6 MEDIUM findings. This is not production qualification or security certification.

- [Judge installation and demo guide](https://gitlab.com/gitlab-ai-hackathon/transcend-october-2026/43244671/unspool/-/blob/main/JUDGE_GUIDE.md)
- [Full release record and limitations](https://gitlab.com/gitlab-ai-hackathon/transcend-october-2026/43244671/unspool/-/blob/main/RELEASE.md)
- [Exact release pipeline](https://gitlab.com/gitlab-ai-hackathon/transcend-october-2026/43244671/unspool/-/pipelines/2969101179)
- [Live read-only Cloud Run report](https://unspool-398376578726.us-central1.run.app)

The automation controller and graph annotation CRUD run locally. No hosted
repository execution, general hands-off security remediation or customer
acceptance is claimed. See the linked submission/evidence map for the actual
bounded synthetic handoff and supervised external lab repair.
