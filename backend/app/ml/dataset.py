"""Turn a long-format visit table into supervised learning rows.

Input contract (one row per patient-visit) is documented in docs/DATA_ONBOARDING.md.
Required: patient_key, visit_date, spherical_equivalent, axial_length.
Everything else is optional and stays missing when absent.

For every visit we build features from that patient's history UP TO AND INCLUDING
that visit, then look forward for a follow-up visit near +6 and +12 months to use
as the target. No future information ever leaks into the features.
"""
from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from app.ml.features import ALL_FEATURES, build_feature_row

HORIZONS = (6, 12)
HORIZON_TOLERANCE_MONTHS = 2.75
# A visit is labelled "fast progression" if SE drops by at least this much over 12 months.
# -0.50 D/year is the cutoff most commonly used in the myopia-control literature.
FAST_PROGRESSION_THRESHOLD_D = -0.50

REQUIRED_COLUMNS = ["patient_key", "visit_date", "spherical_equivalent", "axial_length"]
OPTIONAL_COLUMNS = [
    "age", "sex", "parental_myopia", "visual_acuity", "corneal_curvature", "treatment",
    "screen_time_hours", "near_work_min", "outdoor_min", "sleep_hours",
    "viewing_distance_cm", "posture_score", "continuous_session_min", "source",
]


def load_visits(csv_path: str | Path) -> pd.DataFrame:
    df = pd.read_csv(csv_path)
    missing = [c for c in REQUIRED_COLUMNS if c not in df.columns]
    if missing:
        raise ValueError(f"{csv_path}: missing required column(s): {missing}")
    for col in OPTIONAL_COLUMNS:
        if col not in df.columns:
            df[col] = np.nan
    dates = pd.to_datetime(df["visit_date"], errors="raise")
    if (dates.dropna() > pd.Timestamp(date.today())).any():
        raise ValueError("visit_date cannot be in the future")
    df["visit_date"] = pd.Series([d.date() if pd.notna(d) else None for d in dates], dtype=object)
    if "followup_month" not in df:
        df["followup_month"] = np.nan
    if (df.visit_date.isna() & df.followup_month.isna()).any():
        raise ValueError("Every visit needs a real date or source-recorded followup_month")
    if df.patient_key.isna().any():
        raise ValueError("Missing patient_key")
    for col, low, high in [("spherical_equivalent", -30, 15), ("axial_length", 15, 35),
                           ("age", 0, 120), ("visual_acuity", -.3, 2), ("posture_score", 0, 1),
                           ("followup_month", 0, 600)]:
        df[col] = pd.to_numeric(df[col], errors="raise")
        if (~df[col].dropna().between(low, high)).any():
            raise ValueError(f"{col} outside [{low}, {high}]")
    if df.duplicated(["patient_key", "visit_date", "followup_month"]).any():
        raise ValueError("Duplicate patient visit")
    df = df.dropna(subset=["spherical_equivalent", "axial_length"])
    df = df.sort_values(["patient_key", "visit_date", "followup_month"]).reset_index(drop=True)
    return df


def _months(a: date, b: date) -> float:
    if isinstance(a, (int, float)) and isinstance(b, (int, float)):
        return float(b - a)
    return (b - a).days / 30.4375


def _nearest_future(months_ahead: list[float], target: float) -> int | None:
    best, best_gap = None, HORIZON_TOLERANCE_MONTHS
    for i, m in enumerate(months_ahead):
        gap = abs(m - target)
        if gap <= best_gap:
            best, best_gap = i, gap
    return best


def build_supervised_table(df: pd.DataFrame) -> pd.DataFrame:
    """Return one row per (patient, index visit) with features + horizon targets."""
    records: list[dict[str, Any]] = []

    for patient_key, group in df.groupby("patient_key", sort=False):
        visits = group.to_dict("records")
        sex = next((v.get("sex") for v in visits if isinstance(v.get("sex"), str)), None)
        parental = next(
            (int(v["parental_myopia"]) for v in visits
             if pd.notna(v.get("parental_myopia"))), None
        )

        for i, current in enumerate(visits):
            history = visits[: i + 1]
            try:
                row = build_feature_row(history, sex=sex, parental_myopia=parental)
            except ValueError:
                continue

            record: dict[str, Any] = {
                "patient_key": patient_key,
                "visit_date": current["visit_date"],
                **row,
            }

            future = visits[i + 1:]
            offsets = [_months(current["visit_date"] or current["followup_month"],
                               v["visit_date"] or v["followup_month"]) for v in future]
            for h in HORIZONS:
                j = _nearest_future(offsets, float(h))
                if j is None:
                    record[f"y_se_{h}m"] = np.nan
                    record[f"y_al_{h}m"] = np.nan
                    continue
                record[f"y_se_{h}m"] = float(future[j]["spherical_equivalent"])
                record[f"y_al_{h}m"] = float(future[j]["axial_length"])

            se12 = record.get("y_se_12m")
            record["y_fast_progression"] = (
                np.nan if pd.isna(se12)
                else float((se12 - current["spherical_equivalent"]) <= FAST_PROGRESSION_THRESHOLD_D)
            )
            records.append(record)

    return pd.DataFrame.from_records(records)


def target_columns() -> list[str]:
    return [f"y_{m}_{h}m" for m in ("se", "al") for h in HORIZONS]


def feature_matrix(table: pd.DataFrame, feature_names: list[str] | None = None) -> np.ndarray:
    names = feature_names or ALL_FEATURES
    return table.reindex(columns=names).to_numpy(dtype=float)
