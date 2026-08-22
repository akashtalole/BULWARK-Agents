#!/usr/bin/env bash
# Build and deploy BULWARK to Cloud Run (scaled to zero), then point the
# two Cloud Scheduler jobs at the live URL.
#
# Usage:
#   PROJECT_ID=my-project REGION=us-central1 ./deploy/deploy_cloud_run.sh
#
# Cost controls: --min-instances=0 (scales to zero, $0 while idle),
# --max-instances=3 (hard ceiling against spikes), 1cpu/1Gi (the
# multi-agent event chain needs a bit more headroom than a single-agent
# service, still far from a "big" instance).
set -euo pipefail

PROJECT_ID="${PROJECT_ID:?Set PROJECT_ID, e.g. PROJECT_ID=my-project ./deploy/deploy_cloud_run.sh}"
REGION="${REGION:-us-central1}"
SERVICE_NAME="${SERVICE_NAME:-bulwark}"
SERVICE_ACCOUNT_NAME="${SERVICE_ACCOUNT_NAME:-sa-supervisor}"  # the Cloud Run *ingress* identity; per-agent SAs are enforced in-app
IMAGE="${REGION}-docker.pkg.dev/${PROJECT_ID}/cloud-run-source-deploy/${SERVICE_NAME}"

echo "==> Building container image: ${IMAGE}"
gcloud builds submit --tag "${IMAGE}" .

echo "==> Deploying to Cloud Run: ${SERVICE_NAME} (${REGION})"
gcloud run deploy "${SERVICE_NAME}" \
  --image="${IMAGE}" \
  --project="${PROJECT_ID}" \
  --region="${REGION}" \
  --set-env-vars="GOOGLE_CLOUD_PROJECT=${PROJECT_ID},GOOGLE_GENAI_USE_VERTEXAI=true,USE_FIRESTORE=true,USE_PUBSUB=${USE_PUBSUB:-true},BULWARK_ENVIRONMENT=cloud-run,GEMINI_FLASH_MODEL=${GEMINI_FLASH_MODEL:-gemini-flash-latest},GEMINI_PRO_MODEL=${GEMINI_PRO_MODEL:-gemini-pro-latest},BULWARK_API_KEYS=${BULWARK_API_KEYS:-demo-key}" \
  --min-instances=0 \
  --max-instances="${MAX_INSTANCES:-3}" \
  --cpu=1 \
  --memory=1Gi \
  --allow-unauthenticated \
  --port=8080

SERVICE_URL="$(gcloud run services describe "${SERVICE_NAME}" --region="${REGION}" --format='value(status.url)')"
echo "==> Deployed: ${SERVICE_URL}"

echo "==> Wiring Cloud Scheduler jobs to the live URL"
gcloud scheduler jobs create http bulwark-evidence-sweep \
  --location="${REGION}" \
  --schedule="0 */${EVIDENCE_SWEEP_HOURS:-6} * * *" \
  --uri="${SERVICE_URL}/evidence-collector/tick" \
  --http-method=POST \
  --headers="X-API-Key=${BULWARK_API_KEYS:-demo-key}" \
  2>/dev/null || echo "    bulwark-evidence-sweep already exists, skipping (use 'gcloud scheduler jobs update' to change it)."

gcloud scheduler jobs create http bulwark-drift-sweep \
  --location="${REGION}" \
  --schedule="0 */${DRIFT_SWEEP_HOURS:-24} * * *" \
  --uri="${SERVICE_URL}/drift-sentinel/tick" \
  --http-method=POST \
  --headers="X-API-Key=${BULWARK_API_KEYS:-demo-key}" \
  2>/dev/null || echo "    bulwark-drift-sweep already exists, skipping."

echo
echo "Reminder: this endpoint is protected by the app's own X-API-Key check,"
echo "but for production use also consider --no-allow-unauthenticated + IAM"
echo "invoker bindings scoped to the scheduler's service account, and set"
echo "BULWARK_API_KEYS to your own secret values (not the demo default)."
echo
echo "Service URL: ${SERVICE_URL}"
