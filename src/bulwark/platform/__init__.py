"""Platform layer: the Gemini Enterprise Agent Platform (GEAP) pillars,
each mapped to a concrete module.

- ``store``          -- Firestore/in-memory document storage
- ``event_bus``       -- Pub/Sub-shaped event bus (topics, DLQ, idempotency)
- ``registry``         -- Agent Registry
- ``identity``          -- Agent Identity (per-agent grants, zero trust)
- ``guardrails``         -- Model Armor (injection/tool-poisoning/PII, at every boundary)
- ``observability``       -- OTel spans + audit trail (exported toward BigQuery)
- ``policy``               -- autonomy ladder + kill switch (fleet_config.autonomy_level)
"""
