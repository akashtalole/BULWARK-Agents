# Devpost submission draft -- BULWARK

Copy/adapt the sections below directly into the Devpost submission form
(allthingsagentichackathon.devpost.com). Everything here is grounded in
what's actually in this repository -- no claim below outruns the code.

**Project category:** Fortified Enterprise Fleet

**Repository:** [github.com/akashtalole/BULWARK-Agents](https://github.com/akashtalole/BULWARK-Agents), branch `main`

**Hosted project URL:** see "Deployment" below -- fill in your Cloud Run
URL after running `deploy/setup_gcp.sh` + `deploy/deploy_cloud_run.sh`
(the hackathon rules don't require it to still be live at submission
time, only that the video/repo prove it ran on Google Cloud).

---

## Inspiration

Third-party risk review runs on a fixed calendar -- a vendor gets a full
review once, then nothing until the next cycle, weeks or months later.
Anything that changes in between (a certificate expiring, a control
drifting, a breach at the vendor) sits invisible the whole time: the
*blind window*. On top of that, two of the most expensive parts of the
process are still entirely manual: a security analyst reading a SOC 2
report by hand, and a paralegal reading a vendor contract against a
legal playbook clause by clause. Neither process ever asks the one
question that actually predicts correlated failure -- do a dozen
"independently diversified" vendors secretly share the same
subprocessor? The 2024 CrowdStrike outage is exactly that blind spot
turning into an incident.

## What it does

BULWARK is a twelve-agent fleet, built for the Fortified Enterprise Fleet
track, that runs continuous third-party assurance in both directions:

- **Assessing your vendors.** Forward a SOC 2 report, ISO cert, pen-test
  summary, or contract and the fleet screens it for prompt injection,
  extracts structured claims, cross-references them against your control
  framework and independently observed evidence, decides whether
  anything is actually a gap, and -- only if so -- opens a ticket and
  drafts a follow-up citing the exact codes. Weeks later, a scheduled
  sweep notices an expiring certificate or your own controls drifting
  and reopens the affected assessment with no one asking.
- **Answering buyers' security questionnaires** from the same evidence
  graph, with a citation on every confident answer and an honest
  abstention wherever the evidence doesn't support one.
- **Reviewing contracts automatically.** Contract Intelligence reads
  MSAs/DPAs and flags deviations from a legal playbook (liability caps,
  breach-notification windows, audit rights, subprocessor flow-down)
  instead of a paralegal re-deriving them by hand.
- **Catching hidden portfolio risk.** Concentration Analyzer clusters
  every subprocessor disclosed across the whole vendor portfolio and
  flags where multiple vendors -- especially critical-tier ones --
  secretly depend on the same one, the exact blind spot standard
  per-vendor review structurally can't see.
- **Cutting redundant compliance work.** Framework Crosswalk reports how
  much of a target framework (ISO 27001, NIST CSF) a vendor already
  satisfies via its existing SOC 2 findings, so a compliance team knows
  exactly which controls still need fresh evidence instead of starting
  from zero for every framework they carry.
- **Predicting risk before it's a gap.** Drift Sentinel's fourth signal
  flags a control's residual risk climbing across three consecutive
  reassessments -- reactive gap detection becomes predictive
  early-warning, using an append-only assessment history that didn't
  exist before this pass.
- **Tracking the data-deletion clock a vendor termination creates.** The
  Offboarding Agent starts the deadline every DPA's `termination_
  assistance` clause obligates on offboarding, and Drift Sentinel's
  fifth signal flags it the moment it's missed -- a real, auditable
  data-retention exposure that otherwise lives in a spreadsheet, if it's
  tracked at all.
- **Summarizing the fleet for someone with two minutes, not twenty.**
  Executive Risk Digest turns the fleet's 38 API endpoints of state into
  a short, prioritized narrative grounded only in the week's actual
  urgent items -- critical-tier gaps, top findings, concentration risks,
  overdue offboardings.

## How we built it

Twelve [Google ADK](https://github.com/google/adk-python) agents (seven
Gemini-Flash-backed, one Gemini-Pro-backed for the one genuinely complex
judgment call, four deliberately non-LLM because their job is a lookup
not reasoning) wired together entirely through a Pub/Sub-shaped event
bus (`platform/event_bus.py`) -- no agent module ever calls another
agent module directly. Every Fortified Enterprise Fleet pillar from the
track brief is implemented as real, tested code rather than a diagram:
Agent Registry (`platform/registry.py`), Agent Runtime (ADK `Runner`s +
run checkpointing), Memory Bank (`platform/memory_bank.py`, per-vendor
exceptions that persist across weeks of sweeps), Agent Identity
(`platform/identity.py`, a per-agent zero-trust grant table), Agent
Gateway (`api/routes.py`, API-key auth + rate limiting + the autonomy
ladder), Model Armor (`platform/guardrails.py`, blocking prompt
injection before any LLM call), and Agent Observability
(`platform/observability.py`, OpenTelemetry spans plus a persisted
reasoning-chain record replayable per finding).

FastAPI is the Agent Gateway's HTTP surface; Firestore is the
control-evidence graph (in-memory fallback for local dev, same code path
either way); Cloud Run is the deployment target (scale-to-zero); Cloud
Scheduler drives the two sweep cadences.

## Challenges we ran into

- Keeping the fleet genuinely event-driven under load-bearing scrutiny --
  `tests/test_orchestrator_wiring.py` asserts mechanically that no agent
  module imports another, not just that the diagram says so.
- Making the kill switch and the circuit breaker share one code path
  (`set_global_autonomy(0)`) instead of two flags that could silently
  disagree about whether the fleet is allowed to act.
- Deciding where a security-critical decision belongs: in a prompt
  (arguable, bypassable) or in code (not). The untrusted-provenance
  routing gate and the citation-validation gate on findings are both
  deliberately code, not instructions.
- Scoping the "beyond the spec" additions (Contract Intelligence,
  Concentration Analyzer, Framework Crosswalk, the Offboarding Agent,
  Executive Risk Digest, the risk-trend and offboarding-overdue signals)
  to reuse existing infrastructure -- the same Model Armor gate, the same
  event-bus pattern, Drift Sentinel's existing LLM-judgment step --
  rather than bolting on a parallel system for each one.
- Deciding what "reversible" honestly means: `initiate_offboarding` gets
  a compensating-action record like every other L3 action, but
  `confirm_data_deletion` deliberately doesn't -- it certifies a
  real-world fact, and pretending a database rollback could un-delete
  actual data would be dishonest about what rollback means in this
  system.
- Realizing `Finding` (overwritten in place per vendor+control on every
  reassessment) structurally *cannot* show a risk trajectory, and adding
  an append-only `AssessmentSnapshot` history underneath it rather than
  trying to reconstruct trend data that was never being kept.

## Accomplishments that we're proud of

- All seven Fortified Enterprise Fleet pillars implemented as live,
  tested code, with an honest "what's live vs. what's documented" table
  in the README rather than implying broader GCP bindings than a
  hackathon build actually has.
- 144 passing tests requiring zero live Gemini credentials -- every
  deterministic mechanism (guardrails, citation validation, the autonomy
  ladder, the event bus's DLQ and idempotency dedup, the circuit
  breaker, rollback, the crosswalk lookup, the trend detector, the
  offboarding-deadline tracker) is exercised directly.
- Six genuinely novel capabilities that solve real, underserved
  enterprise pain instead of adding more checklist coverage to the spec.
- A reasoning-chain record on every finding, replayable via
  `GET /findings/{id}/explain` -- "why did the agent decide this" gets a
  structured answer, not a re-run.

## What we learned

- Not every agent in a fleet needs to be an LLM call -- Evidence
  Collector, Concentration Analyzer, Framework Crosswalk, and the
  Offboarding Agent are all deliberately plain Python, because comparing
  values, clustering names, looking up a control's equivalent, or
  comparing a deadline to today is a lookup, not reasoning, and skipping
  the model call removes an entire class of prompt-injection risk on
  exactly the agents with the broadest read access.
- A circuit breaker that doesn't share code with the kill switch isn't
  really a circuit breaker -- there should only ever be one "is the
  fleet allowed to act" answer to get right.
- Mock data belongs in a table with a straight face about which parts
  are mocked; that's a better story for judges than pretending a
  hackathon build has live bindings to six different GCP security
  products.

## What's next

- Wire `contract.terms_extracted` into Remediation Router the same way
  `finding.created` already is, so a critical playbook deviation opens a
  ticket automatically instead of just being queryable.
- Replace the mock internal-evidence sources and playbook with real
  Cloud Asset Inventory / Security Command Center / DLP bindings behind
  the same function signatures -- the shape is already there.
- A lightweight frontend over the existing API surface (the fleet is
  fully usable via `curl`/`jq` today, per `README.md`'s spin-up
  instructions).

## Built with

Google ADK · Gemini (Flash + Pro) · Google Cloud Run · Firestore ·
Pub/Sub · Cloud Scheduler · FastAPI · OpenTelemetry · Python · pytest

---

## Deployment (for the "hosted project URL" field)

```bash
export PROJECT_ID=your-project
export REGION=us-central1
./deploy/setup_gcp.sh          # APIs, Firestore, Pub/Sub topics + DLQs, 12 per-agent service accounts
./deploy/deploy_cloud_run.sh   # build + deploy (scale-to-zero) + wires Cloud Scheduler to the live URL
```

The script prints the deployed service URL; that's what goes in the
Devpost "hosted project URL" field. See `docs/demo_video_script.md` for
how to capture proof of Google Cloud backend execution on video, and
`README.md`'s "Spin-up instructions" for the full local-first walkthrough
that needs no cloud project at all.
