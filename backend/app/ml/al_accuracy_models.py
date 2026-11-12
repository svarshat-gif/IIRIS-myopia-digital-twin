"""Research-only AL history features and estimators; no released artifact changes.

Age advanced by observed elapsed time is explicitly named as a derived value.
Missing follow-up SE remains missing in source data. The last observed SE and
its age are separate history covariates, never a fabricated current measurement.
"""
from __future__ import annotations

from datetime import date

import numpy as np
import pandas as pd
from sklearn.base import BaseEstimator, RegressorMixin, clone
from sklearn.pipeline import Pipeline

from app.ml.dataset import _months


FEATURES = [
    'al', 'derived_age_years', 'last_observed_se_D',
    'se_measurement_age_months', 'sex_male', 'stable_baseline_al_mm',
    'stable_history_months', 'stable_history_count', 'al_change_stable_mm',
    'recent_al_rate_per_year', 'recent3_al_rate_per_year', 'recent4_al_rate_per_year',
    'full_al_rate_per_year', 'last_al_interval_months', 'treatment_atropine',
    'treatment_dims', 'treatment_ortho_k', 'derived_age_at_target_years',
    'log_horizon_months', 'horizon_months',
]


def _finite(value):
    try:
        value = float(value)
    except (TypeError, ValueError):
        return None
    return value if np.isfinite(value) else None


def _time(visit):
    value = visit.get('visit_date')
    if value is not None and pd.notna(value):
        return date.fromisoformat(value) if isinstance(value, str) else value
    return float(visit['followup_month'])


def _rate(history, count=None):
    history = history[-count:] if count else history
    if len(history) < 2:
        return np.nan
    values = [(_months(_time(history[0]), _time(v)), float(v['axial_length'])) for v in history]
    t, y = np.asarray(values, dtype=float).T
    return float(np.polyfit(t, y, 1)[0] * 12) if np.ptp(t) > 0 else np.nan


def feature_row(history, horizon_months, *, stable_trial=False):
    """Read only index-and-earlier records, with treatment stable after trial month3."""
    current = history[-1]
    current_time = _time(current)
    measured_age = next((v for v in reversed(history) if _finite(v.get('age')) is not None), None)
    derived_age = (float(measured_age['age']) + _months(_time(measured_age), current_time) / 12
                   if measured_age is not None else np.nan)
    measured_se = next((v for v in reversed(history)
                        if _finite(v.get('spherical_equivalent')) is not None), None)
    sex = next((str(v['sex']).lower() for v in reversed(history)
                if isinstance(v.get('sex'), str)), None)
    stable = [v for v in history if _finite(v.get('axial_length')) is not None
              and (not stable_trial or float(v['followup_month']) >= 3)]
    if not stable:
        raise ValueError('A measured stable AL anchor is required')
    treatment = str(current.get('treatment') or '').lower()
    last_interval = _months(_time(stable[-2]), current_time) if len(stable) > 1 else np.nan
    return {
        'al': float(current['axial_length']),
        'derived_age_years': derived_age,
        'last_observed_se_D': float(measured_se['spherical_equivalent']) if measured_se is not None else np.nan,
        'se_measurement_age_months': _months(_time(measured_se), current_time) if measured_se is not None else np.nan,
        'sex_male': 1. if sex in ('m', 'male') else (0. if sex in ('f', 'female') else np.nan),
        'stable_baseline_al_mm': float(stable[0]['axial_length']),
        'stable_history_months': _months(_time(stable[0]), current_time),
        'stable_history_count': float(len(stable)),
        'al_change_stable_mm': float(current['axial_length']) - float(stable[0]['axial_length']),
        'recent_al_rate_per_year': _rate(stable, 2),
        'recent3_al_rate_per_year': _rate(stable, 3),
        'recent4_al_rate_per_year': _rate(stable, 4),
        'full_al_rate_per_year': _rate(stable),
        'last_al_interval_months': last_interval,
        'treatment_atropine': float('atropine' in treatment),
        'treatment_dims': float(treatment == 'dims'),
        'treatment_ortho_k': float(treatment in ('ortho_k', 'ortho_k_atropine')),
        'derived_age_at_target_years': derived_age + horizon_months / 12,
        'log_horizon_months': float(np.log1p(horizon_months)),
        'horizon_months': float(horizon_months),
    }


def enrich_row(base_features, history):
    """Live/training shared history builder; set horizon_months before this call.

    Source identity selects the published trial's stabilization boundary only,
    and is not returned as a predictor. For ordinary clinical histories all
    supplied past AL observations are retained.
    """
    horizon = _finite(base_features.get('horizon_months'))
    if horizon is None or horizon <= 0:
        raise ValueError('Set a positive horizon_months before enriching AL features')
    records = [v if isinstance(v, dict) else {
        key: getattr(v, key, None) for key in (
            'patient_key', 'visit_date', 'followup_month', 'age', 'spherical_equivalent',
            'axial_length', 'sex', 'treatment', 'source')} for v in history]
    if not records:
        raise ValueError('Past history is required for AL feature enrichment')
    records = sorted(records, key=_time)
    trial = any(str(v.get('patient_key', '')).startswith('kinoshita:')
                or 'Kinoshita 2020' in str(v.get('source', '')) for v in records)
    result = {**base_features, **feature_row(records, horizon, stable_trial=trial)}
    if pd.isna(result['sex_male']) and _finite(base_features.get('sex_male')) is not None:
        result['sex_male'] = float(base_features['sex_male'])
    return result


def build_enriched_pairs(visits):
    """Each target is a real future AL. Kinoshita enrollment is never an index."""
    rows = []
    for key, group in visits.groupby('patient_key', sort=False):
        records = group.to_dict('records')
        trial = str(key).startswith('kinoshita:')
        for i, current in enumerate(records[:-1]):
            if trial and current['followup_month'] < 3:
                continue
            if _finite(current.get('axial_length')) is None:
                continue
            past = records[:i + 1]
            for future in records[i + 1:]:
                if _finite(future.get('axial_length')) is None:
                    continue
                horizon = _months(_time(current), _time(future))
                if horizon <= 0:
                    raise ValueError('Observed visit times must strictly increase')
                rows.append({'patient_key': key,
                    'index_followup_month': _months(_time(records[0]), _time(current)),
                    **enrich_row({'horizon_months': horizon}, past),
                    'y_al': float(future['axial_length'])})
    return pd.DataFrame(rows)


build_pairs = build_enriched_pairs


class AnchoredALRegressor(RegressorMixin, BaseEstimator):
    """Forecast AL through an observed-change or annualized-rate model."""
    def __init__(self, estimator, target='rate', anchor_index=0, horizon_index=-1):
        self.estimator = estimator
        self.target = target
        self.anchor_index = anchor_index
        self.horizon_index = horizon_index

    def fit(self, x, y, sample_weight=None):
        x = np.asarray(x, dtype=float)
        horizon, anchor = x[:, self.horizon_index], x[:, self.anchor_index]
        if not np.isfinite(anchor).all() or not np.all(horizon > 0):
            raise ValueError('Measured AL anchors and positive horizons are required')
        target = np.asarray(y, dtype=float) - anchor
        if self.target == 'rate':
            target = target * 12 / horizon
        elif self.target != 'change':
            raise ValueError('Expected rate or change target')
        self.estimator_ = clone(self.estimator)
        parameters = {}
        if sample_weight is not None:
            prefix = self.estimator_.steps[-1][0] + '__' if isinstance(self.estimator_, Pipeline) else ''
            parameters[prefix + 'sample_weight'] = sample_weight
        self.estimator_.fit(x, target, **parameters)
        return self

    def predict(self, x):
        x = np.asarray(x, dtype=float)
        change = self.estimator_.predict(x)
        if self.target == 'rate':
            change = change * x[:, self.horizon_index] / 12
        return x[:, self.anchor_index] + change


class HistoryShrinkageRegressor(RegressorMixin, BaseEstimator):
    """Shrink a measured personal growth rate toward a training-only treatment mean."""
    def __init__(self, blend=.5, rate_feature='recent3_al_rate_per_year'):
        self.blend = blend
        self.rate_feature = rate_feature

    def _treatments(self, x):
        return x[:, FEATURES.index('treatment_dims')] * 2 + x[:, FEATURES.index('treatment_atropine')]

    def fit(self, x, y, sample_weight=None):
        x = np.asarray(x, dtype=float)
        weights = np.ones(len(x)) if sample_weight is None else sample_weight
        rates = (np.asarray(y) - x[:, 0]) * 12 / x[:, -1]
        self.mean_rate_ = float(np.average(rates, weights=weights))
        treatments = self._treatments(x)
        self.treatment_rates_ = {float(t): float(np.average(rates[treatments == t], weights=weights[treatments == t]))
                                 for t in np.unique(treatments)}
        return self

    def predict(self, x):
        x = np.asarray(x, dtype=float)
        prior = np.array([self.treatment_rates_.get(float(t), self.mean_rate_) for t in self._treatments(x)])
        historical = x[:, FEATURES.index(self.rate_feature)]
        rate = np.where(np.isfinite(historical), self.blend * historical + (1 - self.blend) * prior, prior)
        return x[:, 0] + rate * x[:, -1] / 12
