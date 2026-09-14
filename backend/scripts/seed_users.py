"""Create the demo sign-in accounts.

Both accounts are built from REAL ROWS OF `data/synthetic_cohort.csv` — the same
file the models were trained on — so every patient in the running application can
be traced back to the dataset that is handed in with the report. Nothing here is
hand-written.

    python scripts/seed_users.py --reset

Creates:
  demo@iiris.health   -> cohort patient SYN00532 (steady progression, -0.48 D/year)
  clear@iiris.health  -> cohort patient SYN00328 (nearly stable, -0.10 D/year)

Both sit in the well-covered part of the training distribution (final SE about
-2.5 to -3.0 D). That matters: below about -4 D the cohort thins out and the
independently fitted quantile models start to disagree with the median model,
which puts the point estimate near the edge of its own interval. A demo should
show a representative patient, not a tail case.

Both are SYNTHETIC people. Delete them before connecting real accounts.
"""
from __future__ import annotations

import argparse
import sys
from datetime import date, timedelta
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import select  # noqa: E402

from app.core.auth import hash_password  # noqa: E402
from app.db.database import SessionLocal, init_db  # noqa: E402
from app.db.models import Appointment, Observation, Patient, User  # noqa: E402
from app.ml import registry  # noqa: E402
from app.ml.dataset import load_visits  # noqa: E402
from app.twin import service as twin_service  # noqa: E402

PASSWORD = "irisdemo2026"
DATA = Path(__file__).resolve().parents[1] / "data" / "synthetic_cohort.csv"

# (email, display name, cohort patient_key)
ACCOUNTS = [
    ("demo@iiris.health", "Aarav Nair", "SYN00532"),
    ("clear@iiris.health", "Rohan Iyer", "SYN00328"),
]

NULLABLE = [
    "age", "visual_acuity", "corneal_curvature", "screen_time_hours", "near_work_min",
    "outdoor_min", "sleep_hours", "viewing_distance_cm", "posture_score",
    "continuous_session_min",
]


def _v(row: dict, key: str):
    value = row.get(key)
    return None if value is None or pd.isna(value) else float(value)


def build_account(db, email: str, name: str, key: str, visits: list[dict]) -> User:
    existing = db.scalars(select(User).where(User.email == email)).first()
    if existing:
        print(f"  {email} already exists — skipping")
        return existing

    first = visits[0]
    user = User(email=email, password_hash=hash_password(PASSWORD), full_name=name)
    db.add(user)
    db.flush()

    patient = Patient(
        owner_user_id=user.user_id,
        external_key=key,                      # the cohort key, so it can be grepped
        age_at_start=_v(first, "age") or 0.0,
        sex=first.get("sex") if isinstance(first.get("sex"), str) else None,
        parental_myopia=(int(first["parental_myopia"])
                         if pd.notna(first.get("parental_myopia")) else None),
        consent_status="synthetic_demo",
        data_source="synthetic_cohort.csv",
    )
    db.add(patient)
    db.flush()

    for row in visits:
        db.add(Observation(
            patient_id=patient.patient_id,
            visit_date=row["visit_date"],
            spherical_equivalent=float(row["spherical_equivalent"]),
            axial_length=float(row["axial_length"]),
            treatment=(row.get("treatment")
                       if isinstance(row.get("treatment"), str) else None),
            source="synthetic_cohort.csv",
            **{k: _v(row, k) for k in NULLABLE},
        ))
        db.flush()
        # Rebuild after every visit so the version history is genuine.
        twin_service.refresh_twin(db, patient, triggered_by="observation")

        db.add(Appointment(
            user_id=user.user_id, patient_id=patient.patient_id,
            scheduled_for=row["visit_date"], time_label="10:30 AM",
            clinic="City Eye Centre", practitioner="Dr A. Menon",
            reason="Myopia review", status="completed",
        ))

    # One upcoming review, six months after the last recorded visit (or soon, if
    # that date has already passed).
    last = visits[-1]["visit_date"]
    upcoming = last + timedelta(days=182)
    if upcoming <= date.today():
        upcoming = date.today() + timedelta(days=74)
    db.add(Appointment(
        user_id=user.user_id, patient_id=patient.patient_id,
        scheduled_for=upcoming, time_label="11:00 AM",
        clinic="City Eye Centre", practitioner="Dr A. Menon",
        reason="6-month myopia review and axial length scan", status="scheduled",
    ))
    db.commit()

    se0 = visits[0]["spherical_equivalent"]
    se1 = visits[-1]["spherical_equivalent"]
    print(f"  {email:<20} <- {key}: {len(visits)} visits, "
          f"SE {se0:+.2f} -> {se1:+.2f} D  (twin v{len(visits)})")
    return user


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--reset", action="store_true",
                    help="Delete the existing demo accounts first.")
    ap.add_argument("--data", type=Path, default=DATA)
    args = ap.parse_args()

    init_db()
    if not registry.is_ready():
        print("WARNING: no trained model. Run `python -m app.ml.train` first.")

    df = load_visits(args.data)
    db = SessionLocal()
    try:
        if args.reset:
            for email, _, _ in ACCOUNTS:
                user = db.scalars(select(User).where(User.email == email)).first()
                if user:
                    db.delete(user)      # cascades to patient, observations, twins
            db.commit()

        print(f"Creating demo accounts from {args.data.name}:")
        for email, name, key in ACCOUNTS:
            visits = df[df["patient_key"] == key].sort_values("visit_date") \
                       .to_dict("records")
            if not visits:
                print(f"  !! {key} not found in {args.data.name} — skipped")
                continue
            build_account(db, email, name, key, visits)
    finally:
        db.close()

    print(f"\nEvery demo patient is a row set from {args.data.name}.")
    print(f"Sign in with either email and the password:  {PASSWORD}")


if __name__ == "__main__":
    main()
