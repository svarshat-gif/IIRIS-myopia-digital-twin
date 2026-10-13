from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.core.access import admin
from app.db.database import get_db
from app.db.models import AccessAudit, ClinicianAssignment, Patient, User

router = APIRouter(prefix="/admin", tags=["administration"], dependencies=[Depends(admin)])


class AssignmentIn(BaseModel):
    clinician_id: str
    patient_id: str


@router.post("/assignments", status_code=201)
def assign(payload: AssignmentIn, db: Session = Depends(get_db)):
    clinician = db.get(User, payload.clinician_id)
    if not clinician or clinician.role != "clinician" or not db.get(Patient, payload.patient_id):
        raise HTTPException(422, "Existing clinician and patient required")
    if not db.get(ClinicianAssignment, (payload.clinician_id, payload.patient_id)):
        db.add(ClinicianAssignment(**payload.model_dump()))
        db.commit()
    return payload.model_dump()


@router.get("/audit")
def audit(limit: int = Query(100, ge=1, le=1000), offset: int = Query(0, ge=0),
          patient_id: str | None = None, db: Session = Depends(get_db)):
    stmt = select(AccessAudit).order_by(AccessAudit.created_at.desc())
    if patient_id:
        stmt = stmt.where(AccessAudit.patient_id == patient_id)
    rows = db.scalars(stmt.offset(offset).limit(limit))
    return {"events": [{c.name: getattr(r, c.name) for c in AccessAudit.__table__.columns} for r in rows]}
