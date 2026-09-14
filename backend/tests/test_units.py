"""Unit tests for the pieces the API depends on."""
from __future__ import annotations

import math
from datetime import date

import pytest

from app.agents.llm import verify_numbers
from app.ml.features import build_feature_row
from app.simulator.constraints import ScenarioRejected, validate_scenario


def _visits():
    return [
        {"visit_date": "2025-01-10", "age": 9.0, "spherical_equivalent": -1.0,
         "axial_length": 23.6, "outdoor_min": 60, "screen_time_hours": 4.0,
         "viewing_distance_cm": 30, "treatment": "none"},
        {"visit_date": "2025-07-10", "age": 9.5, "spherical_equivalent": -1.4,
         "axial_length": 23.8, "outdoor_min": 50, "screen_time_hours": 5.0,
         "viewing_distance_cm": 28, "treatment": "none"},
        {"visit_date": "2026-01-10", "age": 10.0, "spherical_equivalent": -1.9,
         "axial_length": 24.05, "outdoor_min": 40, "screen_time_hours": 6.0,
         "viewing_distance_cm": 26, "treatment": "atropine"},
    ]


def test_feature_row_computes_trends():
    row = build_feature_row(_visits(), sex="female", parental_myopia=1)
    assert row["n_visits"] == 3
    assert row["se"] == -1.9
    assert row["delta_se_last"] == pytest.approx(-0.5, abs=1e-6)
    assert row["se_slope_per_year"] < 0        # getting more myopic
    assert row["al_slope_per_year"] > 0        # eye getting longer
    assert row["treatment_atropine"] == 1.0
    assert row["months_since_baseline"] == pytest.approx(12.0, abs=0.5)


def test_missing_values_stay_missing_and_are_not_invented():
    visits = [{"visit_date": "2026-01-10", "spherical_equivalent": -2.0,
               "axial_length": 24.0}]
    row = build_feature_row(visits)
    assert math.isnan(row["outdoor_min"])
    assert math.isnan(row["screen_time_hours"])
    assert math.isnan(row["posture_score"])
    assert row["se"] == -2.0


def test_overrides_only_affect_the_current_visit():
    base = build_feature_row(_visits())
    cf = build_feature_row(_visits(), overrides={"outdoor_min": 150})
    assert base["outdoor_min"] == 40
    assert cf["outdoor_min"] == 150
    # The 3-visit rolling average must move, but not to the override value --
    # history is preserved.
    assert cf["outdoor_mean_3"] != base["outdoor_mean_3"]
    assert cf["outdoor_mean_3"] < 150
    assert cf["se"] == base["se"]      # clinical values untouched


def test_features_are_order_independent():
    shuffled = [_visits()[2], _visits()[0], _visits()[1]]
    assert build_feature_row(shuffled) == build_feature_row(_visits())


def test_constraints_accept_plausible_and_reject_impossible():
    current = {"outdoor_min": 40, "screen_time_hours": 6.0}
    accepted, warnings = validate_scenario({"outdoor_min": 120}, current)
    assert accepted == {"outdoor_min": 120.0}

    with pytest.raises(ScenarioRejected):
        validate_scenario({"outdoor_min": 2000}, current)
    with pytest.raises(ScenarioRejected):
        validate_scenario({"posture_score": 5}, current)      # score is 0-1
    with pytest.raises(ScenarioRejected):
        validate_scenario({"unknown_thing": 1}, current)


def test_constraints_warn_on_extreme_but_possible_change():
    _, warnings = validate_scenario({"outdoor_min": 400}, {"outdoor_min": 20})
    assert warnings and "extrapolating" in warnings[0]


def test_treatment_choice_is_validated():
    accepted, _ = validate_scenario({"treatment": "atropine"}, {"treatment": "none"})
    assert accepted["treatment"] == "atropine"
    with pytest.raises(ScenarioRejected):
        validate_scenario({"treatment": "laser"}, {"treatment": "none"})


def test_llm_guardrail_accepts_traceable_numbers():
    facts = {"prediction": {"se": -2.42, "lower": -2.85, "upper": -2.01},
             "risk": 0.31}
    ok, bad = verify_numbers(
        "The 12-month estimate is -2.42 D (interval -2.85 to -2.01 D), "
        "with a 31% risk of fast progression.", facts)
    assert ok, bad


def test_llm_guardrail_rejects_invented_numbers():
    facts = {"prediction": {"se": -2.42}}
    ok, bad = verify_numbers(
        "The estimate is -2.42 D and axial length will reach 25.87 mm.", facts)
    assert not ok
    assert "25.87" in bad


def test_llm_guardrail_allows_rounding_and_small_counts():
    facts = {"prediction": {"se": -2.418}}
    ok, _ = verify_numbers("Roughly -2.4 D over the next 12 months.", facts)
    assert ok
