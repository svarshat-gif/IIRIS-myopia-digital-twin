"""Patient + observation endpoints. Adding an observation is what advances the twin."""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.database import get_db
from app.db.models import Observation, Patient
from app.schemas.models import (
    BulkImportIn,
    ObservationAccepted,
    ObservationIn,
    ObservationOut,
    PatientCreate,
    PatientOut,
    PatientSummary,
)
from app.twin import service as twin_service

router = APIRouter(prefix="/patients", tags=["patients"])


@router.post("", response_model=PatientOut, status_code=status.HTTP_201_CREATED,
             summary="Create a de-identified patient record")
def create_patient(payload: PatientCreate, db: Session = Depends(get_db)) -> Patient:
    if payload.external_key:
        existing = db.scalars(
            select(Patient).where(Patient.external_key == payload.external_key)).first()
        if existing:
            raise HTTPException(status.HTTP_409_CONFLICT,
                                f"external_key '{payload.external_key}' already exists "
                                f"(patient_id {existing.patient_id}).")
    patient = Patient(**payload.model_dump())
    db.add(patient)
    db.commit()
    db.refresh(patient)
    return patient


@router.get("", response_model=list[PatientSummary], summary="List patients")
def list_patients(db: Session = Depends(get_db),
                  limit: int = Query(100, ge=1, le=1000),
                  offset: int = Query(0, ge=0)) -> list[dict[str, Any]]:
    # Personal records (those owned by an account) are deliberately excluded here.
    # They are reachable only through /me, by their owner.
    patients = db.scalars(
        select(Patient).where(Patient.owner_user_id.is_(None))
        .offset(offset).limit(limit)).all()
    out: list[dict[str, Any]] = []
    for p in patients:
        obs = twin_service.get_observations(db, p.patient_id)
        version = twin_service.get_current_version(db, p.patient_id)
        risk_band = None
        if version:
            prediction = version.state_json.get("prediction") or {}
            risk_band = (prediction.get("risk") or {}).get("band")
        out.append({
            **PatientOut.model_validate(p).model_dump(),
            "n_visits": len(obs),
            "latest_visit": obs[-1].visit_date if obs else None,
            "twin_version": version.version if version else 0,
            "latest_se": obs[-1].spherical_equivalent if obs else None,
            "latest_al": obs[-1].axial_length if obs else None,
            "risk_band": risk_band,
        })
    return out


@router.get("/{patient_id}", response_model=PatientOut, summary="Get one patient")
def get_patient(patient_id: str, db: Session = Depends(get_db)) -> Patient:
    patient = db.get(Patient, patient_id)
    if patient is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Patient not found.")
    return patient


@router.delete("/{patient_id}", status_code=status.HTTP_204_NO_CONTENT,
               response_class=Response,
               summary="Delete a patient and everything derived from them")
def delete_patient(patient_id: str, db: Session = Depends(get_db)):
    patient = db.get(Patient, patient_id)
    if patient is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Patient not found.")
    db.delete(patient)
    db.commit()


@router.get("/{patient_id}/observations", response_model=list[ObservationOut],
            summary="List a patient's visits")
def list_observations(patient_id: str, db: Session = Depends(get_db)) -> list[Observation]:
    if db.get(Patient, patient_id) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Patient not found.")
    return twin_service.get_observations(db, patient_id)


@router.post("/{patient_id}/observations", response_model=ObservationAccepted,
             status_code=status.HTTP_201_CREATED,
             summary="Add a visit -- this advances the twin to a new version")
def add_observation(patient_id: str, payload: ObservationIn,
                    db: Session = Depends(get_db)) -> dict[str, Any]:
    """The core Digital Twin loop.

    validate -> store observation -> rebuild twin state -> re-run prediction ->
    save a NEW immutable version -> report what changed.
    """
    patient = db.get(Patient, patient_id)
    if patient is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Patient not found.")

    clash = db.scalars(
        select(Observation).where(Observation.patient_id == patient_id,
                                  Observation.visit_date == payload.visit_date)).first()
    if clash:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            f"A visit already exists for {payload.visit_date}. Delete it first or use "
            f"a different date.")

    previous = twin_service.get_current_version(db, patient_id)
    previous_version = previous.version if previous else None

    obs = Observation(patient_id=patient_id, **payload.model_dump())
    db.add(obs)
    db.flush()

    try:
        state = twin_service.refresh_twin(db, patient, triggered_by="observation")
    except ValueError as exc:
        db.rollback()
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc

    change_summary = None
    if previous_version is not None:
        try:
            change_summary = twin_service.compare_versions(
                db, patient_id, previous_version, state["version"])
        except ValueError:
            change_summary = None

    return {
        "patient_id": patient_id,
        "observation_id": obs.observation_id,
        "twin_version": state["version"],
        "previous_version": previous_version,
        "twin": state,
        "change_summary": change_summary,
        "disclaimer": settings.disclaimer,
    }


@router.delete("/{patient_id}/observations/{observation_id}",
               status_code=status.HTTP_204_NO_CONTENT, response_class=Response,
               summary="Delete a visit and rebuild the twin")
def delete_observation(patient_id: str, observation_id: str,
                       db: Session = Depends(get_db)):
    obs = db.get(Observation, observation_id)
    if obs is None or obs.patient_id != patient_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Observation not found.")
    db.delete(obs)
    db.flush()
    patient = db.get(Patient, patient_id)
    if twin_service.get_observations(db, patient_id):
        twin_service.refresh_twin(db, patient, triggered_by="observation_deleted")
    else:
        db.commit()


@router.post("/bulk-import", tags=["import"],
             summary="Import a whole cohort (creates patients, visits and twins)")
def bulk_import(payload: BulkImportIn, db: Session = Depends(get_db)) -> dict[str, Any]:
    """Load many patient-visits in one call.

    This is the endpoint to point at real hospital data once it is de-identified
    and approved -- see docs/DATA_ONBOARDING.md. Rows for the same external_key are
    grouped into one patient, and each patient's twin is built once at the end
    rather than after every row.
    """
    created_patients = 0
    created_observations = 0
    skipped: list[dict[str, Any]] = []
    touched: dict[str, Patient] = {}

    for i, row in enumerate(payload.rows):
        patient = db.scalars(
            select(Patient).where(Patient.external_key == row.external_key)).first()
        if patient is None:
            patient = Patient(
                external_key=row.external_key,
                age_at_start=row.age_at_start if row.age_at_start is not None
                else (row.age if row.age is not None else 0.0),
                sex=row.sex,
                parental_myopia=row.parental_myopia,
                consent_status=payload.consent_status,
                data_source=payload.data_source,
            )
            db.add(patient)
            db.flush()
            created_patients += 1

        exists = db.scalars(
            select(Observation).where(Observation.patient_id == patient.patient_id,
                                      Observation.visit_date == row.visit_date)).first()
        if exists:
            skipped.append({"row": i, "external_key": row.external_key,
                            "reason": f"duplicate visit_date {row.visit_date}"})
            continue

        fields = row.model_dump(exclude={"external_key", "age_at_start", "sex",
                                         "parental_myopia"})
        db.add(Observation(patient_id=patient.patient_id, **fields))
        created_observations += 1
        touched[patient.patient_id] = patient

    db.flush()

    rebuilt = 0
    if payload.rebuild_twins:
        for patient in touched.values():
            try:
                twin_service.refresh_twin(db, patient, triggered_by="import")
                rebuilt += 1
            except ValueError:
                continue
    db.commit()

    return {
        "created_patients": created_patients,
        "created_observations": created_observations,
        "twins_rebuilt": rebuilt,
        "skipped": skipped[:50],
        "skipped_total": len(skipped),
    }
