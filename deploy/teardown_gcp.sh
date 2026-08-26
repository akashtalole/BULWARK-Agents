#!/usr/bin/env bash
# Deletes the resources deploy_cloud_run.sh / deploy_frontend.sh create:
# the Cloud Run service, both Cloud Scheduler jobs, all Firestore data
# (the named "bulwark" database, not the whole project's Firestore), and
# the dashboard's Cloud Storage bucket. This is for getting a clean slate
# before a full redeploy -- e.g. to guarantee no stale data survives
# alongside a fresh BULWARK_SEED_DEMO_DATA run.
#
# Deliberately NOT deleted (safe/cheap to leave, and setup_gcp.sh's own
# idempotent checks skip recreating them if they still exist): the
# Artifact Registry repo and its images, Pub/Sub topics, the twelve
# per-agent IAM service accounts, and enabled APIs.
#
# Usage:
#   PROJECT_ID=my-project ./deploy/teardown_gcp.sh
#
# This is destructive and irreversible -- it asks for confirmation
# before deleting anything. Pass --yes to skip the prompt (e.g. in CI).
set -euo pipefail

PROJECT_ID="${PROJECT_ID:?Set PROJECT_ID, e.g. PROJECT_ID=my-project ./deploy/teardown_gcp.sh}"
REGION="${REGION:-us-central1}"
SERVICE_NAME="${SERVICE_NAME:-bulwark}"
FIRESTORE_DATABASE="${FIRESTORE_DATABASE:-bulwark}"
BUCKET_NAME="${BUCKET_NAME:-${PROJECT_ID}-bulwark-dashboard}"

if [[ "${1:-}" != "--yes" ]]; then
  echo "This permanently deletes, in project ${PROJECT_ID}:"
  echo "  - Cloud Run service:        ${SERVICE_NAME} (${REGION})"
  echo "  - Cloud Scheduler jobs:     bulwark-evidence-sweep, bulwark-drift-sweep"
  echo "  - Firestore database:       ${FIRESTORE_DATABASE} (ALL vendors/findings/questionnaires/etc.)"
  echo "  - Cloud Storage bucket:     gs://${BUCKET_NAME} (the dashboard build)"
  echo
  read -r -p "Type the project id (${PROJECT_ID}) to confirm: " CONFIRM
  if [[ "${CONFIRM}" != "${PROJECT_ID}" ]]; then
    echo "Aborted -- input didn't match ${PROJECT_ID}."
    exit 1
  fi
fi

echo "==> Deleting Cloud Scheduler jobs"
gcloud scheduler jobs delete bulwark-evidence-sweep --location="${REGION}" --project="${PROJECT_ID}" --quiet 2>/dev/null \
  || echo "    bulwark-evidence-sweep doesn't exist, skipping."
gcloud scheduler jobs delete bulwark-drift-sweep --location="${REGION}" --project="${PROJECT_ID}" --quiet 2>/dev/null \
  || echo "    bulwark-drift-sweep doesn't exist, skipping."

echo "==> Deleting the Cloud Run service"
gcloud run services delete "${SERVICE_NAME}" --region="${REGION}" --project="${PROJECT_ID}" --quiet 2>/dev/null \
  || echo "    ${SERVICE_NAME} doesn't exist, skipping."

echo "==> Deleting the Firestore database (disabling delete protection first if needed)"
if gcloud firestore databases describe --database="${FIRESTORE_DATABASE}" --project="${PROJECT_ID}" >/dev/null 2>&1; then
  gcloud firestore databases update --database="${FIRESTORE_DATABASE}" --project="${PROJECT_ID}" --no-delete-protection >/dev/null
  gcloud firestore databases delete --database="${FIRESTORE_DATABASE}" --project="${PROJECT_ID}" --quiet
else
  echo "    ${FIRESTORE_DATABASE} doesn't exist, skipping."
fi

echo "==> Deleting the dashboard's Cloud Storage bucket"
if gsutil ls -b "gs://${BUCKET_NAME}" >/dev/null 2>&1; then
  gsutil -m rm -r "gs://${BUCKET_NAME}"
else
  echo "    gs://${BUCKET_NAME} doesn't exist, skipping."
fi

echo
echo "Done. Rebuild with:"
echo "  PROJECT_ID=${PROJECT_ID} REGION=${REGION} ./deploy/setup_gcp.sh"
echo "  BULWARK_SEED_DEMO_DATA=true BULWARK_UI_PASSWORD=your-password BULWARK_CORS_ALLOW_ORIGINS=https://storage.googleapis.com \\"
echo "    PROJECT_ID=${PROJECT_ID} REGION=${REGION} ./deploy/deploy_cloud_run.sh"
echo "  PROJECT_ID=${PROJECT_ID} REGION=${REGION} ./deploy/deploy_frontend.sh"
