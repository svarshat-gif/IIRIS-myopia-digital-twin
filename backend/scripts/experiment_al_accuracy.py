"""Fixed-grid AL research on existing FIT patients only. Never promote a model.

Run from backend: OMP_NUM_THREADS=1 python scripts/experiment_al_accuracy.py
The sole targets are actual measured future AL, at unchanged +/-0.10mm tolerance.
Calibration/test subjects never enter feature building, CV, or model fitting.
"""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import importlib.util
import json
from pathlib import Path
import sys

import joblib
import numpy as np
import pandas as pd
from sklearn.base import clone
from sklearn.ensemble import ExtraTreesRegressor, HistGradientBoostingRegressor, RandomForestRegressor
from sklearn.impute import SimpleImputer
from sklearn.linear_model import ElasticNet, Ridge
from sklearn.model_selection import GroupKFold
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from app.ml import trajectory  # noqa: E402
from app.ml.al_accuracy_models import (  # noqa: E402
    FEATURES, AnchoredALRegressor, HistoryShrinkageRegressor, build_pairs, enrich_row,
)
from app.ml.dataset import load_visits  # noqa: E402
from app.ml.train import verify_training_source  # noqa: E402

TOLERANCE = .10
SEED = 2026
REPORT_PATH = ROOT / 'artifacts/al_accuracy_search.json'
CANDIDATE_PATH = ROOT / 'artifacts/al_accuracy_candidate.joblib'


def candidate_grid():
    """This grid is fixed before CV, including both target parameterizations."""
    models = {f'incumbent_{name}': ('incumbent', model)
              for name, model in trajectory.candidates().items()}
    for rate in ('recent_al_rate_per_year', 'recent3_al_rate_per_year', 'recent4_al_rate_per_year'):
        for blend in (0., .25, .5, .75, 1.):
            models[f'history_{rate}_blend{blend}'] = ('expanded', HistoryShrinkageRegressor(blend, rate))
    for target in ('rate', 'change'):
        for alpha in (.01, .1, 1., 10., 100.):
            linear = make_pipeline(SimpleImputer(strategy='median', add_indicator=True, keep_empty_features=True),
                                   StandardScaler(), Ridge(alpha=alpha))
            models[f'{target}_ridge_{alpha}'] = ('expanded', AnchoredALRegressor(linear, target))
        for alpha in (.001, .01, .1):
            for ratio in (.3, .8):
                linear = make_pipeline(SimpleImputer(strategy='median', add_indicator=True, keep_empty_features=True),
                    StandardScaler(), ElasticNet(alpha=alpha, l1_ratio=ratio, max_iter=10000, random_state=SEED))
                models[f'{target}_elastic_{alpha}_{ratio}'] = ('expanded', AnchoredALRegressor(linear, target))
        for leaf in (2, 5, 10, 20):
            tree = make_pipeline(SimpleImputer(strategy='median', add_indicator=True, keep_empty_features=True),
                ExtraTreesRegressor(n_estimators=250, min_samples_leaf=leaf, max_features=.8,
                                    n_jobs=1, random_state=SEED))
            models[f'{target}_extra_trees_leaf{leaf}'] = ('expanded', AnchoredALRegressor(tree, target))
        for leaf in (3, 10):
            tree = make_pipeline(SimpleImputer(strategy='median', add_indicator=True, keep_empty_features=True),
                RandomForestRegressor(n_estimators=250, min_samples_leaf=leaf, max_features=.8,
                                      n_jobs=1, random_state=SEED))
            models[f'{target}_random_forest_leaf{leaf}'] = ('expanded', AnchoredALRegressor(tree, target))
        for loss in ('squared_error', 'absolute_error'):
            for leaves in (3, 7, 15):
                tree = HistGradientBoostingRegressor(loss=loss, max_iter=250, max_leaf_nodes=leaves,
                    min_samples_leaf=15, l2_regularization=10, learning_rate=.03,
                    early_stopping=False, random_state=SEED)
                models[f'{target}_hgb_{loss}_leaves{leaves}'] = ('expanded', AnchoredALRegressor(tree, target))
    if importlib.util.find_spec('catboost') is not None:
        from catboost import CatBoostRegressor
        for target in ('rate', 'change'):
            for depth in (3, 5):
                for loss in ('RMSE', 'MAE'):
                    tree = make_pipeline(SimpleImputer(strategy='median', add_indicator=True, keep_empty_features=True),
                        CatBoostRegressor(iterations=500, depth=depth, loss_function=loss,
                            learning_rate=.03, l2_leaf_reg=10, verbose=False, thread_count=1,
                            random_seed=SEED, allow_writing_files=False))
                    models[f'{target}_catboost_depth{depth}_{loss}'] = ('expanded', AnchoredALRegressor(tree, target))
    return models


def metrics(frame, prediction):
    if frame.empty:
        return None
    errors = np.abs(frame.y_al.to_numpy(float) - prediction)
    equal_patient = pd.DataFrame({'patient_key': frame.patient_key.to_numpy(), 'error': errors,
                                 'hit': errors <= TOLERANCE}).groupby('patient_key').mean()
    return {'patients': len(equal_patient), 'pairs': len(frame),
        'patient_mean_mae_mm': float(equal_patient.error.mean()),
        'patient_mean_hit_rate': float(equal_patient.hit.mean()),
        'row_mae_mm': float(errors.mean()), 'row_hit_rate': float(np.mean(errors <= TOLERANCE))}


def summarize(frame, prediction):
    at12 = np.isclose(frame.horizon_months.to_numpy(float), 12)
    return {'all_horizons': metrics(frame, prediction),
            '12_months': metrics(frame.iloc[np.flatnonzero(at12)], prediction[at12])}


def fit_frame():
    dims_meta = verify_training_source(ROOT / 'data/training_visits.csv')
    kino_path = ROOT / 'data/research/kinoshita_visits.csv'
    kino_meta = json.loads(kino_path.with_suffix('.provenance.json').read_text(encoding='utf-8'))
    if (kino_meta.get('license') != 'CC-BY-4.0' or kino_meta.get('data_is_synthetic') is not False
            or kino_meta.get('allowed_targets') != ['al']
            or hashlib.sha256(kino_path.read_bytes()).hexdigest() != kino_meta['table_sha256']):
        raise ValueError('Kinoshita must be the reviewed real AL-only source')
    visits = [('dims', load_visits(ROOT / 'data/training_visits.csv'), dims_meta),
              ('kinoshita', load_visits(kino_path), kino_meta)]
    frames, audit = [], []
    for source, all_visits, meta in visits:
        # Reuse the existing patient split. No held-out labels or scores are read.
        fit, calibration, test = trajectory.source_partitions(all_visits, source)
        fit_ids = set(fit.patient_key)
        if fit_ids & (set(calibration.patient_key) | set(test.patient_key)):
            raise ValueError('Fit/held-out patients overlap')
        fit_visits = all_visits[all_visits.patient_key.isin(fit_ids)].copy()
        base = trajectory.build_pairs(fit_visits).dropna(subset=['al', 'y_al'])
        extra = build_pairs(fit_visits).rename(columns={'y_al': 'y_al_verified'})
        extra = extra.drop(columns=['al'])
        frame = base.merge(extra, how='inner',
            left_on=['patient_key', 'months_since_baseline', 'horizon_months'],
            right_on=['patient_key', 'index_followup_month', 'horizon_months'], validate='one_to_one')
        if len(frame) != len(base) or not np.array_equal(frame.y_al.to_numpy(), frame.y_al_verified.to_numpy()):
            raise ValueError('Feature/target alignment changed source observations')
        frame['source_id'] = source
        frames.append(frame)
        audit.append({'id': source, 'provenance': meta, 'fit_patient_ids': sorted(fit_ids),
                      'fit_patients': len(fit_ids), 'fit_pairs': len(frame),
                      'excluded_calibration_patients': calibration.patient_key.nunique(),
                      'excluded_test_patients': test.patient_key.nunique()})
    return pd.concat(frames, ignore_index=True), audit


def run(report_path=REPORT_PATH, candidate_path=CANDIDATE_PATH):
    grid = candidate_grid()
    grid_spec = {name: {'feature_set': feature_set, 'estimator': repr(model)}
                 for name, (feature_set, model) in grid.items()}
    started = datetime.now(timezone.utc).isoformat()
    grid_hash = hashlib.sha256(json.dumps(grid_spec, sort_keys=True).encode()).hexdigest()
    policy = ('FIT patients only, fixed 5-fold grouped CV with equal-patient training weights and scores. '
              'Reference is the incumbent-grid candidate with lowest all-horizon CV MAE. '
              'Eligible candidates must not worsen reference all-horizon or 12-month MAE. '
              'Rank by minimum of all-horizon and 12-month +/-0.10mm hit rates, then their mean, then lower MAE. '
              'No calibration/test metrics are read and no model is promoted.')
    report_path.parent.mkdir(parents=True, exist_ok=True)
    frozen = {'status': 'grid_frozen_before_cv', 'started_at': started,
              'grid_sha256': grid_hash, 'grid': grid_spec, 'selection_policy': policy,
              'tolerance_mm': TOLERANCE, 'catboost_installed': importlib.util.find_spec('catboost') is not None}
    if frozen['catboost_installed']:
        import catboost
        frozen['catboost_version'] = catboost.__version__
    report_path.write_text(json.dumps(frozen, indent=2), encoding='utf-8')
    frame, audit = fit_frame()
    groups = frame.patient_key.to_numpy()
    folds = list(GroupKFold(n_splits=5, shuffle=True, random_state=SEED).split(frame, groups=groups))
    features = {'incumbent': trajectory.FEATURES['al'], 'expanded': FEATURES}
    results, oof_predictions = [], {}
    for number, (name, (feature_set, candidate)) in enumerate(grid.items(), 1):
        x, y = frame[features[feature_set]].to_numpy(float), frame.y_al.to_numpy(float)
        prediction = np.empty(len(frame))
        for fit_index, validate_index in folds:
            if set(groups[fit_index]) & set(groups[validate_index]):
                raise ValueError('CV patient leakage')
            fitted = clone(candidate).fit(x[fit_index], y[fit_index],
                                         sample_weight=trajectory.patient_weights(frame.iloc[fit_index]))
            prediction[validate_index] = fitted.predict(x[validate_index])
        if not np.isfinite(prediction).all():
            raise ValueError(f'Non-finite CV predictions: {name}')
        scores = summarize(frame, prediction)
        results.append({'candidate': name, 'feature_set': feature_set, **scores})
        oof_predictions[name] = prediction
        print(f'{number}/{len(grid)} {name}: '
              f"all MAE={scores['all_horizons']['patient_mean_mae_mm']:.5f}, "
              f"hit={scores['all_horizons']['patient_mean_hit_rate']:.3%}; "
              f"12m MAE={scores['12_months']['patient_mean_mae_mm']:.5f}, "
              f"hit={scores['12_months']['patient_mean_hit_rate']:.3%}", flush=True)
    reference = min((r for r in results if r['feature_set'] == 'incumbent'),
                    key=lambda r: r['all_horizons']['patient_mean_mae_mm'])
    eligible = [r for r in results if all(r[h]['patient_mean_mae_mm'] <= reference[h]['patient_mean_mae_mm'] + 1e-12
                                         for h in ('all_horizons', '12_months'))]

    def ranking(result):
        hit = [result[h]['patient_mean_hit_rate'] for h in ('all_horizons', '12_months')]
        return min(hit), np.mean(hit), -result['all_horizons']['patient_mean_mae_mm'], -result['12_months']['patient_mean_mae_mm']

    best = max(eligible, key=ranking)
    feature_set, estimator = grid[best['candidate']]
    selected = clone(estimator).fit(frame[features[feature_set]].to_numpy(float), frame.y_al.to_numpy(float),
                                    sample_weight=trajectory.patient_weights(frame))
    prediction = oof_predictions[best['candidate']]
    best_by_source = {source: summarize(frame[frame.source_id == source], prediction[frame.source_id == source])
                      for source in frame.source_id.unique()}
    best_by_horizon = {str(h): metrics(frame[np.isclose(frame.horizon_months, h)],
                                       prediction[np.isclose(frame.horizon_months, h)])
                       for h in sorted(frame.horizon_months.unique())}
    report = {**frozen, 'status': 'completed_development_only',
        'completed_at': datetime.now(timezone.utc).isoformat(), 'data_is_synthetic': False,
        'sources': audit, 'fit_patients': frame.patient_key.nunique(), 'fit_pairs': len(frame),
        'feature_sets': features, 'cv_patient_sets': [sorted(set(groups[val])) for _, val in folds],
        'cv_folds': len(folds), 'reference': reference, 'selected': best,
        'eligible_candidates': [r['candidate'] for r in eligible], 'results': results,
        'selected_by_source': best_by_source, 'selected_by_horizon': best_by_horizon,
        'development_point_estimate_meets_90_percent': all(best[h]['patient_mean_hit_rate'] >= .9
                                                          for h in ('all_horizons', '12_months')),
        'supported_90_percent_claim': False,
        'limitations': ['Development CV after model selection is optimistic; independent evaluation is still required.',
            'Few independent FIT patients, with all-DIMS and orthokeratology/atropine cohorts only.',
            'Treatment modality is associated with cohort; results do not establish treatment effects.',
            'Derived age advances a measured past age by elapsed time and is explicitly named; source age is unchanged.',
            'Last observed SE and its recency are covariates, not invented current or future refraction.',
            'Kinoshita AL history and targets begin at enrollment month3; pre-stabilization AL is excluded from richer history rates.',
            'No labels before6months or beyond36months; monthly/longer extrapolation accuracy is not established.',
            'No changes to released models or their calibration intervals.']}
    report_path.write_text(json.dumps(report, indent=2, allow_nan=False), encoding='utf-8')
    joblib.dump({'point': selected, 'features': features[feature_set],
                 'feature_builder': enrich_row if feature_set == 'expanded' else None,
                 'report': report}, candidate_path)
    print('SELECTED', json.dumps(best), flush=True)
    return report


if __name__ == '__main__':
    run()
