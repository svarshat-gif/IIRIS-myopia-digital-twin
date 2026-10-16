"""Append current-model twin versions without changing observations or old snapshots."""
import sys
from pathlib import Path

from sqlalchemy import select

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.db.database import SessionLocal  # noqa: E402
from app.db.models import Patient  # noqa: E402
from app.ml import registry  # noqa: E402
from app.twin import service  # noqa: E402


def refresh(db):
    version = registry.model_version()
    if not registry.is_ready() or registry.load_bundle().get('data_is_synthetic') is not False:
        raise ValueError('Refresh requires a trained real-data release model')
    updated = skipped = 0
    for patient in db.scalars(select(Patient)).all():
        current = service.get_current_version(db, patient.patient_id)
        if current and current.model_version == version:
            skipped += 1
            continue
        if not service.get_observations(db, patient.patient_id):
            skipped += 1
            continue
        service.refresh_twin(db, patient, triggered_by='model_refresh')
        updated += 1
    return {'model_version': version, 'updated_patients': updated, 'skipped_patients': skipped}


if __name__ == '__main__':
    with SessionLocal() as db:
        print(refresh(db))
