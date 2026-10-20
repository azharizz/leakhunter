# Controlled container isolation drill

This is an executed control check for the disposable Docker settings used by the
VAmPI benchmark. It is not a container escape audit, a malicious multi-tenant
qualification or a proof that the general Python runtime cannot forge evidence.
Run only with synthetic data on a dedicated disposable worker.

The probe tries to write the root/source paths, read a synthetic host canary and
credential paths, find the Docker socket and credential environment variables,
and connect by TCP to metadata (`169.254.169.254:80`) and an external address
(`1.1.1.1:443`). It sends no application request to those addresses, reads no
metadata token, and never prints credential values or file contents. It checks
the observed UID, effective capabilities, privilege flag and cgroup limits.
Missing/unknown limit data fails the probe rather than being counted as safe.

`run.sh` executes both network-none and internal-only network cases, without
mounting host credentials or a Docker socket. The only workload mount is the
read-only synthetic attack script. The actual host canary remains outside it.
It then passes a deliberately synthetic `GITLAB_TOKEN` to a negative-control
container: the probe must return failure, specifically because that variable is
present, while the other checks pass. A nonzero Docker/setup failure alone cannot
pass this negative control; the JSON result is inspected outside that container.

## Observed evidence

Initial [Cloud Build 07483223-985b-423b-805c-c6892f0c17d6](https://console.cloud.google.com/cloud-build/builds;region=us-central1/07483223-985b-423b-805c-c6892f0c17d6?project=398376578726)
passed 15 checks in both network modes. Observed limits were 268435456 bytes
memory, 64 processes and CPU quota 100000 for the 1-CPU configuration.
The final [Cloud Build b99654ca-27aa-4fa1-9411-d8b500637029](https://console.cloud.google.com/cloud-build/builds;region=us-central1/b99654ca-27aa-4fa1-9411-d8b500637029?project=398376578726)
passed all 16 checks in both network modes, including the observed temporary
filesystem bound of at most 32 MiB. The deliberately exposed synthetic credential
was rejected, and the external result inspector confirmed that all other checks
passed in that negative-control run. Resolved runtime image ID:
`sha256:541096ae9b05d3b850341b78790e2ed31e94d5aa0ea086933c6ff0c09ffa2e63`.
The memory/process/CPU observations matched the initial run. These are control
assertions on one worker configuration, not independent vulnerability cases.

Reproduce from the Unspool repository using an authorized GCP account:

```sh
gcloud builds submit benchmarks/isolation \
  --config=benchmarks/isolation/cloudbuild.yaml \
  --project=project-df38a01c-6abb-4bc3-9c1 --region=us-central1 \
  --service-account=projects/project-df38a01c-6abb-4bc3-9c1/serviceAccounts/unspool-build@project-df38a01c-6abb-4bc3-9c1.iam.gserviceaccount.com \
  --gcs-source-staging-dir=gs://project-df38a01c-6abb-4bc3-9c1-unspool-build/source
```

Cloud console evidence requires authorized access. Scripts are public and emit
only booleans, numeric limits and image identities. Download/build steps still
have network access and builder privileges; these workload checks do not certify
dependency builds. A blocked TCP connection to two addresses is not a test of
every possible egress route, DNS channel, kernel weakness or side channel.
The scripts assume `/workspace` and a dedicated Docker daemon per build.
