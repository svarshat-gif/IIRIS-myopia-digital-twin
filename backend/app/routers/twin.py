"""Twin state, versioning and prediction endpoints."""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.database import get_db
from app.db.models import Patient
from app.explain import explainer
from app.fhir import mapping as fhir
from app.ml import registry
from app.schemas.models import ExplainTarget
from app.twin import service as twin_service

router = APIRouter(prefix="/patients/{patient_id}", tags=["twin"])


def _patient_or_404(db: Session, patient_id: str) -> Patient:
    patient = db.get(Patient, patient_id)
    if patient is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Patient not found.")
    return patient


def _state_or_404(db: Session, patient_id: str) -> dict[str, Any]:
    patient = _patient_or_404(db, patient_id)
    version = twin_service.get_current_version(db, patient_id)
    if version is not None:
        return {**version.state_json, "created_at": version.created_at.isoformat()}
    try:
        return twin_service.build_state(db, patient)
    except ValueError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc


@router.get("/twin", summary="Current twin state + history summary")
def get_twin(patient_id: str, rebuild: bool = Query(
        False, description="Recompute from observations instead of returning the "
                           "stored version (useful after retraining)."),
        db: Session = Depends(get_db)) -> dict[str, Any]:
    patient = _patient_or_404(db, patient_id)
    if rebuild:
        try:
            return twin_service.refresh_twin(db, patient, triggered_by="manual")
        except ValueError as exc:
            raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc
    return _state_or_404(db, patient_id)


@router.get("/twin/versions", summary="List every stored twin version")
def list_versions(patient_id: str, db: Session = Depends(get_db)) -> dict[str, Any]:
    _patient_or_404(db, patient_id)
    versions = twin_service.list_versions(db, patient_id)
    return {
        "patient_id": patient_id,
        "versions": [
            {
                "version": v.version,
                "triggered_by": v.triggered_by,
                "model_version": v.model_version,
                "created_at": v.created_at.isoformat(),
                "latest_visit": v.state_json["current"]["visit_date"],
                "spherical_equivalent": v.state_json["current"]["spherical_equivalent"],
                "axial_length": v.state_json["current"]["axial_length"],
                "predicted_se_12m": (
                    ((v.state_json.get("prediction") or {})
                     .get("horizons", {}).get("12m", {}).get("se") or {}).get("value")),
                "risk_band": ((v.state_json.get("prediction") or {})
                              .get("risk") or {}).get("band"),
            }
            for v in versions
        ],
    }


@router.get("/twin/versions/{version}", summary="Replay one historical twin version")
def get_version(patient_id: str, version: int,
                db: Session = Depends(get_db)) -> dict[str, Any]:
    """Answers 'what did the system know before the latest measurement?' with the
    actual stored state, not a recomputation."""
    _patient_or_404(db, patient_id)
    tv = twin_service.get_version(db, patient_id, version)
    if tv is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"Twin version {version} not found.")
    return {**tv.state_json, "created_at": tv.created_at.isoformat()}


@router.get("/twin/compare", summary="Diff two twin versions")
def compare(patient_id: str, from_version: int, to_version: int,
            db: Session = Depends(get_db)) -> dict[str, Any]:
    _patient_or_404(db, patient_id)
    try:
        return twin_service.compare_versions(db, patient_id, from_version, to_version)
    except ValueError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from exc


@router.get("/prediction", summary="Predictions with uncertainty for every horizon")
def get_prediction(patient_id: str, db: Session = Depends(get_db)) -> dict[str, Any]:
    if not registry.is_ready():
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "No trained model is loaded. Run `python -m app.ml.train` in the backend.")
    state = _state_or_404(db, patient_id)
    prediction = state.get("prediction") or twin_service.predict_from_state(
        state["features"])
    return {
        "patient_id": patient_id,
        "twin_version": state.get("version"),
        "as_of_visit": state["current"]["visit_date"],
        **prediction,
    }


@router.get("/explanation", summary="Per-prediction attribution (SHAP when installed)")
def get_explanation(patient_id: str, target: ExplainTarget = "se_12m",
                    top_n: int = Query(8, ge=3, le=25),
                    db: Session = Depends(get_db)) -> dict[str, Any]:
    if not registry.is_ready():
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE,
                            "No trained model is loaded.")
    state = _state_or_404(db, patient_id)
    try:
        result = explainer.explain_prediction(state["features"], target=target,
                                              top_n=top_n)
    except ValueError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc
    return {"patient_id": patient_id, "twin_version": state.get("version"), **result}


@router.get("/fhir", tags=["fhir"],
            summary="Export the patient as a FHIR R4 Bundle")
def get_fhir(patient_id: str,
             include_predictions: bool = Query(True),
             db: Session = Depends(get_db)) -> dict[str, Any]:
    patient = _patient_or_404(db, patient_id)
    observations = twin_service.get_observations(db, patient_id)
    prediction, version_number = None, None
    if include_predictions:
        tv = twin_service.get_current_version(db, patient_id)
        if tv is not None:
            prediction = tv.state_json.get("prediction")
            version_number = tv.version
    bundle = fhir.build_bundle(patient, observations, prediction, version_number)
    return bundle


@router.get("/monitor", summary="Has the latest update materially changed anything?")
def monitor(patient_id: str, db: Session = Depends(get_db)) -> dict[str, Any]:
    _patient_or_404(db, patient_id)
    versions = twin_service.list_versions(db, patient_id)
    if len(versions) < 2:
        return {"patient_id": patient_id, "materially_changed": False, "flags": [],
                "note": "Only one twin version exists; nothing to compare yet.",
                "disclaimer": settings.disclaimer}
    return twin_service.compare_versions(db, patient_id, versions[-2].version,
                                         versions[-1].version)
