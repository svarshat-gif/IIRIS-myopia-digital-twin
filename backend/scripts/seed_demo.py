"""Load a cohort CSV into the database and build each patient's twin history.

Twins are built INCREMENTALLY -- version 1 after the first visit, version 2 after
the second, and so on -- so the version timeline in the UI is a real history, and
"what did the system know before the latest measurement?" has a genuine answer.

    python scripts/seed_demo.py --patients 40
    python scripts/seed_demo.py --data data/my_hospital_cohort.csv --reset
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd
from sqlalchemy import select

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.db.database import Base, SessionLocal, engine, init_db  # noqa: E402
from app.db.models import Observation, Patient  # noqa: E402
from app.ml import registry  # noqa: E402
from app.ml.dataset import load_visits  # noqa: E402
from app.ml.train import verify_training_source  # noqa: E402
from app.twin import service as twin_service  # noqa: E402

NULLABLE = [
    "age", "visual_acuity", "corneal_curvature", "screen_time_hours", "near_work_min",
    "outdoor_min", "sleep_hours", "viewing_distance_cm", "posture_score",
    "continuous_session_min",
]


def _v(row: dict, key: str):
    value = row.get(key)
    return None if value is None or pd.isna(value) else float(value)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--data", type=Path,
                    default=Path(__file__).resolve().parents[1] / "data" /
                    "training_visits.csv")
    ap.add_argument("--patients", type=int, default=40,
                    help="How many patients to load (0 = all).")
    ap.add_argument("--through-month", type=float, default=None, help="Keep later real visits for the update demo")
    ap.add_argument("--reset", action="store_true",
                    help="Drop and recreate all tables first.")
    ap.add_argument("--consent-status", default="open_research")
    ap.add_argument("--data-source", default="Zenodo DIMS 18166476")
    args = ap.parse_args()
    verify_training_source(args.data)

    if args.reset:
        print("Dropping all tables ...")
        Base.metadata.drop_all(bind=engine)
    init_db()

    if not registry.is_ready():
        print("WARNING: no trained model found. Twins will be stored without "
              "predictions. Run `python -m app.ml.train` first for the full demo.")

    df = load_visits(args.data)
    if args.through_month is not None:
        df = df[df.followup_month <= args.through_month]
    keys = list(dict.fromkeys(df["patient_key"]))
    if args.patients:
        keys = keys[: args.patients]
    df = df[df["patient_key"].isin(keys)]

    db = SessionLocal()
    created = versions = 0
    try:
        for key in keys:
            if db.scalar(select(Patient).where(Patient.external_key == str(key))):
                print(f"  {key}: already present; unchanged")
                continue
            rows = df[df["patient_key"] == key].sort_values("visit_date").to_dict("records")
            if not rows:
                continue
            first = rows[0]

            patient = Patient(
                external_key=str(key),
                age_at_start=_v(first, "age"),
                sex=(first.get("sex") if isinstance(first.get("sex"), str) else None),
                parental_myopia=(int(first["parental_myopia"])
                                 if pd.notna(first.get("parental_myopia")) else None),
                consent_status=args.consent_status,
                data_source=args.data_source,
            )
            db.add(patient)
            db.flush()
            created += 1

            for row in rows:
                db.add(Observation(
                    patient_id=patient.patient_id,
                    visit_date=row["visit_date"],
                    followup_month=_v(row, "followup_month"),
                    spherical_equivalent=float(row["spherical_equivalent"]),
                    axial_length=float(row["axial_length"]),
                    treatment=(row.get("treatment")
                               if isinstance(row.get("treatment"), str) else None),
                    source=str(row.get("source") or args.data_source),
                    **{k: _v(row, k) for k in NULLABLE},
                ))
                db.flush()
                # Rebuild the twin after each visit -> a real version history.
                twin_service.refresh_twin(db, patient, triggered_by="observation")
                versions += 1

            print(f"  {key}: {len(rows)} visits -> twin v{len(rows)}")

        db.commit()
    finally:
        db.close()

    print(f"\nSeeded {created} patients and {versions} twin versions from {args.data}")
    print(f"Model: {registry.model_version()}")
    print("Start the API with:  uvicorn app.main:app --reload --port 8000")


if __name__ == "__main__":
    main()
