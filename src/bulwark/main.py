"""ASGI entrypoint for Cloud Run.

Run locally with:  uvicorn bulwark.main:app --reload
On Cloud Run:       uvicorn bulwark.main:app --host 0.0.0.0 --port $PORT
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

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
    if settings.seed_demo_data:
        await _seed_demo_data_in_process()
    yield


async def _seed_demo_data_in_process() -> None:
    """Runs scripts/seed_demo_data.py's scenario inside *this* process so
    it lands in the same in-memory store the running server reads from --
    see BULWARK_SEED_DEMO_DATA's docstring in config.py for why running it
    as a separate `python scripts/seed_demo_data.py` process would not
    actually be visible through this server's API. Awaited directly
    (rather than via `asyncio.run`, which `scripts/seed_demo_data.py`'s
    own `__main__` block uses for standalone invocation) because this
    runs inside uvicorn's already-running event loop during lifespan
    startup, and `asyncio.run` cannot nest inside one."""
    import importlib.util
    from pathlib import Path

    seed_path = Path(__file__).resolve().parent.parent.parent / "scripts" / "seed_demo_data.py"
    if not seed_path.exists():
        logger.error("BULWARK_SEED_DEMO_DATA=true but %s is missing -- skipping seed.", seed_path)
        return
    spec = importlib.util.spec_from_file_location("bulwark_scripts_seed_demo_data", seed_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    await module.main()
    logger.info("Demo data seeded in-process (BULWARK_SEED_DEMO_DATA=true).")


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

# Serves the dashboard (frontend/) built and copied into ./static by the
# Dockerfile's multi-stage build -- see its comment. Registered after
# include_router() above so every API route matches first; anything left
# over falls through to this mount. html=True's directory-index behavior
# is all this needs for SPA routing: the dashboard uses HashRouter, so
# the browser only ever requests this one real path ("/") -- every other
# "route" is a URL fragment the server never sees, so there's no
# "/vendors/123 loaded directly" case to add a wildcard fallback for.
# Absent entirely in local dev (no Docker build ran), which is fine --
# the dashboard runs from `npm run dev` on its own port instead then.
_STATIC_DIR = Path(__file__).resolve().parent.parent.parent / "static"
if _STATIC_DIR.is_dir():
    app.mount("/", StaticFiles(directory=_STATIC_DIR, html=True), name="dashboard")
