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
SERVICE_NAME="${SERVICE_NAME:-bulwark}"
BUCKET_NAME="${BUCKET_NAME:-${PROJECT_ID}-bulwark-dashboard}"

echo "==> Building the dashboard"
BACKEND_URL="$(gcloud run services describe "${SERVICE_NAME}" --region="${REGION}" --project="${PROJECT_ID}" --format='value(status.url)' 2>/dev/null || true)"
if [ -n "${BACKEND_URL}" ]; then
  echo "    defaulting Base URL to the deployed Cloud Run service: ${BACKEND_URL}"
  (cd frontend && npm install && VITE_DEFAULT_BASE_URL="${BACKEND_URL}" npm run build)
else
  echo "    no Cloud Run service named '${SERVICE_NAME}' found in ${REGION} -- deploy it first with"
  echo "    deploy_cloud_run.sh, or set Base URL manually in the dashboard's Connection settings."
  (cd frontend && npm install && npm run build)
fi

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
if [ -n "${BACKEND_URL}" ]; then
  echo "Base URL is already baked in (${BACKEND_URL}) -- nothing to configure there."
else
  echo "Once it's open, set Base URL in the sidebar's Connection settings to your"
  echo "Cloud Run backend URL (from deploy_cloud_run.sh's output)."
fi
echo
echo "If the backend has BULWARK_UI_PASSWORD set, the dashboard opens on a login"
echo "page asking for that password -- see deploy_cloud_run.sh's BULWARK_UI_PASSWORD"
echo "option to gate this URL down to just judges/you instead of anyone who finds it."
echo
echo "And make sure the backend actually allows this origin -- add it to"
echo "BULWARK_CORS_ALLOW_ORIGINS on the Cloud Run service, e.g.:"
echo "  gcloud run services update ${SERVICE_NAME} --region=${REGION} --project=${PROJECT_ID} \\"
echo "    --update-env-vars=BULWARK_CORS_ALLOW_ORIGINS=https://storage.googleapis.com"
