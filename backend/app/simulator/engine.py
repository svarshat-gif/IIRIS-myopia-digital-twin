"""Counterfactual ("what-if") engine.

Clone the current twin -> apply the requested exposure changes -> rebuild
features with the SAME builder used in training -> re-run the SAME model ->
compare trajectories.

Everything it returns is a MODEL ESTIMATE of an association learned from
observational data. It is not a causal effect, and the response says so on every
path.
"""
from __future__ import annotations

import copy
from typing import Any, Sequence

import numpy as np

from app.core.config import settings
from app.ml import registry
from app.ml.features import MODIFIABLE_INPUTS, build_feature_row
from app.simulator.constraints import ScenarioRejected, validate_scenario

CAUSAL_DISCLAIMER = (
    "Counterfactual estimate produced by re-running the prediction model on modified "
    "inputs. It shows how the model's expectation changes, NOT a proven causal effect "
    "of the behaviour change on the eye."
)


def _current_inputs(state: dict[str, Any]) -> dict[str, Any]:
    cur = state["current"]
    values = {**cur.get("behaviour", {}), **cur.get("ergonomics", {})}
    values["treatment"] = cur.get("treatment")
    return values


def _history_from_state(state: dict[str, Any]) -> list[dict[str, Any]]:
    return copy.deepcopy(state["history"])


def _predict(history: Sequence[dict[str, Any]], state: dict[str, Any],
             overrides: dict[str, Any] | None = None) -> dict[str, Any]:
    patient = state["patient"]
    row = build_feature_row(
        history,
        sex=patient.get("sex"),
        parental_myopia=patient.get("parental_myopia"),
        overrides=overrides,
    )
    return registry.predict_from_row(row)


def _diff(baseline: dict[str, Any], counterfactual: dict[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key, cf_entry in counterfactual["horizons"].items():
        base_entry = baseline["horizons"].get(key)
        if not base_entry:
            continue
        item: dict[str, Any] = {"horizon_months": cf_entry["horizon_months"]}
        for measure, unit in (("se", "D"), ("al", "mm")):
            b, c = base_entry.get(measure), cf_entry.get(measure)
            if not b or not c:
                continue
            delta = c["value"] - b["value"]
            item[measure] = {
                "baseline": b["value"],
                "scenario": c["value"],
                "difference": round(delta, 3),
                "unit": unit,
                "baseline_interval": [b["lower"], b["upper"]],
                "scenario_interval": [c["lower"], c["upper"]],
                # A difference smaller than the width of the prediction interval
                # should not be read as a meaningful separation.
                "smaller_than_uncertainty": bool(
                    abs(delta) < (b["upper"] - b["lower"]) / 2.0),
                "direction": _direction(measure, delta),
            }
        out[key] = item

    br, cr = baseline.get("risk"), counterfactual.get("risk")
    if br and cr:
        out["risk"] = {
            "baseline": br["probability"],
            "scenario": cr["probability"],
            "difference": round(cr["probability"] - br["probability"], 4),
            "baseline_band": br["band"],
            "scenario_band": cr["band"],
        }
    return out


def _direction(measure: str, delta: float) -> str:
    """SE closer to zero and smaller AL both mean less myopia."""
    if abs(delta) < 1e-6:
        return "no_change"
    if measure == "se":
        return "less_myopic" if delta > 0 else "more_myopic"
    return "less_elongation" if delta < 0 else "more_elongation"


def _changed_drivers(base_row: dict[str, float], cf_row: dict[str, float],
                     top_n: int = 6) -> list[dict[str, Any]]:
    items = []
    for key in base_row:
        b, c = base_row.get(key), cf_row.get(key)
        if b is None or c is None:
            continue
        if isinstance(b, float) and (np.isnan(b) or np.isnan(c)):
            continue
        if abs(c - b) > 1e-9:
            denom = abs(b) if abs(b) > 1e-9 else 1.0
            items.append({
                "feature": key,
                "baseline": round(float(b), 3),
                "scenario": round(float(c), 3),
                "change": round(float(c - b), 3),
                "relative_change": round(float((c - b) / denom), 3),
            })
    items.sort(key=lambda i: abs(i["relative_change"]), reverse=True)
    return items[:top_n]


def simulate(state: dict[str, Any], scenario: dict[str, Any]) -> dict[str, Any]:
    """Run one scenario against the twin state."""
    current = _current_inputs(state)
    changes, warnings = validate_scenario(scenario.get("changes", {}), current)

    history = _history_from_state(state)
    patient = state["patient"]

    base_row = build_feature_row(history, sex=patient.get("sex"),
                                 parental_myopia=patient.get("parental_myopia"))
    cf_row = build_feature_row(history, sex=patient.get("sex"),
                               parental_myopia=patient.get("parental_myopia"),
                               overrides=changes)

    baseline = registry.predict_from_row(base_row)
    counterfactual = registry.predict_from_row(cf_row)

    return {
        "label": scenario.get("label") or "Scenario",
        "applied_changes": [
            {
                "input": key,
                "label": MODIFIABLE_INPUTS[key].get("label", key),
                "from": current.get(key),
                "to": value,
                "unit": MODIFIABLE_INPUTS[key].get("unit", ""),
            }
            for key, value in changes.items()
        ],
        "baseline": baseline,
        "counterfactual": counterfactual,
        "comparison": _diff(baseline, counterfactual),
        "changed_drivers": _changed_drivers(base_row, cf_row),
        "warnings": warnings,
        "model_version": baseline["model_version"],
        "causal_disclaimer": CAUSAL_DISCLAIMER,
        "disclaimer": settings.disclaimer,
    }


def simulate_many(state: dict[str, Any],
                  scenarios: Sequence[dict[str, Any]]) -> dict[str, Any]:
    results, rejected = [], []
    for sc in scenarios:
        try:
            results.append(simulate(state, sc))
        except ScenarioRejected as exc:
            rejected.append({"label": sc.get("label"), "errors": exc.errors})
    return {
        "scenarios": results,
        "rejected": rejected,
        "causal_disclaimer": CAUSAL_DISCLAIMER,
    }


def sensitivity_sweep(state: dict[str, Any], input_name: str,
                      values: Sequence[float], horizon: str = "12m") -> dict[str, Any]:
    """Sweep one input across a range -> the dose-response curve the UI plots."""
    if input_name not in MODIFIABLE_INPUTS:
        raise ScenarioRejected([f"'{input_name}' is not a modifiable input."])

    patient = state["patient"]
    history = _history_from_state(state)
    baseline_pred = registry.predict_from_row(
        build_feature_row(history, sex=patient.get("sex"),
                          parental_myopia=patient.get("parental_myopia")))

    points = []
    for value in values:
        try:
            changes, _ = validate_scenario({input_name: value}, _current_inputs(state))
        except ScenarioRejected:
            continue
        pred = registry.predict_from_row(
            build_feature_row(history, sex=patient.get("sex"),
                              parental_myopia=patient.get("parental_myopia"),
                              overrides=changes))
        entry = pred["horizons"].get(horizon, {})
        points.append({
            "value": value,
            "predicted_se": (entry.get("se") or {}).get("value"),
            "predicted_al": (entry.get("al") or {}).get("value"),
            "se_lower": (entry.get("se") or {}).get("lower"),
            "se_upper": (entry.get("se") or {}).get("upper"),
            "risk": (pred.get("risk") or {}).get("probability"),
        })

    base_entry = baseline_pred["horizons"].get(horizon, {})
    return {
        "input": input_name,
        "label": MODIFIABLE_INPUTS[input_name].get("label", input_name),
        "unit": MODIFIABLE_INPUTS[input_name].get("unit", ""),
        "horizon": horizon,
        "current_value": _current_inputs(state).get(input_name),
        "baseline_se": (base_entry.get("se") or {}).get("value"),
        "baseline_al": (base_entry.get("al") or {}).get("value"),
        "points": points,
        "causal_disclaimer": CAUSAL_DISCLAIMER,
    }
