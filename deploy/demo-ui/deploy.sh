#!/usr/bin/env bash
# Deploy the read-only demo UI (static files + recorded analyses) to Cloud Run, scaled to zero.
set -euo pipefail

project=project-df38a01c-6abb-4bc3-9c1
region=us-central1
builder=unspool-build@${project}.iam.gserviceaccount.com
runtime=unspool-web@${project}.iam.gserviceaccount.com
tag=$(git rev-parse --short=12 HEAD)
image=${region}-docker.pkg.dev/${project}/unspool/demo-ui:${tag}
here=$(cd "$(dirname "$0")" && pwd)

gcloud builds submit "$here" --project="$project" --region="$region" \
  --config="$here/../cloudrun/cloudbuild.yaml" --substitutions="_IMAGE=$image" \
  --service-account="projects/$project/serviceAccounts/$builder" \
  --gcs-source-staging-dir="gs://${project}-unspool-build/source" --quiet
gcloud run deploy unspool-demo --image="$image" --project="$project" --region="$region" \
  --service-account="$runtime" --port=8080 --cpu=1 --memory=256Mi \
  --min=0 --max=2 --concurrency=80 --timeout=30 --allow-unauthenticated --quiet
gcloud run services describe unspool-demo --project="$project" --region="$region" --format='value(status.url)'
