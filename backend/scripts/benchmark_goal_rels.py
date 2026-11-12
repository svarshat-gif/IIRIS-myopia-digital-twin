"""Leave-one-cohort-out 12-month SE benchmark for the licensed GOAL and RELS data."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.base import BaseEstimator, RegressorMixin, clone
from sklearn.dummy import DummyRegressor
from sklearn.impute import SimpleImputer
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score
from sklearn.model_selection import GroupKFold
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler
from sklearn.linear_model import Ridge

ROOT = Path(__file__).resolve().parents[1]
TABLES = ROOT / 'data/research'
OUT = ROOT.parent.parent / '.tools/model-improvement'
FEATURES = ['current_se', 'last_change', 'mean_change_per_year', 'history_visits']


class ChangeRegressor(RegressorMixin, BaseEstimator):
    """Predict future SE change, anchored to the current measured SE."""
    def __init__(self, estimator):
        self.estimator = estimator

    def fit(self, x, y):
        x = np.asarray(x, dtype=float)
        self.estimator_ = clone(self.estimator).fit(x, np.asarray(y) - x[:, 0])
        self.n_features_in_ = x.shape[1]
        return self

    def predict(self, x):
        x = np.asarray(x, dtype=float)
        return x[:, 0] + self.estimator_.predict(x)


class LastChangeEstimator(RegressorMixin, BaseEstimator):
    """Use only the most recent observed annual change, with a training median fallback."""
    def fit(self, x, y):
        changes = np.asarray(x, dtype=float)[:, 1]
        self.fallback_ = float(np.nanmedian(changes)) if np.isfinite(changes).any() else 0.0
        return self

    def predict(self, x):
        changes = np.asarray(x, dtype=float)[:, 1]
        return np.where(np.isfinite(changes), changes, self.fallback_)


def transitions(cohort: str) -> pd.DataFrame:
    visits = pd.read_csv(TABLES / f'{cohort.lower()}_visits.csv')
    rows = []
    for key, patient in visits.groupby('patient_key', sort=False):
        patient = patient.sort_values('followup_month')
        records = patient.to_dict('records')
        for index, (current, future) in enumerate(zip(records, records[1:])):
            months = future['followup_month'] - current['followup_month']
            current_se, future_se = current['spherical_equivalent'], future['spherical_equivalent']
            if not (np.isclose(months, 12) and pd.notna(current_se) and pd.notna(future_se)):
                continue
            history = [r['spherical_equivalent'] for r in records[:index + 1]
                       if pd.notna(r['spherical_equivalent'])]
            changes = np.diff(history) if len(history) > 1 else np.array([])
            rows.append({'patient_key': key,
                'current_se': float(current_se),
                'last_change': float(changes[-1]) if len(changes) else np.nan,
                'mean_change_per_year': float(np.mean(changes)) if len(changes) else np.nan,
                'history_visits': len(history),
                'target_se': float(future_se)})
    return pd.DataFrame(rows)


def candidates():
    return {
        'carry_forward': ChangeRegressor(DummyRegressor(strategy='constant', constant=0)),
        'mean_training_change': ChangeRegressor(DummyRegressor(strategy='mean')),
        'last_observed_change': ChangeRegressor(LastChangeEstimator()),
        'ridge_change': ChangeRegressor(make_pipeline(SimpleImputer(strategy='median', keep_empty_features=True),
            StandardScaler(), Ridge(alpha=10))),
    }


def metric_set(y, p, groups, bootstrap=True):
    absolute = np.abs(y - p)
    result = {'n_transitions': int(len(y)), 'mae_d': round(float(mean_absolute_error(y, p)), 4),
        'rmse_d': round(float(np.sqrt(mean_squared_error(y, p))), 4),
        'r2': round(float(r2_score(y, p)), 4),
        'within_0_75d_pct': round(float(np.mean(absolute <= .75) * 100), 2)}
    if bootstrap:
        groups = np.asarray(groups)
        keys, inverse = np.unique(groups, return_inverse=True)
        group_indices = [np.flatnonzero(inverse == i) for i in range(len(keys))]
        rng = np.random.default_rng(42)
        values = {name: [] for name in ('mae_d', 'rmse_d', 'within_0_75d_pct')}
        for _ in range(300):
            sample_groups = rng.integers(0, len(keys), len(keys))
            indices = np.concatenate([group_indices[i] for i in sample_groups])
            yy, pp = y[indices], p[indices]
            values['mae_d'].append(mean_absolute_error(yy, pp))
            values['rmse_d'].append(np.sqrt(mean_squared_error(yy, pp)))
            values['within_0_75d_pct'].append(np.mean(np.abs(yy - pp) <= .75) * 100)
        result['patient_cluster_bootstrap_95ci'] = {
            key: [round(float(v), 2) for v in np.quantile(scores, [.025, .975])]
            for key, scores in values.items()}
    return result


def run():
    sources = json.loads((ROOT / 'data/open/research_sources.json').read_text(encoding='utf-8'))
    source = sources['goal_rels']
    workbook = ROOT / 'data/open/goal_rels/goal_rels.xlsx'
    if source['license'] != 'CC-BY-4.0' or hashlib.sha256(workbook.read_bytes()).hexdigest() != source['files']['goal_rels.xlsx']:
        raise ValueError('GOAL/RELS source license or checksum verification failed')
    OUT.mkdir(parents=True, exist_ok=True)
    report = {'source_url': source['source_url'], 'license': source['license'],
        'source_paper': 'https://journals.plos.org/plosmedicine/article?id=10.1371/journal.pmed.1002674',
        'endpoint': 'Next annual right-eye cycloplegic spherical-equivalent refraction',
        'feature_policy': 'Current/past measured SE only; no birth date, future measurement, treatment assignment, axial length or fabricated age.',
        'selection': 'Lowest mean patient-grouped 3-fold CV MAE within training cohort; fixed four transparent candidates.',
        'external_validation': 'Train one population cohort; evaluate on the other, then reverse direction. Subject IDs are disjoint by cohort.',
        'limitations': ['The GOAL workbook does not disclose randomized outdoor-treatment allocation; no intervention effect is estimated.',
            'No axial-length data in the released cohorts; this benchmark evaluates SE only.',
            'This separate population-cohort benchmark does not validate or replace the DIMS-treated twin.',
            'The 0.75 D error tolerance is reported as a descriptive hit rate, not generic model accuracy.'],
        'directions': {}}
    for train_name, test_name in [('rels', 'goal'), ('goal', 'rels')]:
        train, test = transitions(train_name), transitions(test_name)
        x_train, y_train = train[FEATURES].to_numpy(float), train.target_se.to_numpy(float)
        x_test, y_test = test[FEATURES].to_numpy(float), test.target_se.to_numpy(float)
        groups = train.patient_key.to_numpy()
        folds = list(GroupKFold(n_splits=3).split(x_train, y_train, groups))
        scores, fitted = {}, {}
        for name, model in candidates().items():
            fold_mae = []
            for train_index, validation_index in folds:
                fold_model = clone(model)
                fold_model.fit(x_train[train_index], y_train[train_index])
                fold_mae.append(mean_absolute_error(y_train[validation_index],
                                                    fold_model.predict(x_train[validation_index])))
            model.fit(x_train, y_train)
            fitted[name] = model
            scores[name] = {'mean_cv_mae_d': round(float(np.mean(fold_mae)), 4),
                            'std_cv_mae_d': round(float(np.std(fold_mae)), 4)}
        chosen = min(scores, key=lambda name: scores[name]['mean_cv_mae_d'])
        pred = fitted[chosen].predict(x_test)
        result = {'training_cohort': train_name.upper(), 'test_cohort': test_name.upper(),
            'training_patients': int(train.patient_key.nunique()),
            'test_patients': int(test.patient_key.nunique()),
            'training_transitions': len(train), 'test_transitions': len(test),
            'selected_model': chosen, 'training_only_selection': scores,
            'external_test': metric_set(y_test, pred, test.patient_key.to_numpy()),
            'baselines': {'carry_forward': metric_set(y_test, x_test[:, 0], test.patient_key.to_numpy(), bootstrap=False),
                'last_observed_change': metric_set(y_test,
                    x_test[:, 0] + np.nan_to_num(x_test[:, 1], nan=0.0), test.patient_key.to_numpy(), bootstrap=False)}}
        report['directions'][f'{train_name}_to_{test_name}'] = result
        joblib.dump({'model': fitted[chosen], 'features': FEATURES, 'report': result},
                    OUT / f'{train_name}_to_{test_name}_annual_se.joblib')
    (OUT / 'goal_rels_benchmark.json').write_text(json.dumps(report, indent=2, allow_nan=False), encoding='utf-8')
    return report


if __name__ == '__main__':
    print(json.dumps(run(), indent=2))
