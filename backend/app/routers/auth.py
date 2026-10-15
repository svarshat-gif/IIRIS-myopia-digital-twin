"""Sign up, sign in, profile."""
from __future__ import annotations

from datetime import datetime, timezone, timedelta
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.auth import (
    create_access_token,
    get_current_user,
    hash_password,
    password_problems,
    verify_password,
)
from app.db.database import get_db
from app.db.models import Patient, User
from app.schemas.auth import (
    LoginIn,
    PasswordChange,
    ProfileUpdate,
    SignupIn,
    TokenOut,
    UserOut,
)
from app.twin import service as twin_service

router = APIRouter(prefix="/auth", tags=["auth"])


def own_patient(db: Session, user: User) -> Patient | None:
    return db.scalars(
        select(Patient).where(Patient.owner_user_id == user.user_id)
        .order_by(Patient.created_at).limit(1)).first()


def user_payload(db: Session, user: User) -> dict[str, Any]:
    patient = own_patient(db, user)
    n_visits, version = 0, 0
    if patient is not None:
        n_visits = len(twin_service.get_observations(db, patient.patient_id))
        current = twin_service.get_current_version(db, patient.patient_id)
        version = current.version if current else 0
    return {
        "user_id": user.user_id,
        "email": user.email,
        "full_name": user.full_name,
        "role": user.role,
        "created_at": user.created_at,
        "last_login_at": user.last_login_at,
        "patient_id": patient.patient_id if patient else None,
        "n_visits": n_visits,
        "twin_version": version,
        "has_record": n_visits > 0,
    }


@router.post("/signup", response_model=TokenOut, status_code=status.HTTP_201_CREATED,
             summary="Create an account and an empty eye record")
def signup(payload: SignupIn, db: Session = Depends(get_db)) -> dict[str, Any]:
    email = payload.email.lower().strip()
    if db.scalars(select(User).where(User.email == email)).first():
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "An account already exists for that email. Try signing in instead.")

    problems = password_problems(payload.password)
    if problems:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            f"Please choose a password that is {', and '.join(problems)}.")

    user = User(email=email, password_hash=hash_password(payload.password),
                full_name=payload.full_name.strip())
    db.add(user)
    db.flush()

    # Every account gets a clinical record straight away, so the first visit can
    # be added without a separate setup step.
    db.add(Patient(
        owner_user_id=user.user_id,
        external_key=None,
        age_at_start=payload.age,
        sex=payload.sex,
        parental_myopia=payload.parental_myopia,
        consent_status="self_reported",
        data_source="self_reported",
    ))
    user.last_login_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(user)

    token, expires_in = create_access_token(user.user_id, user.email)
    return {"access_token": token, "expires_in": expires_in,
            "user": user_payload(db, user)}


@router.post("/login", response_model=TokenOut, summary="Sign in")
def login(payload: LoginIn, db: Session = Depends(get_db)) -> dict[str, Any]:
    user = db.scalars(
        select(User).where(User.email == payload.email.lower().strip())).first()
    now = datetime.now(timezone.utc)
    if user and user.locked_until and user.locked_until.replace(tzinfo=timezone.utc) > now:
        raise HTTPException(429, "Sign-in temporarily unavailable; try again later", headers={"Retry-After": "900"})
    # Same message either way: never reveal whether an email is registered.
    if user is None or not verify_password(payload.password, user.password_hash):
        if user:
            user.failed_logins += 1
            if user.failed_logins >= 5:
                user.locked_until = now + timedelta(minutes=15)
            db.commit()
        raise HTTPException(status.HTTP_401_UNAUTHORIZED,
                            "That email and password do not match.")
    if not user.is_active:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "This account is disabled.")

    user.last_login_at = datetime.now(timezone.utc)
    user.failed_logins = 0
    user.locked_until = None
    db.commit()
    token, expires_in = create_access_token(user.user_id, user.email)
    return {"access_token": token, "expires_in": expires_in,
            "user": user_payload(db, user)}


@router.get("/me", response_model=UserOut, summary="The signed-in account")
def me(user: User = Depends(get_current_user),
       db: Session = Depends(get_db)) -> dict[str, Any]:
    return user_payload(db, user)


@router.patch("/me", response_model=UserOut, summary="Update name or profile details")
def update_me(payload: ProfileUpdate, user: User = Depends(get_current_user),
              db: Session = Depends(get_db)) -> dict[str, Any]:
    if payload.full_name:
        user.full_name = payload.full_name.strip()

    patient = own_patient(db, user)
    if patient is not None:
        if payload.age is not None:
            patient.age_at_start = payload.age
        if payload.sex is not None:
            patient.sex = payload.sex
        if payload.parental_myopia is not None:
            patient.parental_myopia = payload.parental_myopia
        if payload.ethnicity is not None:
            patient.ethnicity = payload.ethnicity
        # Profile fields feed the model, so the twin is rebuilt to pick them up.
        if twin_service.get_observations(db, patient.patient_id):
            twin_service.refresh_twin(db, patient, triggered_by="profile_update")
    db.commit()
    db.refresh(user)
    return user_payload(db, user)


@router.post("/change-password", status_code=status.HTTP_204_NO_CONTENT,
             response_class=__import__("fastapi").Response,
             summary="Change password")
def change_password(payload: PasswordChange, user: User = Depends(get_current_user),
                    db: Session = Depends(get_db)):
    if not verify_password(payload.current_password, user.password_hash):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED,
                            "Your current password is not correct.")
    problems = password_problems(payload.new_password)
    if problems:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            f"Please choose a password that is {', and '.join(problems)}.")
    user.password_hash = hash_password(payload.new_password)
    db.commit()
