"""Multi-year forward projection.

The trained models predict 6 and 12 months ahead. To show a longer horizon, the
twin is rolled forward autoregressively: predict 12 months, treat that predicted
state as a new (synthetic) visit, predict again, and so on.

BE HONEST ABOUT WHAT THIS COSTS
-------------------------------
Every step after the first is a prediction made from a prediction. Errors
compound, and the model was never trained on its own output. So:

  * uncertainty is widened at each step by combining the per-step interval in
    quadrature (independent-ish errors), which is why the band flares out;
  * `confidence` degrades explicitly per year and is returned to the caller;
  * beyond ~3 years the projection is labelled `indicative` and the UI is
    expected to present it as a shape, not a number.

A projection is a scenario-planning aid. It is not a forecast a clinical
decision should rest on.
"""
from __future__ import annotations

from datetime import date, timedelta
from typing import Any

import numpy as np

from app.core.config import settings
from app.ml import registry
from app.ml.features import build_feature_row

STEP_MONTHS = 12
MAX_YEARS = 8

# Beyond this many rollout steps we stop claiming a usable number.
RELIABLE_STEPS = 3

PROJECTION_DISCLAIMER = (
    "Years beyond the first are produced by feeding the model its own prediction "
    "back in as a new visit. Errors accumulate, so the band widens and the later "
    "years indicate a direction of travel rather than an expected value."
)


def _confidence_label(step: int) -> str:
    if step <= 1:
        return "modelled"
    if step <= RELIABLE_STEPS:
        return "projected"
    return "indicative"


def project(
    history: list[dict[str, Any]],
    *,
    sex: str | None = None,
    parental_myopia: int | None = None,
    years: int = 5,
    overrides: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Roll the twin forward `years` years in 12-month steps.

    `history` is the patient's real visits (oldest first). `overrides` applies a
    sustained behaviour change from now on, which is what makes the scenario
    comparison meaningful over a long horizon.
    """
    if not registry.is_ready():
        raise RuntimeError("No trained model is loaded.")
    years = max(1, min(int(years), MAX_YEARS))

    working = [dict(v) for v in history]
    last = working[-1]
    current_date = date.fromisoformat(str(last["visit_date"]))
    current_age = last.get("age")

    points: list[dict[str, Any]] = []
    # Interval half-widths accumulate in quadrature across rollout steps.
    se_var = 0.0
    al_var = 0.0

    for step in range(1, years + 1):
        row = build_feature_row(working, sex=sex, parental_myopia=parental_myopia,
                                overrides=overrides if step == 1 else None)
        prediction = registry.predict_from_row(row)
        entry = prediction["horizons"].get(f"{STEP_MONTHS}m")
        if not entry or not entry.get("se") or not entry.get("al"):
            break

        se, al = entry["se"], entry["al"]
        se_var += ((se["upper"] - se["lower"]) / 2.0) ** 2
        al_var += ((al["upper"] - al["lower"]) / 2.0) ** 2
        se_half = float(np.sqrt(se_var))
        al_half = float(np.sqrt(al_var))

        current_date = current_date + timedelta(days=int(STEP_MONTHS * 30.4375))
        if current_age is not None:
            current_age = round(current_age + STEP_MONTHS / 12.0, 2)

        points.append({
            "step": step,
            "years_ahead": step,
            "date": current_date.isoformat(),
            "age": current_age,
            "spherical_equivalent": round(se["value"], 3),
            "se_lower": round(se["value"] - se_half, 3),
            "se_upper": round(se["value"] + se_half, 3),
            "axial_length": round(al["value"], 3),
            "al_lower": round(al["value"] - al_half, 3),
            "al_upper": round(al["value"] + al_half, 3),
            "risk": (prediction.get("risk") or {}).get("probability"),
            "confidence": _confidence_label(step),
        })

        # The predicted state becomes the next step's "visit". Exposures are
        # carried forward unchanged (with any sustained override applied), which
        # is the assumption being modelled: nothing else about the child changes.
        next_visit = {
            **last,
            **(overrides or {}),
            "visit_date": current_date.isoformat(),
            "age": current_age,
            "spherical_equivalent": se["value"],
            "axial_length": al["value"],
        }
        working = working + [next_visit]
        last = next_visit

    baseline_se = history[-1].get("spherical_equivalent")
    baseline_al = history[-1].get("axial_length")
    final = points[-1] if points else None

    return {
        "points": points,
        "start": {
            "date": str(history[-1]["visit_date"]),
            "spherical_equivalent": baseline_se,
            "axial_length": baseline_al,
            "age": history[-1].get("age"),
        },
        "summary": None if not final else {
            "years": final["years_ahead"],
            "final_se": final["spherical_equivalent"],
            "final_al": final["axial_length"],
            "total_se_change": round(final["spherical_equivalent"] - baseline_se, 3)
            if baseline_se is not None else None,
            "total_al_change": round(final["axial_length"] - baseline_al, 3)
            if baseline_al is not None else None,
            "mean_annual_se_change": round(
                (final["spherical_equivalent"] - baseline_se) / final["years_ahead"], 3)
            if baseline_se is not None else None,
            "category": categorise(final["spherical_equivalent"]),
            "reliable_through_year": RELIABLE_STEPS,
        },
        "model_version": registry.model_version(),
        "projection_disclaimer": PROJECTION_DISCLAIMER,
        "disclaimer": settings.disclaimer,
    }


# Conventional descriptive bands for refractive error. Descriptive only -- these
# are not diagnostic thresholds and carry no treatment implication.
def categorise(se: float | None) -> dict[str, Any]:
    if se is None:
        return {"label": "unknown", "description": "No refraction value available."}
    if se > -0.50:
        return {"label": "No myopia",
                "description": "Spherical equivalent above -0.50 D."}
    if se > -3.00:
        return {"label": "Low myopia",
                "description": "Between -0.50 D and -3.00 D."}
    if se > -6.00:
        return {"label": "Moderate myopia",
                "description": "Between -3.00 D and -6.00 D."}
    return {"label": "High myopia",
            "description": "-6.00 D or more. Associated in the literature with higher "
                           "long-term risk of ocular complications; a clinician should "
                           "advise on monitoring."}


def quick_project(payload: dict[str, Any], years: int = 5) -> dict[str, Any]:
    """Projection from typed-in values, with no stored patient.

    Powers the public simulator: someone enters what they know and sees a
    modelled trajectory. With a single visit there is no measured trend, so the
    model leans on age, refraction, biometry and exposures -- the response says so.
    """
    visit_date = payload.get("visit_date") or date.today().isoformat()
    visit = {
        "visit_date": visit_date,
        "age": payload.get("age"),
        "spherical_equivalent": payload.get("spherical_equivalent"),
        "axial_length": payload.get("axial_length"),
        "visual_acuity": payload.get("visual_acuity"),
        "corneal_curvature": payload.get("corneal_curvature"),
        "treatment": payload.get("treatment") or "none",
        "screen_time_hours": payload.get("screen_time_hours"),
        "near_work_min": payload.get("near_work_min"),
        "outdoor_min": payload.get("outdoor_min"),
        "sleep_hours": payload.get("sleep_hours"),
        "viewing_distance_cm": payload.get("viewing_distance_cm"),
        "posture_score": payload.get("posture_score"),
        "continuous_session_min": payload.get("continuous_session_min"),
    }
    result = project(
        [visit],
        sex=payload.get("sex"),
        parental_myopia=payload.get("parental_myopia"),
        years=years,
    )
    result["input_quality"] = _input_quality(visit)
    return result


def _input_quality(visit: dict[str, Any]) -> dict[str, Any]:
    """Tell the user how much the answer rests on, rather than pretending
    a one-visit estimate is as good as a followed-up patient."""
    provided = [k for k, v in visit.items() if v is not None and k != "visit_date"]
    behaviour = [k for k in ("screen_time_hours", "near_work_min", "outdoor_min",
                             "sleep_hours") if visit.get(k) is not None]
    ergonomics = [k for k in ("viewing_distance_cm", "posture_score",
                              "continuous_session_min") if visit.get(k) is not None]
    notes = ["Only one time point was supplied, so there is no measured "
             "progression trend for this person. The estimate rests on age, "
             "refraction and the exposures given."]
    if not behaviour:
        notes.append("No behaviour information was given, so screen time, near work "
                     "and outdoor time could not contribute.")
    if not ergonomics:
        notes.append("No ergonomic information was given, so viewing distance and "
                     "session length could not contribute.")
    return {
        "fields_provided": len(provided),
        "has_behaviour": bool(behaviour),
        "has_ergonomics": bool(ergonomics),
        "notes": notes,
    }
