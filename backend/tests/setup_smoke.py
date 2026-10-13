"""Seed real open-data records and test credentials into an isolated smoke DB."""
from sqlalchemy import select
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.config import settings  # noqa: E402
from app.core.auth import hash_password  # noqa: E402
from app.db.database import init_db, SessionLocal  # noqa: E402
from app.db.models import User, Patient, ClinicianAssignment  # noqa: E402

if not settings.database_url.endswith('smoke_test.db'):
    raise RuntimeError('Smoke setup requires an isolated smoke_test.db')
init_db()
with SessionLocal() as db:
    user = db.scalar(select(User).where(User.email == 'clinician-smoke@example.org'))
    if not user:
        user = User(email='clinician-smoke@example.org', full_name='Test clinician', role='clinician',
                    password_hash=hash_password('isolated-clinician-2026'))
        db.add(user)
        db.flush()
    for p in db.scalars(select(Patient)):
        if not db.get(ClinicianAssignment, (user.user_id, p.patient_id)):
            db.add(ClinicianAssignment(clinician_id=user.user_id, patient_id=p.patient_id))
    db.commit()
