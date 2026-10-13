"""Role and assignment checks shared by every patient-data API, including FHIR."""
from fastapi import Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.core.auth import get_current_user
from app.db.database import get_db
from app.db.models import ClinicianAssignment, Patient, User


def admin(user: User = Depends(get_current_user)) -> User:
    if user.role != "admin":
        raise HTTPException(403, "Administrator access required")
    return user


def check_patient(db: Session, user: User, patient_id: str, *, own_allowed=False):
    patient = db.get(Patient, patient_id)
    if patient is None:
        raise HTTPException(404, "Patient not found")
    allowed = user.role == "admin" or (user.role == "clinician" and
        db.get(ClinicianAssignment, (user.user_id, patient_id)) is not None)
    if own_allowed and user.role == "patient" and patient.owner_user_id == user.user_id:
        allowed = True
    if not allowed:
        raise HTTPException(403, "This record is not assigned to your account")
    return patient


def cohort_access(request: Request, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if user.role not in {"clinician", "admin"}:
        raise HTTPException(403, "Use /me for your own record")
    patient_id = request.path_params.get("patient_id")
    if patient_id:
        check_patient(db, user, patient_id)
        request.state.patient_id = patient_id
    if request.method == "DELETE" or request.url.path.endswith("/bulk-import"):
        if user.role != "admin":
            raise HTTPException(403, "Administrator access required")
    return user


def assigned_ids(db: Session, user: User):
    return select(ClinicianAssignment.patient_id).where(ClinicianAssignment.clinician_id == user.user_id)
