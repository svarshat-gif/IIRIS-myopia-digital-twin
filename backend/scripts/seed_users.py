"""Attach an existing verified open-data record to a demo account. No invented visits."""
import argparse
import os

from sqlalchemy import select
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.auth import hash_password, password_problems  # noqa: E402
from app.db.database import SessionLocal, init_db  # noqa: E402
from app.db.models import Patient, User  # noqa: E402


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--email", default="demo@iiris.health")
    args = parser.parse_args()
    password = os.environ.get("DEMO_PASSWORD", "")
    if not password or password_problems(password):
        raise ValueError("Set DEMO_PASSWORD to a policy-compliant password; no bundled credentials")
    init_db()
    with SessionLocal() as db:
        if db.scalar(select(User).where(User.email == args.email)):
            print("Demo account exists; unchanged")
            return
        patient = db.scalar(select(Patient).where(Patient.data_source.not_like("%synthetic%"),
                                                  Patient.consent_status == "open_research",
                                                  Patient.owner_user_id.is_(None)).order_by(Patient.external_key))
        if patient is None:
            raise ValueError("Seed verified open-data records first")
        user = User(email=args.email, full_name="Open research participant", password_hash=hash_password(password))
        db.add(user)
        db.flush()
        patient.owner_user_id = user.user_id
        db.commit()
        print("Demo account linked to open research record; no fabricated appointments or exposures")


if __name__ == "__main__":
    main()
