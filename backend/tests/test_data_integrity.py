"""Generated values here are isolated test fixtures, never training data."""
from pathlib import Path
import math
import pandas as pd
import pytest
from app.ml.dataset import load_visits, build_supervised_table
from app.ml.features import build_feature_row
from app.ml.train import split_by_patient, verify_training_source


def test_three_way_patient_split_is_disjoint():
    fixture = pd.DataFrame({"patient_key": [str(i) for i in range(50) for _ in range(3)]})
    a, b, c = split_by_patient(fixture)
    assert not set(a.patient_key) & set(b.patient_key)
    assert not set(a.patient_key) & set(c.patient_key)
    assert not set(b.patient_key) & set(c.patient_key)


def test_deployable_training_refuses_synthetic_even_if_renamed(tmp_path):
    with pytest.raises(ValueError, match="Synthetic"):
        verify_training_source(Path("synthetic_cohort.csv"))
    with pytest.raises(ValueError, match="provenance"):
        verify_training_source(tmp_path / "renamed.csv")


def test_relative_time_preserves_missing_dates(tmp_path):
    fixture = pd.DataFrame({"patient_key": ["test"] * 2, "visit_date": [None] * 2,
                            "followup_month": [0, 12], "spherical_equivalent": [-1, -1.5],
                            "axial_length": [24, 24.3]})
    path = tmp_path / "test.csv"
    fixture.to_csv(path, index=False)
    visits = load_visits(path)
    assert visits.visit_date.isna().all()
    table = build_supervised_table(visits)
    assert table.iloc[0].y_se_12m == -1.5
    assert pd.isna(table.iloc[0].screen_time_hours)


def test_ergonomic_composite_requires_all_measured_components():
    row = build_feature_row([{"visit_date": "2020-01-01", "spherical_equivalent": -1,
                              "axial_length": 24, "viewing_distance_cm": 30}])
    assert math.isnan(row["ergonomic_load"])


def test_future_target_does_not_change_features(tmp_path):
    fixture = pd.DataFrame({"patient_key": ["test"] * 2, "visit_date": ["2020-01-01", "2021-01-01"],
                            "spherical_equivalent": [-1, -1.5], "axial_length": [24, 24.3]})
    p = tmp_path / "test.csv"
    fixture.to_csv(p, index=False)
    before = build_supervised_table(load_visits(p))
    fixture.loc[1, "spherical_equivalent"] = -3
    fixture.to_csv(p, index=False)
    after = build_supervised_table(load_visits(p))
    assert before.iloc[0].se == after.iloc[0].se
    assert before.iloc[0].y_se_12m != after.iloc[0].y_se_12m
