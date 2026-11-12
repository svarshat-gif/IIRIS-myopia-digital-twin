"""Fixed research candidate sets and calibration. No evaluation subjects enter selection."""
import numpy as np
from sklearn.base import BaseEstimator, ClassifierMixin, RegressorMixin, clone
from sklearn.dummy import DummyRegressor
from sklearn.ensemble import HistGradientBoostingClassifier, HistGradientBoostingRegressor, RandomForestClassifier
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression, Ridge
from sklearn.metrics import accuracy_score, recall_score, roc_auc_score, mean_absolute_error
from sklearn.model_selection import GroupKFold, StratifiedKFold, cross_val_predict
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler


class SigmoidProbabilityModel(ClassifierMixin, BaseEstimator):
    """Calibrate a fitted base model on separate subjects, preserving input NaNs."""
    def __init__(self, base):
        self.base = base

    def _score(self, x):
        p = np.clip(self.base.predict_proba(x)[:, 1], 1e-6, 1 - 1e-6)
        return np.log(p / (1 - p)).reshape(-1, 1)

    def fit(self, x, y):
        self.calibrator_ = LogisticRegression(C=1., solver='liblinear', random_state=42).fit(self._score(x), y)
        self.classes_ = np.array([0, 1])
        return self

    def fit_oof(self, x, y, folds=5):
        """Calibrate from training-only out-of-fold scores; refit base on all training rows."""
        x, y = np.asarray(x), np.asarray(y, dtype=int)
        counts = np.bincount(y, minlength=2)
        n_splits = min(int(folds), int(counts.min()))
        if n_splits < 2:
            raise ValueError('OOF calibration needs at least two examples of each class')
        cv = StratifiedKFold(n_splits=n_splits, shuffle=True, random_state=2026)
        oof = cross_val_predict(self.base, x, y, cv=cv, method='predict_proba', n_jobs=1)[:, 1]
        oof = np.clip(oof, 1e-6, 1 - 1e-6)
        scores = np.log(oof / (1 - oof)).reshape(-1, 1)
        self.calibrator_ = LogisticRegression(C=1., solver='liblinear', random_state=42).fit(scores, y)
        self.base = clone(self.base).fit(x, y)
        self.classes_ = np.array([0, 1])
        return self

    def predict_proba(self, x):
        return self.calibrator_.predict_proba(self._score(x))


class ChangeRegressor(RegressorMixin, BaseEstimator):
    """Fit observed change and add the measured SE. SE is required at prediction."""
    def __init__(self, estimator, anchor_index):
        self.estimator, self.anchor_index = estimator, anchor_index

    def fit(self, x, y):
        x = np.asarray(x)
        if not np.isfinite(x[:, self.anchor_index]).all():
            raise ValueError('A measured baseline SE is required')
        self.estimator_ = clone(self.estimator).fit(x, y - x[:, self.anchor_index])
        return self

    def predict(self, x):
        x = np.asarray(x)
        if not np.isfinite(x[:, self.anchor_index]).all():
            raise ValueError('A measured baseline SE is required')
        return self.estimator_.predict(x) + x[:, self.anchor_index]


class LinearHistoryRegressor(RegressorMixin, BaseEstimator):
    def __init__(self, anchor_index, slope_index):
        self.anchor_index, self.slope_index = anchor_index, slope_index

    def fit(self, x, y):
        delta = y - x[:, self.anchor_index]
        self.mean_change_ = float(np.mean(delta))
        return self

    def predict(self, x):
        x = np.asarray(x)
        change = x[:, self.slope_index]
        return x[:, self.anchor_index] + np.where(np.isfinite(change), change, self.mean_change_)


def classifiers(include_catboost=True):
    models = {}
    for c in (.03, .3, 3):
        for weight in (None, 'balanced'):
            models[f'logistic_C{c}_{weight}'] = make_pipeline(
                SimpleImputer(strategy='median', add_indicator=True, keep_empty_features=True),
                StandardScaler(), LogisticRegression(C=c, class_weight=weight,
                    solver='liblinear', max_iter=2000, random_state=42))
    for leaves in (3, 7):
        for l2 in (1, 10):
            models[f'hgb_{leaves}_l2_{l2}'] = HistGradientBoostingClassifier(
                max_iter=300, max_leaf_nodes=leaves, min_samples_leaf=10, l2_regularization=l2,
                learning_rate=.03, early_stopping=False, random_state=42)
    for leaf in (3, 10):
        models[f'rf_leaf{leaf}'] = make_pipeline(
            SimpleImputer(strategy='median', add_indicator=True, keep_empty_features=True),
            RandomForestClassifier(n_estimators=400, min_samples_leaf=leaf, n_jobs=1, random_state=42))
    if include_catboost:
        from catboost import CatBoostClassifier
        for depth in (3, 5, 7):
            for l2 in (3, 10):
                models[f'catboost_depth{depth}_l2_{l2}'] = CatBoostClassifier(iterations=600,
                    depth=depth, learning_rate=.03, l2_leaf_reg=l2, random_seed=42,
                    verbose=False, thread_count=1, allow_writing_files=False)
    return models


def regressors(features, include_catboost=True):
    anchor = features.index('se')
    wrap = lambda model: ChangeRegressor(model, anchor)  # noqa: E731
    models = {'carry_forward': wrap(DummyRegressor(strategy='constant', constant=0)),
              'mean_change': wrap(DummyRegressor(strategy='mean')),
              'linear_history': LinearHistoryRegressor(anchor, features.index('se_slope_per_year'))}
    for alpha in (1., 10.):
        models[f'change_ridge_{alpha}'] = wrap(make_pipeline(
            SimpleImputer(strategy='median', add_indicator=True, keep_empty_features=True),
            StandardScaler(), Ridge(alpha=alpha)))
    for leaves in (3, 7, 15):
        for l2 in (1, 10):
            models[f'change_hgb_{leaves}_l2_{l2}'] = wrap(HistGradientBoostingRegressor(
                max_iter=300, max_leaf_nodes=leaves, min_samples_leaf=20, learning_rate=.03,
                l2_regularization=l2, early_stopping=False, random_state=42))
    if include_catboost:
        from catboost import CatBoostRegressor
        for depth in (3, 5, 7):
            for l2 in (3, 10):
                models[f'change_catboost_depth{depth}_l2_{l2}'] = wrap(CatBoostRegressor(
                    iterations=600, depth=depth, learning_rate=.03, l2_leaf_reg=l2,
                    random_seed=42, verbose=False, thread_count=1, allow_writing_files=False))
    return models


def select(models, x, y, groups=None, regression=False):
    folds = list(GroupKFold(n_splits=5, shuffle=True, random_state=2026).split(x, y, groups)) if groups is not None else list(
        StratifiedKFold(n_splits=5, shuffle=True, random_state=2026).split(x, y))
    records = []
    for name, model in models.items():
        values = []
        for fit, val in folds:
            fitted = clone(model).fit(x[fit], y[fit])
            value = mean_absolute_error(y[val], fitted.predict(x[val])) if regression else roc_auc_score(
                y[val], fitted.predict_proba(x[val])[:, 1])
            values.append(value)
        record = {'candidate': name, 'mean_cv_score': float(np.mean(values)), 'std_cv_score': float(np.std(values))}
        records.append(record)
        print(name, round(record['mean_cv_score'], 5), flush=True)
    selected = (min if regression else max)(records, key=lambda r: r['mean_cv_score'])['candidate']
    return clone(models[selected]), {'selected': selected,
        'criterion': 'Training-only grouped CV MAE' if regression else 'Training-only CV ROC AUC',
        'folds': 5, 'candidates': records}


def calibration_threshold(y, p):
    """Legacy accuracy threshold constrained to at least 50% sensitivity."""
    candidates = np.unique(np.r_[0., p, 1.])
    valid = [(accuracy_score(y, p >= t), recall_score(y, p >= t, zero_division=0), float(t))
             for t in candidates if recall_score(y, p >= t, zero_division=0) >= .5]
    return max(valid, key=lambda item: (item[0], item[1], -item[2]))[2]


def sensitivity_threshold(y, p, minimum_sensitivity=.8):
    """Choose the most specific threshold meeting a sensitivity floor on calibration data.

    The locked test set must only be used to report the resulting trade-off. This
    policy avoids optimizing raw accuracy under class imbalance.
    """
    y = np.asarray(y, dtype=int)
    p = np.asarray(p, dtype=float)
    if y.ndim != 1 or p.ndim != 1 or len(y) != len(p) or len(y) == 0:
        raise ValueError('y and p must be non-empty one-dimensional arrays of equal length')
    if not np.isin(y, [0, 1]).all() or not np.isfinite(p).all() or ((p < 0) | (p > 1)).any():
        raise ValueError('Expected binary labels and finite probabilities in [0, 1]')
    if not 0 <= minimum_sensitivity <= 1:
        raise ValueError('minimum_sensitivity must be between 0 and 1')
    if not np.any(y == 1):
        raise ValueError('Calibration data must include positive outcomes')

    # nextafter(max(p), +inf) allows the all-negative operating point when the
    # requested sensitivity floor is zero; min(p) always allows all-positive.
    candidates = np.unique(np.r_[np.min(p), p, np.nextafter(np.max(p), np.inf)])
    eligible = []
    for threshold in candidates:
        sensitivity = recall_score(y, p >= threshold, zero_division=0)
        if sensitivity >= minimum_sensitivity:
            eligible.append(float(threshold))
    if not eligible:
        raise ValueError('No calibration threshold meets the requested sensitivity floor')
    # Higher thresholds predict fewer positives and therefore maximize
    # specificity while preserving the requested calibration sensitivity.
    return max(eligible)
