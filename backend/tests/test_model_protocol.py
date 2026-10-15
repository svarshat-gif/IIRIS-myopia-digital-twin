"""Model and simulator protocol tests. Artificial values are TEST FIXTURES ONLY."""
import copy
import sys
from pathlib import Path
import numpy as np
import pandas as pd
import pytest
from app.ml import train, registry
from app.simulator import engine
from app.simulator.constraints import ScenarioRejected


def test_real_training_entrypoint_produces_provenance_and_baseline_report(tmp_path, monkeypatch):
    data = Path(__file__).resolve().parents[1] / 'data/training_visits.csv'
    out = tmp_path / 'real_model.joblib'
    monkeypatch.setattr(sys, 'argv', ['train', '--data', str(data), '--out', str(out)])
    train.main()
    import joblib
    bundle = joblib.load(out)
    assert bundle['data_is_synthetic'] is False
    assert bundle['provenance']['n_patients'] == 20
    for result in bundle['metrics']['regression'].values():
        assert result['calibration_patients'] == 10
        assert result['baselines']['carry_forward']['mae'] >= 0
        assert 'bootstrap_95ci' in result
    assert bundle['metrics']['ablation']['full']['status'] == 'not_evaluable'


def test_cluster_calibration_uses_patients_not_correlated_rows():
    y = np.repeat(np.arange(10), 3).astype(float)
    delta = train.conformal_delta(np.zeros(30), np.ones(30), y, groups=np.repeat(np.arange(10), 3))
    assert delta == 8
    with pytest.raises(ValueError, match='independent'):
        train.conformal_delta(np.zeros(30), np.ones(30), y, groups=np.zeros(30))


def test_risk_classifier_evaluates_independent_test_labels():
    rng = np.random.default_rng(4)
    fixture = pd.DataFrame({'se': rng.normal(size=120)})
    fixture['y_fast_progression'] = (fixture.se < 0).astype(float)
    model, metrics = train.train_risk_classifier(fixture.iloc[:80], fixture.iloc[80:], ['se'])
    assert model is not None
    assert 0 <= metrics['brier'] <= 1
    assert metrics['roc_auc'] > .5


@pytest.fixture
def scenario_fixture(monkeypatch):
    def predict(row):
        exposure = row.get('outdoor_min', 0)
        point = -2 + exposure / 1000
        return {'horizons': {'12m': {'horizon_months': 12,
            'se': {'value': point, 'lower': point - .5, 'upper': point + .5},
            'al': {'value': 24 - exposure / 10000, 'lower': 23, 'upper': 25}}},
            'risk': {'probability': .3, 'band': 'moderate'}, 'model_version': 'unit-fixture'}
    monkeypatch.setattr(registry, 'load_bundle', lambda: {'supported_scenario_inputs': ['outdoor_min']})
    monkeypatch.setattr(registry, 'predict_from_row', predict)
    return {'patient': {'sex': 'female', 'parental_myopia': None},
            'current': {'behaviour': {'outdoor_min': 30}, 'ergonomics': {}, 'treatment': None},
            'history': [{'visit_date': '2020-01-01', 'spherical_equivalent': -2,
                         'axial_length': 24, 'outdoor_min': 30}]}


def test_simulator_clones_state_and_reports_interval_not_causality(scenario_fixture):
    original = copy.deepcopy(scenario_fixture)
    result = engine.simulate(scenario_fixture, {'changes': {'outdoor_min': 120}})
    assert scenario_fixture == original
    assert result['comparison']['12m']['se']['difference'] > 0
    assert result['comparison']['12m']['se']['smaller_than_uncertainty']
    assert result['causal_disclaimer']
    assert result['changed_drivers']


def test_batch_retains_rejections_without_fabricated_results(scenario_fixture):
    result = engine.simulate_many(scenario_fixture, [{'label': 'valid', 'changes': {'outdoor_min': 120}},
        {'label': 'invalid', 'changes': {'outdoor_min': 5000}}])
    assert len(result['scenarios']) == len(result['rejected']) == 1
    sweep = engine.sensitivity_sweep(scenario_fixture, 'outdoor_min', [0, 30, 120, 9999])
    assert len(sweep['points']) == 3
    with pytest.raises(ScenarioRejected):
        engine.sensitivity_sweep(scenario_fixture, 'unknown', [1, 2])


def test_interval_consistency_check_and_risk_bands():
    horizons = {'12m': {'se': {'value': -2, 'lower': -2.5, 'upper': -1.5}}}
    assert 0 <= registry._interval_implied_risk(horizons, {'se': -1}) <= 1
    assert registry._interval_implied_risk(horizons, {'se': None}) is None
    assert [registry.risk_band(x) for x in (.1, .4, .8)] == ['low', 'moderate', 'high']
