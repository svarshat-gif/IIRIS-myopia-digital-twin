"""Per-prediction explanation.

Primary method: SHAP (exact additive attribution) when the `shap` package is
installed. Fallback: marginal ablation attribution, which is always available so
the API never returns "explanation unavailable".

The fallback is clearly LABELLED as a different method in the response -- it
approximates the same question ("which inputs pushed this prediction?") but it is
not a Shapley value and must not be reported as one.

Neither method is evidence of causation. Attribution describes the MODEL, not
the eye.
"""
from __future__ import annotations

from typing import Any

import numpy as np

from app.core.config import settings
from app.ml import registry
from app.ml.features import FEATURE_LABELS, row_to_vector

ATTRIBUTION_DISCLAIMER = (
    "Attribution shows which inputs moved THIS model's output, not which factors "
    "cause myopia progression in this child."
)

_shap_cache: dict[str, Any] = {}


def _try_shap(model, x: np.ndarray, background: np.ndarray):
    """Return (values, method) or (None, None) if SHAP is unavailable/unsupported."""
    try:
        import shap  # noqa: PLC0415
    except ImportError:
        return None, None

    key = id(model)
    explainer = _shap_cache.get(key)
    if explainer is None:
        try:
            explainer = shap.TreeExplainer(model)
            explainer(x[:1])  # probe: raises if the model type is unsupported
            _shap_cache[key] = explainer
        except Exception:
            try:
                explainer = shap.explainers.Permutation(
                    model.predict, background, max_evals=800)
                _shap_cache[key] = explainer
            except Exception:
                return None, None
    try:
        out = explainer(x)
        values = np.asarray(out.values).reshape(-1)
        base = float(np.asarray(out.base_values).reshape(-1)[0])
        method_name = type(explainer).__name__
        return (values, base), f"shap.{method_name}"
    except Exception:
        return None, None


def _ablation(model, x: np.ndarray, feature_names: list[str],
              medians: dict[str, float]) -> tuple[np.ndarray, float]:
    """Marginal attribution: how much does the prediction move if this feature is
    reset to its training-set median while everything else is held fixed?"""
    base_pred = float(model.predict(x)[0])
    contributions = np.zeros(len(feature_names), dtype=float)
    for i, name in enumerate(feature_names):
        median = medians.get(name)
        if median is None or (isinstance(x[0, i], float) and np.isnan(x[0, i])):
            continue
        if abs(float(x[0, i]) - float(median)) < 1e-12:
            continue
        perturbed = x.copy()
        perturbed[0, i] = median
        contributions[i] = base_pred - float(model.predict(perturbed)[0])
    reference = base_pred - float(contributions.sum())
    return contributions, reference


def explain_prediction(feature_row: dict[str, float], *, target: str = "se_12m",
                       top_n: int = 8) -> dict[str, Any]:
    bundle = registry.load_bundle()
    models = bundle["models"].get(target)
    if models is None:
        available = [k for k in bundle["models"] if k != "risk"]
        raise ValueError(f"Unknown explanation target '{target}'. Available: {available}")

    model = models["median"]
    names = list(bundle["feature_names"])
    x = row_to_vector(feature_row, names)

    result, method = _try_shap(model, x, registry.background_sample())
    if result is not None:
        values, reference = result
        method_note = "Exact Shapley attribution for this prediction."
    else:
        values, reference = _ablation(model, x, names, registry.training_medians())
        method = "marginal_ablation"
        method_note = (
            "SHAP is not installed, so contributions come from marginal ablation: each "
            "input is reset to its training median in turn and the change in the "
            "prediction is recorded. Directionally comparable to SHAP but not a "
            "Shapley value. Install shap (requirements-optional.txt) for exact values."
        )

    prediction = float(model.predict(x)[0])
    order = np.argsort(np.abs(values))[::-1][:top_n]
    contributions = [
        {
            "feature": names[i],
            "label": FEATURE_LABELS.get(names[i], names[i]),
            "value": None if np.isnan(x[0, i]) else round(float(x[0, i]), 3),
            "contribution": round(float(values[i]), 4),
            "direction": ("increases_prediction" if values[i] > 0
                          else "decreases_prediction" if values[i] < 0 else "neutral"),
            "missing": bool(np.isnan(x[0, i])),
        }
        for i in order if abs(float(values[i])) > 1e-9
    ]

    return {
        "target": target,
        "target_label": _target_label(target),
        "prediction": round(prediction, 3),
        "reference_value": round(float(reference), 3),
        "method": method,
        "method_note": method_note,
        "contributions": contributions,
        "plain_language": to_plain_language(contributions, target),
        "model_version": bundle["model_version"],
        "attribution_disclaimer": ATTRIBUTION_DISCLAIMER,
        "disclaimer": settings.disclaimer,
    }


def _target_label(target: str) -> str:
    measure, horizon = target.split("_", 1)
    name = "spherical equivalent" if measure == "se" else "axial length"
    return f"Predicted {name} at {horizon.replace('m', ' months')}"


def to_plain_language(contributions: list[dict[str, Any]], target: str) -> list[str]:
    """Short, non-causal sentences for the Explanation panel and the agent."""
    measure = target.split("_")[0]
    lines: list[str] = []
    for c in contributions[:5]:
        if measure == "se":
            effect = ("toward less myopia" if c["contribution"] > 0
                      else "toward more myopia")
        else:
            effect = ("toward a longer eye" if c["contribution"] > 0
                      else "toward a shorter eye")
        value = "not recorded" if c["missing"] else c["value"]
        lines.append(
            f"{c['label']} ({value}) moved this prediction {effect} "
            f"by {abs(c['contribution']):.3f}."
        )
    return lines


def global_importance(top_n: int = 15) -> list[dict[str, Any]]:
    items = registry.load_bundle().get("metrics", {}).get("global_importance", [])
    return [
        {**item, "label": FEATURE_LABELS.get(item["feature"], item["feature"])}
        for item in items[:top_n]
    ]
