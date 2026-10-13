"""Read-only FHIR R4 facade with the same clinician assignments as the twin API."""
from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session
from app.core.auth import get_current_user
from app.core.access import check_patient
from app.db.database import get_db
from app.db.models import User
from app.fhir.mapping import patient_to_fhir, build_bundle
from app.twin.service import get_observations

router = APIRouter(prefix="/fhir", tags=["fhir"])


@router.get("/Patient/{patient_id}")
def patient_resource(patient_id: str, request: Request, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    patient = check_patient(db, user, patient_id)
    request.state.patient_id = patient_id
    return patient_to_fhir(patient)


@router.get("/Observation")
def observation_search(patient: str, request: Request, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    row = check_patient(db, user, patient)
    request.state.patient_id = patient
    bundle = build_bundle(row, get_observations(db, patient))
    entries = [e for e in bundle["entry"] if e["resource"]["resourceType"] == "Observation"]
    return {"resourceType": "Bundle", "type": "searchset", "total": len(entries), "entry": entries}
