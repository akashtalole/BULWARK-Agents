# BULWARK

### Continuous Third-Party Assurance Fleet

A twelve-agent fleet for the **Fortified Enterprise Fleet** track that
collapses the *blind window* -- the time between a risk-relevant signal
existing in the world and a human at your company knowing about it --
from roughly half a review cycle down to the length of one scheduled
sweep, for both directions of third-party risk: assessing your vendors,
and answering buyers' security questionnaires from the same evidence
graph. Five of the twelve agents, plus a predictive upgrade to Drift
Sentinel, go past the spec to solve pain no per-vendor checklist review
can reach: **Contract Intelligence** automates the manual
MSA/DPA-vs-playbook review that eats hundreds of paralegal hours a year,
**Concentration Analyzer** catches the portfolio-level blind spot where
"diversified" vendors secretly share a subprocessor -- the failure
pattern behind incidents like the 2024 CrowdStrike outage --
**Framework Crosswalk** cuts the redundant evidence collection
enterprises repeat across every overlapping compliance framework they
carry, the **Offboarding Agent** operationalizes the DPA-mandated
data-deletion deadline every vendor termination creates -- an obligation
that otherwise lives in a spreadsheet, if it's tracked at all --
**Executive Risk Digest** synthesizes the fleet's 38 API endpoints of
state into a short prioritized narrative a busy executive can actually
read, and Drift Sentinel's new `risk_trend_rising` signal catches a
control's risk climbing across reassessments *before* it becomes a hard
gap.

A [React dashboard](frontend/) sits on top of the same API surface --
fleet health and the kill switch, per-vendor findings with the full
reasoning chain behind each one, the assessment-history risk-trend
chart, concentration risks, the executive digest, and trace timelines --
so the fleet is drivable without `curl`/`jq`, though every one of those
`curl` examples below still works identically.

See [`docs/architecture.md`](docs/architecture.md) for the full system
diagram, the per-agent identity/autonomy table, and the exact event-bus
wiring for all three loops; [`docs/DIAGRAMS.md`](docs/DIAGRAMS.md) for
the full HLD/LLD/DFD/ERD/sequence/state/deployment diagram set;
[`docs/SETUP_GUIDE.md`](docs/SETUP_GUIDE.md)
for detailed install/configuration/deployment instructions beyond the
quick-start below; [`docs/USER_GUIDE.md`](docs/USER_GUIDE.md) for every
workflow and API endpoint with worked examples; [`frontend/README.md`](frontend/README.md)
for the dashboard's own setup and design notes; and
[`docs/demo_video_script.md`](docs/demo_video_script.md) for the
~4-minute demo script, and [`SUBMISSION.md`](SUBMISSION.md) for the
Devpost submission text.

## Hackathon requirements checklist

**Track:** Fortified Enterprise Fleet.

**Technology requirements (all tracks):**

| Requirement | This build |
|---|---|
| Gemini 3.5+ via Gemini API or Vertex AI | `GEMINI_FLASH_MODEL` / `GEMINI_PRO_MODEL` resolve to `gemini-flash-latest` / `gemini-pro-latest` (`src/bulwark/config.py`) -- both Google's rolling aliases for the current-generation model, callable via either the Gemini API (`GOOGLE_API_KEY`) or Vertex AI (`GOOGLE_GENAI_USE_VERTEXAI=true`), see "Configure Gemini" below |
| A Google Agent Framework | [Google ADK](https://github.com/google/adk-python) (`google-adk`) -- every agent is an ADK `LlmAgent` (or, for the three deliberately non-LLM agents, plain Python called the same way); `agents/orchestrator.py` runs them through ADK `Runner`s |
| A Google Cloud infrastructure service | **Cloud Run** (`deploy/deploy_cloud_run.sh`, scale-to-zero), **Firestore** (`platform/store.py`, live when `GOOGLE_CLOUD_PROJECT` is set), **Pub/Sub** (`platform/event_bus.py`, mirrored live when `USE_PUBSUB=true`) -- all three, not just one |

**Fortified Enterprise Fleet pillars** (from the track brief) -- every one is live code, not a diagram:

| Pillar | This build |
|---|---|
| Agent Registry (publish/version/discover) | `platform/registry.py`, live at `GET /registry` -- 12 agents, each with a `departments` tag for cross-department reuse (security/procurement/legal/sales-engineering) |
| Agent Runtime (long-running async execution) | ADK `Runner`s in `agents/orchestrator.py`; Drift Sentinel's sweeps checkpoint progress via `platform/models.py`'s `RunRepo` |
| Memory Bank (persistent cross-session context) | `platform/memory_bank.py` -- per-vendor negotiated exceptions and accepted-risk decisions that outlive any single sweep, with `expires_at` windows spanning weeks, not just the current session |
| Agent Identity (zero-trust access control) | `platform/identity.py` -- a per-agent allow/deny grant table (`tests/test_identity.py` exercises the denials directly, not just the allows) |
| Agent Gateway (unified routing + policy) | `api/routes.py` + `platform/auth.py` -- API-key auth, rate limiting, and the autonomy-ladder kill switch enforced on every route |
| Model Armor (guardrails) | `platform/guardrails.py` -- blocks prompt injection before any LLM call, scans DLP-style patterns before an answer is marked exportable, applied as an ADK plugin so it can't be bypassed by a single agent's prompt |
| Agent Observability (OTel audit + reasoning traces) | `platform/observability.py` -- OpenTelemetry spans plus a persisted reasoning-chain record per decision, replayed at `GET /traces/{id}` and `GET /findings/{id}/explain` |

**Track-specific demonstrations the brief calls out explicitly:**
- *Cross-department reuse* -- `GET /registry` shows the same 12 agents tagged for reuse across Security, Procurement, Legal, and Sales Engineering (`platform/registry.py`'s `departments` field on every `AgentRecord`).
- *Asynchronous context persistence over weeks* -- `platform/memory_bank.py`'s negotiated exceptions and accepted-risk decisions carry an `expires_at` and are read by every subsequent Drift Sentinel sweep, however many weeks later that sweep runs; `has_active_exception` is what stops the fleet from re-litigating an already-accepted risk every six hours.
- *Compliance/data-sovereignty-aware production data interaction* -- `platform/models.py::TenantRepo` records a `region_pin` echoed on every event `Envelope`; findings on a critical-tier vendor or above the residual-risk threshold force `requires_human = true` regardless of autonomy level (section 6.4's mandatory HITL gates); see "Mechanisms worth reading in the code directly" in `docs/architecture.md`.

**Judging-criteria alignment:**

| Criterion | Weight | Where to look |
|---|---|---|
| Innovation & Operational Utility | 40% | The fleet acts autonomously end-to-end (screens → extracts → cross-references → decides → tickets, with no human in the loop unless a mandatory gate fires); Contract Intelligence, Concentration Analyzer, Framework Crosswalk, the Offboarding Agent, Executive Risk Digest, and the risk-trend early-warning signal solve real, underserved enterprise pain (manual contract review, hidden portfolio concentration risk, redundant cross-framework evidence collection, untracked data-deletion obligations, 30+ endpoints nobody has time to click through, reactive-only risk detection) rather than adding checklist coverage -- see "Beyond the spec" in `docs/architecture.md` |
| Architectural Discipline & Tech Stack | 30% | Event-driven decoupling (`tests/test_orchestrator_wiring.py` asserts no agent module imports another), zero-trust identity, a real circuit breaker sharing code with the kill switch, compensating-action rollback, citation-validated anti-hallucination gates -- see "Mechanisms worth reading in the code directly" in `docs/architecture.md` |
| Demo & Production Readiness | 30% | 144 passing tests requiring zero live credentials (`PYTHONPATH=src pytest -q`), a one-command local spin-up, `deploy/setup_gcp.sh` + `deploy/deploy_cloud_run.sh` for real Cloud Run deployment, and `docs/demo_video_script.md` for the required demo video |

## What it does

Forward a vendor's SOC 2 report (or ISO cert, DPA, pen-test summary) and
BULWARK runs the whole onboarding cycle on its own: screen it for prompt
injection, extract structured claims, cross-reference them against your
control framework and independently-observed evidence, decide whether
anything is actually a gap, and -- only if so -- open a ticket and draft
an appeal citing the exact codes. Weeks later, a scheduled sweep notices
a certificate about to expire or your own controls drifting, and reopens
the affected assessment without anyone asking. The same evidence graph
answers a buyer's security questionnaire, with a citation on every answer
and an honest abstention wherever the evidence doesn't support one.

## Features

- **Contract Intelligence: automated MSA/DPA review against a legal
  playbook.** `extract_contract_terms` compares every clause it finds
  against `agents/contract_playbook.py` and flags deviations (an
  unlimited-liability clause, a breach-notification window longer than
  the playbook allows, silence on subprocessor flow-down) as structured,
  actionable data instead of a paralegal's hand-written notes.
- **Concentration Analyzer: catches the risk no single-vendor review
  can see.** A dozen vendors that look independently diversified but all
  secretly depend on the same subprocessor turn one incident into a
  correlated failure across every one of them at once. This agent
  clusters every subprocessor `Contract Intelligence` has ever extracted
  by name across the whole portfolio and flags the overlaps, weighted by
  how many affected vendors are critical-tier.
- **Framework Crosswalk: audit fatigue reduction across overlapping
  compliance frameworks.** SOC 2 for one buyer, ISO 27001 for another,
  NIST CSF for a third -- standard tooling re-collects evidence for each
  independently. `compute_framework_coverage` reports which target-
  framework controls a vendor already indirectly satisfies via its
  existing SOC 2 findings, each covered entry citing the `finding_id`
  that justifies it, so a compliance team sees exactly what's left
  instead of starting from zero.
- **Predictive risk-trend early-warning.** `Finding` overwrites in place
  on every reassessment, so on its own it can never show a trajectory.
  `AssessmentSnapshot` is append-only, and Drift Sentinel's fourth signal
  (`risk_trend_rising`) flags a control's residual risk climbing across
  three consecutive reassessments *before* any single one crosses a hard
  gap threshold -- reactive detection becomes predictive.
- **Offboarding & termination assistance tracking.** `VendorStatus` has
  had an `"offboarding"` value since the very first version of this
  schema, with no code path that ever set or cleared it. This agent
  operationalizes it: `initiate_offboarding` starts the data-deletion
  clock every DPA's `termination_assistance` clause creates (using the
  vendor's own contracted deadline if Contract Intelligence found one,
  else the playbook default), `confirm_data_deletion` closes it out, and
  Drift Sentinel's fifth signal (`offboarding_overdue`) flags a vendor
  still holding your data past the date they were contractually required
  to delete it -- a real, auditable data-retention exposure that
  otherwise lives in a spreadsheet, if it's tracked at all.
- **An executive digest for a fleet with 38 endpoints nobody has time to
  click through.** `gather_digest_inputs` deterministically pulls the
  week's most urgent state (critical-tier gaps, top findings by residual
  risk, concentration risks, overdue offboardings); the Executive Risk
  Digest Agent turns that into a 3-5 paragraph prioritized narrative a
  busy executive can read in under a minute, with every claim grounded in
  the inputs it was given, never invented.
- **Twelve agents, one event bus, zero direct agent-to-agent calls.**
  Every handoff is `bus.publish`/`bus.subscribe` on a named topic
  (`platform/event_bus.py`); `tests/test_orchestrator_wiring.py` asserts
  this mechanically.
- **A hardcoded security gate, not a prompted one.** An untrusted vendor
  artifact is screened by a deterministic Model Armor scan *before* any
  LLM call, and if clean, is only ever read by the Intake Agent -- the
  Supervisor's LLM never sees untrusted content at all, so there's no
  instruction for an injection to override in the first place.
- **A citation-enforced anti-hallucination gate.** Risk Assessor's
  `create_finding` refuses to persist a finding with zero citations, or a
  citation to an id that doesn't exist -- checked in code, not asked of
  the model.
- **A live kill switch, and a circuit breaker that pulls the same
  lever.** `POST /fleet-config {"autonomy_level": 0}` and every L1+
  action across all twelve agents starts raising `AutonomyBlocked` on its
  next tool call. `pause_agent_id` does the same for one agent. A daily
  token-spend cap breach calls the exact same function automatically
  (`platform/spend.py`). No redeploy either way.
- **Per-agent zero-trust identity.** The two agents that read
  attacker-adjacent input (Intake, and Contract Intelligence for vendor
  contracts) have no grant to read evidence or write findings; the agents
  that can write findings never touch a vendor document.
  `platform/identity.py` is the enforced table, not a diagram.
- **A deliberately non-LLM agent.** Evidence Collector costs zero tokens
  and has zero prompt-injection surface, because comparing an observed
  value to a policy is a lookup, not reasoning -- see "Findings and
  learnings" below.
- **Abstention as the feature, not a fallback.** Questionnaire Responder
  answers what it can cite and confidently flags the rest for a human,
  rather than guessing.
- **Mandatory human review that a higher autonomy level can't override.**
  A finding on a critical-tier vendor, a residual risk above threshold,
  or evidence too stale to trust all force `requires_human = true` in
  code (`agents/risk_assessor.py`) -- and outbound vendor email has no
  `send` function anywhere in this codebase, only a draft gated on an
  already-recorded human decision.
- **Every finding explains itself.** `create_finding` persists the
  alternatives it weighed (with scores and why each was or wasn't
  chosen); `GET /findings/{id}/explain` replays that reasoning chain
  alongside the finding, not just its final verdict.
- **Reversible by construction -- except where reversing would be
  dishonest.** The autonomous (L3) actions that change state and could
  legitimately be undone -- reopening an assessment, opening a ticket,
  initiating offboarding -- each write a compensating-action record;
  `POST /runs/{trace_id}/rollback` replays them in reverse, idempotently.
  `confirm_data_deletion` deliberately does not: it certifies a
  real-world fact (the vendor's data is gone), and reversing a database
  field wouldn't un-delete it.

## Technologies used

- **Gemini** (Flash for seven agents, **Pro** reserved for Risk
  Assessor's final cross-referencing judgment; Evidence Collector,
  Concentration Analyzer, Framework Crosswalk, and the Offboarding Agent
  make zero LLM calls at all), via the
  [Google ADK](https://github.com/google/adk-python) (`google-adk`)
- **Google Cloud Run** -- scale-to-zero deployment
- **Pub/Sub** -- the event bus, mirrored live when `USE_PUBSUB=true`
- **Firestore** -- the control-evidence graph, audit log, Memory Bank (in-memory fallback for local dev/tests)
- **Cloud Scheduler** -- the two sweep cadences
- **FastAPI** -- the Agent Gateway's HTTP surface
- **OpenTelemetry** -- Agent Observability spans

## What's live vs. what's documented

Everything above the line in this table is real code, exercised by the
test suite, that runs unmodified whether `GOOGLE_CLOUD_PROJECT` is unset
(local dev) or set (Cloud Run). Below the line is represented by
equivalent-purpose logic and documented for the real integration, because
this repo has no GCP project to verify a live binding against -- the
table says so directly rather than implying broader GCP bindings than a
hackathon build actually has.

| Live | Represented / documented |
|---|---|
| Agent Registry, Agent Identity, Model Armor, Agent Observability, the event bus + DLQ + idempotency, the kill switch, Firestore-shaped storage, Memory Bank, Cloud Run deploy | BigQuery audit warehouse (the audit log is real and queryable via `GET /traces/{id}`; a live BigQuery export isn't wired) · Cloud DLP (represented by `guardrails.scan_for_dlp_violation`, same pattern/patterns a DLP inspection job would flag) · Vertex AI Vector Search (represented by a substring match over control titles in `questionnaire_responder.search_evidence`) · Cloud Asset Inventory / Security Command Center / IAM / Logging / GitHub / Jira (represented by `agents/internal_sources.py`, a small labeled mock dataset, illustrative rather than a live integration) |

`deploy/setup_gcp.sh` provisions the real Pub/Sub topics, per-agent
service accounts with least-privilege IAM, and Firestore; swapping the
mocked sources/DLP/Vector Search for live calls is a matter of replacing
those functions' bodies behind the same return shape, not a redesign.

## Repository layout

```
src/bulwark/
  agents/        12 ADK agent definitions + orchestrator.py (event-bus wiring) + mock internal sources
                 + contract_playbook.py, framework_crosswalk_reference.py (illustrative reference data)
  platform/      store, event_bus, registry, identity, guardrails, observability, policy (kill switch),
                 spend (circuit breaker), rollback (compensating actions), models (data graph + reasoning
                 records + assessment snapshots + tenants + offboarding records + digests), memory_bank, auth
  api/           FastAPI routes + schemas (38 routes -- see docs/architecture.md's API surface table)
  main.py        ASGI entrypoint (Cloud Run / uvicorn)
tests/           144 tests, no live Gemini credentials required
deploy/          setup_gcp.sh, deploy_cloud_run.sh
docs/            architecture.md (diagram + agent table + event table + API surface + mechanisms)
                 + DIAGRAMS.md (HLD/LLD/DFD/ERD/sequence/state/deployment diagrams, all Mermaid)
                 + SETUP_GUIDE.md (detailed install/config/deployment) + USER_GUIDE.md (every
                 workflow + API endpoint, worked examples) + demo_video_script.md (the required
                 ~4-minute demo video, scripted)
scripts/         seed_demo_data.py, demo_cli.py
frontend/        React + Vite + TypeScript dashboard over the API surface above -- see frontend/README.md
SUBMISSION.md    Devpost submission text, drafted from this README
```

## Spin-up instructions

### 1. Install dependencies

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
pip install pytest pytest-asyncio httpx  # dev/test only
```

### 2. Run the test suite (no cloud setup or API keys required)

```bash
PYTHONPATH=src pytest -q
```

Every deterministic piece -- guardrail detection/redaction, the
citation-validation gate, the autonomy ladder and kill switch, the event
bus's DLQ and idempotency dedup, Drift Sentinel's expiry/drift detection,
Questionnaire Responder's confidence/DLP gating, and the full API request
flow -- is tested directly, without needing a live Gemini call.

### 3. Run the service locally

```bash
export PYTHONPATH=src
uvicorn bulwark.main:app --reload --port 8080
```

No `GOOGLE_CLOUD_PROJECT` needed for this -- everything runs in-memory.
Explore immediately, no credentials required:

```bash
python scripts/seed_demo_data.py   # seeds vendors, findings, a poisoned artifact, a questionnaire
curl -s -H 'X-API-Key: demo-key' http://localhost:8080/registry | jq
curl -s -H 'X-API-Key: demo-key' http://localhost:8080/vendors | jq
curl -s -H 'X-API-Key: demo-key' http://localhost:8080/evidence-collector/tick -X POST | jq   # deterministic, works with zero credentials
```

### 4. Run the dashboard

```bash
cd frontend
npm install
npm run dev   # http://localhost:5173, talks to the server from step 3
```

Open **Connection** in the sidebar to confirm the Base URL (`http://localhost:8080`
by default) and API key (`demo-key` by default) match your running
server -- both live in `localStorage`, per browser. See
[`frontend/README.md`](frontend/README.md) for building/deploying it.

### 5. Configure Gemini and run a full agent cycle

```bash
# Path A: Gemini API / AI Studio
export GOOGLE_API_KEY=your-key

# Path B: Vertex AI (uses Application Default Credentials)
export GOOGLE_CLOUD_PROJECT=your-project
export GOOGLE_GENAI_USE_VERTEXAI=true
gcloud auth application-default login
```

Then, with the server running:

```bash
python scripts/demo_cli.py
```

This drives the real multi-agent cycle end to end: blocks a poisoned
artifact, onboards a clean vendor, prints its full reasoning-chain trace,
answers a questionnaire, triggers both sweeps, and demonstrates the kill
switch live.

### 6. Deploy to Cloud Run

```bash
export PROJECT_ID=your-project
export REGION=us-central1

./deploy/setup_gcp.sh          # APIs, Firestore, Pub/Sub topics + DLQs, 12 per-agent service accounts
./deploy/deploy_cloud_run.sh   # build + deploy (scale-to-zero, max-instances=3) + wires Cloud Scheduler to the live URL
```

## Environment variables

| Variable | Purpose | Default |
|---|---|---|
| `GOOGLE_API_KEY` | Gemini API key (Path A) | unset |
| `GOOGLE_CLOUD_PROJECT` | GCP project (Path B / Firestore / Pub/Sub) | unset |
| `GOOGLE_GENAI_USE_VERTEXAI` | Use Vertex AI instead of the Gemini API | `false` |
| `GEMINI_FLASH_MODEL` / `GEMINI_PRO_MODEL` | Model ids | `gemini-flash-latest` / `gemini-pro-latest` |
| `USE_FIRESTORE` | Use Firestore instead of in-memory stores | `true` if `GOOGLE_CLOUD_PROJECT` is set |
| `USE_PUBSUB` | Also mirror events onto real Pub/Sub topics | `false` |
| `BULWARK_API_KEYS` | Comma-separated Agent Gateway allowlist | `demo-key` |
| `BULWARK_CORS_ALLOW_ORIGINS` | Comma-separated origins allowed to call the API cross-origin (the dashboard's origin) | `http://localhost:5173,http://127.0.0.1:5173` |
| `RATE_LIMIT_REQUESTS` / `RATE_LIMIT_WINDOW_SECONDS` | Gateway rate limit | `30` / `60` |
| `ANSWER_CONFIDENCE_THRESHOLD` | Questionnaire abstention threshold | `0.75` |
| `EVIDENCE_FRESHNESS_DAYS` | Evidence staleness window | `30` |
| `EVIDENCE_SWEEP_HOURS` / `DRIFT_SWEEP_HOURS` | Scheduler cadence | `6` / `24` |
| `RESIDUAL_RISK_HUMAN_THRESHOLD` | Mandatory-human-review risk threshold (of 1-25) | `15` |

`fleet_config.max_daily_token_spend` (the circuit breaker's cap) is a
runtime value, not an env var -- set it via `POST /fleet-config` or
`FleetConfigRepo`, since it's meant to be adjustable without a redeploy,
same as the kill switch it shares a code path with.

See [`.env.example`](.env.example) for the full list.

## Findings and learnings

- **Not every agent in a fleet needs to be an LLM call.** Evidence
  Collector compares an observed value to a policy value -- that's a
  lookup, not reasoning. Making it deterministic Python instead of an ADK
  `LlmAgent` costs zero tokens on a step that runs every six hours across
  every control, *and* removes an entire class of risk: there's no prompt
  for anything to inject into, because there's no prompt. Good agent
  design sometimes means recognizing where an agent isn't needed at all.
- **The security-critical decision belongs in code, not in a prompt.**
  Two gates in this build are deliberately not "the agent is instructed
  to..." -- the untrusted-provenance routing gate (an untrusted event
  literally cannot reach the Supervisor's context window) and the
  citation-validation gate on findings (rejected by a post-processor
  before persistence). An instruction can be argued with by a good enough
  injection; a code path that was never wired can't be.
- **Autonomy ceilings need two independent checks, not one.** An agent's
  own registered ceiling (what it declared it's allowed to do) and the
  global kill switch (what's currently allowed fleet-wide) are separate
  gates in `platform/policy.py`. Collapsing them into one dial would mean
  bumping the global level for one agent's legitimate need accidentally
  raises every other agent's ceiling too.
- **A circuit breaker that doesn't share code with the kill switch isn't
  really a circuit breaker.** It would be easy to have spend-cap breach
  set some separate `emergency_stop` flag that every check site would
  also need to know about. Instead `check_circuit_breaker()` just calls
  `set_global_autonomy(0)` -- the exact function the manual kill switch
  calls -- so there's only ever one "is the fleet allowed to act" answer
  to get right, not two that could disagree.
- **The correlation id you actually have beats the one the spec named.**
  Section 8 says `POST /runs/{id}/rollback`, but this build's `Run`
  records only exist for Drift Sentinel's own sweep checkpointing --
  `trace_id` is what's actually threaded through every hop of a causal
  chain (every Envelope, every audit entry, every reasoning record).
  Rather than force-fitting a `run_id` into functions that don't
  naturally have one, rollback groups by `trace_id` and says so in the
  docstring, rather than pretending the path parameter's name is the
  whole story.
- **Mock data belongs to a table with a straight face about which parts
  are mocked.** `agents/internal_sources.py` is illustrative, not a live
  Cloud Asset Inventory call; the README says so directly rather than
  implying otherwise in a demo -- a genuinely better story for judges
  than pretending a hackathon build has live bindings to six different
  GCP security products.

## Cost controls

Cloud Run deployed with `--min-instances=0` (scales to zero) and
`--max-instances=3`; Flash is the default model for seven of twelve
agents, with Pro reserved for the one step that needs it; Evidence
Collector, Concentration Analyzer, Framework Crosswalk, and the
Offboarding Agent make zero LLM calls at all; Firestore instead of an
always-on database; the API is protected by
the app's own `X-API-Key` check. Turn the Cloud Run service and Cloud
Scheduler jobs off after recording your demo.
