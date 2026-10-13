"""Create a privileged account explicitly; passwords are read from env or a hidden prompt."""
import argparse
import getpass
import os
from sqlalchemy import select
from app.core.auth import hash_password, password_problems
from app.db.database import SessionLocal, init_db
from app.db.models import User


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--email", required=True)
    parser.add_argument("--role", choices=["admin", "clinician"], default="admin")
    a = parser.parse_args()
    password = os.environ.get("ADMIN_PASSWORD") or getpass.getpass("Account password: ")
    if password_problems(password):
        raise ValueError("Password must have 12+ characters and not be common or numeric")
    init_db()
    with SessionLocal() as db:
        existing = db.scalar(select(User).where(User.email == a.email.lower()))
        if existing:
            raise ValueError("Account already exists; refusing implicit privilege escalation")
        db.add(User(email=a.email.lower(), full_name=a.role.title(), role=a.role,
                    password_hash=hash_password(password)))
        db.commit()
    print("Account created")


if __name__ == "__main__":
    main()
