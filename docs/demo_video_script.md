# Demo video script (~4 minutes)

Devpost requires: problem overview, value proposition, a live app
demonstration, and proof of Google Cloud backend execution -- all in one
unedited take. This script maps each requirement to a timestamp and an
exact command, built around `scripts/demo_cli.py` (against a locally
running server with real Gemini credentials) and `scripts/seed_demo_data.py`
(fallback if credentials aren't available during recording).

Record the terminal and a browser tab (or `jq`-formatted terminal output)
side by side. Nothing here needs to be edited together after the fact --
every step below is one command producing one visible result.

## 0:00 - 0:30 -- Problem overview

Say, on camera or voiceover, something close to:

> "Enterprises re-review the same vendors on a fixed calendar, so a new
> risk sits invisible for weeks between reviews -- that's the blind
> window. And the reviews themselves are manual: a security analyst
> reading a SOC 2 report by hand, a paralegal reading a DPA against a
> legal playbook by hand, nobody ever checking whether a dozen
> 'diversified' vendors secretly share the same subprocessor until an
> incident like the 2024 CrowdStrike outage makes that concentration
> risk impossible to ignore."

## 0:30 - 1:00 -- Value proposition

> "BULWARK is a twelve-agent fleet that collapses that blind window to
> the length of one scheduled sweep, in both directions: it assesses your
> vendors continuously, and it answers buyers' security questionnaires
> from the same evidence graph. Six capabilities go past standard
> third-party risk review entirely: Contract Intelligence automates
> contract-vs-playbook review, Concentration Analyzer catches the
> shared-subprocessor blind spot no single-vendor review can see,
> Framework Crosswalk cuts redundant evidence collection across
> overlapping compliance frameworks, a predictive risk-trend signal
> catches a control getting worse before it's a hard gap, the Offboarding
> Agent tracks the data-deletion deadline every vendor termination
> creates -- otherwise a spreadsheet, if it's tracked at all -- and
> Executive Risk Digest turns 38 API endpoints of fleet state into a
> narrative a busy executive can actually read."

Show the architecture diagram (`docs/architecture.md`'s mermaid diagram,
rendered on GitHub) for ~5 seconds here.

## 1:00 - 3:15 -- Live app demonstration

Run, on screen, exactly:

```bash
export PYTHONPATH=src
uvicorn bulwark.main:app --reload --port 8080 &
python scripts/demo_cli.py --url http://localhost:8080 --api-key demo-key
```

Narrate each step as it prints (`demo_cli.py` already emits a numbered
list matching this beat-for-beat):

1. **Poisoned artifact blocked (the 30-second demo moment).** "This SOC 2
   report contains a prompt injection -- 'ignore previous instructions.'
   Model Armor blocks it deterministically, in code, before any LLM call
   -- there's no prompt for the injection to override."
2. **Clean vendor onboarded -- the full Onboard loop, autonomously.**
   "No human touched this. Intake extracted claims, Risk Assessor
   cross-referenced them against live evidence, decided, and opened a
   ticket -- Gemini Pro reserved for that one judgment call, Flash for
   everything else."
3. **The reasoning-chain trace.** "Every finding explains itself -- the
   alternatives it weighed, the score for each, and why the ones it
   didn't pick lost. This isn't a chat transcript, it's a structured
   audit record."
4. **Contract Intelligence + Concentration Analyzer -- the Assure loop.**
   "This DPA's breach-notification window is flagged against our legal
   playbook automatically. And because this vendor discloses the same
   AWS region an existing critical-tier vendor also uses, Concentration
   Analyzer just caught a portfolio risk that per-vendor review would
   never see."
5. **Framework Crosswalk.** "This vendor already has a satisfied SOC 2
   finding for MFA -- Framework Crosswalk reports that ISO 27001's
   equivalent control is already covered too, without collecting a
   single new piece of evidence."
6. **Buyer questionnaire answered from the same evidence graph**, with a
   citation on the confident answer and an honest abstention on the one
   without evidence.
7. **Evidence Collector and Drift Sentinel sweeps**, run manually here
   but scheduled via Cloud Scheduler in production -- "this is what
   closes the blind window without anyone asking, and Drift Sentinel's
   assessment-history endpoint shows exactly the trail the new
   risk_trend_rising signal watches for a control getting worse across
   reassessments before it's ever a hard gap."
8. **Offboarding a vendor.** "This DPA obligated the vendor to certify
   data deletion within 30 days of the relationship ending -- that
   obligation usually lives in a spreadsheet, if it's tracked at all.
   One call starts the clock, and if it's ever missed, Drift Sentinel
   raises it as a critical signal automatically."
9. **The executive risk digest.** "This fleet has 38 API endpoints --
   nobody has time to click through all of them every week. One call
   generates a prioritized narrative, grounded only in the fleet's actual
   current state, that a busy executive can read in under a minute."
10. **The kill switch, live.** "One call drops every agent in the fleet
    to Observe-only -- no redeploy, no restart." Show the autonomy level
    flip in the JSON response, then flip it back.

## 3:15 - 3:45 -- Proof of Google Cloud backend execution

Pick whichever of these you actually have credentials/quota for at
recording time -- one is enough, more is stronger:

- **Deployed on Cloud Run:** run `./deploy/setup_gcp.sh && ./deploy/deploy_cloud_run.sh`
  ahead of time, then on camera run `gcloud run services describe bulwark --region $REGION`
  and re-run `demo_cli.py --url <the Cloud Run URL>` against the live
  deployment instead of localhost.
- **Firestore-backed:** export `GOOGLE_CLOUD_PROJECT` and re-run the
  demo, then show the Firestore console with `vendors`/`findings`/
  `agent_registry` collections populated live.
- **Real Pub/Sub:** export `USE_PUBSUB=true` alongside `GOOGLE_CLOUD_PROJECT`
  and show the Cloud Console Pub/Sub topics list matching
  `platform/event_bus.py`'s topic names, with message counts ticking up
  during the demo run.
- **Cloud Logging:** show the structured audit-log entries this build
  writes appearing in Cloud Logging for the Cloud Run service.

Per the hackathon rules, the app does not need to still be live at
submission time -- this segment of the video *is* the proof, so it's
fine to scale the Cloud Run service back to zero (or delete it)
immediately after recording to avoid ongoing cost.

## 3:45 - 4:00 -- Close

> "Twelve agents, one event bus, zero direct agent-to-agent calls, a
> zero-trust identity table, and a kill switch that actually works.
> That's BULWARK."

## Fallback: no live Gemini credentials during recording

If credentials aren't available at record time, run
`python scripts/seed_demo_data.py` instead of `demo_cli.py` -- it drives
the same deterministic tool functions directly (no LLM calls needed) and
prints the same narrative beats (poisoned artifact, clean vendor with a
gap finding, the DPA + concentration-risk scenario, the crosswalk
coverage check, three worsening reassessments and the risk-trend signal
Drift Sentinel catches from them, offboarding the DPA vendor and its
data-deletion deadline, and a questionnaire). The executive digest isn't
in this fallback -- its narrative step is genuine LLM judgment, so it
needs real Gemini credentials.
Narrate over it the same way; call out explicitly on camera that this
run is exercising the deterministic code paths without a live model call,
and point to `README.md`'s "What's live vs. what's documented" table so
judges know exactly which parts that substitutes for.
