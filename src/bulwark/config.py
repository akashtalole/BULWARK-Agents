"""Environment-driven configuration.

Same zero-cloud-setup philosophy as the rest of this hackathon's builds:
every setting comes from env vars, and the whole fleet runs in-memory with
no GCP project configured, then transparently upgrades to Firestore +
real Pub/Sub topics on Cloud Run.
"""

from __future__ import annotations

import os
from dataclasses import dataclass


def _bool_env(name: str, default: bool) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class Settings:
    # Two models, deliberately: Flash for the six workhorse agents, Pro
    # reserved for Risk Assessor's final cross-referencing reasoning --
    # the hackathon's own cost guidance ("reserve Pro for complex final
    # reasoning") applied literally, not just cited.
    gemini_flash_model: str = os.environ.get("GEMINI_FLASH_MODEL", "gemini-flash-latest")
    gemini_pro_model: str = os.environ.get("GEMINI_PRO_MODEL", "gemini-pro-latest")
    has_llm_credentials: bool = bool(
        os.environ.get("GOOGLE_API_KEY")
        or (
            os.environ.get("GOOGLE_CLOUD_PROJECT")
            and _bool_env("GOOGLE_GENAI_USE_VERTEXAI", False)
        )
    )

    gcp_project: str | None = os.environ.get("GOOGLE_CLOUD_PROJECT")
    # A named database, not the special "(default)" one -- confirmed via a
    # real Cloud Run deploy crash (see platform/store.py's module
    # docstring): the Python client resolves "(default)" to that exact
    # literal string whether it's passed explicitly or omitted, and
    # something downstream percent-encodes its parentheses, which
    # Firestore then rejects with "Invalid database id %28default%29" on
    # every startup. deploy/setup_gcp.sh creates a database named
    # "bulwark" to match.
    firestore_database: str = os.environ.get("FIRESTORE_DATABASE", "bulwark")
    use_firestore: bool = bool(os.environ.get("GOOGLE_CLOUD_PROJECT")) and _bool_env(
        "USE_FIRESTORE", True
    )
    # Real Pub/Sub is only attempted when explicitly turned on -- the
    # in-memory bus already reproduces the topic/subscriber/DLQ contract,
    # so this is opt-in rather than inferred from GOOGLE_CLOUD_PROJECT.
    use_pubsub: bool = _bool_env("USE_PUBSUB", False)

    api_keys: tuple[str, ...] = tuple(
        k.strip()
        for k in os.environ.get("BULWARK_API_KEYS", "demo-key").split(",")
        if k.strip()
    )

    rate_limit_requests: int = int(os.environ.get("RATE_LIMIT_REQUESTS", "30"))
    rate_limit_window_seconds: int = int(os.environ.get("RATE_LIMIT_WINDOW_SECONDS", "60"))

    # Questionnaire Responder abstains below this confidence rather than
    # guessing -- see platform/policy.py and agents/questionnaire_responder.py.
    answer_confidence_threshold: float = float(os.environ.get("ANSWER_CONFIDENCE_THRESHOLD", "0.75"))

    # Evidence older than this is downgraded to "stale" and stops
    # satisfying controls -- see platform/models.py.
    evidence_freshness_days: int = int(os.environ.get("EVIDENCE_FRESHNESS_DAYS", "30"))

    # Cadence for the two scheduled sweeps (Cloud Scheduler in prod; a
    # manual/`send_later`-driven tick in this demo -- see scripts/).
    evidence_sweep_hours: int = int(os.environ.get("EVIDENCE_SWEEP_HOURS", "6"))
    drift_sweep_hours: int = int(os.environ.get("DRIFT_SWEEP_HOURS", "24"))

    # Section 6.4's mandatory human-in-the-loop gates: a finding with
    # residual_risk at or above this (of 1-25) always requires a human
    # decision before it's considered resolved, regardless of autonomy
    # level -- same for any finding on a critical-tier vendor. See
    # platform/policy.py's requires_mandatory_human_review.
    residual_risk_human_threshold: int = int(os.environ.get("RESIDUAL_RISK_HUMAN_THRESHOLD", "15"))

    default_tenant: str = os.environ.get("BULWARK_DEFAULT_TENANT", "acme-eu")

    # Agent Gateway CORS: the frontend/ dashboard runs on its own origin
    # (Vite dev server locally, a separate static host in production) and
    # calls this API cross-origin with X-API-Key -- comma-separated list,
    # defaults to the Vite dev server ports so local dev works with zero
    # configuration. Tighten this to the deployed dashboard's real origin
    # before shipping it anywhere public.
    cors_allow_origins: tuple[str, ...] = tuple(
        o.strip()
        for o in os.environ.get(
            "BULWARK_CORS_ALLOW_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173"
        ).split(",")
        if o.strip()
    )

    # Local-demo convenience: seeds scripts/seed_demo_data.py's scenario
    # into the *same process* as the running server on startup. Off by
    # default -- the store is pure in-memory unless USE_FIRESTORE is set,
    # so running the seed script as a separate `python` process (as a
    # naive two-terminal walkthrough would) writes into a store the
    # server never sees. This flag is the fix: one process, one store.
    seed_demo_data: bool = _bool_env("BULWARK_SEED_DEMO_DATA", False)

    service_name: str = os.environ.get("BULWARK_SERVICE_NAME", "bulwark")
    service_version: str = os.environ.get("BULWARK_SERVICE_VERSION", "0.1.0")
    environment: str = os.environ.get("BULWARK_ENVIRONMENT", "local")


settings = Settings()
