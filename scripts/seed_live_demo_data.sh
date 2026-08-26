#!/usr/bin/env bash
# Seeds the demo scenario DIRECTLY into the live Firestore database a
# deployed Cloud Run service reads from -- bypasses
# BULWARK_SEED_DEMO_DATA + cold-start timing entirely (main.py's seeding
# hook only runs once per container start, so it's easy for the env var
# to never actually reach a running container, or for the seed to run
# before you ever hit the URL to trigger a cold start).
#
# scripts/seed_demo_data.py's repos route straight to Firestore whenever
# USE_FIRESTORE=true and GOOGLE_CLOUD_PROJECT are set (see
# platform/store.py) -- this runs it locally with the SAME project and
# database name the deployed service uses, so it writes into the exact
# Firestore data the live dashboard already reads from. No redeploy, no
# cold start, no env var to get lost on the way to Cloud Run.
#
# Usage:
#   PROJECT_ID=my-project ./scripts/seed_live_demo_data.sh
#
# Requires local credentials with Firestore write access to the project
# (the same ones your other gcloud/deploy commands already use):
#   gcloud auth application-default login
#
# Safe to run more than once -- vendors are looked up by name and
# reused, but findings/artifacts/tickets are not deduplicated, so
# rerunning adds another round of those rather than being fully
# idempotent. Fine for a demo; don't loop it.
set -euo pipefail

PROJECT_ID="${PROJECT_ID:?Set PROJECT_ID, e.g. PROJECT_ID=my-project ./scripts/seed_live_demo_data.sh}"
FIRESTORE_DATABASE="${FIRESTORE_DATABASE:-bulwark}"

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${REPO_ROOT}"

if [ -x ".venv/bin/python3" ]; then
  PYTHON=".venv/bin/python3"
else
  PYTHON="python3"
  echo "==> No .venv found -- installing dependencies with ${PYTHON}"
  "${PYTHON}" -m pip install -q -r requirements.txt
fi

echo "==> Seeding the demo scenario directly into Firestore (project=${PROJECT_ID}, database=${FIRESTORE_DATABASE})"
GOOGLE_CLOUD_PROJECT="${PROJECT_ID}" \
USE_FIRESTORE=true \
FIRESTORE_DATABASE="${FIRESTORE_DATABASE}" \
PYTHONPATH=src \
  "${PYTHON}" scripts/seed_demo_data.py

echo
echo "Done. Refresh the dashboard (Vendors / Questionnaires) -- it reads"
echo "from this same Firestore database, so no redeploy or cold start needed."
