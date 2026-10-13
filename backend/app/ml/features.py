"""Feature engineering.

ONE builder is used by training, live prediction and the counterfactual
simulator. If these ever diverge, the what-if results become meaningless, so
everything funnels through `build_feature_row`.

Missing values are kept as NaN. HistGradientBoosting handles NaN natively, which
lets us honour the project rule: never invent a clinical or behavioural value.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import date
from typing import Any, Iterable, Sequence

import numpy as np

# --- Feature groups (used for the ablation study) --------------------------
CLINICAL_FEATURES: list[str] = [
    "age",
    "sex_male",
    "parental_myopia",
    "se",
    "al",
    "visual_acuity",
    "corneal_curvature",
    "al_se_ratio",
    "se_slope_per_year",
    "al_slope_per_year",
    "delta_se_last",
    "delta_al_last",
    "months_since_last_visit",
    "n_visits",
    "months_since_baseline",
    "se_since_baseline",
    "al_since_baseline",
    "treatment_active",
    "treatment_atropine",
    "treatment_optical",
]

BEHAVIOUR_FEATURES: list[str] = [
    "screen_time_hours",
    "near_work_min",
    "outdoor_min",
    "sleep_hours",
    "screen_time_mean_3",
    "outdoor_mean_3",
    "delta_outdoor_min",
    "near_to_outdoor_ratio",
]

ERGONOMIC_FEATURES: list[str] = [
    "viewing_distance_cm",
    "posture_score",
    "continuous_session_min",
    "viewing_distance_mean_3",
    "ergonomic_load",
]

ALL_FEATURES: list[str] = CLINICAL_FEATURES + BEHAVIOUR_FEATURES + ERGONOMIC_FEATURES

FEATURE_SETS: dict[str, list[str]] = {
    "clinical": CLINICAL_FEATURES,
    "clinical_behaviour": CLINICAL_FEATURES + BEHAVIOUR_FEATURES,
    "full": ALL_FEATURES,
}

# Human-readable labels for the explanation UI.
FEATURE_LABELS: dict[str, str] = {
    "age": "Age (years)",
    "sex_male": "Sex (male)",
    "parental_myopia": "Number of myopic parents",
    "se": "Current spherical equivalent",
    "al": "Current axial length",
    "visual_acuity": "Visual acuity (logMAR)",
    "corneal_curvature": "Corneal curvature",
    "al_se_ratio": "Axial length / corneal ratio proxy",
    "se_slope_per_year": "Recent SE trend (D/year)",
    "al_slope_per_year": "Recent AL growth rate (mm/year)",
    "delta_se_last": "SE change since last visit",
    "delta_al_last": "AL change since last visit",
    "months_since_last_visit": "Months since last visit",
    "n_visits": "Number of recorded visits",
    "months_since_baseline": "Months since first visit",
    "se_since_baseline": "Total SE change since baseline",
    "al_since_baseline": "Total AL change since baseline",
    "treatment_active": "Any myopia-control treatment",
    "treatment_atropine": "Atropine treatment",
    "treatment_optical": "Optical treatment (ortho-k / DIMS)",
    "screen_time_hours": "Screen time (h/day)",
    "near_work_min": "Near work (min/day)",
    "outdoor_min": "Outdoor time (min/day)",
    "sleep_hours": "Sleep (h/night)",
    "screen_time_mean_3": "Screen time, recent average",
    "outdoor_mean_3": "Outdoor time, recent average",
    "delta_outdoor_min": "Change in outdoor time",
    "near_to_outdoor_ratio": "Near-work to outdoor ratio",
    "viewing_distance_cm": "Viewing distance (cm)",
    "posture_score": "Posture score (0-1)",
    "continuous_session_min": "Continuous near-work session (min)",
    "viewing_distance_mean_3": "Viewing distance, recent average",
    "ergonomic_load": "Composite ergonomic load",
}

# Inputs a user is allowed to change in a what-if scenario, with the plausible
# range the constraint layer enforces.
MODIFIABLE_INPUTS: dict[str, dict[str, Any]] = {
    "screen_time_hours": {"min": 0.0, "max": 16.0, "step": 0.5, "unit": "h/day",
                          "label": "Screen time"},
    "near_work_min": {"min": 0.0, "max": 720.0, "step": 15.0, "unit": "min/day",
                      "label": "Near work"},
    "outdoor_min": {"min": 0.0, "max": 480.0, "step": 15.0, "unit": "min/day",
                    "label": "Outdoor time"},
    "sleep_hours": {"min": 3.0, "max": 12.0, "step": 0.5, "unit": "h/night",
                    "label": "Sleep"},
    "viewing_distance_cm": {"min": 10.0, "max": 80.0, "step": 1.0, "unit": "cm",
                            "label": "Viewing distance"},
    "posture_score": {"min": 0.0, "max": 1.0, "step": 0.05, "unit": "score",
                      "label": "Posture score"},
    "continuous_session_min": {"min": 5.0, "max": 240.0, "step": 5.0, "unit": "min",
                               "label": "Continuous session length"},
    "treatment": {"choices": ["none", "atropine", "ortho_k", "dims", "single_vision"],
                  "label": "Treatment"},
}

OPTICAL_TREATMENTS = {"ortho_k", "dims", "mist", "defocus", "misight"}


@dataclass
class VisitRecord:
    """Framework-agnostic view of one visit, so training (DataFrame rows) and the
    API (ORM rows) can share the same feature code."""

    visit_date: date | float
    age: float | None = None
    spherical_equivalent: float | None = None
    axial_length: float | None = None
    visual_acuity: float | None = None
    corneal_curvature: float | None = None
    treatment: str | None = None
    screen_time_hours: float | None = None
    near_work_min: float | None = None
    outdoor_min: float | None = None
    sleep_hours: float | None = None
    viewing_distance_cm: float | None = None
    posture_score: float | None = None
    continuous_session_min: float | None = None

    @classmethod
    def from_any(cls, obj: Any) -> "VisitRecord":
        get = (lambda k: obj.get(k)) if isinstance(obj, dict) else (lambda k: getattr(obj, k, None))
        vd = get("visit_date")
        if vd is None or (isinstance(vd, float) and math.isnan(vd)):
            vd = _f(get("followup_month"))
            if vd is None:
                raise ValueError("A calendar date or measured follow-up month is required")
        if isinstance(vd, str):
            vd = date.fromisoformat(vd)
        return cls(
            visit_date=vd,
            age=_f(get("age")),
            spherical_equivalent=_f(get("spherical_equivalent")),
            axial_length=_f(get("axial_length")),
            visual_acuity=_f(get("visual_acuity")),
            corneal_curvature=_f(get("corneal_curvature")),
            treatment=get("treatment"),
            screen_time_hours=_f(get("screen_time_hours")),
            near_work_min=_f(get("near_work_min")),
            outdoor_min=_f(get("outdoor_min")),
            sleep_hours=_f(get("sleep_hours")),
            viewing_distance_cm=_f(get("viewing_distance_cm")),
            posture_score=_f(get("posture_score")),
            continuous_session_min=_f(get("continuous_session_min")),
        )


def _f(v: Any) -> float | None:
    if v is None:
        return None
    try:
        fv = float(v)
    except (TypeError, ValueError):
        return None
    return None if math.isnan(fv) else fv


NAN = float("nan")


def _months_between(a: date, b: date) -> float:
    if isinstance(a, (int, float)) and isinstance(b, (int, float)):
        return float(b - a)
    return (b - a).days / 30.4375


def _slope_per_year(points: Sequence[tuple[float, float]]) -> float:
    """Least-squares slope over (months, value) pairs; NaN if under-determined."""
    pts = [(m, v) for m, v in points if v is not None and not math.isnan(v)]
    if len(pts) < 2:
        return NAN
    xs = np.array([p[0] for p in pts], dtype=float)
    ys = np.array([p[1] for p in pts], dtype=float)
    if float(np.ptp(xs)) < 1e-6:
        return NAN
    slope_per_month = float(np.polyfit(xs, ys, 1)[0])
    return slope_per_month * 12.0


def _mean_last(values: Iterable[float | None], n: int) -> float:
    vals = [v for v in values if v is not None and not math.isnan(v)][-n:]
    return float(np.mean(vals)) if vals else NAN


def build_feature_row(
    history: Sequence[Any],
    *,
    sex: str | None = None,
    parental_myopia: int | None = None,
    overrides: dict[str, Any] | None = None,
) -> dict[str, float]:
    """Build the model input from a patient's visit history.

    `history` is ordered oldest -> newest; the last entry is the current state.
    `overrides` applies what-if changes to the CURRENT visit only (the simulator
    uses this, so the counterfactual differs from baseline in exactly the fields
    the user changed).
    """
    visits = [VisitRecord.from_any(v) for v in history]
    visits.sort(key=lambda v: v.visit_date)
    if not visits:
        raise ValueError("Cannot build features from an empty history.")

    current = visits[-1]
    if overrides:
        current = VisitRecord(**{**current.__dict__})
        for key, value in overrides.items():
            if key == "treatment":
                current.treatment = value
            elif hasattr(current, key):
                setattr(current, key, _f(value))

    baseline = visits[0]
    prev = visits[-2] if len(visits) > 1 else None
    months = [_months_between(baseline.visit_date, v.visit_date) for v in visits]

    treatment = current.treatment.lower() if isinstance(current.treatment, str) else None
    row: dict[str, float] = {
        # --- clinical ---
        "age": current.age if current.age is not None else NAN,
        "sex_male": 1.0 if (sex or "").lower() in {"m", "male"} else
                    (0.0 if sex else NAN),
        "parental_myopia": float(parental_myopia) if parental_myopia is not None else NAN,
        "se": current.spherical_equivalent if current.spherical_equivalent is not None else NAN,
        "al": current.axial_length if current.axial_length is not None else NAN,
        "visual_acuity": current.visual_acuity if current.visual_acuity is not None else NAN,
        "corneal_curvature": current.corneal_curvature
        if current.corneal_curvature is not None else NAN,
        "al_se_ratio": (current.axial_length / current.corneal_curvature)
        if current.axial_length and current.corneal_curvature else NAN,
        "se_slope_per_year": _slope_per_year(
            list(zip(months, [v.spherical_equivalent for v in visits]))[-4:]
        ),
        "al_slope_per_year": _slope_per_year(
            list(zip(months, [v.axial_length for v in visits]))[-4:]
        ),
        "delta_se_last": (current.spherical_equivalent - prev.spherical_equivalent)
        if prev and current.spherical_equivalent is not None
        and prev.spherical_equivalent is not None else NAN,
        "delta_al_last": (current.axial_length - prev.axial_length)
        if prev and current.axial_length is not None and prev.axial_length is not None else NAN,
        "months_since_last_visit": _months_between(prev.visit_date, current.visit_date)
        if prev else NAN,
        "n_visits": float(len(visits)),
        "months_since_baseline": _months_between(baseline.visit_date, current.visit_date),
        "se_since_baseline": (current.spherical_equivalent - baseline.spherical_equivalent)
        if current.spherical_equivalent is not None
        and baseline.spherical_equivalent is not None else NAN,
        "al_since_baseline": (current.axial_length - baseline.axial_length)
        if current.axial_length is not None and baseline.axial_length is not None else NAN,
        "treatment_active": NAN if treatment is None else (0.0 if treatment in {"none", "single_vision", ""} else 1.0),
        "treatment_atropine": NAN if treatment is None else float("atropine" in treatment),
        "treatment_optical": NAN if treatment is None else float(treatment in OPTICAL_TREATMENTS),
        # --- behaviour ---
        "screen_time_hours": current.screen_time_hours
        if current.screen_time_hours is not None else NAN,
        "near_work_min": current.near_work_min if current.near_work_min is not None else NAN,
        "outdoor_min": current.outdoor_min if current.outdoor_min is not None else NAN,
        "sleep_hours": current.sleep_hours if current.sleep_hours is not None else NAN,
        "screen_time_mean_3": _mean_last(
            [v.screen_time_hours for v in visits[:-1]] + [current.screen_time_hours], 3
        ),
        "outdoor_mean_3": _mean_last(
            [v.outdoor_min for v in visits[:-1]] + [current.outdoor_min], 3
        ),
        "delta_outdoor_min": (current.outdoor_min - prev.outdoor_min)
        if prev and current.outdoor_min is not None and prev.outdoor_min is not None else NAN,
        "near_to_outdoor_ratio": (current.near_work_min / max(current.outdoor_min, 1.0))
        if current.near_work_min is not None and current.outdoor_min is not None else NAN,
        # --- ergonomics ---
        "viewing_distance_cm": current.viewing_distance_cm
        if current.viewing_distance_cm is not None else NAN,
        "posture_score": current.posture_score if current.posture_score is not None else NAN,
        "continuous_session_min": current.continuous_session_min
        if current.continuous_session_min is not None else NAN,
        "viewing_distance_mean_3": _mean_last(
            [v.viewing_distance_cm for v in visits[:-1]] + [current.viewing_distance_cm], 3
        ),
        "ergonomic_load": _ergonomic_load(current),
    }
    return row


def _ergonomic_load(v: VisitRecord) -> float:
    """Composite exposure index: closer working distance, longer unbroken sessions
    and poorer posture all increase load. Descriptive only -- not a clinical score."""
    if any(x is None for x in (v.viewing_distance_cm, v.continuous_session_min, v.posture_score)):
        return NAN
    dist = v.viewing_distance_cm if v.viewing_distance_cm else 33.0
    session = v.continuous_session_min if v.continuous_session_min is not None else 30.0
    posture = v.posture_score if v.posture_score is not None else 0.7
    dioptric_demand = 100.0 / max(dist, 5.0)          # dioptres of accommodation
    return float(dioptric_demand * (session / 60.0) * (1.5 - posture))


def row_to_vector(row: dict[str, float], feature_names: Sequence[str]) -> np.ndarray:
    return np.array([[row.get(name, NAN) for name in feature_names]], dtype=float)
