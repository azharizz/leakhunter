#!/usr/bin/env bash
set -euo pipefail

project=project-df38a01c-6abb-4bc3-9c1
region=us-central1
number=398376578726
deployer=unspool-deploy@${project}.iam.gserviceaccount.com
builder=unspool-build@${project}.iam.gserviceaccount.com
runtime=unspool-web@${project}.iam.gserviceaccount.com
provider=projects/${number}/locations/global/workloadIdentityPools/unspool-gitlab/providers/gitlab
revision=${CI_COMMIT_SHA:-$(git rev-parse HEAD)}
[[ "$revision" =~ ^[0-9a-f]{40}$ ]]
image=${region}-docker.pkg.dev/${project}/unspool/report:${revision}

if [[ -n "${GCP_ID_TOKEN:-}" ]]; then
  umask 077
  credential_dir=$(mktemp -d)
  trap 'rm -rf "$credential_dir"' EXIT
  printf '%s' "$GCP_ID_TOKEN" > "$credential_dir/token"
  gcloud iam workload-identity-pools create-cred-config "$provider" \
    --service-account="$deployer" --credential-source-file="$credential_dir/token" \
    --output-file="$credential_dir/credentials.json" --quiet
  gcloud auth login --cred-file="$credential_dir/credentials.json" --quiet
fi

# The container build context contains only independently verified public files.
test -s public/health.json
python3 -c 'import json,sys; assert json.load(open("public/health.json")) == {"status":"ok","commit":sys.argv[1],"verified":True}' "$revision"
cp deploy/cloudrun/Dockerfile public/Dockerfile
gcloud builds submit public --project="$project" --region="$region" \
  --config=deploy/cloudrun/cloudbuild.yaml --substitutions="_IMAGE=$image" \
  --service-account="projects/$project/serviceAccounts/$builder" \
  --gcs-source-staging-dir="gs://${project}-unspool-build/source" --quiet
gcloud run deploy unspool --image="$image" --project="$project" --region="$region" \
  --service-account="$runtime" --port=8080 --cpu=1 --memory=256Mi \
  --min=0 --max=1 --concurrency=80 --timeout=30 --quiet
url=$(gcloud run services describe unspool --project="$project" --region="$region" --format='value(status.url)')
python3 -m unspool.smoke --url "$url" --commit "$revision"
printf 'Unspool Cloud Run: %s\n' "$url"
