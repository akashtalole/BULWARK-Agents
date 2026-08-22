"""ASGI entrypoint for Cloud Run.

Run locally with:  uvicorn bulwark.main:app --reload
On Cloud Run:       uvicorn bulwark.main:app --host 0.0.0.0 --port $PORT
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from bulwark.api.routes import router, set_orchestration_fns
from bulwark.config import settings
from bulwark.platform.registry import bootstrap_registry

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(settings.service_name)


@asynccontextmanager
async def lifespan(_: FastAPI):
    bootstrap_registry()
    logger.info(
        "BULWARK starting: environment=%s firestore=%s pubsub=%s llm_credentials=%s",
        settings.environment, settings.use_firestore, settings.use_pubsub, settings.has_llm_credentials,
    )
    if settings.has_llm_credentials:
        from bulwark.agents.orchestrator import generate_digest, process_vendor_artifact, run_drift_sweep, submit_questionnaire

        set_orchestration_fns(process_vendor_artifact, submit_questionnaire, run_drift_sweep, generate_digest)
    else:
        logger.warning(
            "No Gemini credentials found (GOOGLE_API_KEY or Vertex AI project). "
            "POST endpoints that invoke an agent will return 503 until credentials are configured."
        )
    yield


app = FastAPI(
    title="BULWARK",
    description=(
        "Fortified Enterprise Fleet track: a continuous third-party assurance fleet on "
        "Google ADK, Gemini, Cloud Run, Pub/Sub, and Firestore."
    ),
    version=settings.service_version,
    lifespan=lifespan,
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=list(settings.cors_allow_origins),
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(router)
