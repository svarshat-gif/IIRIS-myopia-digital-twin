"""Plausibility gate for what-if scenarios.

Requirement from the build guide: "scenarios outside realistic ranges should be
rejected instead of producing confident-looking outputs."

Two levels:
  * HARD  -> outside the physiologically/behaviourally possible range. Rejected.
  * SOFT  -> possible but far outside what the training data covered, so the
             model is extrapolating. Accepted, but the response is flagged so the
             UI can show the warning next to the number.
"""
from __future__ import annotations

from typing import Any

from app.ml.features import MODIFIABLE_INPUTS

# Largest change from the patient's own current value we consider a realistic
# behaviour change over one follow-up interval.
MAX_PLAUSIBLE_DELTA: dict[str, float] = {
    "screen_time_hours": 6.0,
    "near_work_min": 300.0,
    "outdoor_min": 240.0,
    "sleep_hours": 3.0,
    "viewing_distance_cm": 25.0,
    "posture_score": 0.6,
    "continuous_session_min": 120.0,
}


class ScenarioRejected(ValueError):
    """Raised when a scenario is outside the range the model may be asked about."""

    def __init__(self, errors: list[str]):
        self.errors = errors
        super().__init__("; ".join(errors))


def validate_scenario(changes: dict[str, Any],
                      current: dict[str, Any]) -> tuple[dict[str, Any], list[str]]:
    """Return (accepted changes, warnings). Raises ScenarioRejected on hard errors."""
    errors: list[str] = []
    warnings: list[str] = []
    accepted: dict[str, Any] = {}

    for key, value in changes.items():
        if value is None:
            continue
        spec = MODIFIABLE_INPUTS.get(key)
        if spec is None:
            errors.append(
                f"'{key}' is not a modifiable input. Allowed: "
                f"{sorted(MODIFIABLE_INPUTS)}"
            )
            continue

        if "choices" in spec:
            if value not in spec["choices"]:
                errors.append(f"{key}='{value}' is not one of {spec['choices']}")
                continue
            accepted[key] = value
            continue

        try:
            numeric = float(value)
        except (TypeError, ValueError):
            errors.append(f"{key} must be a number, got {value!r}")
            continue

        if numeric < spec["min"] or numeric > spec["max"]:
            errors.append(
                f"{key}={numeric}{spec.get('unit', '')} is outside the plausible range "
                f"{spec['min']}-{spec['max']}{spec.get('unit', '')}"
            )
            continue

        baseline = current.get(key)
        limit = MAX_PLAUSIBLE_DELTA.get(key)
        if baseline is not None and limit is not None:
            delta = abs(numeric - float(baseline))
            if delta > limit:
                warnings.append(
                    f"{key} changes by {delta:.1f}{spec.get('unit', '')} from the "
                    f"patient's current {baseline}{spec.get('unit', '')}. That is a very "
                    f"large change; the model is extrapolating beyond what it has seen."
                )
        if baseline is None:
            warnings.append(
                f"{key} is not recorded for this patient, so the scenario compares "
                f"against a model estimate rather than a measured baseline."
            )
        accepted[key] = numeric

    if errors:
        raise ScenarioRejected(errors)
    return accepted, warnings
