"""Request/response models. FastAPI turns these into the OpenAPI schema that the
frontend and any external client program against."""
from __future__ import annotations

from datetime import date
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

Horizon = Literal["6m", "12m"]
ExplainTarget = Literal["se_6m", "se_12m", "al_6m", "al_12m"]


class PatientCreate(BaseModel):
    model_config = ConfigDict(json_schema_extra={"example": {
        "external_key": "SYN00042", "age_at_start": 9.5, "sex": "female",
        "parental_myopia": 1, "consent_status": "synthetic", "data_source": "synthetic",
    }})

    external_key: str | None = Field(
        None, max_length=128,
        description="De-identified study key. NEVER a name, MRN or contact detail.")
    age_at_start: float = Field(..., ge=0, le=30)
    sex: Literal["male", "female", "other", "unknown"] | None = None
    ethnicity: str | None = Field(None, max_length=64)
    parental_myopia: int | None = Field(None, ge=0, le=2,
                                        description="Number of myopic parents (0-2).")
    consent_status: str = Field("synthetic", max_length=32)
    data_source: str = Field("synthetic", max_length=64)
    notes: str | None = None


class PatientOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    patient_id: str
    external_key: str | None
    age_at_start: float
    sex: str | None
    ethnicity: str | None
    parental_myopia: int | None
    consent_status: str
    data_source: str
    created_at: Any = None


class PatientSummary(PatientOut):
    n_visits: int = 0
    latest_visit: date | None = None
    twin_version: int = 0
    latest_se: float | None = None
    latest_al: float | None = None
    risk_band: str | None = None


class ObservationIn(BaseModel):
    model_config = ConfigDict(json_schema_extra={"example": {
        "visit_date": "2026-09-01", "age": 10.5,
        "spherical_equivalent": -2.35, "axial_length": 24.31,
        "visual_acuity": 0.05, "treatment": "none",
        "screen_time_hours": 5.0, "near_work_min": 240, "outdoor_min": 45,
        "viewing_distance_cm": 28, "posture_score": 0.6,
        "continuous_session_min": 60,
    }})

    visit_date: date | None = None
    followup_month: float | None = Field(None, ge=0, le=600, description="Source-recorded months since baseline, when dates are unavailable")
    age: float | None = Field(None, ge=0, le=30)
    # Clinical
    spherical_equivalent: float = Field(..., ge=-30, le=15, description="Dioptres.")
    axial_length: float = Field(..., ge=15, le=35, description="Millimetres.")
    visual_acuity: float | None = Field(None, ge=-0.3, le=2.0, description="logMAR.")
    corneal_curvature: float | None = Field(None, ge=5, le=12)
    treatment: str | None = Field(None, max_length=64)
    # Behaviour -- leave null when not measured. Never fill these in with guesses.
    screen_time_hours: float | None = Field(None, ge=0, le=24)
    near_work_min: float | None = Field(None, ge=0, le=1440)
    outdoor_min: float | None = Field(None, ge=0, le=1440)
    sleep_hours: float | None = Field(None, ge=0, le=24)
    # Ergonomics
    viewing_distance_cm: float | None = Field(None, ge=5, le=200)
    posture_score: float | None = Field(None, ge=0, le=1)
    continuous_session_min: float | None = Field(None, ge=0, le=1440)
    source: str = Field("manual", max_length=64)

    @field_validator("visit_date")
    @classmethod
    def not_absurdly_future(cls, v: date) -> date:
        from datetime import timedelta
        if v is not None and v > date.today():
            raise ValueError("visit_date cannot be in the future.")
        return v

    @model_validator(mode="after")
    def has_time(self):
        if self.visit_date is None and self.followup_month is None:
            raise ValueError("Provide visit_date or source-recorded followup_month")
        return self


class ObservationOut(ObservationIn):
    model_config = ConfigDict(from_attributes=True)
    observation_id: str
    patient_id: str


class ObservationAccepted(BaseModel):
    """What POST /observations returns: the new twin version and its predictions."""
    patient_id: str
    observation_id: str
    twin_version: int
    previous_version: int | None
    twin: dict[str, Any]
    change_summary: dict[str, Any] | None = None
    disclaimer: str


class ScenarioIn(BaseModel):
    model_config = ConfigDict(json_schema_extra={"example": {
        "label": "More outdoor time, less screen",
        "changes": {"outdoor_min": 120, "screen_time_hours": 3,
                    "viewing_distance_cm": 40},
    }})

    label: str | None = Field(None, max_length=128)
    changes: dict[str, Any] = Field(
        ...,
        description="Modifiable inputs to change. GET /api/v1/meta/inputs lists them "
                    "with their plausible ranges.")


class MultiScenarioIn(BaseModel):
    scenarios: list[ScenarioIn]


class SensitivityIn(BaseModel):
    input_name: str
    values: list[float] = Field(..., min_length=2, max_length=25)
    horizon: Horizon = "12m"


class AgentQueryIn(BaseModel):
    model_config = ConfigDict(json_schema_extra={"example": {
        "question": "How does the predicted trajectory change if this child "
                    "spends 2 hours outdoors instead?",
    }})

    question: str = Field(..., min_length=3, max_length=1000)
    patient_id: str | None = None


class BulkVisitRow(ObservationIn):
    """One row of a bulk import. Carries the patient key so a whole cohort can be
    loaded in a single call."""
    external_key: str
    age_at_start: float | None = None
    sex: Literal["male", "female", "other", "unknown"] | None = None
    parental_myopia: int | None = Field(None, ge=0, le=2)


class BulkImportIn(BaseModel):
    rows: list[BulkVisitRow]
    data_source: str = "import"
    consent_status: str = "approved"
    rebuild_twins: bool = True


class HealthOut(BaseModel):
    data_source: str | None = None
    status: str
    api_version: str
    environment: str
    model_loaded: bool
    model_version: str
    data_is_synthetic: bool | None
    llm_provider: str
    evidence_offline: bool
    database: str
