"""Model and simulator protocol tests. Artificial values are TEST FIXTURES ONLY."""
import copy
import hashlib
import json
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

    # Exercise real expanded training with the baseline just trained above.
    # Every artifact remains under tmp_path, and no release promotion is requested.
    from app.core.config import settings
    from app.ml import expanded
    from app.ml.dataset import build_supervised_table, load_visits
    from app.ml.features import ALL_FEATURES
    monkeypatch.setattr(settings, 'artifacts_dir', tmp_path)
    monkeypatch.setattr(settings, 'model_bundle_name', 'real_model.joblib')
    baseline_hash = hashlib.sha256(out.read_bytes()).hexdigest()
    sidecar = out.with_suffix('.metrics.json')
    baseline_metrics_hash = hashlib.sha256(sidecar.read_bytes()).hexdigest()
    with pytest.raises(ValueError, match='Explicit promotion'):
        expanded.run(out, include_catboost=False, promote=False)
    assert hashlib.sha256(out.read_bytes()).hexdigest() == baseline_hash

    goal_visits, goal_meta = expanded.checked_table('goal')
    rels_visits, rels_meta = expanded.checked_table('rels')
    assert goal_meta['license'] == rels_meta['license'] == 'CC-BY-4.0'
    assert goal_meta['data_is_synthetic'] is rels_meta['data_is_synthetic'] is False
    assert goal_meta['role'] == '12-month SE/progression model development'
    assert rels_meta['role'] == 'Study-held-out SE/progression evaluation'
    assert goal_visits.patient_key.nunique() == 1610
    assert rels_visits.patient_key.nunique() == 2042
    dims_sets = train.split_by_patient(build_supervised_table(load_visits(data)))
    goal_sets = expanded.split_goal(build_supervised_table(goal_visits))
    combined = [pd.concat([dims, goal], ignore_index=True).dropna(subset=[expanded.TARGET, 'se'])
                for dims, goal in zip(dims_sets, goal_sets)]
    memberships = [set(frame.patient_key) for frame in combined]
    assert all(not memberships[i] & memberships[j] for i in range(3) for j in range(i))
    assert not set.union(*memberships) & set(rels_visits.patient_key)

    selection_groups = []
    select = expanded.select

    def audited_select(*args, **kwargs):
        groups = kwargs.get('groups', args[3] if len(args) > 3 else None)
        selection_groups.append(set(groups))
        return select(*args, **kwargs)

    monkeypatch.setattr(expanded, 'select', audited_select)
    candidate_path = tmp_path / 'candidate.joblib'
    report = expanded.run(candidate_path, include_catboost=False, promote=False)
    assert report['data_is_synthetic'] is False
    assert report['catboost_included'] is False
    assert report['model_version'].startswith('mdt-expanded-')
    assert report['split'] == {name: {'patients': frame.patient_key.nunique(), 'rows': len(frame)}
                               for name, frame in zip(('fit', 'calibration', 'test'), combined)}
    assert len(selection_groups) == 2
    assert all(groups <= memberships[0] for groups in selection_groups)
    assert all(not groups & (memberships[1] | memberships[2] | set(rels_visits.patient_key))
               for groups in selection_groups)
    assert set(report['evaluation']) == {
        'goal_internal', 'dims_reused', 'rels_common_support', 'rels_later_extrapolation'}
    assert report['evaluation']['rels_common_support']['n_patients'] > 0
    assert report['evaluation']['rels_later_extrapolation']['n_patients'] > 0
    assert 'risk_external_gate' in report
    candidate = joblib.load(candidate_path)
    saved_report = json.loads(candidate_path.with_suffix('.metrics.json').read_text(encoding='utf-8'))
    assert candidate['report'] == saved_report == report
    x = combined[2][ALL_FEATURES].head(3).to_numpy(float)
    for model in ('point', 'lower', 'upper'):
        assert np.isfinite(candidate[model].predict(x)).all()
    assert candidate['risk'].predict_proba(x).shape == (len(x), 2)
    assert np.allclose(candidate['risk'].predict_proba(x).sum(axis=1), 1)
    # A passing calibration gate is still insufficient to mutate the released
    # artifact when promote=False. Both original artifacts must be byte-identical.
    assert hashlib.sha256(out.read_bytes()).hexdigest() == baseline_hash
    assert hashlib.sha256(sidecar.read_bytes()).hexdigest() == baseline_metrics_hash
    assert 'expanded_training' not in joblib.load(out)

    recursive_path = tmp_path / 'recursive.joblib'
    recursive = copy.deepcopy(bundle)
    recursive['expanded_training'] = {'model_version': report['model_version']}
    joblib.dump(recursive, recursive_path)
    with monkeypatch.context() as scoped:
        scoped.setattr(settings, 'model_bundle_name', recursive_path.name)
        with pytest.raises(ValueError, match='recursively retrain'):
            expanded.run(tmp_path / 'recursive_candidate.joblib', include_catboost=False, promote=False)
    assert not (tmp_path / 'recursive_candidate.joblib').exists()


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
