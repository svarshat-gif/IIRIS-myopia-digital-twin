"""Research-only AL and SE estimator contracts."""
import numpy as np
import pandas as pd
from sklearn.dummy import DummyRegressor
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

from app.ml import al_accuracy_models as al_models
from app.ml import se_accuracy_models as se_models


def _visit(month, *, al=None, se=None, age=None, treatment='dims', patient='patient'):
    return {
        'patient_key': patient,
        'followup_month': month,
        'axial_length': al,
        'spherical_equivalent': se,
        'age': age,
        'sex': 'F',
        'treatment': treatment,
    }


def test_al_history_features_use_measured_history_and_trial_stabilization():
    history = [
        _visit(0, al=24.0, se=-1.0, age=8.0, treatment='ortho_k_atropine',
               patient='kinoshita:ortho_k_atropine:1'),
        _visit(3, al=24.05, se=-1.1, treatment='ortho_k_atropine',
               patient='kinoshita:ortho_k_atropine:1'),
        _visit(9, al=24.2, se=None, treatment='ortho_k_atropine',
               patient='kinoshita:ortho_k_atropine:1'),
    ]

    row = al_models.enrich_row({'horizon_months': 6, 'sex_male': np.nan}, history)

    assert row['stable_baseline_al_mm'] == 24.05
    assert row['stable_history_count'] == 2
    assert row['derived_age_years'] == 8.75
    assert row['derived_age_at_target_years'] == 9.25
    assert row['last_observed_se_D'] == -1.1
    assert row['sex_male'] == 0
    assert row['treatment_atropine'] == 1
    assert row['treatment_ortho_k'] == 1


def test_al_pairs_use_observed_future_labels_and_anchored_estimators():
    visits = pd.DataFrame([
        _visit(0, al=24.0, se=-1.0),
        _visit(6, al=24.1, se=-1.2),
        _visit(12, al=24.25, se=-1.4),
    ])
    pairs = al_models.build_pairs(visits)
    assert pairs.horizon_months.tolist() == [6.0, 12.0, 6.0]
    assert pairs.y_al.tolist() == [24.1, 24.25, 24.25]

    x = np.zeros((3, len(al_models.FEATURES)))
    x[:, 0] = pairs.al
    x[:, -1] = pairs.horizon_months
    x[:, al_models.FEATURES.index('treatment_dims')] = 1
    x[:, al_models.FEATURES.index('recent3_al_rate_per_year')] = [.2, .3, .4]
    y = x[:, 0] + .2 * x[:, -1] / 12
    model = al_models.AnchoredALRegressor(DummyRegressor()).fit(x, y)
    np.testing.assert_allclose(model.predict(x), x[:, 0] + .2 * x[:, -1] / 12)

    shrinkage = al_models.HistoryShrinkageRegressor(blend=.5).fit(
        x, pairs.y_al, sample_weight=np.ones(len(x)))
    assert np.isfinite(shrinkage.predict(x)).all()


def test_se_history_features_do_not_fill_unmeasured_followup():
    history = [
        _visit(0, al=24.0, se=-1.0, age=8.0),
        _visit(6, al=24.1, se=-1.2),
        _visit(12, al=24.2, se=-1.5),
    ]
    row = se_models.enrich_row({
        'se': -1.5,
        'horizon_months': 12,
        'months_since_last_visit': 6,
        'delta_se_last': -.3,
        'delta_al_last': .1,
    }, history)

    assert row['se_measurements'] == 3
    assert row['baseline_se_observed'] == -1.0
    assert row['se_observed_span_months'] == 12
    assert row['age_from_recorded_age_and_time'] == 9.0
    assert row['treatment_dims_observed'] == 1
    assert row['se_last_annualized_change'] == -.6
    assert row['se_times_horizon'] == -1.5


def test_se_change_regressor_clones_pipeline_and_anchors_predictions():
    features = ['se', 'horizon_months', 'se_times_horizon',
                'se_last_annualized_change', 'recent_rate_times_horizon']
    frame = pd.DataFrame([
        [-1.0, 6.0, 0.0, -.2, 0.0],
        [-2.0, 12.0, 0.0, -.4, 0.0],
    ], columns=features)
    target = np.array([-1.2, -2.4])
    estimator = Pipeline([('scale', StandardScaler()), ('regressor', DummyRegressor())])
    model = se_models.SEChangeRegressor(estimator, features).fit(
        frame, target, sample_weight=np.array([1.0, 2.0]))

    prediction = model.predict(pd.DataFrame([[-3.0, 6.0, 0.0, -.6, 0.0]], columns=features))
    assert prediction[0] == -3.2
    assert model.max_horizon_ == 12


def test_se_ensemble_supports_median_and_weighted_mean():
    features = ['se', 'horizon_months', 'se_times_horizon']
    frame = pd.DataFrame([[-1.0, 6.0, 0.0], [-2.0, 12.0, 0.0]], columns=features)
    target = np.array([-1.1, -2.3])
    estimators = [
        (name, se_models.SEChangeRegressor(DummyRegressor(), features))
        for name in ('first', 'second')
    ]
    for aggregation in ('median', 'mean'):
        ensemble = se_models.SEForecastEnsemble(estimators, aggregation=aggregation).fit(frame, target)
        assert np.isfinite(ensemble.predict(frame)).all()
