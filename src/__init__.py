"""BULWARK: Continuous Third-Party Assurance Fleet.

Fortified Enterprise Fleet track submission. A fleet of seven agents,
published to an Agent Registry and run on an event-driven Agent Runtime,
that collapses the "blind window" between a risk-relevant signal existing
in the world and a human at the company knowing about it -- for both
directions of third-party risk: assessing vendors, and answering buyers'
security questionnaires from the same evidence graph.

Scoping note: this build implements the full architecture -- event bus,
Firestore-shaped evidence graph, per-agent identity grants, Model Armor
guardrails at every untrusted boundary, a central kill switch, and
citation-enforced findings -- against Firestore/in-memory storage and an
in-process Pub/Sub-shaped event bus, both of which transparently upgrade
to real GCP services when credentials are configured. Live bindings to
BigQuery, Cloud DLP, and Vertex AI Vector Search are documented and
wired for Cloud Run deployment (see deploy/) but represented locally by
equivalent-purpose logic, since this repo has no GCP credentials to
verify them against. See README.md "What's live vs. what's documented"
for the exact line.
"""

__version__ = "0.1.0"
