"""Model metadata, modifiable inputs, health -- everything the UI needs to
configure itself instead of hard-coding assumptions about the model."""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.access import admin
from app.db.database import get_db
from app.db.models import Observation, Patient, TwinVersion
from app.explain import explainer
from app.ml import registry, onset
from app.ml.features import MODIFIABLE_INPUTS
from app.schemas.models import HealthOut

router = APIRouter(tags=["meta"])


@router.get("/health", response_model=HealthOut, summary="Liveness + configuration")
def health() -> dict[str, Any]:
    loaded = registry.is_ready()
    synthetic = None
    if loaded:
        synthetic = registry.load_bundle().get("data_is_synthetic")
    return {
        "status": "ok",
        "api_version": settings.api_version,
        "environment": settings.environment,
        "model_loaded": loaded,
        "model_version": registry.model_version(),
        "data_is_synthetic": synthetic,
        "data_source": registry.load_bundle().get("data_source") if loaded else None,
        "llm_provider": settings.llm_provider,
        "evidence_offline": settings.evidence_offline,
        "database": settings.database_url.split("://")[0],
    }


@router.get("/meta/model", summary="Model card: how it was trained and validated")
def model_card() -> dict[str, Any]:
    if not registry.is_ready():
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE,
                            "No trained model is loaded. Run `python -m app.ml.train`.")
    bundle = registry.load_bundle()
    return {
        "model_version": bundle["model_version"],
        "trained_at": bundle["trained_at"],
        "data_source": bundle["data_source"],
        "data_is_synthetic": bundle["data_is_synthetic"],
        "provenance": bundle.get("provenance", {}),
        "supported_scenario_inputs": bundle.get("supported_scenario_inputs", []),
        "algorithm": "Training-only patient-grouped CV selection of carry-forward/change/HGB point models; "
                     "anchored quantile models with held-out conformal calibration",
        "horizons_months": bundle["horizons"],
        "interval_coverage": bundle["interval_coverage"],
        "risk_definition": bundle["risk_definition"],
        "n_features": len(bundle["feature_names"]),
        "feature_names": bundle["feature_names"],
        "feature_sets": bundle["feature_sets"],
        "metrics": bundle["metrics"],
        "research_datasets": onset.catalog(),
        "onset_model": onset.metadata(),
        "global_importance": explainer.global_importance(),
        "limitations": [
            "Trained on observational longitudinal data; associations only, never "
            "causal effects.",
            "Predictions are for clinical decision support and must be reviewed by a "
            "clinician.",
            "Counterfactual scenarios re-run the model on modified inputs; they do not "
            "model the biology of the eye.",
            "Behaviour and ergonomics are self-reported or app-derived and are "
            "non-medical-grade.",
            "Performance figures apply to the cohort the model was trained on and will "
            "differ on a different population.",
        ] + bundle.get("provenance", {}).get("limitations", []) + (["THIS MODEL IS TRAINED ON SYNTHETIC DATA. Its metrics describe a "
              "generated cohort and carry no clinical meaning."]
             if bundle["data_is_synthetic"] else []),
    }


@router.get('/meta/datasets', summary='Dataset roles: training, reference and research only')
def research_datasets():
    return onset.catalog()


@router.get("/meta/inputs", summary="Modifiable inputs and their plausible ranges")
def modifiable_inputs() -> dict[str, Any]:
    return {
        "inputs": [{"name": k, **v, "available": k in registry.load_bundle().get("supported_scenario_inputs", [])}
                   for k, v in MODIFIABLE_INPUTS.items()] if registry.is_ready() else [],
        "note": "The simulator rejects values outside these ranges rather than "
                "returning a confident-looking extrapolation.",
    }


@router.get("/meta/stats", summary="What is loaded in this deployment")
def stats(db: Session = Depends(get_db), user=Depends(admin)) -> dict[str, Any]:
    return {
        "patients": db.scalar(select(func.count()).select_from(Patient)) or 0,
        "observations": db.scalar(select(func.count()).select_from(Observation)) or 0,
        "twin_versions": db.scalar(select(func.count()).select_from(TwinVersion)) or 0,
        "data_sources": [
            {"source": s, "patients": n} for s, n in
            db.execute(select(Patient.data_source, func.count())
                       .group_by(Patient.data_source)).all()
        ],
        "disclaimer": settings.disclaimer,
    }
