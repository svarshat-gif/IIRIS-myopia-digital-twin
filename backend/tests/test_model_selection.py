"""Forecast anchoring and independent-group selection contracts; artificial test values only."""
import numpy as np
import pytest
from sklearn.dummy import DummyRegressor
from sklearn.linear_model import LogisticRegression

from app.ml import selection, onset, research_models
from scripts.train_expanded_onset import bootstrap_threshold_ci


def test_change_forecast_preserves_observed_patient_level():
    x = np.array([[22., np.nan], [24., np.nan], [26., np.nan], [28., np.nan]])
    model = selection.AnchoredRegressor(DummyRegressor(strategy='mean'), 0).fit(x, x[:, 0] + .2)
    # Absolute eye size differences must not swamp a common observed change.
    np.testing.assert_allclose(model.predict([[21., np.nan], [30., np.nan]]), [21.2, 30.2])
    missing = np.array([[np.nan, np.nan]])
    assert np.isfinite(model.predict(missing)).all()
    assert np.isnan(missing).all()  # fallback leaves unknown input unknown
    with pytest.raises(ValueError, match='Observed training anchors'):
        model.fit(missing, [24.])


def test_selection_folds_keep_every_patient_together(monkeypatch):
    groups = np.repeat(np.arange(8), 3)
    x = np.column_stack([np.arange(24), np.full(24, np.nan)])
    y = x[:, 0] + .1
    checked = []

    def score(model, x_train, y_train, cv, **kwargs):
        assert len(x_train) == 24 and len(y_train) == 24
        for fit, val in cv:
            assert not set(groups[fit]) & set(groups[val])
            assert set(fit) | set(val) == set(range(24))
        checked.append(len(cv))
        return np.full(len(cv), -.1)

    monkeypatch.setattr(selection, 'cross_val_score', score)
    _, report = selection.select_progression(x, y, groups, 0, {})
    assert checked and all(n == 12 for n in checked)
    assert report['folds'] == 12 and 'training-only' in report['criterion']


def test_majority_accuracy_does_not_hide_missed_onsets():
    y = np.array([0] * 108 + [1] * 16)
    m = onset.scores(y, np.full(124, .13))
    assert m['accuracy'] == .871
    assert m['sensitivity'] == 0 and m['balanced_accuracy'] == .5


def test_challenger_cannot_overwrite_released_onset_model():
    with pytest.raises(ValueError, match='separate output'):
        onset.train(search=True)
    with pytest.raises(ValueError, match='overwrite'):
        onset.train(out=onset.MODEL_PATH, search=True)


def test_onset_search_rejects_invented_missing_predictors():
    with pytest.raises(ValueError, match='no imputation'):
        selection.select_onset(np.array([[np.nan]]), np.array([0]))


def test_onset_threshold_selection_honors_sensitivity_floor_without_test_labels():
    y_select = np.array([0, 0, 1, 1, 1])
    p_select = np.array([.05, .2, .55, .7, .9])
    threshold = research_models.sensitivity_threshold(y_select, p_select, minimum_sensitivity=.8)
    assert threshold == .55  # any higher threshold misses too many positive cases
    assert np.sum((y_select == 1) & (p_select >= threshold)) / np.sum(y_select == 1) == 1.0


def test_onset_threshold_selection_rejects_selection_data_without_events():
    with pytest.raises(ValueError, match='positive outcomes'):
        research_models.sensitivity_threshold(np.zeros(5, dtype=int), np.linspace(.1, .5, 5),
                                              minimum_sensitivity=.8)


def test_threshold_bootstrap_resamples_positive_and_negative_subjects_separately():
    y = np.array([0, 0, 1, 1])
    p = np.array([.1, .2, .8, .9])
    ci = bootstrap_threshold_ci(y, p, threshold=.5, repeats=50)
    assert ci == {key: [1.0, 1.0] for key in
                  ('accuracy', 'balanced_accuracy', 'sensitivity', 'specificity')}


def test_probability_calibration_uses_training_oof_scores():
    x = np.arange(40, dtype=float).reshape(-1, 1)
    y = np.array([0] * 20 + [1] * 20)
    model = research_models.SigmoidProbabilityModel(
        LogisticRegression(solver='liblinear', random_state=42)).fit_oof(x, y)
    p = model.predict_proba([[10.], [30.]])[:, 1]
    assert np.isfinite(p).all() and np.all((p >= 0) & (p <= 1))
    with pytest.raises(ValueError, match='two examples'):
        research_models.SigmoidProbabilityModel(LogisticRegression()).fit_oof(x[:21], y[:21])
