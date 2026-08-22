# Devpost Submission — BULWARK

Copy/paste each section directly into the matching Devpost form field.
Everything below is grounded in what's actually in this repository (12
agents, 144 tests, 38 API routes) — no claim outruns the code.

---

## 1. Elevator pitch (200 char max)

```
BULWARK closes the third-party risk blind window: a 12-agent Gemini fleet that continuously assesses vendors and answers security questionnaires from one shared, auditable evidence graph.
```
*(187 characters)*

---

## 2. Project Story

```markdown
## Inspiration

Third-party risk review runs on a fixed calendar — a vendor gets a full
review once, then nothing until the next cycle, weeks or months later.
Anything that changes in between (a certificate expiring, a control
drifting, a breach at the vendor, a subprocessor quietly added) sits
invisible the whole time: the *blind window*. On top of that, the most
expensive parts of the process are still entirely manual — a security
analyst reading a SOC 2 report by hand, a paralegal reading a vendor
contract against a legal playbook clause by clause, an executive
clicking through dozens of dashboards hoping to notice the one urgent
item. And no manual process ever asks the one question that actually
predicts correlated failure: do a dozen "independently diversified"
vendors secretly share the same subprocessor? The 2024 CrowdStrike
outage is exactly that blind spot turning into an incident.

## What it does

BULWARK is a 12-agent fleet, built for the Fortified Enterprise Fleet
track, that runs continuous third-party assurance in both directions:

- **Assessing your vendors.** Forward a SOC 2 report, ISO cert,
  pen-test summary, or contract and the fleet screens it for prompt
  injection, extracts structured claims, cross-references them against
  your control framework and independently observed evidence, decides
  whether anything is actually a gap, and — only if so — opens a ticket
  and drafts a follow-up citing the exact codes. Weeks later, a
  scheduled sweep notices an expiring certificate or your own controls
  drifting and reopens the affected assessment with no one asking.
- **Answering buyers' security questionnaires** from the same evidence
  graph, with a citation on every confident answer and an honest
  abstention wherever the evidence doesn't support one.
- **Reviewing contracts automatically.** Contract Intelligence reads
  MSAs/DPAs and flags deviations from a legal playbook (liability caps,
  breach-notification windows, audit rights, subprocessor flow-down)
  instead of a paralegal re-deriving them by hand.
- **Catching hidden portfolio risk.** Concentration Analyzer clusters
  every subprocessor disclosed across the whole vendor portfolio and
  flags where multiple vendors — especially critical-tier ones —
  secretly depend on the same one, the exact blind spot standard
  per-vendor review structurally can't see.
- **Cutting redundant compliance work.** Framework Crosswalk reports
  how much of a target framework (ISO 27001, NIST CSF) a vendor already
  satisfies via its existing SOC 2 findings, so a compliance team knows
  exactly which controls still need fresh evidence instead of starting
  from zero for every framework they carry.
- **Predicting risk before it's a gap.** Drift Sentinel's fourth signal
  flags a control's residual risk climbing across three consecutive
  reassessments — reactive gap detection becomes predictive
  early-warning.
- **Tracking the data-deletion clock a vendor termination creates.**
  The Offboarding Agent starts the deadline every DPA's
  `termination_assistance` clause obligates on offboarding, and Drift
  Sentinel's fifth signal flags it the moment it's missed — a real,
  auditable data-retention exposure that otherwise lives in a
  spreadsheet, if it's tracked at all.
- **Summarizing the fleet for someone with two minutes, not twenty.**
  Executive Risk Digest turns the fleet's 38 API endpoints of state
  into a short, prioritized narrative grounded only in the week's
  actual urgent items.

## How we built it

Twelve Google ADK agents (seven Gemini-Flash-backed, one
Gemini-Pro-backed for the one genuinely complex judgment call, four
deliberately non-LLM because their job is a lookup, not reasoning)
wired together entirely through a Pub/Sub-shaped event bus — no agent
module ever calls another agent module directly, which
`tests/test_orchestrator_wiring.py` asserts mechanically. Every
Fortified Enterprise Fleet pillar from the track brief is implemented
as real, tested code rather than a diagram: Agent Registry, Agent
Runtime (ADK `Runner`s + run checkpointing), Memory Bank (per-vendor
exceptions that persist across weeks of sweeps), Agent Identity (a
per-agent zero-trust grant table), Agent Gateway (API-key auth + rate
limiting + an autonomy ladder), Model Armor (blocking prompt injection
before any LLM call), and Agent Observability (OpenTelemetry spans plus
a persisted reasoning-chain record replayable per finding).

FastAPI is the Agent Gateway's HTTP surface; Firestore is the
control-evidence graph (in-memory fallback for local dev, same code
path either way); Cloud Run is the deployment target (scale-to-zero);
Cloud Scheduler drives the sweep cadences; Pub/Sub mirrors the event
bus when live.

## Challenges we ran into

- Keeping the fleet genuinely event-driven under load-bearing scrutiny
  — a test asserts mechanically that no agent module imports another,
  not just that the diagram says so.
- Making the kill switch and the circuit breaker share one code path
  (`set_global_autonomy(0)`) instead of two flags that could silently
  disagree about whether the fleet is allowed to act.
- Deciding where a security-critical decision belongs: in a prompt
  (arguable, bypassable) or in code (not). The untrusted-provenance
  routing gate and the citation-validation gate on findings are both
  deliberately code, not instructions.
- Scoping every "beyond the spec" addition (Contract Intelligence,
  Concentration Analyzer, Framework Crosswalk, the Offboarding Agent,
  Executive Risk Digest, the risk-trend and offboarding-overdue
  signals) to reuse existing infrastructure — the same Model Armor
  gate, the same event-bus pattern, Drift Sentinel's existing
  LLM-judgment step — rather than bolting on a parallel system each
  time.
- Deciding what "reversible" honestly means: most L3 autonomous actions
  get a compensating-action record, but confirming a vendor's data
  deletion deliberately doesn't — it certifies a real-world fact, and
  pretending a database rollback could un-delete actual data would be
  dishonest about what rollback means in this system.
- Realizing `Finding` (overwritten in place per vendor+control on every
  reassessment) structurally *cannot* show a risk trajectory, and
  adding an append-only `AssessmentSnapshot` history underneath it
  rather than trying to reconstruct trend data that was never being
  kept.

## Accomplishments that we're proud of

- All seven Fortified Enterprise Fleet pillars implemented as live,
  tested code, with an honest "what's live vs. what's documented" table
  rather than implying broader GCP bindings than a hackathon build
  actually has.
- 144 passing tests requiring zero live Gemini credentials — every
  deterministic mechanism (guardrails, citation validation, the
  autonomy ladder, the event bus's DLQ and idempotency dedup, the
  circuit breaker, rollback, the crosswalk lookup, the trend detector,
  the offboarding-deadline tracker) is exercised directly.
- Six genuinely novel capabilities that solve real, underserved
  enterprise pain instead of adding more checklist coverage to the
  spec.
- A reasoning-chain record on every finding, replayable via one API
  call — "why did the agent decide this" gets a structured answer, not
  a re-run.

## What we learned

- Not every agent in a fleet needs to be an LLM call — four of the
  twelve agents here are deliberately plain Python, because comparing
  values, clustering names, looking up a control's equivalent, or
  comparing a deadline to today is a lookup, not reasoning, and
  skipping the model call removes an entire class of prompt-injection
  risk on exactly the agents with the broadest read access.
- A circuit breaker that doesn't share code with the kill switch isn't
  really a circuit breaker — there should only ever be one "is the
  fleet allowed to act" answer to get right.
- Mock data belongs in a table with a straight face about which parts
  are mocked; that's a better story for judges than pretending a
  hackathon build has live bindings to six different GCP security
  products.

## What's next for BULWARK

- Wire `contract.terms_extracted` into Remediation Router the same way
  `finding.created` already is, so a critical playbook deviation opens
  a ticket automatically instead of just being queryable.
- Replace the mock internal-evidence sources and playbook with real
  Cloud Asset Inventory / Security Command Center / DLP bindings behind
  the same function signatures — the shape is already there.
- A lightweight frontend over the existing API surface (the fleet is
  fully usable via `curl`/`jq` today).
- Wire the Executive Risk Digest to a real weekly Cloud Scheduler
  cadence with an email/Slack delivery target once the recipient
  workflow is chosen.
```

**Built with** (tags — up to 25):

```
google-adk, gemini, gemini-flash, gemini-pro, google-cloud-run,
google-cloud-firestore, google-cloud-pubsub, google-cloud-scheduler,
vertex-ai, fastapi, python, pydantic, uvicorn, opentelemetry, pytest,
docker, rest-api, mermaid, multi-agent-systems, event-driven-architecture,
zero-trust-security, prompt-injection-defense, json, google-cloud-iam,
asyncio
```

---

## 3. Reproducible testing instructions

**Yes.** `README.md`'s "Spin-up instructions" section (steps 1–2) is
exactly this:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
pip install pytest pytest-asyncio httpx  # dev/test only

PYTHONPATH=src pytest -q
```

144 tests, zero live Gemini credentials required — every deterministic
mechanism (guardrails, citation validation, the autonomy ladder, the
event bus's DLQ/idempotency, the circuit breaker, rollback, both
deterministic agents' detection logic) is exercised directly against
the tool functions; the API layer is tested with the LLM-backed
orchestration functions swapped for fakes. If a test fails on a fresh
clone, it's a real regression, not a missing credential.

`docs/SETUP_GUIDE.md` has the full walkthrough (local run, seeding demo
data, and real Cloud Run deployment via `deploy/setup_gcp.sh` +
`deploy/deploy_cloud_run.sh`) if judges want to go beyond the test
suite.

---

## 4. Which Google SDK did you use?

**Google Agent Development Kit (ADK)** — `google-adk` (Python). Every
agent is an ADK `LlmAgent` (or, for the four deliberately non-LLM
agents, a plain Python function called through the same tool-call
contract); `agents/orchestrator.py` runs them through ADK `Runner`s,
and Model Armor is wired in as ADK `before_model_callback` /
`after_model_callback` / `before_tool_callback` plugins so it can't be
bypassed by a single agent's prompt.

---

## 5. Which Google Cloud Service(s) did you use?

- **Cloud Run** — deployment target, scale-to-zero (`--min-instances=0`,
  `--max-instances=3`); `deploy/deploy_cloud_run.sh`.
- **Firestore** (Native mode) — the control-evidence graph (vendors,
  artifacts, findings, contract terms, concentration risks, assessment
  snapshots, offboarding records, digests); in-memory fallback with the
  identical code path for local dev/tests.
- **Pub/Sub** — mirrors the in-process event bus's topics live when
  `USE_PUBSUB=true`; `deploy/setup_gcp.sh` provisions the topics + DLQ
  topics.
- **Cloud Scheduler** — drives the Evidence Collector and Drift
  Sentinel sweep cadences against the deployed Cloud Run URL.
- **Vertex AI / Gemini API** — model access path for every LLM-backed
  agent (`GOOGLE_GENAI_USE_VERTEXAI=true` + Application Default
  Credentials for Vertex AI, or `GOOGLE_API_KEY` for the Gemini API
  directly).
- **IAM** — twelve least-privilege per-agent service accounts, one per
  agent, provisioned by `deploy/setup_gcp.sh` to mirror
  `platform/identity.py`'s allow/deny grant table exactly.

---

## 6. Architecture diagram / Which Google AI Models did you use?

**Architecture diagram:** attached — `bulwark_architecture_diagram.png`
(rendered from the live Mermaid source in `docs/architecture.md`, kept
in sync with the actual code, not hand-drawn). The full diagram set
(HLD/LLD/DFD/ERD/sequence/state/deployment, 26 diagrams total) is in
[`docs/DIAGRAMS.md`](DIAGRAMS.md).

**Google AI Models:**

- **Gemini Flash** — seven of the twelve agents (Supervisor, Intake,
  Contract Intelligence, Executive Risk Digest, Questionnaire
  Responder, Drift Sentinel, Remediation Router).
- **Gemini Pro** — Risk Assessor's final cross-referencing judgment,
  the one step in the fleet that's genuine complex reasoning (per the
  hackathon's own cost guidance: reserve Pro for that, not for
  rubber-stamping).
- Both resolve via the rolling `gemini-flash-latest` /
  `gemini-pro-latest` aliases (`GEMINI_FLASH_MODEL` /
  `GEMINI_PRO_MODEL` in `src/bulwark/config.py`), Google's current-
  generation models at deploy time — pin an exact dated model string in
  those env vars before submission if Devpost's verification needs one
  spelled out literally rather than resolved via the alias.
- The remaining four agents (Evidence Collector, Concentration
  Analyzer, Framework Crosswalk, the Offboarding Agent) are
  deliberately zero-LLM — see "What we learned" above for why.

---

## 7. OPTIONAL — Link to a piece of content (blog, podcast, video)

Not yet produced. `docs/demo_video_script.md` has the full ~4-minute
demo video script (problem overview → value prop → live app
demonstration → proof of Google Cloud backend execution) ready to
record; once recorded and published somewhere public (YouTube, etc.),
paste that link here and add a line stating it was created for this
hackathon.

---

## 8. OPTIONAL — Link to a social media post

Not yet posted. If you post one, include the `#AllThingsAgentic
Hackathon` hashtag and paste the link here.
