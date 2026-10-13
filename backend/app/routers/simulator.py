"""Public simulator: type in values, see a modelled future trajectory.

No account and no stored record required, which is the point -- it is the front
door of the product. Nothing typed here is persisted.
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, status

from app.core.config import settings
from app.ml import registry
from app.ml.features import MODIFIABLE_INPUTS
from app.schemas.auth import QuickSimulationIn
from app.simulator import projection
from app.simulator.constraints import ScenarioRejected, validate_scenario

router = APIRouter(prefix="/simulator", tags=["simulator"])


@router.post("/project", summary="Project myopia forward from typed-in values")
def quick_project(payload: QuickSimulationIn) -> dict[str, Any]:
    if not registry.is_ready():
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE,
                            "The prediction model is not loaded on this server.")

    values = payload.model_dump(exclude={"years", "compare_with"})
    # Axial length is optional in the form; when it is absent the model simply
    # treats it as missing rather than having a value invented for it.
    baseline = projection.quick_project(values, years=payload.years)

    scenario = None
    if payload.compare_with:
        current = {k: values.get(k) for k in MODIFIABLE_INPUTS}
        try:
            changes, warnings = validate_scenario(payload.compare_with, current)
            from app.simulator.engine import require_supported_inputs
            require_supported_inputs(changes)
        except ScenarioRejected as exc:
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_ENTITY,
                {"message": "That comparison scenario is outside a realistic range.",
                 "errors": exc.errors}) from exc
        scenario = projection.quick_project({**values, **changes}, years=payload.years)
        scenario["applied_changes"] = changes
        scenario["warnings"] = warnings

    return {
        "baseline": baseline,
        "scenario": scenario,
        "years": payload.years,
        "disclaimer": settings.disclaimer,
        "not_a_diagnosis": (
            "This is a modelled estimate from the values you entered. It is not an eye "
            "test, not a diagnosis, and not a substitute for seeing an optometrist or "
            "ophthalmologist."
        ),
    }


@router.get("/inputs", summary="Fields the simulator accepts, with ranges")
def simulator_inputs() -> dict[str, Any]:
    return {
        "required": [
            {"name": "age", "label": "Age", "unit": "years", "min": 3, "max": 30,
             "step": 0.5,
             "help": "Younger eyes tend to progress faster, so this matters a lot."},
            {"name": "spherical_equivalent", "label": "Spherical equivalent",
             "unit": "D", "min": -30, "max": 15, "step": 0.25,
             "help": "From your prescription. Negative means short-sighted. "
                     "If you have sphere and cylinder, use sphere + cylinder/2."},
        ],
        "clinical": [
            {"name": "axial_length", "label": "Axial length", "unit": "mm",
             "min": 15, "max": 35, "step": 0.01,
             "help": "The length of the eye, from a biometry scan. Leave blank "
                     "if you do not have it."},
            {"name": "visual_acuity", "label": "Visual acuity", "unit": "logMAR",
             "min": -0.3, "max": 2, "step": 0.01,
             "help": "0.00 is 6/6 vision. Leave blank if unsure."},
            {"name": "parental_myopia", "label": "Short-sighted parents",
             "unit": "", "min": 0, "max": 2, "step": 1,
             "help": "How many biological parents wear glasses for distance."},
        ],
        "behaviour": [
            {"name": "screen_time_hours", "label": "Screen time", "unit": "h/day",
             "min": 0, "max": 16, "step": 0.5},
            {"name": "near_work_min", "label": "Reading and homework",
             "unit": "min/day", "min": 0, "max": 720, "step": 15},
            {"name": "outdoor_min", "label": "Time outdoors", "unit": "min/day",
             "min": 0, "max": 480, "step": 15},
            {"name": "sleep_hours", "label": "Sleep", "unit": "h/night",
             "min": 3, "max": 12, "step": 0.5},
        ],
        "ergonomics": [
            {"name": "viewing_distance_cm", "label": "Screen or book distance",
             "unit": "cm", "min": 10, "max": 80, "step": 1},
            {"name": "continuous_session_min", "label": "Time before a break",
             "unit": "min", "min": 5, "max": 240, "step": 5},
            {"name": "posture_score", "label": "Posture", "unit": "",
             "min": 0, "max": 1, "step": 0.05,
             "help": "1 means upright and well supported."},
        ],
        "treatments": ["none", "single_vision", "atropine", "ortho_k", "dims"],
        "note": "Only age and spherical equivalent are required. Anything you leave "
                "blank is treated as unknown -- it is never filled in with a guess.",
    }
