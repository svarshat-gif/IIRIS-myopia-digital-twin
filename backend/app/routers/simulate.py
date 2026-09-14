"""Counterfactual simulation endpoints."""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.db.models import Simulation
from app.ml import registry
from app.schemas.models import MultiScenarioIn, ScenarioIn, SensitivityIn
from app.simulator import engine
from app.simulator.constraints import ScenarioRejected
from app.routers.twin import _state_or_404

router = APIRouter(prefix="/patients/{patient_id}", tags=["simulation"])


def _require_model() -> None:
    if not registry.is_ready():
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE,
                            "No trained model is loaded, so scenarios cannot be run.")


@router.post("/simulate", summary="Run one what-if scenario")
def simulate(patient_id: str, payload: ScenarioIn,
             db: Session = Depends(get_db)) -> dict[str, Any]:
    _require_model()
    state = _state_or_404(db, patient_id)
    try:
        result = engine.simulate(state, payload.model_dump())
    except ScenarioRejected as exc:
        # 422: the request was well-formed but the scenario is outside the range
        # the model may be asked about.
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, {
            "message": "Scenario rejected as implausible.",
            "errors": exc.errors,
        }) from exc

    record = Simulation(
        patient_id=patient_id,
        baseline_twin_version=state.get("version") or 0,
        scenario_json=payload.model_dump(),
        results_json=result["comparison"],
        label=payload.label,
    )
    db.add(record)
    db.commit()
    return {"simulation_id": record.simulation_id, "patient_id": patient_id,
            "twin_version": state.get("version"), **result}


@router.post("/simulate/batch", summary="Run several scenarios and compare them")
def simulate_batch(patient_id: str, payload: MultiScenarioIn,
                   db: Session = Depends(get_db)) -> dict[str, Any]:
    _require_model()
    state = _state_or_404(db, patient_id)
    result = engine.simulate_many(state, [s.model_dump() for s in payload.scenarios])
    return {"patient_id": patient_id, "twin_version": state.get("version"), **result}


@router.post("/sensitivity", summary="Sweep one input to get a dose-response curve")
def sensitivity(patient_id: str, payload: SensitivityIn,
                db: Session = Depends(get_db)) -> dict[str, Any]:
    _require_model()
    state = _state_or_404(db, patient_id)
    try:
        return engine.sensitivity_sweep(state, payload.input_name, payload.values,
                                        payload.horizon)
    except ScenarioRejected as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY,
                            {"errors": exc.errors}) from exc


@router.get("/simulations", summary="Previously stored scenarios for this patient")
def list_simulations(patient_id: str, db: Session = Depends(get_db)) -> dict[str, Any]:
    from sqlalchemy import select
    rows = db.scalars(
        select(Simulation).where(Simulation.patient_id == patient_id)
        .order_by(Simulation.created_at.desc()).limit(50)).all()
    return {"patient_id": patient_id, "simulations": [
        {"simulation_id": r.simulation_id, "label": r.label,
         "baseline_twin_version": r.baseline_twin_version,
         "scenario": r.scenario_json, "results": r.results_json,
         "created_at": r.created_at.isoformat()}
        for r in rows
    ]}
