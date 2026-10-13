"""Loads the trained model bundle and serves predictions for one twin state.

The bundle is produced by `python -m app.ml.train` and holds, for every target:
  - a median model  (HistGradientBoostingRegressor, loss="squared_error")
  - a lower and an upper quantile model -> the prediction interval
plus a progression-risk classifier, the feature list, evaluation metrics and a
background sample used by the explainer.
"""
from __future__ import annotations

import math
import threading
from pathlib import Path
from typing import Any

import joblib
import numpy as np

from app.core.config import settings
from app.ml.dataset import FAST_PROGRESSION_THRESHOLD_D as FAST_PROGRESSION_CUTOFF_D
from app.ml.features import ALL_FEATURES, row_to_vector

_lock = threading.Lock()
_bundle: dict[str, Any] | None = None


class ModelNotTrainedError(RuntimeError):
    pass


def load_bundle(force: bool = False) -> dict[str, Any]:
    global _bundle
    with _lock:
        if _bundle is None or force:
            path: Path = settings.model_path
            if not path.exists():
                raise ModelNotTrainedError(
                    f"No model bundle at {path}. Run:  python -m app.ml.train"
                )
            _bundle = joblib.load(path)
        return _bundle


def is_ready() -> bool:
    try:
        load_bundle()
        return True
    except ModelNotTrainedError:
        return False


def model_version() -> str:
    try:
        return load_bundle()["model_version"]
    except ModelNotTrainedError:
        return "untrained"


def feature_names() -> list[str]:
    try:
        return list(load_bundle()["feature_names"])
    except ModelNotTrainedError:
        return list(ALL_FEATURES)


def metrics() -> dict[str, Any]:
    return load_bundle().get("metrics", {})


def _predict_one(model, x: np.ndarray) -> float:
    return float(model.predict(x)[0])


def predict_from_row(row: dict[str, float]) -> dict[str, Any]:
    """Predict every horizon from one feature row.

    Returns a structure the API, the simulator and the UI all consume unchanged.
    """
    bundle = load_bundle()
    names = bundle["feature_names"]
    x = row_to_vector(row, names)
    warnings = list(bundle.get("provenance", {}).get("limitations", []))
    for feature, (low, high) in bundle.get("training_ranges", {}).items():
        value = row.get(feature)
        if value is not None and np.isfinite(value) and not low <= value <= high:
            warnings.append(f"{feature} is outside the observed training range [{low:g}, {high:g}]; extrapolation is unreliable")

    horizons: dict[str, Any] = {}
    for horizon in bundle["horizons"]:
        entry: dict[str, Any] = {"horizon_months": horizon}
        for measure in ("se", "al"):
            models = bundle["models"].get(f"{measure}_{horizon}m")
            if not models:
                continue
            point = _predict_one(models["median"], x)
            lower = _predict_one(models["lower"], x)
            upper = _predict_one(models["upper"], x)
            # Quantile models are fitted independently and can cross on sparse
            # regions; order them, then apply the conformal widening that makes
            # the stated coverage honest (see app/ml/train.py:conformal_delta).
            delta = float(models.get("conformal_delta", 0.0))
            lower, upper = min(lower, upper) - delta, max(lower, upper) + delta
            entry[measure] = {
                "value": round(point, 3),
                "lower": round(min(lower, point), 3),
                "upper": round(max(upper, point), 3),
                "interval_label": f"{int(bundle['interval_coverage'] * 100)}% prediction interval",
            }
        horizons[f"{horizon}m"] = entry

    risk_model = bundle["models"].get("risk")
    risk: dict[str, Any] | None = None
    if risk_model is not None:
        p = float(risk_model.predict_proba(x)[0][1])
        risk = {
            "probability": round(p, 4),
            "band": risk_band(p),
            "definition": bundle["risk_definition"],
        }
        # The regression and the classifier are trained independently, so they
        # can disagree -- most often on patients unlike the training cohort.
        # Rather than showing a confident number that contradicts the interval
        # displayed right next to it, we detect the conflict and say so.
        implied = _interval_implied_risk(horizons, row)
        if implied is not None:
            risk["interval_implied_probability"] = round(implied, 4)
            if abs(implied - p) >= RISK_DISAGREEMENT_THRESHOLD:
                risk["consistent_with_interval"] = False
                risk["consistency_note"] = (
                    "The progression-risk model and the prediction interval disagree "
                    "for this record (they are trained separately). Treat the risk "
                    "figure with extra caution and rely on the predicted range."
                )
            else:
                risk["consistent_with_interval"] = True

    return {
        "horizons": horizons,
        "risk": risk,
        "model_version": bundle["model_version"],
        "features_used": names,
        "warnings": warnings,
        "data_source": bundle.get("data_source"),
        "risk_unavailable_reason": "Insufficient independent labelled patients for a risk classifier" if risk is None else None,
    }


# How far the two estimates may drift before we flag the conflict to the user.
RISK_DISAGREEMENT_THRESHOLD = 0.25


def _interval_implied_risk(horizons: dict[str, Any],
                           row: dict[str, float]) -> float | None:
    """Probability of fast progression implied by the 12-month SE interval.

    Treats the calibrated 90% band as +/- 1.645 sigma of a normal, which is a
    rough but serviceable way to ask "does the interval agree with the
    classifier?". Used only for the consistency check, never as the reported risk.
    """
    entry = (horizons.get("12m") or {}).get("se")
    current = row.get("se")
    if not entry or current is None or (isinstance(current, float)
                                        and math.isnan(current)):
        return None
    sigma = (entry["upper"] - entry["lower"]) / (2 * 1.645)
    if sigma <= 1e-6:
        return None
    change = entry["value"] - current
    z = (FAST_PROGRESSION_CUTOFF_D - change) / sigma
    return 0.5 * (1.0 + math.erf(z / math.sqrt(2.0)))


def risk_band(p: float) -> str:
    if p < 0.25:
        return "low"
    if p < 0.55:
        return "moderate"
    return "high"


def background_sample() -> np.ndarray:
    return np.asarray(load_bundle()["background"], dtype=float)


def training_medians() -> dict[str, float]:
    return dict(load_bundle().get("feature_medians", {}))
