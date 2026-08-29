# Setup Guide

This is the detailed version of README.md's "Spin-up instructions" --
every path (local, Docker, Cloud Run), every environment variable, and
the failure modes you'll actually hit. If you just want the fastest
path to a running instance, README.md's quick-start is enough; come
here when you need the full picture or something isn't working.

## Contents

- [Prerequisites](#prerequisites)
- [Path 1: Local, in-memory, no cloud project](#path-1-local-in-memory-no-cloud-project)
- [Running the test suite](#running-the-test-suite)
- [Running the dashboard](#running-the-dashboard)
- [Configuring Gemini credentials](#configuring-gemini-credentials)
- [Environment variable reference](#environment-variable-reference)
- [Path 2: Local with Docker](#path-2-local-with-docker)
- [Path 3: Deploy to Google Cloud](#path-3-deploy-to-google-cloud)
- [Verifying a deployment](#verifying-a-deployment)
- [Cost controls](#cost-controls)
- [Troubleshooting](#troubleshooting)

## Prerequisites

| For | You need |
|---|---|
| Local dev (Path 1) | Python 3.11+, `pip` |
| Docker (Path 2) | Docker |
| Cloud Run (Path 3) | A GCP project with billing enabled, the `gcloud` CLI authenticated (`gcloud auth login`), and `PROJECT_ID` you can set env vars against |
| Live Gemini calls (any path) | Either a Gemini API key (console.cloud.google.com / AI Studio) **or** a GCP project with Vertex AI enabled |

Nothing here requires a GCP project to get the API running -- the whole
fleet operates in-memory with zero cloud setup. A GCP project is only
needed once you want (a) real Gemini calls from the agents' LLM steps,
or (b) Firestore/Pub/Sub/Cloud Run instead of the in-memory equivalents.

## Path 1: Local, in-memory, no cloud project

```bash
git clone https://github.com/akashtalole/BULWARK-Agents.git
cd BULWARK-Agents
python3 -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt
pip install pytest pytest-asyncio httpx   # dev/test only, not needed to run the service
```

Run it:

```bash
export PYTHONPATH=src
export BULWARK_SEED_DEMO_DATA=true   # seeds realistic demo data on startup, see below
uvicorn bulwark.main:app --reload --port 8080
```

You now have a fully working BULWARK instance at `http://localhost:8080`.
Every deterministic mechanism (Model Armor screening, the kill switch,
Evidence Collector, Concentration Analyzer, Framework Crosswalk, the
citation-validation gate) works immediately with **zero credentials**.
The three routes that call an LLM -- `POST /vendors/artifacts` (both
branches: SOC2/ISO-style extraction via Intake, and MSA/DPA-style
contract review via Contract Intelligence), `POST /questionnaires`, and
`POST /drift-sentinel/tick` -- return `503 Orchestration is not
configured` until you add Gemini credentials -- see
[Configuring Gemini credentials](#configuring-gemini-credentials) below.

`BULWARK_SEED_DEMO_DATA=true` (set above) already seeded realistic data
on startup -- vendors, findings, a poisoned artifact, a questionnaire,
works with zero credentials (see `scripts/seed_demo_data.py`'s module
docstring). Explore it immediately:

```bash
curl -s -H 'X-API-Key: demo-key' http://localhost:8080/registry | jq
curl -s -H 'X-API-Key: demo-key' http://localhost:8080/vendors | jq
```

If you'd rather seed on demand instead of on every startup, leave
`BULWARK_SEED_DEMO_DATA` unset and run `python scripts/seed_demo_data.py`
directly -- but only from code that shares the running server's process
(e.g. a debugger attached to it), or against a shared `USE_FIRESTORE=true`
store. Run as a separate `python` process against the default in-memory
store, its writes land in a store the running server never reads from.

`demo-key` is the default API key (`BULWARK_API_KEYS` in
[Environment variable reference](#environment-variable-reference)).

## Running the test suite

```bash
PYTHONPATH=src pytest -q
```

195 tests, none requiring live Gemini credentials -- every deterministic
piece (guardrails, citation validation, the autonomy ladder, event-bus
DLQ/idempotency, the circuit breaker, rollback, the crosswalk lookup,
risk-trend detection, offboarding-deadline tracking) is exercised
directly against the tool functions,
and the API layer is tested with the LLM-backed orchestration functions
swapped for fakes (see `tests/test_api.py`'s module docstring). If a test
fails on a fresh clone, it's a real regression, not a missing credential
-- see [Troubleshooting](#troubleshooting).

## Running the dashboard

```bash
cd frontend
npm install
npm run dev
```

Opens on `http://localhost:5173`, talks to whatever Agent Gateway is
configured under **Connection** in the sidebar (`http://localhost:8080` +
`demo-key` by default, both stored in `localStorage`). Needs the server
from [Path 1](#path-1-local-in-memory-no-cloud-project) (or Docker/Cloud
Run) already running -- the dashboard is a client, it has no server of
its own beyond Vite's dev server / a static file host in production. See
[`frontend/README.md`](https://github.com/akashtalole/BULWARK-Agents/blob/main/frontend/README.md)
for the production build and CORS configuration when the dashboard is
deployed to its own origin.

## Configuring Gemini credentials

Pick exactly one path.

**Path A -- Gemini API / AI Studio** (fastest to set up):

```bash
export GOOGLE_API_KEY=your-key
```

Get a key at [aistudio.google.com](https://aistudio.google.com/apikey).

**Path B -- Vertex AI** (uses your GCP project's Application Default
Credentials, no separate API key to manage):

```bash
export GOOGLE_CLOUD_PROJECT=your-project
export GOOGLE_GENAI_USE_VERTEXAI=true
gcloud auth application-default login
```

Either way, restart the server (`uvicorn` doesn't need a code change,
just fresh env vars in the process) and the four LLM-backed routes stop
returning 503. Verify with:

```bash
curl -s -H 'X-API-Key: demo-key' -X POST http://localhost:8080/vendors/artifacts \
  -H 'Content-Type: application/json' \
  -d '{"vendor_name": "Test Co", "doc_type": "SOC2", "raw_text": "We enforce MFA for all employee access."}'
```

A `200` with `"status": "extracted"` means credentials are working. A
`503` means they aren't picked up yet -- double-check the env var is
actually exported in the same shell/process that started `uvicorn`.

## Environment variable reference

Every setting is env-var-driven (`src/bulwark/config.py`); nothing is
hardcoded, and there's no config file to edit. Copy `.env.example` to
`.env` as a starting point (note: `main.py` doesn't auto-load `.env` --
either `export` the values yourself or run under `dotenv run`).

| Variable | Purpose | Default |
|---|---|---|
| `GOOGLE_API_KEY` | Gemini API key (credential Path A) | unset |
| `GOOGLE_CLOUD_PROJECT` | GCP project id (credential Path B, and/or Firestore/Pub/Sub) | unset |
| `GOOGLE_GENAI_USE_VERTEXAI` | Route Gemini calls through Vertex AI instead of the Gemini API | `false` |
| `GEMINI_FLASH_MODEL` | Model id for the seven Flash-backed agents | `gemini-3.5-flash` (GA) |
| `GEMINI_PRO_MODEL` | Model id for Risk Assessor (the one agent on Pro) | `gemini-3.1-pro-preview` (preview -- no GA Gemini 3.5+ Pro model exists yet; override if your project lacks allowlist access) |
| `USE_FIRESTORE` | Use Firestore instead of in-memory dict stores | `true` once `GOOGLE_CLOUD_PROJECT` is set, otherwise `false` |
| `FIRESTORE_DATABASE` | Firestore database id -- use a named database (`deploy/setup_gcp.sh` creates one called `bulwark`), never the literal `(default)`: confirmed via a real Cloud Run crash that the Python client resolves `(default)` to that literal string either way, and something downstream percent-encodes its parentheses, which Firestore then rejects | `bulwark` |
| `USE_PUBSUB` | Also mirror every event onto real Pub/Sub topics (in-process dispatch always happens regardless) | `false` |
| `BULWARK_API_KEYS` | Comma-separated allowlist the Agent Gateway accepts in `X-API-Key` | `demo-key` |
| `BULWARK_CORS_ALLOW_ORIGINS` | Comma-separated origins allowed to call the API cross-origin (the dashboard's origin) | `http://localhost:5173,http://127.0.0.1:5173` |
| `RATE_LIMIT_REQUESTS` | Requests allowed per key per window | `30` |
| `RATE_LIMIT_WINDOW_SECONDS` | Rate-limit window length | `60` |
| `ANSWER_CONFIDENCE_THRESHOLD` | Questionnaire Responder abstains below this (0.0-1.0) | `0.75` |
| `EVIDENCE_FRESHNESS_DAYS` | Evidence older than this is downgraded to "stale" | `30` |
| `EVIDENCE_SWEEP_HOURS` | Cloud Scheduler cadence for `/evidence-collector/tick` in production | `6` |
| `DRIFT_SWEEP_HOURS` | Cloud Scheduler cadence for `/drift-sentinel/tick` in production | `24` |
| `RESIDUAL_RISK_HUMAN_THRESHOLD` | A finding at/above this residual_risk (1-25) always requires human review | `15` |
| `BULWARK_DEFAULT_TENANT` | Tenant id used throughout this single-tenant-demo build | `acme-eu` |
| `BULWARK_SERVICE_NAME` | Service name (Cloud Run service name, OTel resource name) | `bulwark` |
| `BULWARK_SERVICE_VERSION` | Version string surfaced in observability spans | `0.1.0` |
| `BULWARK_ENVIRONMENT` | Free-text environment label (`local`, `cloud-run`, ...) | `local` |

One setting is **not** an env var on purpose: `fleet_config.max_daily_token_spend`
(the circuit breaker's cap) is a runtime value you set via
`POST /fleet-config`, the same way you'd operate the kill switch --
adjustable without a redeploy. See the User Guide's "Fleet management"
section.

## Path 2: Local with Docker

```bash
docker build -t bulwark .
docker run -p 8080:8080 \
  -e GOOGLE_API_KEY=your-key \
  -e BULWARK_API_KEYS=demo-key \
  bulwark
```

The image is `python:3.11-slim`, installs `requirements.txt`, and runs
`uvicorn bulwark.main:app` on `$PORT` (defaults to 8080, which is also
what Cloud Run injects at deploy time -- same image, no changes needed
between local Docker and Cloud Run).

## Path 3: Deploy to Google Cloud

This provisions real infrastructure and will incur (small) GCP charges
while running -- see [Cost controls](#cost-controls) to keep it near
zero. `--min-instances=0` means the Cloud Run service costs nothing
while idle; the only ongoing cost is Firestore/Pub/Sub storage, which is
negligible for a demo-sized dataset.

```bash
export PROJECT_ID=your-project
export REGION=us-central1        # optional, this is the default
gcloud auth login                 # if you haven't already
gcloud config set project "$PROJECT_ID"
```

**Step 1 -- provision infrastructure** (`deploy/setup_gcp.sh`):

```bash
./deploy/setup_gcp.sh
```

This enables the required APIs, creates Firestore in Native mode (if not
already present), creates every Pub/Sub topic in `platform/event_bus.py`
plus a matching `.dlq` topic for each, and creates twelve per-agent
service accounts with IAM bindings that mirror `platform/identity.py`'s
allow/deny table exactly -- e.g. `sa-intake` gets `storage.objectViewer`
on the quarantine bucket and `datastore.user`, nothing else; `sa-crosswalk`
gets `datastore.user` only, no `aiplatform.user`, because it's
deterministic and never calls Gemini. Idempotent -- re-running it skips
anything that already exists.

**Step 2 -- build and deploy** (`deploy/deploy_cloud_run.sh`):

```bash
./deploy/deploy_cloud_run.sh
```

This builds the container via Cloud Build, deploys it to Cloud Run with
`--min-instances=0 --max-instances=3`, sets `GOOGLE_GENAI_USE_VERTEXAI=true`
(so the deployed service uses Vertex AI credential Path B automatically,
via the Cloud Run service account's Application Default Credentials --
no `GOOGLE_API_KEY` to manage in production), sets `USE_FIRESTORE=true`
and `USE_PUBSUB=true`, and wires the two Cloud Scheduler jobs
(`EVIDENCE_SWEEP_HOURS`, `DRIFT_SWEEP_HOURS`) to hit the freshly deployed
service's URL. It prints the deployed service URL at the end -- that's
what you'd use for a Devpost "hosted project URL" field, or just to
`curl` against directly.

Override any of these via env vars before running either script:
`PROJECT_ID` (required), `REGION`, `SERVICE_NAME`, `MAX_INSTANCES`,
`BULWARK_API_KEYS`, `GEMINI_FLASH_MODEL`, `GEMINI_PRO_MODEL`,
`USE_PUBSUB`.

## Verifying a deployment

```bash
SERVICE_URL=$(gcloud run services describe bulwark --region "$REGION" --format='value(status.url)')

curl -s "$SERVICE_URL/status"                                            # public, no API key needed
curl -s -H "X-API-Key: demo-key" "$SERVICE_URL/registry" | jq             # confirms all 12 agents registered
curl -s -H "X-API-Key: demo-key" -X POST "$SERVICE_URL/evidence-collector/tick" | jq   # deterministic, proves the service is actually running
```

To confirm Firestore is actually being used (not just configured):
check the Firestore console for the `vendors`, `findings`, and
`agent_registry` collections after running a request that writes data.
To confirm Pub/Sub: check the Cloud Console's Pub/Sub topics list for
names matching `platform/event_bus.py`'s topics, with message counts
ticking up as you exercise the API.

## Cost controls

- Cloud Run: `--min-instances=0` (scales to zero, no charge while idle),
  `--max-instances=3` (hard ceiling against a runaway spike).
- Firestore and Pub/Sub: negligible at demo data volumes; nothing here
  provisions an always-on database or cluster.
- Gemini: Flash is the default model for seven of the twelve agents; Pro
  is reserved for the one step (Risk Assessor) that needs it; four agents
  (Evidence Collector, Concentration Analyzer, Framework Crosswalk, the
  Offboarding Agent) make zero LLM calls at all.
- The circuit breaker (`platform/spend.py`) tracks real token spend
  against `fleet_config.max_daily_token_spend` and drops the whole fleet
  to autonomy level 0 on breach -- set a low cap while experimenting if
  you want a hard backstop against an unexpectedly chatty agent loop.
- **Turn things off after you're done**: `gcloud run services delete
  bulwark --region "$REGION"` and delete the two Cloud Scheduler jobs
  (`gcloud scheduler jobs list`) if you provisioned them. Per the
  hackathon's own rules, the app does not need to still be live at
  submission time -- a recorded demo plus this repo's deploy scripts are
  sufficient proof it ran on Google Cloud.

## Troubleshooting

**`ModuleNotFoundError: No module named 'bulwark'`** -- `PYTHONPATH=src`
isn't set. Every command in this guide that isn't `pytest` (which reads
`pythonpath = ["src"]` from `pyproject.toml` automatically) needs
`export PYTHONPATH=src` first, or run commands with the venv active and
`PYTHONPATH=src` prefixed.

**`ModuleNotFoundError: No module named 'fastapi'` (or `google.adk`,
etc.)** -- you're not in the virtualenv, or `pip install -r
requirements.txt` didn't run in it. `which python` should point inside
`.venv/`.

**Routes return `503 Orchestration is not configured`** -- no Gemini
credentials are set (see [Configuring Gemini credentials](#configuring-gemini-credentials)).
This is expected and correct for `/evidence-collector/tick`,
`/concentration-analyzer/tick`, `/concentration-risks`,
`/vendors/{id}/crosswalk`, and `/vendors/{id}/assessment-history` to
**never** 503 this way -- those five are fully deterministic and work
with zero credentials. If one of those five is 503ing, that's a real
bug, not a missing-credential situation.

**`401 Unauthorized`** -- missing or wrong `X-API-Key` header. Check it
against `BULWARK_API_KEYS` (default `demo-key`).

**`429 Too Many Requests`** -- you've exceeded `RATE_LIMIT_REQUESTS`
within `RATE_LIMIT_WINDOW_SECONDS` for that API key. Wait out the
window, or raise the limit for local experimentation.

**Cloud Run deploy succeeds but every request 503s** -- almost always
missing Vertex AI access on the Cloud Run service account, or the
project doesn't have the Vertex AI API enabled (`deploy/setup_gcp.sh`
enables it, but a manually-run deploy might have skipped that step).
Check Cloud Run's logs (`gcloud run services logs read bulwark --region
"$REGION"`) for the actual exception.

**Tests fail on a fresh clone with no other changes** -- run
`PYTHONPATH=src pytest -q -x` to stop at the first failure and read the
traceback; this is not expected on `main` and should be reported as a
bug rather than worked around.
