"""Iiris -- Myopia Digital Twin API. Application entry point.

Run locally:
    uvicorn app.main:app --reload --port 8000
Interactive docs:
    http://localhost:8000/docs
"""
from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, RedirectResponse

from app.core.config import settings
from app.core.security import require_api_key
from app.core.access import cohort_access
from app.core.middleware import ControlsMiddleware, JsonFormatter
from app.db.database import init_db
from app.ml import registry
from app.routers import (
    agent, attachments, auth, evidence, me, meta, patients, simulate, simulator, twin, admin, fhir,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-7s %(name)s | %(message)s",
)
log = logging.getLogger("iiris")
for handler in logging.getLogger().handlers:
    handler.setFormatter(JsonFormatter())

API_PREFIX = "/api/v1"

DESCRIPTION = """
**Iiris** -- a personal eye-health digital twin.

A **Digital Twin API**, not a `/predict` wrapper.

A normal ML API answers *"what is the prediction?"*. This one answers:

* What is this patient's **current twin state**, and how has it changed?
* What does the model **predict**, and with how much **uncertainty**?
* What happens under a **what-if scenario**?
* **Why** did the model say that?
* What **evidence** relates to the factors involved?
* And every new observation **advances the twin to a new version**, so any past
  state can be replayed.

---

**Clinical scope.** Decision support only. The system does not diagnose, does not
prescribe, and does not claim causal treatment effects. Simulated scenarios are
model estimates produced by re-running a predictive model on modified inputs.

**Data scope.** Check `GET /api/v1/health` -> `data_is_synthetic`. When true, the
loaded model was trained on generated data and its metrics carry no clinical meaning.
"""

TAGS = [
    {"name": "meta", "description": "Health, model card, configurable inputs."},
    {"name": "auth", "description": "Sign up, sign in, profile."},
    {"name": "my record", "description": "Everything scoped to the signed-in user."},
    {"name": "simulator", "description": "Public projection from typed-in values."},
    {"name": "attachments", "description": "Prescription photos and scan reports."},
    {"name": "patients", "description": "De-identified patients and their visits. "
                                        "Adding a visit advances the twin."},
    {"name": "twin", "description": "Twin state, version history, prediction, "
                                    "explanation, monitoring."},
    {"name": "simulation", "description": "Counterfactual what-if scenarios."},
    {"name": "agent", "description": "Tool-using agent over the twin."},
    {"name": "evidence", "description": "Literature retrieval and citation cache."},
    {"name": "fhir", "description": "HL7 FHIR R4 export."},
    {"name": "import", "description": "Bulk cohort import."},
]


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    log.info("Database ready (%s)", settings.database_url.split("://")[0])
    if registry.is_ready():
        bundle = registry.load_bundle()
        if settings.environment == "production" and bundle.get("data_is_synthetic") is not False:
            raise RuntimeError("Production requires a verified real-data model")
        log.info("Model loaded: %s (synthetic=%s)",
                 bundle["model_version"], bundle["data_is_synthetic"])
        if bundle["data_is_synthetic"]:
            log.warning("Model is trained on SYNTHETIC data -- outputs have no "
                        "clinical meaning.")
    else:
        if settings.environment == "production":
            raise RuntimeError("Model artifact missing. Run make model before building the release image")
        log.warning("No model bundle found. Prediction, simulation and explanation "
                    "endpoints will return 503 until you run: python -m app.ml.train")
    if settings.api_key:
        log.info("API-key authentication is ENABLED.")
    else:
        log.warning("API-key authentication is DISABLED (development default). "
                    "Set API_KEY before exposing this service.")
    yield


app = FastAPI(
    title=settings.app_name,
    version=settings.api_version,
    description=DESCRIPTION,
    openapi_tags=TAGS,
    lifespan=lifespan,
    contact={"name": "Myopia Digital Twin capstone"},
    license_info={"name": "MIT"},
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(ControlsMiddleware)

_guard = [Depends(require_api_key)]
app.include_router(meta.router, prefix=API_PREFIX, dependencies=_guard)
app.include_router(auth.router, prefix=API_PREFIX, dependencies=_guard)
app.include_router(me.router, prefix=API_PREFIX, dependencies=_guard)
app.include_router(attachments.router, prefix=API_PREFIX, dependencies=_guard)
app.include_router(simulator.router, prefix=API_PREFIX, dependencies=_guard)
_cohort_guard = [*_guard, Depends(cohort_access)]
app.include_router(patients.router, prefix=API_PREFIX, dependencies=_cohort_guard)
app.include_router(twin.router, prefix=API_PREFIX, dependencies=_cohort_guard)
app.include_router(simulate.router, prefix=API_PREFIX, dependencies=_cohort_guard)
app.include_router(agent.router, prefix=API_PREFIX, dependencies=_guard)
app.include_router(evidence.router, prefix=API_PREFIX, dependencies=_guard)
app.include_router(admin.router, prefix=API_PREFIX, dependencies=_guard)
app.include_router(fhir.router, prefix=API_PREFIX, dependencies=_guard)
app.include_router(fhir.router, dependencies=_guard)

from app.simulator.constraints import ScenarioRejected


@app.exception_handler(ScenarioRejected)
async def rejected_scenario(request, exc):
    return JSONResponse({"detail": {"message": "Scenario unavailable", "errors": exc.errors}}, status_code=422)


@app.get("/readyz", tags=["meta"])
def readyz():
    from sqlalchemy import text
    from app.db.database import engine
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        if not registry.is_ready():
            raise RuntimeError("Model unavailable")
        registry.load_bundle()
    except Exception:
        return JSONResponse({"status": "not_ready"}, status_code=503)
    return {"status": "ready", "model_version": registry.model_version()}


@app.get("/", include_in_schema=False)
def root() -> RedirectResponse:
    return RedirectResponse("/docs")


@app.get("/healthz", include_in_schema=False)
def healthz() -> JSONResponse:
    """Unauthenticated liveness probe for container orchestrators."""
    return JSONResponse({"status": "ok", "version": settings.api_version})
