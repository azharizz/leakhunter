# Unspool demo UI (Cloud Run)

The real Unspool front-end (`unspool/static`) served with recorded analyses from MR !30: the leak
candidate, GitLab Duo's fix, and a no-policy run. Static files only; a small script in `site/app/index.html`
answers the app's `/api` calls from `site/api-*/` and refuses every write, so the demo is read-only.

Deploy (scales to zero; pay only while it is open):

```sh
bash deploy/demo-ui/deploy.sh
```

It builds with the project's dedicated build service account (as `deploy/cloudrun` does) and deploys
`unspool-demo` with no minimum instances, so it costs nothing while nobody has it open.
