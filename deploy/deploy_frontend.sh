#!/usr/bin/env bash
# Build and deploy the BULWARK dashboard (frontend/) as a static site on
# Google Cloud Storage -- the simplest way to get it a real public URL
# without a second Cloud Run service or a custom domain.
#
# Usage:
#   PROJECT_ID=my-project ./deploy/deploy_frontend.sh
set -euo pipefail

PROJECT_ID="${PROJECT_ID:?Set PROJECT_ID, e.g. PROJECT_ID=my-project ./deploy/deploy_frontend.sh}"
REGION="${REGION:-us-central1}"
BUCKET_NAME="${BUCKET_NAME:-${PROJECT_ID}-bulwark-dashboard}"

echo "==> Building the dashboard"
(cd frontend && npm install && npm run build)

echo "==> Ensuring the Cloud Storage bucket exists"
if ! gsutil ls -b "gs://${BUCKET_NAME}" >/dev/null 2>&1; then
  gsutil mb -p "${PROJECT_ID}" -l "${REGION}" "gs://${BUCKET_NAME}"
else
  echo "    gs://${BUCKET_NAME} already exists, skipping."
fi

echo "==> Making it publicly readable"
gsutil iam ch allUsers:objectViewer "gs://${BUCKET_NAME}" >/dev/null

echo "==> Uploading the build (mirrors frontend/dist exactly, deleting anything stale)"
gsutil -m rsync -r -d frontend/dist "gs://${BUCKET_NAME}"

URL="https://storage.googleapis.com/${BUCKET_NAME}/index.html"
echo
echo "Deployed: ${URL}"
echo
echo "This is a plain static file, not a load-balancer-fronted website. The"
echo "app uses hash-based routing (#/vendors/123) specifically so this works:"
echo "every in-app URL, including bookmarked/shared deep links, is really"
echo "just the one object above plus a fragment the server never sees, so"
echo "there's nothing to 404 on."
echo
echo "Once it's open, set these in the sidebar's Connection settings:"
echo "  Base URL: your Cloud Run backend URL (from deploy_cloud_run.sh's output)"
echo "  API key:  your BULWARK_API_KEYS value (demo-key unless you changed it)"
echo
echo "And make sure the backend actually allows this origin -- add it to"
echo "BULWARK_CORS_ALLOW_ORIGINS on the Cloud Run service, e.g.:"
echo "  gcloud run services update bulwark --region=${REGION} --project=${PROJECT_ID} \\"
echo "    --update-env-vars=BULWARK_CORS_ALLOW_ORIGINS=https://storage.googleapis.com"
