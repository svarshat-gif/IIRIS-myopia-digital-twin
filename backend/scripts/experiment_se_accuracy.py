"""Frozen-grid SE development search using existing GOAL/DIMS FIT patients only.

No calibration, test or RELS labels select candidates. Selection maximizes
equal-patient 12-month ±0.50D hit rate subject to nonworsening 12-month and
all-horizon equal-patient MAE versus the incumbent recipe retrained in each fold.
Run from backend: python scripts/experiment_se_accuracy.py
"""
from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import joblib  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
from sklearn.base import clone  # noqa: E402
from sklearn.ensemble import ExtraTreesRegressor, GradientBoostingRegressor, HistGradientBoostingRegressor  # noqa: E402
from sklearn.impute import SimpleImputer  # noqa: E402
from sklearn.linear_model import Ridge  # noqa: E402
from sklearn.model_selection import GroupKFold  # noqa: E402
from sklearn.pipeline import make_pipeline  # noqa: E402
from sklearn.preprocessing import StandardScaler  # noqa: E402

from app.ml import trajectory  # noqa: E402
from app.ml.dataset import _months, load_visits  # noqa: E402
from app.ml.expanded import checked_table  # noqa: E402
from app.ml.features import build_feature_row  # noqa: E402
from app.ml.se_accuracy_models import enrich_row, SEChangeRegressor, SEForecastEnsemble  # noqa: E402

REPORT = ROOT / 'artifacts/se_accuracy_search.json'
MODEL = ROOT / 'artifacts/se_accuracy_candidate.joblib'
BASE = tuple(trajectory.FEATURES['se'])
HISTORY = tuple(dict.fromkeys(BASE[:-1] + ('baseline_se_observed', 'se_measurements',
    'se_observed_span_months', 'se_slope_all', 'se_slope_last2', 'se_slope_previous',
    'se_slope_acceleration', 'se_last_annualized_change', 'se_history_residual_std',
    'se_times_horizon', 'recent_rate_times_horizon', 'horizon_months')))
CLINICAL = HISTORY[:-1] + ('al', 'al_slope_per_year', 'delta_al_last', 'al_since_baseline',
    'al_last_annualized_change', 'last_recorded_age', 'months_since_recorded_age',
    'age_from_recorded_age_and_time', 'sex_male', 'parental_myopia',
    'treatment_dims_observed', 'treatment_orthok_observed', 'treatment_single_vision_observed', 'horizon_months')
FEATURE_SETS = {'base': BASE, 'history': HISTORY, 'clinical': CLINICAL}


def frozen_grid():
    specs = [{'name': 'incumbent_hgb_rate7', 'family': 'hgb', 'features': 'base',
              'mode': 'rate', 'loss': 'squared_error', 'leaves': 7, 'iterations': 150}]
    for features, leaves_options in [('history', [7, 15]), ('clinical', [15])]:
        for leaves in leaves_options:
            for loss in ['squared_error', 'absolute_error']:
                for mode in ['rate', 'change']:
                    specs.append({'name': f'hgb_{features}_{mode}_{loss}_{leaves}',
                        'family': 'hgb', 'features': features, 'mode': mode,
                        'loss': loss, 'leaves': leaves, 'iterations': 350})
    for mode in ['rate', 'change']:
        specs.append({'name': f'hgb_clinical_{mode}_absolute_error_7_long', 'family': 'hgb',
            'features': 'clinical', 'mode': mode, 'loss': 'absolute_error', 'leaves': 7, 'iterations': 650})
    for depth in [4, 6]:
        for loss in ['RMSE', 'MAE']:
            specs.append({'name': f'cat_clinical_change_{loss}_{depth}', 'family': 'catboost',
                'features': 'clinical', 'mode': 'change', 'loss': loss, 'depth': depth, 'iterations': 500})
        specs.append({'name': f'cat_clinical_rate_RMSE_{depth}', 'family': 'catboost',
            'features': 'clinical', 'mode': 'rate', 'loss': 'RMSE', 'depth': depth, 'iterations': 500})
    for mode in ['rate', 'change']:
        specs.append({'name': f'ridge_history_{mode}', 'family': 'ridge', 'features': 'history', 'mode': mode})
    specs += [
        {'name': 'extra_clinical_change', 'family': 'extra', 'features': 'clinical', 'mode': 'change'},
        {'name': 'huber_history_change', 'family': 'huber', 'features': 'history', 'mode': 'change'},
    ]
    blends = [
        {'name': 'median_robust_three', 'members': ['hgb_history_change_absolute_error_15', 'cat_clinical_change_MAE_6', 'ridge_history_change'], 'aggregation': 'median'},
        {'name': 'blend_history_cat6', 'members': ['hgb_history_change_absolute_error_15', 'cat_clinical_change_RMSE_6'], 'aggregation': 'mean'},
        {'name': 'blend_incumbent_cat4', 'members': ['incumbent_hgb_rate7', 'cat_clinical_change_MAE_4'], 'aggregation': 'mean'},
        {'name': 'blend_clinical_cat4', 'members': ['hgb_clinical_change_absolute_error_15', 'cat_clinical_change_RMSE_4'], 'aggregation': 'mean'},
    ]
    return specs, blends


def estimator(spec):
    family = spec['family']
    if family == 'hgb':
        model = HistGradientBoostingRegressor(loss=spec['loss'], max_iter=spec['iterations'],
            max_leaf_nodes=spec['leaves'], min_samples_leaf=20, l2_regularization=20,
            learning_rate=.04, early_stopping=False, random_state=42)
    elif family == 'catboost':
        from catboost import CatBoostRegressor
        model = CatBoostRegressor(loss_function=spec['loss'], iterations=spec['iterations'],
            depth=spec['depth'], learning_rate=.04, l2_leaf_reg=10, thread_count=1,
            nan_mode='Min', random_seed=42, verbose=False, allow_writing_files=False)
    elif family == 'ridge':
        model = make_pipeline(SimpleImputer(strategy='median', add_indicator=True, keep_empty_features=True),
            StandardScaler(), Ridge(alpha=100))
    elif family == 'extra':
        model = make_pipeline(SimpleImputer(strategy='median', add_indicator=True, keep_empty_features=True),
            ExtraTreesRegressor(n_estimators=300, min_samples_leaf=10, max_features=.8,
                n_jobs=1, random_state=42))
    else:
        model = make_pipeline(SimpleImputer(strategy='median', add_indicator=True, keep_empty_features=True),
            GradientBoostingRegressor(loss='huber', n_estimators=300, max_depth=3,
                min_samples_leaf=30, learning_rate=.04, random_state=42))
    return SEChangeRegressor(model, FEATURE_SETS[spec['features']], spec['mode'], input_features=CLINICAL)


def build_enriched_pairs(visits):
    """Observed SE pairs with features from history through the index visit only."""
    records = []
    for key, group in visits.groupby('patient_key', sort=False):
        visits_for_patient = group.to_dict('records')
        for index, current in enumerate(visits_for_patient[:-1]):
            if not pd.notna(current['spherical_equivalent']):
                continue
            past = visits_for_patient[:index + 1]
            sex = next((visit.get('sex') for visit in past if isinstance(visit.get('sex'), str)), None)
            parental = next((int(visit['parental_myopia']) for visit in past if pd.notna(visit.get('parental_myopia'))), None)
            base = build_feature_row(past, sex=sex, parental_myopia=parental)
            start = current['visit_date'] if current['visit_date'] is not None else current['followup_month']
            for future in visits_for_patient[index + 1:]:
                if not pd.notna(future['spherical_equivalent']):
                    continue
                end = future['visit_date'] if future['visit_date'] is not None else future['followup_month']
                horizon = _months(start, end)
                if horizon <= 0:
                    raise ValueError('Strictly increasing observed visits required')
                row = enrich_row({**base, 'horizon_months': horizon}, past)
                records.append({**row, 'patient_key': key, 'y_se': float(future['spherical_equivalent'])})
    return pd.DataFrame(records)


def fitting_pairs():
    provenance = trajectory.fixed.verify_training_source(ROOT / 'data/training_visits.csv')
    dims = load_visits(ROOT / 'data/training_visits.csv')
    goal, goal_meta = checked_table('goal')
    sources, records, audit = [('dims', dims, provenance), ('goal', goal, goal_meta)], [], []
    for source, visits, meta in sources:
        partitions = trajectory.source_partitions(visits, source)
        fit_ids = set(partitions[0].patient_key)
        # Existing fixed split is the authority. Reserved frames are discarded
        # before enriched features, scoring or candidate selection is computed.
        del partitions
        fit_visits = visits[visits.patient_key.isin(fit_ids)].copy()
        audit.append({'source': source, 'fit_patients': len(fit_ids),
            'fit_ids_sha256': hashlib.sha256('\n'.join(sorted(fit_ids)).encode()).hexdigest(),
            'table_sha256': meta.get('table_sha256'), 'license': meta.get('license')})
        pairs = build_enriched_pairs(fit_visits)
        pairs['source_id'] = source
        records.append(pairs)
    return pd.concat(records, ignore_index=True), audit


def metric(frame, prediction):
    errors = np.abs(frame.y_se.to_numpy(float) - prediction)
    grouped = pd.DataFrame({'patient': frame.patient_key.to_numpy(), 'absolute': errors,
                            'hit': errors <= .5}).groupby('patient')
    return {'n_pairs': len(frame), 'n_patients': int(frame.patient_key.nunique()),
        'mae': float(errors.mean()), 'hit_rate_050D': float((errors <= .5).mean()),
        'patient_mean_mae': float(grouped.absolute.mean().mean()),
        'patient_mean_hit_rate_050D': float(grouped.hit.mean().mean())}


def scores(frame, prediction):
    twelve = np.isclose(frame.horizon_months.to_numpy(float), 12)
    return {'all_observed': metric(frame, prediction), '12m': metric(frame.loc[twelve], prediction[twelve]),
        'by_horizon': {str(h): metric(frame.loc[frame.horizon_months == h], prediction[frame.horizon_months.to_numpy() == h])
                       for h in sorted(frame.horizon_months.unique())},
        'by_source': {source: {'all_observed': metric(frame.loc[frame.source_id == source], prediction[frame.source_id.to_numpy() == source]),
            '12m': metric(frame.loc[(frame.source_id == source) & twelve], prediction[(frame.source_id.to_numpy() == source) & twelve])}
                       for source in sorted(frame.source_id.unique())}}


def save(report):
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_text(json.dumps(report, indent=2, allow_nan=False), encoding='utf-8')


def main():
    specs, blends = frozen_grid()
    protected = [ROOT / f'artifacts/{name}.joblib' for name in ['progression_model', 'trajectory_model', 'onset_model']]
    before = {str(path): hashlib.sha256(path.read_bytes()).hexdigest() for path in protected if path.exists()}
    frozen = {'specs': specs, 'blends': blends, 'features': FEATURE_SETS,
        'folds': 3, 'fold_seed': 2026, 'primary_tolerance_D': .5,
        'selection': 'Maximize equal-patient 12m hit rate, subject to nonworsening equal-patient 12m and all-horizon MAE versus incumbent; tie-break all-horizon hit rate then MAE.',
        'feature_definitions': {
            'base': 'Existing SE trajectory features, current measurements and past history only.',
            'history': 'Measured baseline SE, observed SE count/span, all/recent/prior slopes and acceleration, annualized last SE change, prior residual SD, SE/rate × known forecast horizon.',
            'clinical': 'Index AL and past AL changes; previously recorded age, elapsed time and explicit calculated age; observed sex/parental metadata; observed DIMS/orthokeratology/single-vision modality flags. Unknowns remain NaN.',
        },
        'forbidden_features': ['patient_key', 'source_id', 'future outcomes', 'future metadata', 'eventual visit count'],
    }
    report = {'status': 'grid_frozen_before_data_loading', 'frozen_grid': frozen,
        'grid_sha256': hashlib.sha256(json.dumps(frozen, sort_keys=True).encode()).hexdigest(),
        'evaluation_scope': 'Existing GOAL+DIMS FIT patients only; no calibration/test/RELS evaluation or selection.',
        'protected_artifacts_before': before, 'results': [], 'skipped': []}
    save(report)
    started = time.monotonic()
    frame, audit = fitting_pairs()
    report.update(source_audit=audit, fit_patients=int(frame.patient_key.nunique()), fit_pairs=len(frame), status='cross_validation_running')
    groups, y = frame.patient_key.to_numpy(), frame.y_se.to_numpy(float)
    folds = list(GroupKFold(n_splits=3, shuffle=True, random_state=2026).split(frame, y, groups))
    report['fold_patient_counts'] = [{'fit': len(set(groups[a])), 'validation': len(set(groups[b]))} for a, b in folds]
    predictions, models = {}, {}
    for spec in specs:
        if spec['family'] == 'catboost' and importlib.util.find_spec('catboost') is None:
            report['skipped'].append({'candidate': spec['name'], 'reason': 'CatBoost not installed'})
            continue
        model = estimator(spec)
        oof, fold_scores = np.full(len(frame), np.nan), []
        candidate_started = time.monotonic()
        for fit, val in folds:
            assert not set(groups[fit]) & set(groups[val])
            trained = clone(model).fit(frame.iloc[fit], y[fit], sample_weight=trajectory.patient_weights(frame.iloc[fit]))
            oof[val] = trained.predict(frame.iloc[val])
            fold_scores.append(scores(frame.iloc[val], oof[val]))
        if not np.isfinite(oof).all():
            raise ValueError(f'Nonfinite out-of-fold predictions: {spec["name"]}')
        result = {'candidate': spec['name'], 'metrics': scores(frame, oof), 'folds': fold_scores,
                  'elapsed_seconds': time.monotonic() - candidate_started}
        report['results'].append(result)
        predictions[spec['name']], models[spec['name']] = oof, model
        save(report)
        print(spec['name'], '12m hit', round(result['metrics']['12m']['patient_mean_hit_rate_050D'], 4),
              'MAE', round(result['metrics']['12m']['patient_mean_mae'], 4), flush=True)
    for spec in blends:
        if any(name not in predictions for name in spec['members']):
            report['skipped'].append({'candidate': spec['name'], 'reason': 'Unavailable predeclared member'})
            continue
        values = np.array([predictions[name] for name in spec['members']])
        oof = np.median(values, axis=0) if spec['aggregation'] == 'median' else values.mean(axis=0)
        predictions[spec['name']] = oof
        models[spec['name']] = SEForecastEnsemble(tuple((name, models[name]) for name in spec['members']), aggregation=spec['aggregation'])
        report['results'].append({'candidate': spec['name'], 'metrics': scores(frame, oof),
            'folds': [scores(frame.iloc[val], oof[val]) for _, val in folds]})
    baseline = next(item for item in report['results'] if item['candidate'] == 'incumbent_hgb_rate7')['metrics']
    for item in report['results']:
        item['eligible'] = all(item['metrics'][scope]['patient_mean_mae'] <= baseline[scope]['patient_mean_mae'] + 1e-12
                               for scope in ['12m', 'all_observed'])
    eligible = [item for item in report['results'] if item['eligible']]
    winner = max(eligible, key=lambda item: (item['metrics']['12m']['patient_mean_hit_rate_050D'],
        item['metrics']['all_observed']['patient_mean_hit_rate_050D'], -item['metrics']['12m']['patient_mean_mae']))
    final = clone(models[winner['candidate']]).fit(frame, y, sample_weight=trajectory.patient_weights(frame))
    bundle = {'status': 'development_candidate_only', 'point': final, 'features': CLINICAL,
        'feature_sets': FEATURE_SETS, 'feature_builder': enrich_row, 'grid_sha256': report['grid_sha256'],
        'source_audit': audit, 'selected_candidate': winner['candidate'], 'cv_metrics': winner['metrics'],
        'report': {'winner': winner['candidate'], 'winner_cv_metrics': winner['metrics'], 'frozen_grid': frozen},
        'limitations': ['No calibration/test/RELS selection or evaluation performed.',
            'Development CV after selection is optimistic; separate evaluation required.',
            'No calibrated prediction interval or 90% accuracy claim.']}
    joblib.dump(bundle, MODEL)
    round_trip = joblib.load(MODEL)['point'].predict(frame.iloc[:10])
    np.testing.assert_allclose(round_trip, final.predict(frame.iloc[:10]))
    after = {str(path): hashlib.sha256(path.read_bytes()).hexdigest() for path in protected if path.exists()}
    if before != after:
        raise RuntimeError('A protected serving artifact changed during experiment')
    report.update(status='development_search_complete', winner=winner['candidate'],
        winner_metrics=winner['metrics'], incumbent_cv_metrics=baseline,
        carry_forward_cv_metrics=scores(frame, frame.se.to_numpy(float)),
        model_path=str(MODEL), protected_artifacts_after=after,
        elapsed_seconds=time.monotonic() - started,
        limitations=bundle['limitations'])
    save(report)
    print('WINNER', winner['candidate'], json.dumps(winner['metrics']['12m']), flush=True)


if __name__ == '__main__':
    main()
