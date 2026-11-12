"""Patient-grouped, time-conditioned SE/AL forecasts for selectable months.

Only pairs of actually observed visits supply labels. Intermediate months are
model interpolation and months beyond the observed follow-up are extrapolation.
The nominal interval coverage is not a point-prediction accuracy percentage.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
from functools import lru_cache
import hashlib
import json
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from scipy.stats import beta
from sklearn.base import BaseEstimator, RegressorMixin, clone
from sklearn.dummy import DummyRegressor
from sklearn.ensemble import HistGradientBoostingRegressor
from sklearn.impute import SimpleImputer
from sklearn.linear_model import Ridge
from sklearn.model_selection import GroupKFold, GroupShuffleSplit
from sklearn.pipeline import Pipeline, make_pipeline
from sklearn.preprocessing import StandardScaler

from app.core.config import settings
from app.ml.dataset import load_visits, build_supervised_table, _months
from app.ml.features import build_feature_row
from app.ml import train as fixed

ROOT = Path(__file__).resolve().parents[2]
MODEL_PATH = settings.artifacts_dir / 'trajectory_model.joblib'
MAX_REQUEST_MONTHS = 120
TOLERANCES = {'se': (.50, .75), 'al': (.10, .20)}
FEATURES = {measure: ['age', measure, f'{measure}_slope_per_year',
    f'delta_{measure}_last', 'months_since_last_visit', 'n_visits',
    'months_since_baseline', f'{measure}_since_baseline',
    'treatment_atropine', 'treatment_optical', 'horizon_months'] for measure in ('se', 'al')}


def build_pairs(visits: pd.DataFrame) -> pd.DataFrame:
    """Features stop at the index visit; each label is a real later measurement."""
    rows = []
    for key, group in visits.groupby('patient_key', sort=False):
        history = group.to_dict('records')
        for i, current in enumerate(history[:-1]):
            if str(key).startswith('kinoshita:') and current['followup_month'] < 3:
                # Trial baseline follows three months of OK stabilization;
                # atropine has not started at enrollment in the combination arm.
                continue
            past = history[:i + 1]
            sex = next((v.get('sex') for v in past if isinstance(v.get('sex'), str)), None)
            parental = next((int(v['parental_myopia']) for v in past
                             if pd.notna(v.get('parental_myopia'))), None)
            features = build_feature_row(past, sex=sex, parental_myopia=parental)
            start = current['visit_date'] if current['visit_date'] is not None else current['followup_month']
            for future in history[i + 1:]:
                end = future['visit_date'] if future['visit_date'] is not None else future['followup_month']
                horizon = _months(start, end)
                if horizon <= 0:
                    raise ValueError('Visits must have strictly increasing observed times')
                rows.append({'patient_key': key, 'horizon_months': horizon,
                    **features, 'y_se': future['spherical_equivalent'],
                    'y_al': future['axial_length']})
    return pd.DataFrame(rows)


class HorizonRateRegressor(RegressorMixin, BaseEstimator):
    """Learn annualized change, then add elapsed-time change to the measured anchor."""
    def __init__(self, estimator, anchor_index=1, horizon_index=-1):
        self.estimator, self.anchor_index, self.horizon_index = estimator, anchor_index, horizon_index

    def fit(self, x, y, sample_weight=None):
        x = np.asarray(x, dtype=float)
        horizon = x[:, self.horizon_index]
        if not np.isfinite(x[:, self.anchor_index]).all() or not np.all(horizon > 0):
            raise ValueError('Observed anchors and positive measured horizons are required')
        self.max_horizon_ = float(np.max(horizon))
        self.estimator_ = clone(self.estimator)
        params = {}
        if sample_weight is not None:
            prefix = self.estimator_.steps[-1][0] + '__' if isinstance(self.estimator_, Pipeline) else ''
            params[prefix + 'sample_weight'] = sample_weight
        rate = (np.asarray(y) - x[:, self.anchor_index]) * 12 / horizon
        self.estimator_.fit(x, rate, **params)
        return self

    def predict(self, x):
        x = np.asarray(x, dtype=float)
        horizon = x[:, self.horizon_index]
        if not np.isfinite(x[:, self.anchor_index]).all() or not np.all(horizon > 0):
            raise ValueError('A measured anchor and positive horizon are required')
        design = x.copy()
        # Beyond observed follow-up, retain the learned terminal rate rather
        # than extrapolating a polynomial rate to an unsupported magnitude.
        design[:, self.horizon_index] = np.minimum(horizon, self.max_horizon_)
        return x[:, self.anchor_index] + self.estimator_.predict(design) * horizon / 12


def candidates():
    models = {'carry_forward': DummyRegressor(strategy='constant', constant=0),
              'mean_rate': DummyRegressor(strategy='mean')}
    for alpha in (10., 100.):
        models[f'ridge_rate_{alpha:g}'] = make_pipeline(
            SimpleImputer(strategy='median', add_indicator=True, keep_empty_features=True),
            StandardScaler(), Ridge(alpha=alpha))
    for leaves in (3, 7):
        models[f'hgb_rate_{leaves}'] = HistGradientBoostingRegressor(max_iter=150,
            max_leaf_nodes=leaves, min_samples_leaf=20, l2_regularization=20,
            learning_rate=.04, early_stopping=False, random_state=42)
    return {name: HorizonRateRegressor(model) for name, model in models.items()}


def patient_weights(frame):
    # Long follow-up creates more pairs, not more independent participants.
    return (1 / frame.groupby('patient_key').patient_key.transform('size')).to_numpy(float)


def choose_point(frame, measure):
    x, y = frame[FEATURES[measure]].to_numpy(float), frame[f'y_{measure}'].to_numpy(float)
    groups = frame.patient_key.to_numpy()
    folds = list(GroupKFold(n_splits=min(3, len(np.unique(groups))),
                           shuffle=True, random_state=2026).split(x, y, groups))
    options, records = candidates(), []
    for name, candidate in options.items():
        errors = []
        for fit, val in folds:
            model = clone(candidate).fit(x[fit], y[fit], patient_weights(frame.iloc[fit]))
            absolute = np.abs(y[val] - model.predict(x[val]))
            errors.append(float(pd.Series(absolute).groupby(groups[val]).mean().mean()))
        records.append({'candidate': name, 'patient_mean_cv_mae': float(np.mean(errors))})
    winner = min(records, key=lambda item: item['patient_mean_cv_mae'])['candidate']
    point = options[winner].fit(x, y, patient_weights(frame))
    return point, {'selected': winner, 'criterion': 'Training-only patient-grouped CV; equal patient mean MAE',
                   'folds': len(folds), 'candidates': records}


def _exact_interval(successes, n):
    if n == 0:
        return None
    return [float(beta.ppf(.025, successes, n - successes + 1)) if successes else 0.,
            float(beta.ppf(.975, successes + 1, n - successes)) if successes < n else 1.]


def evaluate(frame, measure, entry, bootstrap_repeats=300):
    sub = frame.dropna(subset=[measure, f'y_{measure}'])
    if sub.empty:
        return {'status': 'not_evaluable'}
    x, y = sub[FEATURES[measure]].to_numpy(float), sub[f'y_{measure}'].to_numpy(float)
    pred = entry['point'].predict(x)
    lo, hi = interval(entry, x)
    error = np.abs(y - pred)
    metrics = fixed.regression_metrics(y, pred)
    if not np.isfinite(metrics['r2']):
        metrics['r2'] = None
    metrics.update(n_patients=int(sub.patient_key.nunique()),
        interval_coverage=float(np.mean((y >= lo) & (y <= hi))),
        mean_interval_width=float(np.mean(hi - lo)),
        carry_forward_mae=float(np.mean(np.abs(y - sub[measure].to_numpy(float)))))
    primary = TOLERANCES[measure][0]
    metrics['tolerance'] = primary
    metrics['tolerance_unit'] = 'D' if measure == 'se' else 'mm'
    metrics['tolerance_hit_rates'] = {str(t): float(np.mean(error <= t)) for t in TOLERANCES[measure]}
    within = pd.Series(error <= primary).groupby(sub.patient_key.to_numpy()).all()
    metrics['patients_all_within_tolerance'] = float(within.mean())
    metrics['patient_all_within_95ci'] = _exact_interval(int(within.sum()), len(within))
    keys, inverse = np.unique(sub.patient_key, return_inverse=True)
    indices = [np.flatnonzero(inverse == i) for i in range(len(keys))]
    rng, boot = np.random.default_rng(42), []
    for _ in range(bootstrap_repeats):
        take = np.concatenate([indices[i] for i in rng.integers(0, len(keys), len(keys))])
        boot.append([float(np.mean(error[take])), float(np.mean(error[take] <= primary))])
    metrics['bootstrap_95ci'] = {name: [float(v) for v in np.quantile(np.asarray(boot)[:, i], [.025, .975])]
                                for i, name in enumerate(('mae', 'tolerance_hit_rate'))}
    metrics['point_estimate_meets_90_percent'] = metrics['tolerance_hit_rates'][str(primary)] >= .90
    metrics['supported_90_percent_claim'] = metrics['patient_all_within_95ci'][0] >= .90
    return metrics


def interval(entry, x):
    pred = entry['point'].predict(x)
    a, b = entry['lower'].predict(x), entry['upper'].predict(x)
    horizon = x[:, -1]
    correction = entry['conformal_delta'] * np.sqrt(horizon / 12)
    lo, hi = np.minimum(a, b) - correction, np.maximum(a, b) + correction
    # This widening is an explicit extrapolation heuristic, not a coverage claim.
    extra = np.sqrt(np.maximum(1., horizon / entry['max_horizon_months']))
    return pred - (pred - np.minimum(lo, pred)) * extra, pred + (np.maximum(hi, pred) - pred) * extra


def source_partitions(visits, source_id):
    pairs = build_pairs(visits)
    if source_id == 'dims':
        sets = fixed.split_by_patient(build_supervised_table(visits))
    elif source_id == 'goal':
        from app.ml.expanded import split_goal
        sets = split_goal(build_supervised_table(visits))
    else:
        groups = pairs.patient_key.to_numpy()
        fitcal, test = next(GroupShuffleSplit(test_size=.2, random_state=42).split(pairs, groups=groups))
        fit, cal = next(GroupShuffleSplit(test_size=.25, random_state=43).split(pairs.iloc[fitcal], groups=groups[fitcal]))
        sets = [pairs.iloc[fitcal[fit]], pairs.iloc[fitcal[cal]], pairs.iloc[test]]
    ids = [set(frame.patient_key) for frame in sets]
    if any(ids[i] & ids[j] for i in range(3) for j in range(i)):
        raise ValueError('Patient overlap between fitting, calibration and test')
    return [pairs[pairs.patient_key.isin(keys)].copy() for keys in ids]


def train(out=MODEL_PATH):
    provenance = fixed.verify_training_source(ROOT / 'data/training_visits.csv')
    dims = load_visits(ROOT / 'data/training_visits.csv')
    from app.ml.expanded import checked_table
    goal, goal_meta = checked_table('goal')
    rels, rels_meta = checked_table('rels')
    sources = [('dims', dims, provenance), ('goal', goal, goal_meta)]
    kino_path = ROOT / 'data/research/kinoshita_visits.csv'
    if kino_path.exists():
        meta = json.loads(kino_path.with_suffix('.provenance.json').read_text(encoding='utf-8'))
        if meta.get('data_is_synthetic') is not False or meta.get('license') != 'CC-BY-4.0':
            raise ValueError('Unverified Kinoshita source')
        if hashlib.sha256(kino_path.read_bytes()).hexdigest() != meta['table_sha256']:
            raise ValueError('Kinoshita table checksum mismatch')
        kino = load_visits(kino_path)
        # No follow-up refraction was published; enrollment SE is a baseline covariate only.
        sources.append(('kinoshita', kino, meta))
    partitions = [[], [], []]
    source_meta = []
    for name, visits, meta in sources:
        source_meta.append({'id': name, 'provenance': meta})
        for i, frame in enumerate(source_partitions(visits, name)):
            frame['source_id'] = name
            if name == 'kinoshita':
                frame['y_se'] = np.nan
            partitions[i].append(frame)
    fit, cal, test = [pd.concat(parts, ignore_index=True) for parts in partitions]
    entries, reports = {}, {}
    for measure in ('se', 'al'):
        f, c, t = [frame.dropna(subset=[measure, f'y_{measure}']).copy() for frame in (fit, cal, test)]
        print('TRAIN', measure, 'patients', f.patient_key.nunique(), c.patient_key.nunique(), t.patient_key.nunique(), flush=True)
        point, selection = choose_point(f, measure)
        x, y = f[FEATURES[measure]].to_numpy(float), f[f'y_{measure}'].to_numpy(float)
        qargs = dict(max_iter=150, max_leaf_nodes=7, min_samples_leaf=20,
            l2_regularization=20, learning_rate=.04, early_stopping=False, random_state=42)
        lower = HorizonRateRegressor(HistGradientBoostingRegressor(loss='quantile', quantile=.05, **qargs)).fit(x, y, patient_weights(f))
        upper = HorizonRateRegressor(HistGradientBoostingRegressor(loss='quantile', quantile=.95, **qargs)).fit(x, y, patient_weights(f))
        xc, yc = c[FEATURES[measure]].to_numpy(float), c[f'y_{measure}'].to_numpy(float)
        a, b = lower.predict(xc), upper.predict(xc)
        scores = np.maximum(np.minimum(a, b) - yc, yc - np.maximum(a, b)) / np.sqrt(xc[:, -1] / 12)
        scores = pd.Series(scores).groupby(c.patient_key.to_numpy()).max().to_numpy()
        if len(scores) < 9:
            raise ValueError('At least nine independent calibration patients are needed')
        quantile = min(1., np.ceil((len(scores) + 1) * .9) / len(scores))
        delta = max(0., float(np.quantile(scores, quantile, method='higher')))
        entry = {'point': point, 'lower': lower, 'upper': upper, 'conformal_delta': delta,
            'features': FEATURES[measure], 'max_horizon_months': float(f.horizon_months.max()),
            'observed_horizons_months': sorted(float(v) for v in f.horizon_months.unique()),
            'training_ranges': {key: [float(f[key].min()), float(f[key].max())]
                                for key in FEATURES[measure][:-1] if f[key].notna().any()}}
        entries[measure] = entry
        report = {'model_selection': selection, 'split_patients': {name: int(frame.patient_key.nunique())
            for name, frame in zip(('fit', 'calibration', 'test'), (f, c, t))},
            'observed_horizons_months': entry['observed_horizons_months'],
            'test_overall': evaluate(t, measure, entry),
            'test_by_horizon': {str(h): evaluate(t[np.isclose(t.horizon_months, h)], measure, entry)
                                for h in sorted(t.horizon_months.unique())},
            'test_by_source': {source: evaluate(t[t.source_id == source], measure, entry)
                                for source in t.source_id.unique()}}
        if measure == 'se':
            external = build_pairs(rels)
            report['external_rels'] = {'overall': evaluate(external, measure, entry),
                'by_horizon': {str(h): evaluate(external[np.isclose(external.horizon_months, h)], measure, entry)
                               for h in sorted(external.horizon_months.unique())},
                'provenance': rels_meta}
        reports[measure] = report
        print('RESULT', measure, json.dumps(report['test_overall']), flush=True)
    stamp = datetime.now(timezone.utc).isoformat()
    fingerprint = Path(__file__).read_bytes() + json.dumps(source_meta, sort_keys=True).encode()
    version = 'trajectory-' + hashlib.sha256(fingerprint).hexdigest()[:12]
    report = {'model_version': version, 'trained_at': stamp, 'data_is_synthetic': False,
        'status': 'experimental',
        'request_range_months': [1, MAX_REQUEST_MONTHS], 'nominal_interval_coverage': .9,
        'sources': source_meta, 'metrics': reports,
        'tolerance_policy': {'se_D': list(TOLERANCES['se']), 'al_mm': list(TOLERANCES['al']),
            'note': 'Fixed development error tolerances; not a clinical acceptance standard. First tolerance is primary. No test-based tolerance changes.'},
        'limitations': ['Only observed visit pairs are labels; unmeasured months are interpolation.',
            'Beyond observed follow-up, terminal learned annualized change is extrapolated and ranges widened heuristically.',
            'A nominal 90% prediction range is not 90% point accuracy; coverage is unverified at unmeasured horizons.',
            'Repeated pairs remain correlated within patients; all splits, CV and confidence intervals use patient groups.',
            'No externally evaluated axial-length cohort is available; source-specific internal test results are reported.',
            'Most AL training participants received orthokeratology with or without atropine; follow-up age was not published in that source.',
            'Pooled SE performance does not establish performance in treated children; the small DIMS source test trails carry-forward.',
            'Current treatment is an observational covariate; treatment changes and causal effects are not modeled.']}
    out = Path(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump({'report': report, 'models': entries}, out)
    out.with_suffix('.metrics.json').write_text(json.dumps(report, indent=2, allow_nan=False), encoding='utf-8')
    load.cache_clear()
    return report


@lru_cache(maxsize=1)
def load():
    if not MODEL_PATH.exists():
        raise FileNotFoundError('Train the selectable-horizon model: python -m app.ml.trajectory')
    bundle = joblib.load(MODEL_PATH)
    if bundle['report'].get('data_is_synthetic') is not False:
        raise ValueError('Synthetic trajectory model refused')
    return bundle


def metadata():
    try:
        return load()['report']
    except FileNotFoundError:
        return {'status': 'not_trained', 'request_range_months': [1, MAX_REQUEST_MONTHS]}


def forecast(row, horizon_months):
    if isinstance(horizon_months, bool) or not isinstance(horizon_months, (int, np.integer)) or not 1 <= horizon_months <= MAX_REQUEST_MONTHS:
        raise ValueError(f'horizon_months must be an integer from 1 to {MAX_REQUEST_MONTHS}')
    bundle = load()
    months = np.arange(1, horizon_months + 1)
    horizons = {f'{h}m': {'horizon_months': int(h)} for h in months}
    warnings = ['Experimental forecast: point accuracy of 90% has not been established.']
    for measure, entry in bundle['models'].items():
        anchor = row.get(measure)
        if anchor is None or not np.isfinite(anchor):
            warnings.append(f'A measured current {measure.upper()} is required for its forecast.')
            continue
        x = np.array([[h if key == 'horizon_months' else row.get(key, np.nan)
                       for key in entry['features']] for h in months], dtype=float)
        point, (lower, upper) = entry['point'].predict(x), interval(entry, x)
        observed = entry['observed_horizons_months']
        minimum = min(observed)
        for i, h in enumerate(months):
            status = ('extrapolated_horizon' if h < minimum or h > entry['max_horizon_months'] else
                      'observed_horizon' if any(abs(h - v) < .25 for v in observed) else 'interpolated_horizon')
            horizons[f'{h}m'][measure] = {'value': round(float(point[i]), 3),
                'lower': round(float(lower[i]), 3), 'upper': round(float(upper[i]), 3),
                'interval_label': 'Estimated range', 'forecast_method': 'time_conditioned_change',
                'support': {'status': status, 'observed_horizons_months': observed,
                    'training_min_horizon_months': minimum,
                    'training_max_horizon_months': entry['max_horizon_months'],
                    'accuracy_at_this_horizon_established': False}}
        if horizon_months < minimum:
            warnings.append(f'{measure.upper()} before {minimum:g} months extrapolates to a shorter horizon; accuracy and range coverage are unverified.')
        elif horizon_months > entry['max_horizon_months']:
            warnings.append(f'{measure.upper()} beyond {entry["max_horizon_months"]:g} months extrapolates the learned rate; accuracy and range coverage are unverified.')
        elif not any(abs(horizon_months - v) < .25 for v in observed):
            warnings.append(f'{measure.upper()} at {horizon_months} months interpolates between observed follow-ups; accuracy at that exact month is unverified.')
        for key, bounds in entry['training_ranges'].items():
            value = row.get(key)
            if value is not None and np.isfinite(value) and not bounds[0] <= value <= bounds[1]:
                warnings.append(f'{key} is outside the {measure.upper()} training range; extrapolation is unreliable.')
    return {'horizons': horizons, 'requested_horizon_months': int(horizon_months),
        'status': 'experimental',
        'model_version': bundle['report']['model_version'], 'risk': None,
        'risk_unavailable_reason': 'The selectable-horizon endpoint forecasts SE and AL; no risk probability is estimated.',
        'warnings': list(dict.fromkeys(warnings)), 'data_source': 'Verified longitudinal observed-visit pairs',
        'nominal_interval_coverage': .9}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', type=Path, default=MODEL_PATH)
    args = parser.parse_args()
    # Import the canonical module even under ``python -m`` so joblib stores an
    # importable class path, never ``__main__.HorizonRateRegressor``.
    from app.ml.trajectory import train as train_importable
    report = train_importable(args.out)
    print('Saved', report['model_version'], 'to', args.out, flush=True)
