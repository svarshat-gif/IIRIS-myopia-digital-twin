"""Importable experimental SE estimators and index-time-only history features.

These classes are research candidates. They do not replace serving artifacts or
provide calibrated intervals. Unknown measurements remain NaN in the design.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from sklearn.base import BaseEstimator, RegressorMixin, clone
from sklearn.pipeline import Pipeline

from app.ml.dataset import _months


def _number(value):
    try:
        result = float(value)
    except (TypeError, ValueError):
        return np.nan
    return result if np.isfinite(result) else np.nan


def _time(visit):
    return visit['visit_date'] if visit.get('visit_date') is not None else float(visit['followup_month'])


def _slope(points):
    if len(points) < 2 or np.ptp([point[0] for point in points]) <= 0:
        return np.nan
    return float(np.polyfit([point[0] for point in points], [point[1] for point in points], 1)[0] * 12)


def enrich_row(base_features, history):
    """Enrich existing live/training features using visits through the index only.

    No future visit, source ID, patient ID, eventual visit count or future
    treatment enters this function. Calculated age is explicitly separate from
    a measured age, and requires a previously recorded age and elapsed time.
    """
    row = dict(base_features)
    if not history:
        return row
    history = [visit if isinstance(visit, dict) else {name: getattr(visit, name, None)
        for name in ('visit_date', 'followup_month', 'spherical_equivalent', 'axial_length', 'age', 'treatment')}
        for visit in history]
    current = history[-1]
    index_time = _time(current)
    points = []
    for visit in history:
        value = _number(visit.get('spherical_equivalent'))
        if np.isfinite(value):
            points.append((_months(index_time, _time(visit)), value))
    row['se_measurements'] = float(len(points))
    row['se_observed_span_months'] = points[-1][0] - points[0][0] if points else np.nan
    row['baseline_se_observed'] = points[0][1] if points else np.nan
    row['se_slope_all'] = _slope(points)
    row['se_slope_last2'] = _slope(points[-2:])
    row['se_slope_previous'] = _slope(points[:-1][-4:])
    row['se_slope_acceleration'] = (row['se_slope_last2'] - row['se_slope_previous']
        if len(points) >= 3 else np.nan)
    gap = _number(row.get('months_since_last_visit'))
    row['se_last_annualized_change'] = _number(row.get('delta_se_last')) * 12 / gap if gap > 0 else np.nan
    row['al_last_annualized_change'] = _number(row.get('delta_al_last')) * 12 / gap if gap > 0 else np.nan
    if len(points) >= 3:
        values = np.array([point[1] for point in points])
        times = np.array([point[0] for point in points])
        row['se_history_residual_std'] = float(np.std(values - np.polyval(np.polyfit(times, values, 1), times)))
    else:
        row['se_history_residual_std'] = np.nan
    age_records = [(visit, _number(visit.get('age'))) for visit in history]
    age_records = [(visit, value) for visit, value in age_records if np.isfinite(value)]
    if age_records:
        visit, value = age_records[-1]
        elapsed = _months(_time(visit), index_time)
        row['last_recorded_age'] = value
        row['months_since_recorded_age'] = elapsed
        row['age_from_recorded_age_and_time'] = value + elapsed / 12
    else:
        row.update(last_recorded_age=np.nan, months_since_recorded_age=np.nan,
                   age_from_recorded_age_and_time=np.nan)
    treatment = current.get('treatment')
    treatment = treatment.lower() if isinstance(treatment, str) and treatment else None
    for name, values in [('dims', {'dims'}), ('orthok', {'ortho_k', 'ortho_k_atropine'}),
                         ('single_vision', {'single_vision', 'none'})]:
        row[f'treatment_{name}_observed'] = float(treatment in values) if treatment is not None else np.nan
    horizon = _number(row.get('horizon_months'))
    row['se_times_horizon'] = _number(row.get('se')) * horizon / 12
    row['recent_rate_times_horizon'] = row['se_last_annualized_change'] * horizon / 12
    return row


class SEChangeRegressor(RegressorMixin, BaseEstimator):
    """Predict measured SE change or annualized rate, anchored on current SE."""
    def __init__(self, estimator, features, target_mode='rate', input_features=None):
        self.estimator = estimator
        self.features = features
        self.target_mode = target_mode
        self.input_features = input_features

    def _frame(self, frame):
        return frame if isinstance(frame, pd.DataFrame) else pd.DataFrame(frame,
            columns=self.input_features if self.input_features is not None else self.features)

    def _design(self, frame, clamp=False):
        frame = self._frame(frame).copy()
        if clamp:
            frame['horizon_months'] = np.minimum(frame.horizon_months, self.max_horizon_)
        if 'se_times_horizon' in self.features:
            frame['se_times_horizon'] = frame.se * frame.horizon_months / 12
        if 'recent_rate_times_horizon' in self.features:
            frame['recent_rate_times_horizon'] = frame.se_last_annualized_change * frame.horizon_months / 12
        return frame[list(self.features)].to_numpy(float)

    def fit(self, frame, y, sample_weight=None):
        frame = self._frame(frame)
        x = self._design(frame)
        anchor = frame['se'].to_numpy(float)
        horizon = frame['horizon_months'].to_numpy(float)
        if not np.isfinite(anchor).all() or not np.all(horizon > 0):
            raise ValueError('Measured anchors and positive observed horizons required')
        self.max_horizon_ = float(horizon.max())
        target = np.asarray(y) - anchor
        if self.target_mode == 'rate':
            target = target * 12 / horizon
        elif self.target_mode != 'change':
            raise ValueError('Unknown target transformation')
        self.estimator_ = clone(self.estimator)
        kwargs = {}
        if sample_weight is not None:
            prefix = self.estimator_.steps[-1][0] + '__' if isinstance(self.estimator_, Pipeline) else ''
            kwargs[prefix + 'sample_weight'] = sample_weight
        self.estimator_.fit(x, target, **kwargs)
        return self

    def predict(self, frame):
        frame = self._frame(frame)
        design = self._design(frame, clamp=True)
        horizon = frame['horizon_months'].to_numpy(float)
        predicted = self.estimator_.predict(design)
        change = predicted * horizon / 12 if self.target_mode == 'rate' else predicted * np.maximum(1., horizon / self.max_horizon_)
        return frame['se'].to_numpy(float) + change


class SEForecastEnsemble(RegressorMixin, BaseEstimator):
    def __init__(self, estimators, weights=None, aggregation='mean'):
        self.estimators = estimators
        self.weights = weights
        self.aggregation = aggregation

    def fit(self, frame, y, sample_weight=None):
        self.estimators_ = [(name, clone(model).fit(frame, y, sample_weight=sample_weight))
                            for name, model in self.estimators]
        return self

    def predict(self, frame):
        predictions = np.array([model.predict(frame) for _, model in self.estimators_])
        if self.aggregation == 'median':
            return np.median(predictions, axis=0)
        return np.average(predictions, axis=0, weights=self.weights)
