"""Account, profile, appointment and quick-simulator schemas."""
from __future__ import annotations

from datetime import date, datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field


class SignupIn(BaseModel):
    model_config = ConfigDict(json_schema_extra={"example": {
        "email": "riya@example.com", "password": "seeclearly2026",
        "full_name": "Riya S", "age": 12.5, "sex": "female", "parental_myopia": 1,
    }})

    email: EmailStr
    password: str = Field(..., min_length=12, max_length=128)
    full_name: str = Field(..., min_length=1, max_length=120)
    # Optional profile details, used to start the person's eye record.
    age: float | None = Field(None, ge=0, le=120)
    sex: Literal["male", "female", "other", "unknown"] | None = None
    parental_myopia: int | None = Field(None, ge=0, le=2)


class LoginIn(BaseModel):
    model_config = ConfigDict(json_schema_extra={"example": {
        "email": "demo@iiris.health", "password": "irisdemo2026"}})
    email: EmailStr
    password: str


class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int
    user: "UserOut"


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    user_id: str
    email: str
    full_name: str
    role: Literal["patient", "clinician", "admin"] = "patient"
    created_at: datetime | None = None
    last_login_at: datetime | None = None
    patient_id: str | None = None
    n_visits: int = 0
    twin_version: int = 0
    has_record: bool = False


class ProfileUpdate(BaseModel):
    full_name: str | None = Field(None, min_length=1, max_length=120)
    age: float | None = Field(None, ge=0, le=120)
    sex: Literal["male", "female", "other", "unknown"] | None = None
    parental_myopia: int | None = Field(None, ge=0, le=2)
    ethnicity: str | None = Field(None, max_length=64)


class PasswordChange(BaseModel):
    current_password: str
    new_password: str = Field(..., min_length=12, max_length=128)


class AppointmentIn(BaseModel):
    model_config = ConfigDict(json_schema_extra={"example": {
        "scheduled_for": "2026-11-14", "time_label": "10:30 AM",
        "clinic": "City Eye Centre", "practitioner": "Dr Menon",
        "reason": "6-month myopia review", "status": "scheduled",
    }})

    scheduled_for: date
    time_label: str | None = Field(None, max_length=32)
    clinic: str | None = Field(None, max_length=160)
    practitioner: str | None = Field(None, max_length=160)
    reason: str | None = Field(None, max_length=200)
    status: Literal["scheduled", "completed", "cancelled"] = "scheduled"
    notes: str | None = None
    observation_id: str | None = None


class AppointmentOut(AppointmentIn):
    model_config = ConfigDict(from_attributes=True)
    appointment_id: str
    created_at: datetime | None = None
    is_past: bool = False


class QuickSimulationIn(BaseModel):
    """Values typed into the public simulator. Only age + SE are required."""

    model_config = ConfigDict(json_schema_extra={"example": {
        "age": 10, "spherical_equivalent": -1.5, "axial_length": 23.9,
        "sex": "female", "parental_myopia": 1,
        "screen_time_hours": 6, "near_work_min": 240, "outdoor_min": 30,
        "viewing_distance_cm": 25, "posture_score": 0.5,
        "continuous_session_min": 90, "years": 5,
    }})

    age: float = Field(..., ge=3, le=30)
    spherical_equivalent: float = Field(..., ge=-30, le=15,
                                        description="Dioptres, negative for myopia.")
    axial_length: float | None = Field(
        None, ge=15, le=35,
        description="Millimetres. A human eye is roughly 20-30 mm.")
    visual_acuity: float | None = Field(None, ge=-0.3, le=2.0)
    corneal_curvature: float | None = Field(None, ge=5, le=12)
    sex: Literal["male", "female", "other", "unknown"] | None = None
    parental_myopia: int | None = Field(None, ge=0, le=2)
    treatment: str | None = None

    # Bounds match GET /simulator/inputs, so the form and the API agree and a
    # value the UI accepts can never be rejected by the server.
    screen_time_hours: float | None = Field(None, ge=0, le=16)
    near_work_min: float | None = Field(None, ge=0, le=720)
    outdoor_min: float | None = Field(None, ge=0, le=480)
    sleep_hours: float | None = Field(None, ge=3, le=14)
    viewing_distance_cm: float | None = Field(None, ge=10, le=80)
    posture_score: float | None = Field(None, ge=0, le=1)
    continuous_session_min: float | None = Field(None, ge=5, le=240)

    years: int = Field(5, ge=1, le=8)
    # Optional second scenario, compared side by side with the values above.
    compare_with: dict[str, Any] | None = Field(
        None, description="Changed exposures for a comparison scenario, "
                          "e.g. {\"outdoor_min\": 120, \"screen_time_hours\": 2}")




class ProjectionIn(BaseModel):
    """Projection for the signed-in user's own record."""
    years: int = Field(5, ge=1, le=8)
    changes: dict[str, Any] | None = None
