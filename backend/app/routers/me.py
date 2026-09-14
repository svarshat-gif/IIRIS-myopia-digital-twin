"""Everything scoped to the signed-in user's own record.

The generic /patients/{id}/... endpoints still exist for research cohorts and for
the API's own documentation. These /me/... endpoints are what the app uses, so
the client never has to know or send a patient id -- which also means it cannot
ask for someone else's.
"""
from __future__ import annotations

from datetime import date
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.auth import get_current_user
from app.core.config import settings
from app.db.database import get_db
from app.db.models import Appointment, Observation, Patient, Simulation, User
from app.explain import explainer
from app.fhir import mapping as fhir
from app.ml import registry
from app.routers.auth import own_patient
from app.schemas.auth import AppointmentIn, AppointmentOut, ProjectionIn
from app.schemas.models import ExplainTarget, ObservationIn, ScenarioIn, SensitivityIn
from app.simulator import engine, projection
from app.simulator.constraints import ScenarioRejected
from app.twin import service as twin_service

router = APIRouter(prefix="/me", tags=["my record"])


def _patient(db: Session, user: User) -> Patient:
    patient = own_patient(db, user)
    if patient is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND,
                            "This account has no eye record yet.")
    return patient


def _state(db: Session, user: User) -> dict[str, Any]:
    patient = _patient(db, user)
    version = twin_service.get_current_version(db, patient.patient_id)
    if version is not None:
        return {**version.state_json, "created_at": version.created_at.isoformat()}
    try:
        return twin_service.build_state(db, patient)
    except ValueError as exc:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "Add your first eye test result to start your record.") from exc


def _require_model() -> None:
    if not registry.is_ready():
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE,
                            "The prediction model is not loaded on this server.")


# --------------------------------------------------------------------------
# Record + twin
# --------------------------------------------------------------------------

@router.get("/summary", summary="Everything the home screen needs, in one call")
def summary(user: User = Depends(get_current_user),
            db: Session = Depends(get_db)) -> dict[str, Any]:
    patient = _patient(db, user)
    observations = twin_service.get_observations(db, patient.patient_id)
    version = twin_service.get_current_version(db, patient.patient_id)

    today = date.today()
    appointments = db.scalars(
        select(Appointment).where(Appointment.user_id == user.user_id)
        .order_by(Appointment.scheduled_for)).all()
    upcoming = [a for a in appointments
                if a.scheduled_for >= today and a.status == "scheduled"]
    past = [a for a in appointments if a.scheduled_for < today or a.status != "scheduled"]

    state = version.state_json if version else None
    latest = observations[-1] if observations else None
    previous = observations[-2] if len(observations) > 1 else None

    return {
        "user": {"full_name": user.full_name, "email": user.email},
        "has_record": bool(observations),
        "n_visits": len(observations),
        "twin_version": version.version if version else 0,
        "profile": {
            "age_at_start": patient.age_at_start, "sex": patient.sex,
            "parental_myopia": patient.parental_myopia,
        },
        "latest": None if latest is None else {
            "visit_date": latest.visit_date.isoformat(),
            "age": latest.age,
            "spherical_equivalent": latest.spherical_equivalent,
            "axial_length": latest.axial_length,
            "visual_acuity": latest.visual_acuity,
            "treatment": latest.treatment,
        },
        "change_since_previous": None if previous is None or latest is None else {
            "spherical_equivalent": round(
                latest.spherical_equivalent - previous.spherical_equivalent, 3),
            "axial_length": round(latest.axial_length - previous.axial_length, 3),
            "months": round((latest.visit_date - previous.visit_date).days / 30.4375, 1),
            # Days too, so the UI can avoid saying "over 0 months" when two
            # results were entered close together.
            "days": (latest.visit_date - previous.visit_date).days,
        },
        "category": projection.categorise(
            latest.spherical_equivalent if latest else None),
        "derived": state["derived"] if state else None,
        "prediction": state.get("prediction") if state else None,
        "data_completeness": state["data_completeness"] if state else None,
        "next_appointment": None if not upcoming else {
            "appointment_id": upcoming[0].appointment_id,
            "scheduled_for": upcoming[0].scheduled_for.isoformat(),
            "time_label": upcoming[0].time_label,
            "clinic": upcoming[0].clinic,
            "practitioner": upcoming[0].practitioner,
            "reason": upcoming[0].reason,
            "days_away": (upcoming[0].scheduled_for - today).days,
        },
        "appointment_counts": {"upcoming": len(upcoming), "past": len(past)},
        "model_version": registry.model_version(),
        "model_loaded": registry.is_ready(),
        "data_is_synthetic": (registry.load_bundle().get("data_is_synthetic")
                              if registry.is_ready() else None),
        "disclaimer": settings.disclaimer,
    }


@router.get("/twin", summary="My full twin state")
def my_twin(user: User = Depends(get_current_user),
            db: Session = Depends(get_db)) -> dict[str, Any]:
    return _state(db, user)


@router.get("/records", summary="My eye test history, newest first")
def my_records(user: User = Depends(get_current_user),
               db: Session = Depends(get_db)) -> dict[str, Any]:
    patient = _patient(db, user)
    observations = twin_service.get_observations(db, patient.patient_id)
    rows = []
    for i, obs in enumerate(observations):
        previous = observations[i - 1] if i > 0 else None
        rows.append({
            "observation_id": obs.observation_id,
            "visit_date": obs.visit_date.isoformat(),
            "age": obs.age,
            "spherical_equivalent": obs.spherical_equivalent,
            "axial_length": obs.axial_length,
            "visual_acuity": obs.visual_acuity,
            "corneal_curvature": obs.corneal_curvature,
            "treatment": obs.treatment,
            "screen_time_hours": obs.screen_time_hours,
            "near_work_min": obs.near_work_min,
            "outdoor_min": obs.outdoor_min,
            "sleep_hours": obs.sleep_hours,
            "viewing_distance_cm": obs.viewing_distance_cm,
            "posture_score": obs.posture_score,
            "continuous_session_min": obs.continuous_session_min,
            "source": obs.source,
            "category": projection.categorise(obs.spherical_equivalent),
            "change": None if previous is None else {
                "spherical_equivalent": round(
                    obs.spherical_equivalent - previous.spherical_equivalent, 3),
                "axial_length": round(obs.axial_length - previous.axial_length, 3),
                "months": round((obs.visit_date - previous.visit_date).days / 30.4375, 1),
            },
        })
    rows.reverse()
    return {"records": rows, "n_visits": len(rows)}


@router.post("/records", status_code=status.HTTP_201_CREATED,
             summary="Add an eye test result -- this updates my twin")
def add_record(payload: ObservationIn, user: User = Depends(get_current_user),
               db: Session = Depends(get_db)) -> dict[str, Any]:
    patient = _patient(db, user)
    clash = db.scalars(
        select(Observation).where(Observation.patient_id == patient.patient_id,
                                  Observation.visit_date == payload.visit_date)).first()
    if clash:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            f"You already have a result saved for {payload.visit_date:%d %B %Y}. "
            f"Edit or delete it first.")

    previous = twin_service.get_current_version(db, patient.patient_id)
    previous_version = previous.version if previous else None

    obs = Observation(patient_id=patient.patient_id, **payload.model_dump())
    db.add(obs)
    db.flush()

    # First result also sets the starting age on the profile.
    if previous_version is None and payload.age is not None and not patient.age_at_start:
        patient.age_at_start = payload.age

    try:
        state = twin_service.refresh_twin(db, patient, triggered_by="observation")
    except ValueError as exc:
        db.rollback()
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc

    change_summary = None
    if previous_version is not None:
        try:
            change_summary = twin_service.compare_versions(
                db, patient.patient_id, previous_version, state["version"])
        except ValueError:
            change_summary = None

    return {"observation_id": obs.observation_id, "twin_version": state["version"],
            "previous_version": previous_version, "twin": state,
            "change_summary": change_summary, "disclaimer": settings.disclaimer}


@router.delete("/records/{observation_id}", status_code=status.HTTP_204_NO_CONTENT,
               response_class=Response, summary="Delete one saved result")
def delete_record(observation_id: str, user: User = Depends(get_current_user),
                  db: Session = Depends(get_db)):
    patient = _patient(db, user)
    obs = db.get(Observation, observation_id)
    if obs is None or obs.patient_id != patient.patient_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "That result was not found.")
    db.delete(obs)
    db.flush()
    if twin_service.get_observations(db, patient.patient_id):
        twin_service.refresh_twin(db, patient, triggered_by="record_deleted")
    else:
        db.commit()


@router.get("/prediction", summary="My prediction with uncertainty")
def my_prediction(user: User = Depends(get_current_user),
                  db: Session = Depends(get_db)) -> dict[str, Any]:
    _require_model()
    state = _state(db, user)
    prediction = state.get("prediction") or twin_service.predict_from_state(
        state["features"])
    return {"twin_version": state.get("version"),
            "as_of_visit": state["current"]["visit_date"], **prediction}


@router.get("/explanation", summary="Why my prediction looks like this")
def my_explanation(target: ExplainTarget = "se_12m",
                   top_n: int = Query(8, ge=3, le=25),
                   user: User = Depends(get_current_user),
                   db: Session = Depends(get_db)) -> dict[str, Any]:
    _require_model()
    state = _state(db, user)
    try:
        return explainer.explain_prediction(state["features"], target=target, top_n=top_n)
    except ValueError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc


@router.get("/versions", summary="My twin's version history")
def my_versions(user: User = Depends(get_current_user),
                db: Session = Depends(get_db)) -> dict[str, Any]:
    patient = _patient(db, user)
    versions = twin_service.list_versions(db, patient.patient_id)
    return {"versions": [
        {"version": v.version, "triggered_by": v.triggered_by,
         "model_version": v.model_version, "created_at": v.created_at.isoformat(),
         "latest_visit": v.state_json["current"]["visit_date"],
         "spherical_equivalent": v.state_json["current"]["spherical_equivalent"],
         "axial_length": v.state_json["current"]["axial_length"],
         "predicted_se_12m": (((v.state_json.get("prediction") or {})
                               .get("horizons", {}).get("12m", {}).get("se") or {})
                              .get("value")),
         "risk_band": ((v.state_json.get("prediction") or {}).get("risk") or {}).get("band")}
        for v in versions]}


@router.get("/fhir", summary="Export my record as a FHIR R4 Bundle")
def my_fhir(user: User = Depends(get_current_user),
            db: Session = Depends(get_db)) -> dict[str, Any]:
    patient = _patient(db, user)
    observations = twin_service.get_observations(db, patient.patient_id)
    version = twin_service.get_current_version(db, patient.patient_id)
    return fhir.build_bundle(
        patient, observations,
        version.state_json.get("prediction") if version else None,
        version.version if version else None)


# --------------------------------------------------------------------------
# Simulation
# --------------------------------------------------------------------------

@router.post("/simulate", summary="Run a what-if scenario on my record")
def my_simulate(payload: ScenarioIn, user: User = Depends(get_current_user),
                db: Session = Depends(get_db)) -> dict[str, Any]:
    _require_model()
    patient = _patient(db, user)
    state = _state(db, user)
    try:
        result = engine.simulate(state, payload.model_dump())
    except ScenarioRejected as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY,
                            {"message": "That scenario is outside a realistic range.",
                             "errors": exc.errors}) from exc

    record = Simulation(patient_id=patient.patient_id,
                        baseline_twin_version=state.get("version") or 0,
                        scenario_json=payload.model_dump(),
                        results_json=result["comparison"], label=payload.label)
    db.add(record)
    db.commit()
    return {"simulation_id": record.simulation_id, **result}


@router.post("/sensitivity", summary="Dose-response sweep on my record")
def my_sensitivity(payload: SensitivityIn, user: User = Depends(get_current_user),
                   db: Session = Depends(get_db)) -> dict[str, Any]:
    _require_model()
    state = _state(db, user)
    try:
        return engine.sensitivity_sweep(state, payload.input_name, payload.values,
                                        payload.horizon)
    except ScenarioRejected as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY,
                            {"errors": exc.errors}) from exc


@router.post("/project", summary="Project my trajectory years ahead")
def my_projection(payload: ProjectionIn, user: User = Depends(get_current_user),
                  db: Session = Depends(get_db)) -> dict[str, Any]:
    _require_model()
    state = _state(db, user)
    patient_meta = state["patient"]

    changes = None
    if payload.changes:
        from app.simulator.constraints import validate_scenario
        current = {**state["current"].get("behaviour", {}),
                   **state["current"].get("ergonomics", {}),
                   "treatment": state["current"].get("treatment")}
        try:
            changes, _ = validate_scenario(payload.changes, current)
        except ScenarioRejected as exc:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY,
                                {"errors": exc.errors}) from exc

    baseline = projection.project(
        state["history"], sex=patient_meta.get("sex"),
        parental_myopia=patient_meta.get("parental_myopia"), years=payload.years)

    scenario = None
    if changes:
        scenario = projection.project(
            state["history"], sex=patient_meta.get("sex"),
            parental_myopia=patient_meta.get("parental_myopia"),
            years=payload.years, overrides=changes)

    return {"baseline": baseline, "scenario": scenario,
            "applied_changes": changes or {},
            "history": state["history"]}


# --------------------------------------------------------------------------
# Appointments
# --------------------------------------------------------------------------

@router.get("/appointments", response_model=list[AppointmentOut],
            summary="My appointments")
def list_appointments(user: User = Depends(get_current_user),
                      db: Session = Depends(get_db)) -> list[dict[str, Any]]:
    today = date.today()
    rows = db.scalars(
        select(Appointment).where(Appointment.user_id == user.user_id)
        .order_by(Appointment.scheduled_for.desc())).all()
    return [{**AppointmentOut.model_validate(a).model_dump(),
             "is_past": a.scheduled_for < today} for a in rows]


@router.post("/appointments", response_model=AppointmentOut,
             status_code=status.HTTP_201_CREATED, summary="Book or log an appointment")
def create_appointment(payload: AppointmentIn, user: User = Depends(get_current_user),
                       db: Session = Depends(get_db)) -> Appointment:
    patient = own_patient(db, user)
    appointment = Appointment(user_id=user.user_id,
                              patient_id=patient.patient_id if patient else None,
                              **payload.model_dump())
    db.add(appointment)
    db.commit()
    db.refresh(appointment)
    return appointment


@router.patch("/appointments/{appointment_id}", response_model=AppointmentOut,
              summary="Update an appointment")
def update_appointment(appointment_id: str, payload: AppointmentIn,
                       user: User = Depends(get_current_user),
                       db: Session = Depends(get_db)) -> Appointment:
    appointment = db.get(Appointment, appointment_id)
    if appointment is None or appointment.user_id != user.user_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Appointment not found.")
    for key, value in payload.model_dump().items():
        setattr(appointment, key, value)
    db.commit()
    db.refresh(appointment)
    return appointment


@router.delete("/appointments/{appointment_id}", status_code=status.HTTP_204_NO_CONTENT,
               response_class=Response, summary="Delete an appointment")
def delete_appointment(appointment_id: str, user: User = Depends(get_current_user),
                       db: Session = Depends(get_db)):
    appointment = db.get(Appointment, appointment_id)
    if appointment is None or appointment.user_id != user.user_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Appointment not found.")
    db.delete(appointment)
    db.commit()
