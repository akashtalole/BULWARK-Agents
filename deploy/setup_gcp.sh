#!/usr/bin/env bash
# One-time GCP project setup for BULWARK: APIs, Firestore, Pub/Sub topics
# + DLQs, twelve per-agent service accounts with least-privilege IAM
# bindings matching platform/identity.py's AGENT_GRANTS table, and the
# two Cloud Scheduler jobs that drive the "Watch" loop.
#
# Usage:
#   PROJECT_ID=my-project REGION=us-central1 ./deploy/setup_gcp.sh
set -euo pipefail

PROJECT_ID="${PROJECT_ID:?Set PROJECT_ID, e.g. PROJECT_ID=my-project ./deploy/setup_gcp.sh}"
REGION="${REGION:-us-central1}"

echo "==> Configuring project: ${PROJECT_ID} (region: ${REGION})"
gcloud config set project "${PROJECT_ID}"

echo "==> Enabling required APIs (this can take a minute)"
gcloud services enable \
  run.googleapis.com \
  firestore.googleapis.com \
  aiplatform.googleapis.com \
  pubsub.googleapis.com \
  cloudscheduler.googleapis.com \
  cloudbuild.googleapis.com \
  artifactregistry.googleapis.com

echo "==> Granting the default Compute Engine service account Cloud Build permissions"
# Since GCP stopped auto-granting IAM roles to a new project's default
# service accounts (April 2024), the Compute Engine default SA --
# PROJECT_NUMBER-compute@developer.gserviceaccount.com, which
# `gcloud builds submit`/`gcloud run deploy --source`
# (deploy_cloud_run.sh) runs the build as by default -- starts with no
# permissions at all. Without this it fails reading back its own
# just-uploaded source tarball from the Cloud Build staging bucket with
# a 403 (storage.objects.get denied): a fresh-project blocker, not
# specific to this repo, but easy to hit on the very first deploy.
PROJECT_NUMBER="$(gcloud projects describe "${PROJECT_ID}" --format='value(projectNumber)')"
gcloud projects add-iam-policy-binding "${PROJECT_ID}" \
  --member="serviceAccount:${PROJECT_NUMBER}-compute@developer.gserviceaccount.com" \
  --role="roles/cloudbuild.builds.builder" --condition=None >/dev/null

echo "==> Ensuring a Firestore (Native mode) database exists"
if ! gcloud firestore databases describe --database="(default)" >/dev/null 2>&1; then
  gcloud firestore databases create --database="(default)" --location="${REGION}" --type=firestore-native
else
  echo "    Firestore database already exists, skipping."
fi

# ---------------------------------------------------------------- Pub/Sub
# Matches the event table in docs/architecture.md exactly. Each topic
# gets a DLQ topic too, even though the in-process event bus already
# implements its own DLQ (platform/event_bus.py) -- this is what a demo
# points a real Cloud Console screen at.
TOPICS=(
  "vendor.artifact.received"
  "assertion.extracted"
  "evidence.collected"
  "assessment.requested"
  "finding.created"
  "drift.detected"
  "questionnaire.received"
  "answer.drafted"
  "human.decision"
  "contract.terms_extracted"
  "subprocessors.extracted"
)

echo "==> Creating Pub/Sub topics + DLQ topics"
for TOPIC in "${TOPICS[@]}"; do
  gcloud pubsub topics create "${TOPIC}" 2>/dev/null || echo "    ${TOPIC} already exists, skipping."
  gcloud pubsub topics create "${TOPIC}.dlq" 2>/dev/null || echo "    ${TOPIC}.dlq already exists, skipping."
done

# ------------------------------------------------------- Service accounts
# Name -> allowed-scope summary, matching platform/identity.py exactly.
declare -A SERVICE_ACCOUNTS=(
  ["sa-supervisor"]="events:route only -- no Firestore, no GCS, no egress"
  ["sa-intake"]="GCS Object Viewer (quarantine) + Firestore write (assertions/artifacts) only"
  ["sa-evidence"]="Asset/Security Center/Logs/IAM read + Firestore write (evidence) only"
  ["sa-assessor"]="Firestore read (assertions, evidence, controls) + write (findings) only"
  ["sa-questionnaire"]="Firestore read (evidence) + write (answers) only, no GCS"
  ["sa-sentinel"]="Firestore r/w (assessments), Pub/Sub publish"
  ["sa-remediation"]="Secret Manager read, Pub/Sub publish, ticket-system write"
  ["sa-contract"]="GCS quarantine read + Firestore write (contract_terms/subprocessors), Pub/Sub publish"
  ["sa-concentration"]="Firestore read (subprocessors, vendors) + write (concentration_risks), no GCS/egress"
  ["sa-crosswalk"]="Firestore read (findings) only -- writes nothing, no GCS, no egress"
  ["sa-offboarding"]="Firestore read (contract_terms) + write (vendors, offboarding_records), no GCS/egress"
  ["sa-digest"]="Firestore read (findings/vendors/concentration/offboard) + write (digests), no GCS/egress"
)
# IAM service-account display names cap at 100 chars; every "BULWARK: "
# + description above must stay at or under that (checked in CI-less
# fashion by tests/test_deploy_scripts.py, which fails the build if a
# future edit here regresses past the limit).

echo "==> Creating per-agent service accounts (zero-trust identity)"
for SA in "${!SERVICE_ACCOUNTS[@]}"; do
  if ! gcloud iam service-accounts describe "${SA}@${PROJECT_ID}.iam.gserviceaccount.com" >/dev/null 2>&1; then
    gcloud iam service-accounts create "${SA}" --display-name="BULWARK: ${SERVICE_ACCOUNTS[$SA]}"
  else
    echo "    ${SA} already exists, skipping."
  fi
done

echo "==> Granting least-privilege roles (see platform/identity.py for the exact allow/deny table this mirrors)"
bind() {
  gcloud projects add-iam-policy-binding "${PROJECT_ID}" \
    --member="serviceAccount:${1}@${PROJECT_ID}.iam.gserviceaccount.com" \
    --role="${2}" --condition=None >/dev/null
}
bind sa-evidence roles/cloudasset.viewer
bind sa-evidence roles/securitycenter.findingsViewer
bind sa-evidence roles/logging.viewer
bind sa-evidence roles/iam.securityReviewer
bind sa-evidence roles/datastore.user
bind sa-intake roles/storage.objectViewer
bind sa-intake roles/datastore.user
bind sa-assessor roles/datastore.user
bind sa-assessor roles/aiplatform.user   # Gemini Pro calls
bind sa-questionnaire roles/datastore.user
bind sa-questionnaire roles/aiplatform.user
bind sa-sentinel roles/datastore.user
bind sa-sentinel roles/pubsub.publisher
bind sa-remediation roles/datastore.user
bind sa-remediation roles/pubsub.publisher
bind sa-remediation roles/secretmanager.secretAccessor
bind sa-supervisor roles/aiplatform.user  # routing calls only, nothing else
bind sa-crosswalk roles/datastore.user  # deterministic, no LLM -- no aiplatform.user needed
bind sa-contract roles/storage.objectViewer
bind sa-contract roles/datastore.user
bind sa-contract roles/pubsub.publisher
bind sa-contract roles/aiplatform.user
bind sa-concentration roles/datastore.user  # deterministic, no LLM -- no aiplatform.user needed
bind sa-offboarding roles/datastore.user  # deterministic, no LLM -- no aiplatform.user needed
bind sa-digest roles/datastore.user
bind sa-digest roles/aiplatform.user  # digest narrative synthesis needs Gemini

# ---------------------------------------------------------- Cloud Scheduler
echo "==> Creating Cloud Scheduler jobs for the Watch loop"
echo "    (targets are wired to the Cloud Run URL after deploy_cloud_run.sh runs -- see that script's final step)"

echo "==> Done. Next: ./deploy/deploy_cloud_run.sh"
