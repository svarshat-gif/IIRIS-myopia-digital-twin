"""The Digital Twin itself: build state, version it, predict from it.

A twin is not a model call. It is a persistent, versioned representation of one
patient -- history, current state, derived trend, prediction with uncertainty and
provenance -- that is rebuilt and re-stored every time a new observation arrives.
"""
from __future__ import annotations

from datetime import date
from typing import Any, Sequence

import math

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.models import Observation, Patient, Prediction, TwinVersion
from app.ml import registry
from app.ml.features import (
    BEHAVIOUR_FEATURES,
    CLINICAL_FEATURES,
    ERGONOMIC_FEATURES,
    build_feature_row,
)

BEHAVIOUR_FIELDS = ["screen_time_hours", "near_work_min", "outdoor_min", "sleep_hours"]
ERGONOMIC_FIELDS = ["viewing_distance_cm", "posture_score", "continuous_session_min"]
CLINICAL_FIELDS = ["spherical_equivalent", "axial_length", "visual_acuity", "corneal_curvature"]


def elapsed_months(a: Observation, b: Observation) -> float:
    if a.visit_date is not None and b.visit_date is not None:
        return (b.visit_date - a.visit_date).days / 30.4375
    if a.followup_month is not None and b.followup_month is not None:
        return b.followup_month - a.followup_month
    raise ValueError("Cannot mix calendar dates and relative follow-up for one patient")


def _clean(value: Any) -> Any:
    """JSON cannot hold NaN; missing stays missing as null."""
    if isinstance(value, float) and (math.isnan(value) or math.isinf(value)):
        return None
    return value


def get_patient(db: Session, patient_id: str) -> Patient | None:
    return db.get(Patient, patient_id)


def get_observations(db: Session, patient_id: str,
                     as_of: date | None = None) -> list[Observation]:
    stmt = select(Observation).where(Observation.patient_id == patient_id)
    if as_of is not None:
        stmt = stmt.where(Observation.visit_date <= as_of)
    return list(db.scalars(stmt.order_by(Observation.visit_date, Observation.followup_month)))


def _observation_dict(obs: Observation) -> dict[str, Any]:
    return {
        "observation_id": obs.observation_id,
        "visit_date": obs.visit_date.isoformat() if obs.visit_date else None,
        "followup_month": obs.followup_month,
        "age": _clean(obs.age),
        "spherical_equivalent": _clean(obs.spherical_equivalent),
        "axial_length": _clean(obs.axial_length),
        "visual_acuity": _clean(obs.visual_acuity),
        "corneal_curvature": _clean(obs.corneal_curvature),
        "treatment": obs.treatment,
        "screen_time_hours": _clean(obs.screen_time_hours),
        "near_work_min": _clean(obs.near_work_min),
        "outdoor_min": _clean(obs.outdoor_min),
        "sleep_hours": _clean(obs.sleep_hours),
        "viewing_distance_cm": _clean(obs.viewing_distance_cm),
        "posture_score": _clean(obs.posture_score),
        "continuous_session_min": _clean(obs.continuous_session_min),
        "source": obs.source,
    }


def _completeness(observations: Sequence[Observation], fields: list[str]) -> float:
    if not observations:
        return 0.0
    total = len(observations) * len(fields)
    present = sum(
        1 for o in observations for f in fields if getattr(o, f, None) is not None
    )
    return round(present / total, 3) if total else 0.0


def build_state(db: Session, patient: Patient,
                observations: Sequence[Observation] | None = None,
                *, with_prediction: bool = True) -> dict[str, Any]:
    """Assemble the full twin state for a patient at their latest observation."""
    obs = list(observations) if observations is not None else get_observations(
        db, patient.patient_id)
    if not obs:
        raise ValueError("Patient has no observations; the twin cannot be built yet.")

    history = [_observation_dict(o) for o in obs]
    current = history[-1]
    row = build_feature_row(obs, sex=patient.sex, parental_myopia=patient.parental_myopia)
    features = {k: _clean(v) for k, v in row.items()}

    state: dict[str, Any] = {
        "patient": {
            "patient_id": patient.patient_id,
            "external_key": patient.external_key,
            "age_at_start": patient.age_at_start,
            "sex": patient.sex,
            "ethnicity": patient.ethnicity,
            "parental_myopia": patient.parental_myopia,
            "consent_status": patient.consent_status,
            "data_source": patient.data_source,
        },
        "current": {
            "visit_date": current["visit_date"],
            "followup_month": current.get("followup_month"),
            "age": current["age"],
            "spherical_equivalent": current["spherical_equivalent"],
            "axial_length": current["axial_length"],
            "visual_acuity": current["visual_acuity"],
            "treatment": current["treatment"],
            "behaviour": {f: current[f] for f in BEHAVIOUR_FIELDS},
            "ergonomics": {f: current[f] for f in ERGONOMIC_FIELDS},
        },
        "history": history,
        "derived": {
            "n_visits": len(obs),
            "first_visit": history[0]["visit_date"],
            "latest_visit": current["visit_date"],
            "months_since_baseline": features.get("months_since_baseline"),
            "se_slope_per_year": features.get("se_slope_per_year"),
            "al_slope_per_year": features.get("al_slope_per_year"),
            "se_since_baseline": features.get("se_since_baseline"),
            "al_since_baseline": features.get("al_since_baseline"),
            "ergonomic_load": features.get("ergonomic_load"),
        },
        "data_completeness": {
            "clinical": _completeness(obs, CLINICAL_FIELDS),
            "behaviour": _completeness(obs, BEHAVIOUR_FIELDS),
            "ergonomics": _completeness(obs, ERGONOMIC_FIELDS),
        },
        "features": features,
        "feature_groups": {
            "clinical": CLINICAL_FEATURES,
            "behaviour": BEHAVIOUR_FEATURES,
            "ergonomics": ERGONOMIC_FEATURES,
        },
        "model_version": registry.model_version(),
        "disclaimer": settings.disclaimer,
    }

    if with_prediction and registry.is_ready():
        state["prediction"] = predict_from_state(row)
    else:
        state["prediction"] = None
    return state


def predict_from_state(feature_row: dict[str, float], horizon_months: int | None = None) -> dict[str, Any]:
    if horizon_months is not None:
        from app.ml.trajectory import forecast
        return {**forecast(feature_row, horizon_months), 'disclaimer': settings.disclaimer}
    result = registry.predict_from_row(feature_row)
    return {
        "horizons": result["horizons"],
        "risk": result["risk"],
        "model_version": result["model_version"],
        "warnings": result.get("warnings", []),
        "data_source": result.get("data_source"),
        "risk_unavailable_reason": result.get("risk_unavailable_reason"),
        "disclaimer": settings.disclaimer,
    }


def latest_version_number(db: Session, patient_id: str) -> int:
    value = db.scalar(
        select(func.max(TwinVersion.version)).where(TwinVersion.patient_id == patient_id)
    )
    return int(value or 0)


def save_version(db: Session, patient: Patient, state: dict[str, Any],
                 triggered_by: str) -> TwinVersion:
    """Persist an immutable snapshot and its predictions. Never mutates old rows."""
    version = latest_version_number(db, patient.patient_id) + 1
    state = {**state, "version": version, "triggered_by": triggered_by}

    tv = TwinVersion(
        patient_id=patient.patient_id,
        version=version,
        state_json=state,
        triggered_by=triggered_by,
        model_version=state.get("model_version"),
    )
    db.add(tv)

    prediction = state.get("prediction")
    if prediction:
        for key, entry in prediction["horizons"].items():
            se = entry.get("se") or {}
            al = entry.get("al") or {}
            risk = prediction.get("risk") or {}
            db.add(Prediction(
                patient_id=patient.patient_id,
                twin_version=version,
                horizon_months=entry["horizon_months"],
                predicted_se=se.get("value"),
                predicted_se_lower=se.get("lower"),
                predicted_se_upper=se.get("upper"),
                predicted_al=al.get("value"),
                predicted_al_lower=al.get("lower"),
                predicted_al_upper=al.get("upper"),
                progression_risk=risk.get("probability"),
                risk_band=risk.get("band"),
                model_version=prediction["model_version"],
            ))
    db.flush()
    prior = get_version(db, patient.patient_id, version - 1) if version > 1 else None
    flag = compare_versions(db, patient.patient_id, version - 1, version) if prior else {
        "materially_changed": False, "flags": [], "note": "Baseline version; nothing to compare"}
    tv.state_json = {**state, "monitor": flag}
    db.flush()
    return tv


def refresh_twin(db: Session, patient: Patient, triggered_by: str) -> dict[str, Any]:
    """Rebuild the twin from all observations and store it as a new version."""
    db.execute(select(Patient).where(Patient.patient_id == patient.patient_id).with_for_update())
    observations = get_observations(db, patient.patient_id)
    if any(o.visit_date is None for o in observations) and any(o.visit_date is not None for o in observations):
        raise ValueError("Use source-recorded followup_month for this research record; calendar dates are unknown")
    state = build_state(db, patient, observations)
    tv = save_version(db, patient, state, triggered_by)
    db.commit()
    return {**tv.state_json, "created_at": tv.created_at.isoformat()}


def get_current_version(db: Session, patient_id: str) -> TwinVersion | None:
    return db.scalars(
        select(TwinVersion)
        .where(TwinVersion.patient_id == patient_id)
        .order_by(TwinVersion.version.desc())
        .limit(1)
    ).first()


def get_version(db: Session, patient_id: str, version: int) -> TwinVersion | None:
    return db.scalars(
        select(TwinVersion).where(
            TwinVersion.patient_id == patient_id, TwinVersion.version == version)
    ).first()


def list_versions(db: Session, patient_id: str) -> list[TwinVersion]:
    return list(db.scalars(
        select(TwinVersion)
        .where(TwinVersion.patient_id == patient_id)
        .order_by(TwinVersion.version)
    ))


def compare_versions(db: Session, patient_id: str, a: int, b: int) -> dict[str, Any]:
    """What changed between two twin versions -- the Monitor agent's core tool."""
    va, vb = get_version(db, patient_id, a), get_version(db, patient_id, b)
    if va is None or vb is None:
        raise ValueError(f"Twin version {a if va is None else b} not found.")

    sa, sb = va.state_json, vb.state_json
    changes: list[dict[str, Any]] = []

    def _cmp(label: str, x: Any, y: Any, unit: str = "", tol: float = 1e-9) -> None:
        if x is None or y is None:
            if x != y:
                changes.append({"field": label, "from": x, "to": y, "delta": None, "unit": unit})
            return
        if isinstance(x, (int, float)) and isinstance(y, (int, float)):
            if abs(y - x) > tol:
                changes.append({"field": label, "from": round(float(x), 4),
                                "to": round(float(y), 4),
                                "delta": round(float(y) - float(x), 4), "unit": unit})
        elif x != y:
            changes.append({"field": label, "from": x, "to": y, "delta": None, "unit": unit})

    _cmp("spherical_equivalent", sa["current"]["spherical_equivalent"],
         sb["current"]["spherical_equivalent"], "D")
    _cmp("axial_length", sa["current"]["axial_length"], sb["current"]["axial_length"], "mm")
    _cmp("treatment", sa["current"].get("treatment"), sb["current"].get("treatment"))
    for f in BEHAVIOUR_FIELDS:
        _cmp(f, sa["current"]["behaviour"].get(f), sb["current"]["behaviour"].get(f))
    for f in ERGONOMIC_FIELDS:
        _cmp(f, sa["current"]["ergonomics"].get(f), sb["current"]["ergonomics"].get(f))

    pred_changes: list[dict[str, Any]] = []
    pa, pb = sa.get("prediction"), sb.get("prediction")
    if pa and pb:
        for key in pb["horizons"]:
            if key not in pa["horizons"]:
                continue
            for measure in ("se", "al"):
                x = (pa["horizons"][key].get(measure) or {}).get("value")
                y = (pb["horizons"][key].get(measure) or {}).get("value")
                if x is not None and y is not None:
                    pred_changes.append({
                        "field": f"predicted_{measure}_{key}",
                        "from": x, "to": y, "delta": round(y - x, 4),
                        "unit": "D" if measure == "se" else "mm",
                    })
        ra, rb = pa.get("risk"), pb.get("risk")
        if ra and rb:
            pred_changes.append({
                "field": "progression_risk", "from": ra["probability"],
                "to": rb["probability"],
                "delta": round(rb["probability"] - ra["probability"], 4),
                "unit": "probability", "band_from": ra["band"], "band_to": rb["band"],
            })

    material = _material_change(pred_changes)
    return {
        "patient_id": patient_id,
        "from_version": a,
        "to_version": b,
        "observed_changes": changes,
        "prediction_changes": pred_changes,
        "materially_changed": material["flag"],
        "flags": material["reasons"],
        "disclaimer": settings.disclaimer,
    }


# Thresholds at which a change is worth a clinician's attention. These are
# engineering defaults for the demo, not validated clinical alert thresholds.
MATERIAL_SE_DELTA = 0.25    # dioptres
MATERIAL_AL_DELTA = 0.10    # mm
MATERIAL_RISK_DELTA = 0.15  # absolute probability


def _material_change(pred_changes: list[dict[str, Any]]) -> dict[str, Any]:
    reasons: list[str] = []
    for c in pred_changes:
        d = c.get("delta")
        if d is None:
            continue
        if c["field"].startswith("predicted_se") and abs(d) >= MATERIAL_SE_DELTA:
            reasons.append(
                f"{c['field']} moved by {d:+.2f} D (threshold {MATERIAL_SE_DELTA} D)")
        if c["field"].startswith("predicted_al") and abs(d) >= MATERIAL_AL_DELTA:
            reasons.append(
                f"{c['field']} moved by {d:+.2f} mm (threshold {MATERIAL_AL_DELTA} mm)")
        if c["field"] == "progression_risk":
            if abs(d) >= MATERIAL_RISK_DELTA:
                reasons.append(f"progression risk moved by {d:+.2f}")
            if c.get("band_from") != c.get("band_to"):
                reasons.append(
                    f"risk band changed {c.get('band_from')} -> {c.get('band_to')}")
    return {"flag": bool(reasons), "reasons": reasons}
