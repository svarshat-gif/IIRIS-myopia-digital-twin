"""Training-only model selection; held-out calibration/test rows never enter CV."""
import numpy as np
from sklearn.base import BaseEstimator, RegressorMixin, clone
from sklearn.dummy import DummyRegressor
from sklearn.ensemble import HistGradientBoostingRegressor, HistGradientBoostingClassifier, RandomForestClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.model_selection import GroupKFold, RepeatedStratifiedKFold, cross_val_score
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler
from sklearn.svm import SVC


class AnchoredRegressor(RegressorMixin, BaseEstimator):
    """Predict measured baseline + learned change, with a trained missing-anchor fallback."""
    def __init__(self, estimator, anchor_index):
        self.estimator = estimator
        self.anchor_index = anchor_index

    def fit(self, x, y):
        x = np.asarray(x, dtype=float)
        anchor = x[:, self.anchor_index]
        if not np.isfinite(anchor).all():
            raise ValueError('Observed training anchors are required; do not invent measurements')
        self.estimator_ = clone(self.estimator).fit(x, np.asarray(y) - anchor)
        # Public inputs may omit AL. Use an explicitly trained absolute estimator,
        # not an invented baseline, in that case. Unknown input remains NaN.
        options = self.estimator.get_params()
        quantile = options.get('quantile') if options.get('loss') == 'quantile' else None
        kwargs = {'loss': 'quantile', 'quantile': quantile} if quantile is not None else {}
        self.missing_anchor_model_ = HistGradientBoostingRegressor(max_iter=100,
            max_leaf_nodes=3, min_samples_leaf=3, l2_regularization=10,
            early_stopping=False, random_state=42, **kwargs).fit(x, y)
        self.n_features_in_ = x.shape[1]
        return self

    def predict(self, x):
        x = np.asarray(x, dtype=float)
        anchor = x[:, self.anchor_index]
        result = self.estimator_.predict(x) + anchor
        missing = ~np.isfinite(anchor)
        if missing.any():
            result[missing] = self.missing_anchor_model_.predict(x[missing])
        return result


def progression_candidates(anchor_index, params):
    # A fixed, compact candidate set. It is not expanded after reading test scores.
    return {
        'carry_forward': AnchoredRegressor(DummyRegressor(strategy='constant', constant=0), anchor_index),
        'mean_change': AnchoredRegressor(DummyRegressor(strategy='mean'), anchor_index),
        'change_hgb_regularized': AnchoredRegressor(HistGradientBoostingRegressor(
            **{**params, 'max_leaf_nodes': 3, 'min_samples_leaf': 3, 'l2_regularization': 10}), anchor_index),
        'change_hgb_smooth': AnchoredRegressor(HistGradientBoostingRegressor(
            **{**params, 'max_leaf_nodes': 3, 'min_samples_leaf': 6, 'l2_regularization': 30}), anchor_index),
        'change_hgb_flexible': AnchoredRegressor(HistGradientBoostingRegressor(
            **{**params, 'max_leaf_nodes': 7, 'min_samples_leaf': 3, 'l2_regularization': 1}), anchor_index),
        'absolute_hgb_previous': HistGradientBoostingRegressor(**params),
    }


def select_progression(x, y, groups, anchor_index, params):
    folds = []
    for seed in (41, 42, 43):
        cv = GroupKFold(n_splits=min(4, len(np.unique(groups))), shuffle=True, random_state=seed)
        folds.extend(list(cv.split(x, y, groups)))
    candidates = progression_candidates(anchor_index, params)
    records = []
    for name, model in candidates.items():
        errors = -cross_val_score(model, x, y, cv=folds, scoring='neg_mean_absolute_error', n_jobs=1)
        records.append({'candidate': name, 'mean_cv_mae': round(float(errors.mean()), 6),
                        'std_cv_mae': round(float(errors.std()), 6)})
    chosen = min(records, key=lambda r: r['mean_cv_mae'])['candidate']
    return candidates[chosen], {'selected': chosen, 'criterion': 'Lowest mean training-only patient-grouped CV MAE',
        'folds': len(folds), 'candidates': records}


def onset_candidates():
    candidates = {}
    for c in (.03, .3, 3, 30):
        candidates[f'logistic_C{c:g}'] = make_pipeline(StandardScaler(),
            LogisticRegression(C=c, max_iter=2000, random_state=42))
    for c in (.1, 1, 10, 100):
        candidates[f'rbf_svm_C{c:g}'] = make_pipeline(StandardScaler(), SVC(C=c, gamma='scale'))
    for leaves, l2 in ((3, 10), (5, 10), (9, 1)):
        candidates[f'hgb_{leaves}_l2_{l2}'] = HistGradientBoostingClassifier(max_iter=150,
            max_leaf_nodes=leaves, min_samples_leaf=15, l2_regularization=l2,
            learning_rate=.05, early_stopping=False, random_state=42)
    for leaf in (5, 15):
        candidates[f'random_forest_leaf{leaf}'] = RandomForestClassifier(n_estimators=200,
            min_samples_leaf=leaf, max_features=1.0, random_state=42, n_jobs=1)
    return candidates


def select_onset(x, y, objective='roc_auc'):
    if not np.isfinite(x).all():
        raise ValueError('Selection expects the reviewed complete OLSM measurements; no imputation is performed')
    if objective not in {'roc_auc', 'accuracy'}:
        raise ValueError("objective must be 'roc_auc' or 'accuracy'")
    folds = list(RepeatedStratifiedKFold(n_splits=5, n_repeats=2, random_state=2026).split(x, y))
    candidates, records = onset_candidates(), []
    for name, model in candidates.items():
        values = cross_val_score(model, x, y, cv=folds, scoring=objective, n_jobs=1)
        records.append({f'mean_cv_{objective}': round(float(values.mean()), 6),
                        f'std_cv_{objective}': round(float(values.std()), 6),
                        'candidate': name})
    chosen = max(records, key=lambda r: r[f'mean_cv_{objective}'])['candidate']
    return candidates[chosen], {'selected': chosen,
        'criterion': f'Highest mean training-only repeated stratified CV {objective}',
        'objective': objective, 'threshold': 0.5 if objective == 'accuracy' else None,
        'folds': len(folds), 'candidates': records}
