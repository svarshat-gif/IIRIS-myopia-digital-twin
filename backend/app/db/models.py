"""Relational model of the Digital Twin.

The twin is a set of linked records rather than one JSON blob, so that any
historical state can be replayed ("what did the system know before this visit?").
"""
from __future__ import annotations

import uuid
from datetime import date, datetime, timezone

from sqlalchemy import (
    JSON,
    Boolean,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.database import Base


def _uuid() -> str:
    return uuid.uuid4().hex


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class User(Base):
    """An account. One person signing in to see their own eye records.

    The account holds the identity (email, display name). The clinical record
    lives in `patients`, linked by `owner_user_id`. Keeping them in separate
    tables means the clinical tables stay free of identifying fields, so a
    research export of `patients` + `observations` is de-identified by
    construction -- you simply never join `users`.
    """

    __tablename__ = "users"

    user_id: Mapped[str] = mapped_column(String(64), primary_key=True, default=_uuid)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    full_name: Mapped[str] = mapped_column(String(120))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    patients: Mapped[list["Patient"]] = relationship(
        back_populates="owner", cascade="all, delete-orphan")
    appointments: Mapped[list["Appointment"]] = relationship(
        back_populates="user", cascade="all, delete-orphan",
        order_by="Appointment.scheduled_for")


class Patient(Base):
    """A de-identified clinical record. Never store names, MRNs or contact details here.

    `owner_user_id` links it to the account that may view it. It is nullable so
    that research cohorts (which have no account behind them) can coexist with
    personal records in the same table.
    """

    __tablename__ = "patients"

    patient_id: Mapped[str] = mapped_column(String(64), primary_key=True, default=_uuid)
    owner_user_id: Mapped[str | None] = mapped_column(
        ForeignKey("users.user_id", ondelete="CASCADE"), index=True)
    external_key: Mapped[str | None] = mapped_column(String(128), unique=True, index=True)
    age_at_start: Mapped[float] = mapped_column(Float)
    sex: Mapped[str | None] = mapped_column(String(16))
    ethnicity: Mapped[str | None] = mapped_column(String(64))
    parental_myopia: Mapped[int | None] = mapped_column(Integer)  # 0 / 1 / 2 parents
    consent_status: Mapped[str] = mapped_column(String(32), default="synthetic")
    data_source: Mapped[str] = mapped_column(String(64), default="synthetic")
    notes: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    owner: Mapped["User | None"] = relationship(back_populates="patients")
    observations: Mapped[list["Observation"]] = relationship(
        back_populates="patient", cascade="all, delete-orphan", order_by="Observation.visit_date"
    )
    twin_versions: Mapped[list["TwinVersion"]] = relationship(
        back_populates="patient", cascade="all, delete-orphan", order_by="TwinVersion.version"
    )


class Observation(Base):
    """One clinical visit plus the behaviour/ergonomics reported for that visit.

    Behaviour and ergonomics are nullable on purpose: if the source dataset does
    not measure them, they stay NULL. They are never imputed with invented values.
    """

    __tablename__ = "observations"

    observation_id: Mapped[str] = mapped_column(String(64), primary_key=True, default=_uuid)
    patient_id: Mapped[str] = mapped_column(
        ForeignKey("patients.patient_id", ondelete="CASCADE"), index=True
    )
    visit_date: Mapped[date | None] = mapped_column(Date, index=True)
    followup_month: Mapped[float | None] = mapped_column(Float)
    age: Mapped[float | None] = mapped_column(Float)

    # Clinical / biomarker layer
    spherical_equivalent: Mapped[float] = mapped_column(Float)   # dioptres, e.g. -2.35
    axial_length: Mapped[float] = mapped_column(Float)           # mm, e.g. 24.31
    visual_acuity: Mapped[float | None] = mapped_column(Float)   # logMAR
    corneal_curvature: Mapped[float | None] = mapped_column(Float)  # mm
    treatment: Mapped[str | None] = mapped_column(String(64))    # none|atropine|ortho_k|dims|...

    # Behaviour layer
    screen_time_hours: Mapped[float | None] = mapped_column(Float)
    near_work_min: Mapped[float | None] = mapped_column(Float)
    outdoor_min: Mapped[float | None] = mapped_column(Float)
    sleep_hours: Mapped[float | None] = mapped_column(Float)

    # Ergonomics layer
    viewing_distance_cm: Mapped[float | None] = mapped_column(Float)
    posture_score: Mapped[float | None] = mapped_column(Float)   # 0-1, 1 = good posture
    continuous_session_min: Mapped[float | None] = mapped_column(Float)

    source: Mapped[str] = mapped_column(String(64), default="manual")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    patient: Mapped[Patient] = relationship(back_populates="observations")

    __table_args__ = (
        UniqueConstraint("patient_id", "visit_date", name="uq_patient_visit"),
        UniqueConstraint("patient_id", "followup_month", name="uq_patient_followup"),
        Index("ix_obs_patient_date", "patient_id", "visit_date"),
    )


class TwinVersion(Base):
    """An immutable snapshot of the twin. A new row is written on every update."""

    __tablename__ = "twin_versions"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=_uuid)
    patient_id: Mapped[str] = mapped_column(
        ForeignKey("patients.patient_id", ondelete="CASCADE"), index=True
    )
    version: Mapped[int] = mapped_column(Integer)
    state_json: Mapped[dict] = mapped_column(JSON)
    triggered_by: Mapped[str] = mapped_column(String(64))  # observation|manual|retrain
    model_version: Mapped[str | None] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    patient: Mapped[Patient] = relationship(back_populates="twin_versions")

    __table_args__ = (UniqueConstraint("patient_id", "version", name="uq_patient_version"),)


class Prediction(Base):
    __tablename__ = "predictions"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=_uuid)
    patient_id: Mapped[str] = mapped_column(
        ForeignKey("patients.patient_id", ondelete="CASCADE"), index=True
    )
    twin_version: Mapped[int] = mapped_column(Integer)
    horizon_months: Mapped[int] = mapped_column(Integer)
    predicted_se: Mapped[float | None] = mapped_column(Float)
    predicted_se_lower: Mapped[float | None] = mapped_column(Float)
    predicted_se_upper: Mapped[float | None] = mapped_column(Float)
    predicted_al: Mapped[float | None] = mapped_column(Float)
    predicted_al_lower: Mapped[float | None] = mapped_column(Float)
    predicted_al_upper: Mapped[float | None] = mapped_column(Float)
    progression_risk: Mapped[float | None] = mapped_column(Float)
    risk_band: Mapped[str | None] = mapped_column(String(16))
    model_version: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Simulation(Base):
    __tablename__ = "simulations"

    simulation_id: Mapped[str] = mapped_column(String(64), primary_key=True, default=_uuid)
    patient_id: Mapped[str] = mapped_column(
        ForeignKey("patients.patient_id", ondelete="CASCADE"), index=True
    )
    baseline_twin_version: Mapped[int] = mapped_column(Integer)
    scenario_json: Mapped[dict] = mapped_column(JSON)
    results_json: Mapped[dict] = mapped_column(JSON)
    label: Mapped[str | None] = mapped_column(String(128))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Evidence(Base):
    __tablename__ = "evidence"

    evidence_id: Mapped[str] = mapped_column(String(64), primary_key=True, default=_uuid)
    query: Mapped[str] = mapped_column(String(512), index=True)
    source: Mapped[str] = mapped_column(String(32))  # europe_pmc|pubmed|local_corpus
    external_id: Mapped[str | None] = mapped_column(String(128))
    title: Mapped[str] = mapped_column(Text)
    abstract: Mapped[str | None] = mapped_column(Text)
    authors: Mapped[str | None] = mapped_column(Text)
    journal: Mapped[str | None] = mapped_column(String(256))
    year: Mapped[str | None] = mapped_column(String(16))
    doi: Mapped[str | None] = mapped_column(String(256))
    url: Mapped[str | None] = mapped_column(String(512))
    retrieved_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class AgentRun(Base):
    """Audit trail: every agent answer records which tools produced it."""

    __tablename__ = "agent_runs"

    run_id: Mapped[str] = mapped_column(String(64), primary_key=True, default=_uuid)
    patient_id: Mapped[str | None] = mapped_column(String(64), index=True)
    question: Mapped[str] = mapped_column(Text)
    plan_json: Mapped[dict] = mapped_column(JSON)
    trace_json: Mapped[dict] = mapped_column(JSON)
    answer: Mapped[str] = mapped_column(Text)
    llm_used: Mapped[str] = mapped_column(String(64), default="none")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Appointment(Base):
    """A clinic visit -- past or upcoming.

    A completed appointment can be linked to the Observation recorded at it, so
    the appointment history and the measurement history stay consistent.
    """

    __tablename__ = "appointments"

    appointment_id: Mapped[str] = mapped_column(String(64), primary_key=True, default=_uuid)
    user_id: Mapped[str] = mapped_column(
        ForeignKey("users.user_id", ondelete="CASCADE"), index=True)
    patient_id: Mapped[str | None] = mapped_column(String(64), index=True)
    observation_id: Mapped[str | None] = mapped_column(String(64))

    scheduled_for: Mapped[date] = mapped_column(Date, index=True)
    time_label: Mapped[str | None] = mapped_column(String(32))     # "10:30 AM"
    clinic: Mapped[str | None] = mapped_column(String(160))
    practitioner: Mapped[str | None] = mapped_column(String(160))
    reason: Mapped[str | None] = mapped_column(String(200))
    status: Mapped[str] = mapped_column(String(24), default="scheduled")
    notes: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    user: Mapped[User] = relationship(back_populates="appointments")

    __table_args__ = (Index("ix_appt_user_date", "user_id", "scheduled_for"),)


class Attachment(Base):
    """A file a user attached to their record -- a prescription photo, a scan report.

    The bytes live on disk under artifacts/uploads/<user_id>/; this row holds the
    metadata and the ownership link. `observation_id` optionally ties the file to
    the specific eye test it documents.
    """

    __tablename__ = "attachments"

    attachment_id: Mapped[str] = mapped_column(String(64), primary_key=True, default=_uuid)
    user_id: Mapped[str] = mapped_column(
        ForeignKey("users.user_id", ondelete="CASCADE"), index=True)
    patient_id: Mapped[str | None] = mapped_column(String(64), index=True)
    observation_id: Mapped[str | None] = mapped_column(String(64), index=True)

    filename: Mapped[str] = mapped_column(String(255))
    content_type: Mapped[str] = mapped_column(String(80))
    kind: Mapped[str] = mapped_column(String(32), default="prescription")
    size_bytes: Mapped[int] = mapped_column(Integer)
    stored_path: Mapped[str] = mapped_column(String(1024))
    note: Mapped[str | None] = mapped_column(Text)
    taken_on: Mapped[date | None] = mapped_column(Date)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
