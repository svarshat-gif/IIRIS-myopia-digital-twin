"""Serving, elapsed-time behavior and record isolation for selectable forecasts."""
from __future__ import annotations

import json
import hashlib
import os
from pathlib import Path
import subprocess
import sys

import numpy as np
import joblib
import pytest
from sklearn.dummy import DummyRegressor
from sqlalchemy import func, select

from app.db.database import SessionLocal
from app.db.models import Observation, Patient, Simulation, TwinVersion
from app.ml import trajectory
from app.ml.features import build_feature_row
from tests.conftest import API, AuthorizedClient
from tests.test_auth import auth, register


def test_rate_regressor_anchors_change_to_elapsed_time_without_mutating_input():
    # A known -0.6 D/year change at two actual follow-up durations.
    x = np.array([[10., -2., 6.], [11., -3., 12.]])
    model = trajectory.HorizonRateRegressor(DummyRegressor()).fit(x, [-2.3, -3.6])
    query = np.array([[10., -2., 1.], [10., -2., 10.], [10., -2., 60.]])
    original = query.copy()
    np.testing.assert_allclose(model.predict(query), [-2.05, -2.5, -5.])
    np.testing.assert_array_equal(query, original)
    with pytest.raises(ValueError, match='measured anchor'):
        model.predict([[10., np.nan, 12.]])
    with pytest.raises(ValueError, match='positive horizon'):
        model.predict([[10., -2., 0.]])


@pytest.fixture
def measured_row():
    return build_feature_row([{'followup_month': 0., 'age': 10.,
        'spherical_equivalent': -1.5, 'axial_length': 23.9, 'treatment': 'none'}])


@pytest.mark.parametrize('months', [1, 2, 6, 10, 24, 30, 36, 48, 60, 120])
def test_real_forecasts_have_every_requested_month_and_ordered_ranges(measured_row, months):
    result = trajectory.forecast(measured_row, months)
    assert result['requested_horizon_months'] == months
    assert list(result['horizons']) == [f'{h}m' for h in range(1, months + 1)]
    assert result['status'] == 'experimental'
    for point in result['horizons'].values():
        for measure in ('se', 'al'):
            value = point[measure]
            assert value['lower'] <= value['value'] <= value['upper']
            assert np.isfinite([value['lower'], value['value'], value['upper']]).all()
            assert value['support']['accuracy_at_this_horizon_established'] is False
    if months > 36 or months < 3:
        assert result['horizons'][f'{months}m']['al']['support']['status'] == 'extrapolated_horizon'
        assert any('coverage are unverified' in message for message in result['warnings'])
    if months == 10:
        assert result['horizons'][f'{months}m']['se']['support']['status'] == 'interpolated_horizon'


@pytest.mark.parametrize('months', [0, 121, -1, 1.5, True, '12'])
def test_forecast_rejects_invalid_durations(measured_row, months):
    with pytest.raises(ValueError, match='integer from 1 to 120'):
        trajectory.forecast(measured_row, months)


def test_missing_axial_length_is_not_invented(measured_row):
    measured_row['al'] = np.nan
    result = trajectory.forecast(measured_row, 24)
    assert all('al' not in point and 'se' in point for point in result['horizons'].values())
    assert any('measured current AL' in message for message in result['warnings'])


def test_artifact_loads_in_a_fresh_serving_process():
    # Catches the __main__.HorizonRateRegressor pickle bug after CLI training.
    script = ('from app.ml.trajectory import load; '
              'import json; b=load(); '
              'print(json.dumps({k:type(v["point"]).__module__ for k,v in b["models"].items()}))')
    env = {**os.environ, 'OMP_NUM_THREADS': '1'}
    result = subprocess.run([sys.executable, '-c', script],
        cwd=Path(__file__).resolve().parents[1], env=env, text=True,
        capture_output=True, timeout=90, check=True)
    assert json.loads(result.stdout) == {'se': 'app.ml.trajectory', 'al': 'app.ml.trajectory'}


def test_cohort_forecast_is_read_only_and_preserves_legacy_snapshot(client, admin_headers, patient):
    private = AuthorizedClient(client, admin_headers)
    path = f'{API}/patients/{patient}'
    before = private.get(f'{path}/twin/versions').json()
    legacy = private.get(f'{path}/prediction').json()
    for months in (1, 10, 24, 60, 120):
        response = private.get(f'{path}/prediction?horizon_months={months}')
        assert response.status_code == 200, response.text
        assert response.json()['requested_horizon_months'] == months
        assert response.json()['twin_version'] == legacy['twin_version']
    assert private.get(f'{path}/twin/versions').json() == before
    assert private.get(f'{path}/prediction').json() == legacy
    assert client.get(f'{path}/prediction?horizon_months=10').status_code == 401


@pytest.mark.parametrize('months', ['0', '121', '-1', '1.5', 'true'])
def test_private_api_rejects_invalid_durations(client, admin_headers, patient, months):
    response = client.get(f'{API}/patients/{patient}/prediction?horizon_months={months}',
                          headers=admin_headers)
    assert response.status_code == 422


def test_personal_forecast_uses_owned_record(client):
    account = register(client, 'selectable-owner@example.com', age=10.)
    headers = auth(account['access_token'])
    response = client.post(f'{API}/me/records', headers=headers, json={
        'visit_date': '2026-01-01', 'spherical_equivalent': -1.5, 'axial_length': 23.9})
    assert response.status_code == 201, response.text
    response = client.get(f'{API}/me/prediction?horizon_months=30', headers=headers)
    assert response.status_code == 200, response.text
    assert response.json()['requested_horizon_months'] == 30
    assert '30m' in response.json()['horizons']
    assert client.get(f'{API}/me/prediction?horizon_months=30').status_code == 401


def _clinical_counts():
    with SessionLocal() as db:
        return [db.scalar(select(func.count()).select_from(model))
                for model in (Patient, Observation, TwinVersion, Simulation)]


def test_public_forecast_does_not_save_inputs_and_preserves_missing_al(client):
    before = _clinical_counts()
    response = client.post(f'{API}/simulator/forecast', json={
        'age': 10, 'spherical_equivalent': -1.5, 'horizon_months': 10})
    assert response.status_code == 200, response.text
    body = response.json()
    assert body['inputs_persisted'] is False
    assert body['requested_horizon_months'] == 10
    assert all('al' not in point for point in body['horizons'].values())
    assert any('one measured starting point' in warning for warning in body['warnings'])
    assert _clinical_counts() == before


@pytest.mark.parametrize('change', [
    {'horizon_months': 0}, {'horizon_months': 121}, {'horizon_months': 1.5},
    {'horizon_months': True}, {'axial_length': 2}, {'age': 0}])
def test_public_forecast_validates_measurements_and_duration(client, change):
    response = client.post(f'{API}/simulator/forecast', json={
        'age': 10, 'spherical_equivalent': -1.5, 'horizon_months': 10, **change})
    assert response.status_code == 422


def test_missing_trajectory_artifact_returns_service_unavailable(client, monkeypatch):
    def missing():
        raise FileNotFoundError('Train the selectable-horizon model')
    monkeypatch.setattr(trajectory, 'load', missing)
    response = client.post(f'{API}/simulator/forecast', json={
        'age': 10, 'spherical_equivalent': -1.5, 'horizon_months': 10})
    assert response.status_code == 503
    assert 'Train the selectable-horizon model' in response.json()['detail']


def test_real_trajectory_training_roundtrip_keeps_release_untouched(tmp_path):
    release = trajectory.MODEL_PATH
    before = hashlib.sha256(release.read_bytes()).hexdigest()
    candidate = tmp_path / 'trajectory_candidate.joblib'
    report = trajectory.train(candidate)
    assert hashlib.sha256(release.read_bytes()).hexdigest() == before
    stored = joblib.load(candidate)
    assert stored['report'] == json.loads(candidate.with_suffix('.metrics.json').read_text())
    assert report['data_is_synthetic'] is False and report['status'] == 'experimental'
    assert {source['id'] for source in report['sources']} == {'dims', 'goal', 'kinoshita'}
    assert report['request_range_months'] == [1, 120]
    # Calibration and evaluation remain separate; AL cannot acquire PLOS labels.
    assert report['metrics']['al']['split_patients'] == {'fit': 51, 'calibration': 25, 'test': 17}
    assert set(report['metrics']['al']['test_by_source']) == {'dims', 'kinoshita'}
    assert set(report['metrics']['se']['test_by_source']) == {'dims', 'goal'}
    assert report['metrics']['se']['external_rels']['overall']['n_patients'] == 1901
    for measure, model in stored['models'].items():
        measured = report['metrics'][measure]['test_overall']
        assert 0 <= measured['tolerance_hit_rates'][str(trajectory.TOLERANCES[measure][0])] <= 1
        assert measured['supported_90_percent_claim'] is False
        assert measured['carry_forward_mae'] >= 0
        assert model['point'].__class__.__module__ == 'app.ml.trajectory'
        assert model['max_horizon_months'] == 36
        assert all(h > 0 for h in model['observed_horizons_months'])
