"""Train the progression models and write the deployable bundle.

    python -m app.ml.train --data data/training_visits.csv

Design decisions that matter for the report:

* Splits are BY PATIENT (GroupShuffleSplit). No patient contributes rows to more
  than one split, so repeated visits cannot leak between train and test.
* Five model families are compared on the identical split -- Ridge, Random Forest,
  XGBoost, LightGBM and HistGradientBoosting -- plus a carry-forward baseline.
  HistGradientBoosting is the DEPLOYED model because it is the one that also
  supports quantile loss (needed for the prediction interval) and NaN inputs
  natively (needed because behaviour/ergonomics are often unrecorded).
* Uncertainty comes from quantile regression that is then CONFORMALIZED
  (Romano et al., "Conformalized Quantile Regression"): a 5th- and 95th-percentile
  model is trained alongside each median model, and the resulting band is widened
  by a constant estimated on a held-out validation split of *unseen patients* so
  that the stated 90% interval actually covers ~90% of unseen outcomes. Raw
  quantile forests routinely under-cover; without this step the interval would
  claim more confidence than it has.
* HistGradientBoosting accepts NaN natively, so partially-recorded behaviour and
  ergonomics rows are used as-is rather than imputed with invented values.
* The ablation (clinical / +behaviour / +ergonomics) runs on the same splits and
  the same hyperparameters, so the comparison is fair.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import (
    HistGradientBoostingClassifier,
    HistGradientBoostingRegressor,
    RandomForestRegressor,
)
from sklearn.inspection import permutation_importance
from sklearn.linear_model import Ridge
from sklearn.metrics import (
    average_precision_score,
    brier_score_loss,
    mean_absolute_error,
    r2_score,
    roc_auc_score,
    root_mean_squared_error,
)
from sklearn.model_selection import GroupShuffleSplit, GroupKFold, cross_val_predict
from sklearn.pipeline import make_pipeline
from sklearn.impute import SimpleImputer
from sklearn.preprocessing import StandardScaler

from app.core.config import settings
from app.ml.dataset import (
    FAST_PROGRESSION_THRESHOLD_D,
    HORIZONS,
    build_supervised_table,
    load_visits,
)
from app.ml.features import ALL_FEATURES, FEATURE_SETS

INTERVAL_COVERAGE = 0.90
LOWER_Q, UPPER_Q = 0.05, 0.95


def verify_training_source(path: Path) -> dict:
    if "synthetic" in path.name.lower():
        raise ValueError("Synthetic data cannot produce a deployable model")
    metadata = path.with_suffix(".provenance.json")
    if not metadata.exists():
        raise ValueError("Missing verified provenance. Run scripts/build_training_table.py first")
    provenance = json.loads(metadata.read_text(encoding="utf-8"))
    if provenance.get("data_is_synthetic") is not False or not provenance.get("sources"):
        raise ValueError("Only verified real open data may produce a deployable model")
    if hashlib.sha256(path.read_bytes()).hexdigest() != provenance["table_sha256"]:
        raise ValueError("Training table checksum does not match verified provenance")
    return provenance


def bootstrap_metrics(y, prediction, groups, repeats=500) -> dict:
    """Resample independent patients, retaining all their repeated visits."""
    groups = np.asarray(groups)
    keys = np.unique(groups)
    rng = np.random.default_rng(42)
    values = {k: [] for k in ("mae", "rmse", "r2")}
    for _ in range(repeats):
        take = np.concatenate([np.flatnonzero(groups == k) for k in rng.choice(keys, len(keys), replace=True)])
        scores = regression_metrics(y[take], prediction[take])
        for k in values:
            if np.isfinite(scores[k]):
                values[k].append(scores[k])
    return {k: [round(float(v), 4) for v in np.quantile(samples, [.025, .975])]
            for k, samples in values.items() if samples}

HGB_PARAMS = dict(
    max_iter=100,
    learning_rate=0.06,
    max_depth=None,
    max_leaf_nodes=7,
    min_samples_leaf=3,
    l2_regularization=10.0,
    early_stopping=False,
    validation_fraction=0.15,
    random_state=42,
)


def split_by_patient(table: pd.DataFrame, seed: int = 42
                     ) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    groups = table["patient_key"].to_numpy()
    idx = np.arange(len(table))

    small = table.patient_key.nunique() <= 40
    outer = GroupShuffleSplit(n_splits=1, test_size=0.10 if small else 0.20, random_state=seed)
    trainval_i, test_i = next(outer.split(idx, groups=groups))

    # At least ten independent calibration patients for a finite 90% band.
    inner = GroupShuffleSplit(n_splits=1, test_size=10 if small else 0.20, random_state=seed + 1)
    tr_rel, val_rel = next(inner.split(trainval_i, groups=groups[trainval_i]))

    train = table.iloc[trainval_i[tr_rel]].reset_index(drop=True)
    val = table.iloc[trainval_i[val_rel]].reset_index(drop=True)
    test = table.iloc[test_i].reset_index(drop=True)

    sets = [set(f.patient_key) for f in (train, val, test)]
    assert all(not sets[i] & sets[j] for i in range(3) for j in range(i)), "patient leakage"
    return train, val, test


def _xy(frame: pd.DataFrame, features: list[str], target: str
        ) -> tuple[np.ndarray, np.ndarray]:
    sub = frame.dropna(subset=[target])
    X = sub.reindex(columns=features).to_numpy(dtype=float)
    y = sub[target].to_numpy(dtype=float)
    return X, y


def regression_metrics(y_true: np.ndarray, y_pred: np.ndarray) -> dict[str, float]:
    return {
        "n": int(len(y_true)),
        "mae": round(float(mean_absolute_error(y_true, y_pred)), 4),
        "rmse": round(float(root_mean_squared_error(y_true, y_pred)), 4),
        "r2": round(float(r2_score(y_true, y_pred)), 4),
    }


def conformal_delta(lower: np.ndarray, upper: np.ndarray, y: np.ndarray,
                    coverage: float = INTERVAL_COVERAGE, groups=None) -> float:
    """Split-conformal correction for a quantile interval (CQR).

    The nonconformity score is how far the true value fell OUTSIDE the predicted
    band (negative when comfortably inside). Widening the band by the empirical
    (1-alpha) quantile of these scores gives finite-sample coverage on exchangeable
    data. Computed on validation patients the models never saw.
    """
    lo = np.minimum(lower, upper)
    hi = np.maximum(lower, upper)
    scores = np.maximum(lo - y, y - hi)
    if groups is not None:
        scores = pd.Series(scores).groupby(np.asarray(groups)).max().to_numpy()
    n = len(scores)
    if n < 9:
        raise ValueError("At least nine independent calibration patients required for 90% intervals")
    level = min(1.0, np.ceil((n + 1) * coverage) / n)
    return float(max(0.0, np.quantile(scores, level, method="higher")))


def train_regressors(train: pd.DataFrame, val: pd.DataFrame, test: pd.DataFrame,
                     features: list[str]) -> tuple[dict[str, Any], dict[str, Any]]:
    models: dict[str, Any] = {}
    metrics: dict[str, Any] = {}

    for measure in ("se", "al"):
        for horizon in HORIZONS:
            target = f"y_{measure}_{horizon}m"
            Xtr, ytr = _xy(train, features, target)
            Xte, yte = _xy(test, features, target)
            if len(ytr) < 12 or len(yte) < 2:
                print(f"  ! skipping {target}: not enough labelled rows "
                      f"(train={len(ytr)}, test={len(yte)})")
                continue

            median = HistGradientBoostingRegressor(**HGB_PARAMS).fit(Xtr, ytr)
            lower = HistGradientBoostingRegressor(
                loss="quantile", quantile=LOWER_Q, **HGB_PARAMS).fit(Xtr, ytr)
            upper = HistGradientBoostingRegressor(
                loss="quantile", quantile=UPPER_Q, **HGB_PARAMS).fit(Xtr, ytr)

            # Calibrate the band on validation patients (never seen in training).
            Xva, yva = _xy(val, features, target)
            calibration = val.dropna(subset=[target])
            delta = conformal_delta(lower.predict(Xva), upper.predict(Xva), yva,
                                    groups=calibration.patient_key)

            models[f"{measure}_{horizon}m"] = {
                "median": median, "lower": lower, "upper": upper,
                "conformal_delta": delta}

            pred = median.predict(Xte)
            lo = np.minimum(lower.predict(Xte), upper.predict(Xte))
            hi = np.maximum(lower.predict(Xte), upper.predict(Xte))
            entry = regression_metrics(yte, pred)
            entry["bootstrap_95ci"] = bootstrap_metrics(yte, pred, test.dropna(subset=[target]).patient_key)
            entry["calibration_patients"] = int(calibration.patient_key.nunique())
            # Out-of-fold development scores do not inspect calibration/test patients.
            development = train.dropna(subset=[target])
            folds = GroupKFold(n_splits=min(4, development.patient_key.nunique()))
            oof = cross_val_predict(HistGradientBoostingRegressor(**HGB_PARAMS), Xtr, ytr,
                                   cv=folds, groups=development.patient_key)
            entry["development_grouped_cv"] = regression_metrics(ytr, oof)
            entry["interval_coverage_raw"] = round(
                float(np.mean((yte >= lo) & (yte <= hi))), 4)
            lo_c, hi_c = lo - delta, hi + delta
            entry["interval_coverage"] = round(
                float(np.mean((yte >= lo_c) & (yte <= hi_c))), 4)
            entry["mean_interval_width"] = round(float(np.mean(hi_c - lo_c)), 4)
            entry["conformal_delta"] = round(delta, 4)
            entry["nominal_coverage"] = INTERVAL_COVERAGE

            # Reference baselines on the identical split.
            entry["baselines"] = {}
            ridge = make_pipeline(SimpleImputer(strategy="median", keep_empty_features=True), StandardScaler(),
                                  Ridge(alpha=10.0)).fit(Xtr, ytr)
            entry["baselines"]["ridge"] = regression_metrics(yte, ridge.predict(Xte))
            rf = make_pipeline(
                SimpleImputer(strategy="median", keep_empty_features=True),
                RandomForestRegressor(n_estimators=200, min_samples_leaf=3,
                                      random_state=42, n_jobs=-1),
            ).fit(Xtr, ytr)
            entry["baselines"]["random_forest"] = regression_metrics(yte, rf.predict(Xte))

            # XGBoost and LightGBM are optional installs. When present they join
            # the comparison on the identical split, so the choice of deployed
            # model is an evidenced one rather than an assumption.
            try:
                from xgboost import XGBRegressor  # noqa: PLC0415
                xgb = XGBRegressor(
                    n_estimators=400, learning_rate=0.06, max_depth=5,
                    subsample=0.9, colsample_bytree=0.9, reg_lambda=1.0,
                    random_state=42, n_jobs=-1, verbosity=0,
                ).fit(Xtr, ytr)
                entry["baselines"]["xgboost"] = regression_metrics(yte, xgb.predict(Xte))
            except ImportError:
                pass
            try:
                from lightgbm import LGBMRegressor  # noqa: PLC0415
                lgbm = LGBMRegressor(
                    n_estimators=400, learning_rate=0.06, num_leaves=31,
                    min_child_samples=20, reg_lambda=1.0, random_state=42,
                    n_jobs=-1, verbose=-1,
                ).fit(Xtr, ytr)
                entry["baselines"]["lightgbm"] = regression_metrics(yte, lgbm.predict(Xte))
            except ImportError:
                pass
            # "Carry forward the current value" -- the no-model baseline any
            # clinical prediction must beat to be worth anything.
            sub_te = test.dropna(subset=[target])
            naive = sub_te[measure].to_numpy(dtype=float)
            mask = ~np.isnan(naive)
            entry["baselines"]["carry_forward"] = regression_metrics(yte[mask], naive[mask])
            entry["baselines"]["carry_forward"]["bootstrap_95ci"] = bootstrap_metrics(
                yte[mask], naive[mask], sub_te.patient_key.to_numpy()[mask])

            metrics[target] = entry
            others = " ".join(f"{k}={v['mae']}" for k, v in entry["baselines"].items())
            print(f"  {target}: MAE={entry['mae']} RMSE={entry['rmse']} R2={entry['r2']} "
                  f"coverage {entry['interval_coverage_raw']}->{entry['interval_coverage']}")
            print(f"      vs  {others}")

    return models, metrics


def train_risk_classifier(train: pd.DataFrame, test: pd.DataFrame, features: list[str]
                          ) -> tuple[Any, dict[str, Any]]:
    target = "y_fast_progression"
    Xtr, ytr = _xy(train, features, target)
    Xte, yte = _xy(test, features, target)
    if len(np.unique(ytr)) < 2 or len(np.unique(yte)) < 2 or len(yte) < 10:
        print("  ! skipping risk classifier: degenerate labels")
        return None, {}

    clf = HistGradientBoostingClassifier(
        max_iter=250, learning_rate=0.06, min_samples_leaf=20,
        l2_regularization=1.0, early_stopping=True, validation_fraction=0.15,
        random_state=42,
    ).fit(Xtr, ytr)

    proba = clf.predict_proba(Xte)[:, 1]
    m = {
        "n": int(len(yte)),
        "positive_rate": round(float(yte.mean()), 4),
        "roc_auc": round(float(roc_auc_score(yte, proba)), 4),
        "pr_auc": round(float(average_precision_score(yte, proba)), 4),
        "brier": round(float(brier_score_loss(yte, proba)), 4),
        "definition": f"SE change over 12 months <= {FAST_PROGRESSION_THRESHOLD_D} D",
    }
    print(f"  risk: ROC-AUC={m['roc_auc']} PR-AUC={m['pr_auc']} Brier={m['brier']} "
          f"(base rate {m['positive_rate']})")
    return clf, m


def run_ablation(train: pd.DataFrame, test: pd.DataFrame) -> dict[str, Any]:
    """Clinical vs +behaviour vs +ergonomics on identical splits.

    This is the experiment that tests the project's central claim: that the
    behavioural and ergonomic layers add predictive value over biomarkers alone.
    """
    results: dict[str, Any] = {}
    for set_name, features in FEATURE_SETS.items():
        extra = [f for f in features if f not in FEATURE_SETS["clinical"]]
        if extra and not train.reindex(columns=extra).notna().any().any():
            results[set_name] = {"status": "not_evaluable", "reason": "No measured behaviour/ergonomics in these sources"}
            continue
        entry: dict[str, Any] = {"n_features": len(features)}
        for measure in ("se", "al"):
            for horizon in HORIZONS:
                target = f"y_{measure}_{horizon}m"
                Xtr, ytr = _xy(train, features, target)
                Xte, yte = _xy(test, features, target)
                if len(ytr) < 50 or len(yte) < 10:
                    continue
                model = HistGradientBoostingRegressor(**HGB_PARAMS).fit(Xtr, ytr)
                entry[target] = regression_metrics(yte, model.predict(Xte))

        Xtr, ytr = _xy(train, features, "y_fast_progression")
        Xte, yte = _xy(test, features, "y_fast_progression")
        if len(np.unique(ytr)) > 1 and len(yte) > 10:
            clf = HistGradientBoostingClassifier(
                max_iter=250, learning_rate=0.06, min_samples_leaf=20,
                early_stopping=True, validation_fraction=0.15, random_state=42,
            ).fit(Xtr, ytr)
            entry["y_fast_progression"] = {
                "roc_auc": round(float(roc_auc_score(yte, clf.predict_proba(Xte)[:, 1])), 4)
            }
        results[set_name] = entry
        print(f"  [{set_name}] SE-12m MAE="
              f"{entry.get('y_se_12m', {}).get('mae', 'n/a')} "
              f"AL-12m MAE={entry.get('y_al_12m', {}).get('mae', 'n/a')} "
              f"risk AUC={entry.get('y_fast_progression', {}).get('roc_auc', 'n/a')}")
    return results


def global_importance(model, X: np.ndarray, y: np.ndarray, features: list[str],
                      n_repeats: int = 8) -> list[dict[str, Any]]:
    r = permutation_importance(model, X, y, n_repeats=n_repeats,
                               random_state=42, scoring="neg_mean_absolute_error")
    order = np.argsort(r.importances_mean)[::-1]
    return [
        {"feature": features[i],
         "importance": round(float(r.importances_mean[i]), 5),
         "std": round(float(r.importances_std[i]), 5)}
        for i in order
    ]


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--data", type=Path,
                    default=Path(__file__).resolve().parents[2] / "data" / "training_visits.csv")
    ap.add_argument("--out", type=Path, default=settings.model_path)
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--skip-ablation", action="store_true")
    args = ap.parse_args()

    provenance = verify_training_source(args.data)
    print(f"Loading visits from {args.data}")
    visits = load_visits(args.data)
    table = build_supervised_table(visits)
    print(f"  {visits['patient_key'].nunique()} patients, {len(visits)} visits, "
          f"{len(table)} supervised rows")

    train, val, test = split_by_patient(table, seed=args.seed)
    print(f"  split by patient -> train {train.patient_key.nunique()} / "
          f"val {val.patient_key.nunique()} / test {test.patient_key.nunique()}")

    features = list(ALL_FEATURES)

    print("\nTraining regression models (median + 5th/95th quantile):")
    models, metrics = train_regressors(train, val, test, features)
    if not models:
        raise ValueError("No evaluable real-data targets; refusing to write a deployable bundle")

    print("\nTraining progression-risk classifier:")
    risk_model, risk_metrics = train_risk_classifier(train, test, features)
    if risk_model is not None:
        models["risk"] = risk_model

    ablation: dict[str, Any] = {}
    if not args.skip_ablation:
        print("\nAblation study (clinical / +behaviour / +ergonomics):")
        ablation = run_ablation(train, test)

    print("\nGlobal permutation importance (SE 12-month model):")
    importance: list[dict[str, Any]] = []
    if "se_12m" in models:
        Xte, yte = _xy(test, features, "y_se_12m")
        importance = global_importance(models["se_12m"]["median"], Xte, yte, features)
        for item in importance[:8]:
            print(f"  {item['feature']:<26} {item['importance']:+.4f}")

    # Background sample + medians for the explainer and the "typical patient" view.
    train_X = train.reindex(columns=features).to_numpy(dtype=float)
    rng = np.random.default_rng(args.seed)
    take = rng.choice(len(train_X), size=min(120, len(train_X)), replace=False)
    background = train_X[take]
    medians = {f: (None if np.all(np.isnan(train_X[:, i]))
                   else float(np.nanmedian(train_X[:, i])))
               for i, f in enumerate(features)}

    fingerprint = hashlib.sha256(
        args.data.read_bytes() + str(args.seed).encode()).hexdigest()[:8]
    trained_at = datetime.now(timezone.utc)
    bundle = {
        "model_version": f"mdt-{trained_at:%Y%m%d}-{fingerprint}",
        "trained_at": trained_at.isoformat(),
        "data_source": "; ".join(provenance["source_names"]),
        "data_is_synthetic": provenance["data_is_synthetic"],
        "provenance": provenance,
        "supported_scenario_inputs": [],
        "training_ranges": {f: [float(train[f].min()), float(train[f].max())]
                            for f in features if train[f].notna().any()},
        "feature_names": features,
        "feature_sets": FEATURE_SETS,
        "horizons": list(HORIZONS),
        "interval_coverage": INTERVAL_COVERAGE,
        "quantiles": [LOWER_Q, UPPER_Q],
        "risk_definition": f"P(SE change over 12 months <= {FAST_PROGRESSION_THRESHOLD_D} D)",
        "models": models,
        "background": background,
        "feature_medians": medians,
        "metrics": {
            "regression": metrics,
            "risk": risk_metrics,
            "ablation": ablation,
            "global_importance": importance,
            "split": {
                "strategy": "GroupShuffleSplit by patient_key (no patient in two splits)",
                "train_patients": int(train.patient_key.nunique()),
                "val_patients": int(val.patient_key.nunique()),
                "test_patients": int(test.patient_key.nunique()),
            },
            "n_patients": int(visits["patient_key"].nunique()),
            "n_visits": int(len(visits)),
        },
    }

    args.out.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump(bundle, args.out)
    report = args.out.with_suffix(".metrics.json")
    report.write_text(json.dumps({**bundle["metrics"], "provenance": provenance,
                                 "trained_at": bundle["trained_at"], "model_version": bundle["model_version"]},
                                indent=2, default=str, allow_nan=False), encoding="utf-8")

    print(f"\nSaved model bundle -> {args.out}")
    print(f"Saved metrics       -> {report}")
    print(f"model_version       =  {bundle['model_version']}")
    if bundle["data_is_synthetic"]:
        print("\nNOTE: trained on SYNTHETIC data. These metrics describe a generated "
              "cohort and are not clinical performance figures.")


if __name__ == "__main__":
    main()
