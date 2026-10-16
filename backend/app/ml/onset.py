"""Separate five-year incident-myopia research model. Never a progression endpoint."""
from functools import lru_cache
import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.calibration import CalibratedClassifierCV
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.frozen import FrozenEstimator
from sklearn.metrics import (roc_auc_score, average_precision_score, brier_score_loss, log_loss,
                            accuracy_score, balanced_accuracy_score, precision_score, recall_score,
                            f1_score, confusion_matrix)
from sklearn.model_selection import train_test_split

from app.core.config import settings
from app.ml.selection import select_onset

ROOT = Path(__file__).resolve().parents[2]
MODEL_PATH = settings.artifacts_dir / 'onset_model.joblib'
CLINICAL = ['age', 'gender', 'spheq', 'al', 'mommy', 'dadmy']
ACTIVITY = ['sporthr', 'readhr', 'comphr', 'studyhr', 'tvhr']
DISCLAIMER = ('Exploratory five-year myopia-onset association for initially nonmyopic children aged 5-9. '
              'Not a 6/12-month progression estimate, diagnosis, clinical validation or causal intervention effect.')


def catalog():
    path = ROOT / 'data/research/catalog.json'
    return json.loads(path.read_text(encoding='utf-8')) if path.exists() else {
        'datasets': [], 'excluded': [], 'note': 'Run scripts/build_research_datasets.py to prepare research data.'}


def scores(y, p):
    predicted = np.asarray(p) >= .5
    return {'roc_auc': round(float(roc_auc_score(y, p)), 4),
            'average_precision': round(float(average_precision_score(y, p)), 4),
            'brier': round(float(brier_score_loss(y, p)), 4),
            'log_loss': round(float(log_loss(y, p, labels=[0, 1])), 4),
            'accuracy': round(float(accuracy_score(y, predicted)), 4),
            'balanced_accuracy': round(float(balanced_accuracy_score(y, predicted)), 4),
            'sensitivity': round(float(recall_score(y, predicted, zero_division=0)), 4),
            'specificity': round(float(recall_score(y, predicted, pos_label=0, zero_division=0)), 4),
            'precision': round(float(precision_score(y, predicted, zero_division=0)), 4),
            'f1': round(float(f1_score(y, predicted, zero_division=0)), 4)}


def train(data=ROOT / 'data/research/olsm_onset.csv', out=None, search=False):
    data = Path(data)
    if search and out is None:
        raise ValueError('Candidate search requires a separate output path; it cannot overwrite the released model')
    out = Path(out) if out else MODEL_PATH
    if search and out.resolve() == MODEL_PATH.resolve():
        raise ValueError('Candidate search cannot overwrite the released model')
    provenance = json.loads((data.parent / 'catalog.json').read_text(encoding='utf-8'))
    source = next(d for d in provenance['datasets'] if d['id'] == 'olsm')
    if source['data_is_synthetic'] is not False or source['license'] != 'GPL-3':
        raise ValueError('Only the verified licensed real OLSM source is supported')
    if hashlib.sha256(data.read_bytes()).hexdigest() != source['table_sha256']:
        raise ValueError('Onset table checksum mismatch')
    df = pd.read_csv(data)
    if len(df) != 618 or df.patient_key.duplicated().any() or not df.myopic.isin([0, 1]).all():
        raise ValueError('Invalid independent subject/outcome structure')
    indices = np.arange(len(df))
    fitcal, test = train_test_split(indices, test_size=.2, stratify=df.myopic, random_state=42)
    fit, cal = train_test_split(fitcal, test_size=.25, stratify=df.iloc[fitcal].myopic, random_state=43)
    groups = [set(df.iloc[s].patient_key) for s in (fit, cal, test)]
    assert all(not groups[i] & groups[j] for i in range(3) for j in range(i))
    models, metrics = {}, {}
    y = df.myopic.to_numpy()
    for name, columns in [('clinical', CLINICAL), ('clinical_activity', CLINICAL + ACTIVITY)]:
        x = df[columns].to_numpy(dtype=float)
        if search:
            base, selection = select_onset(x[fit], y[fit])
        else:
            base = HistGradientBoostingClassifier(max_iter=100, max_leaf_nodes=5,
                min_samples_leaf=15, l2_regularization=10, learning_rate=.05,
                early_stopping=False, random_state=42)
            selection = {'selected': 'fixed_hgb_incumbent',
                'criterion': 'Retained incumbent; challenger did not consistently improve the existing benchmark'}
        base.fit(x[fit], y[fit])
        model = CalibratedClassifierCV(FrozenEstimator(base), method='sigmoid').fit(x[cal], y[cal])
        if search:
            missing_base = HistGradientBoostingClassifier(max_iter=100, max_leaf_nodes=5,
                min_samples_leaf=15, l2_regularization=10, learning_rate=.05,
                early_stopping=False, random_state=42).fit(x[fit], y[fit])
            missing_model = CalibratedClassifierCV(FrozenEstimator(missing_base), method='sigmoid').fit(x[cal], y[cal])
        else:
            missing_model = model
        p = model.predict_proba(x[test])[:, 1]
        result = scores(y[test], p)
        rng = np.random.default_rng(42)
        boot = []
        for _ in range(500):
            take = rng.choice(len(test), len(test), replace=True)
            if len(np.unique(y[test][take])) == 2:
                boot.append(scores(y[test][take], p[take]))
        result['bootstrap_95ci'] = {k: [round(float(v), 4) for v in np.quantile(
            [b[k] for b in boot], [.025, .975])] for k in result}
        result['confusion_matrix'] = confusion_matrix(y[test], p >= .5, labels=[0, 1]).tolist()
        result['decision_threshold'] = .5
        result['model_selection'] = selection
        result['native_missing_fallback'] = scores(y[test], missing_model.predict_proba(x[test])[:, 1])
        result['prevalence_baseline'] = scores(y[test], np.repeat(y[fit].mean(), len(test)))
        models[name] = {'model': model, 'features': columns, 'missing_model': missing_model,
                        'algorithm': selection['selected']}
        metrics[name] = result
    stamp = datetime.now(timezone.utc).isoformat()
    protocol = Path(__file__).read_text(encoding='utf-8') + Path(__file__).with_name('selection.py').read_text(encoding='utf-8')
    version = 'onset5y-' + hashlib.sha256(data.read_bytes() + protocol.encode() + str(search).encode()).hexdigest()[:10]
    report = {'model_version': version, 'trained_at': stamp, 'data_is_synthetic': False,
        'source': source, 'endpoint': 'Myopia onset within five years of baseline',
        'n_patients': len(df), 'n_positive': int(df.myopic.sum()),
        'split': {k: len(s) for k, s in [('train_patients', fit), ('calibration_patients', cal), ('test_patients', test)]},
        'split_positive': {k: int(y[s].sum()) for k, s in [('train', fit), ('calibration', cal), ('test', test)]},
        'split_strategy': 'Fixed stratified subject split; each subject has one row; no test tuning',
        'calibration': 'Sigmoid calibration on separate held-out subjects', 'metrics': metrics,
        'selection': ('13 fixed candidate configurations; ten training-only CV folds per feature set; ROC AUC objective'
                      if search else 'Original fixed HGB retained; candidate search is an opt-in, separately saved experiment'),
        'release_status': 'challenger_only' if search else 'retained_incumbent',
        'test_status': 'Same locked benchmark as previous report; previously reported results, not new external validation',
        'limitations': source['limitations'] + ['Only 81 onsets; small historical single-cohort holdout.',
            'No external validation, individual probability interval or causal exposure effect.',
            'Activity and clinical models have separate test results; no test-selected winner.',
            'Accuracy is threshold-dependent; always compare majority baseline, sensitivity and balanced accuracy.'],
        'disclaimer': DISCLAIMER}
    bundle = {'report': report, 'models': models,
              'training_ranges': {c: [float(df.iloc[fit][c].min()), float(df.iloc[fit][c].max())]
                                  for c in CLINICAL + ACTIVITY}}
    out.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump(bundle, out)
    out.with_suffix('.metrics.json').write_text(json.dumps(report, indent=2, allow_nan=False), encoding='utf-8')
    load.cache_clear()
    return report


@lru_cache(maxsize=1)
def load():
    path = MODEL_PATH
    if not path.exists():
        raise FileNotFoundError('Run build_research_datasets.py and python -m app.ml.onset')
    bundle = joblib.load(path)
    if bundle['report']['data_is_synthetic'] is not False:
        raise ValueError('Synthetic onset model refused')
    if bundle['report'].get('release_status') == 'challenger_only':
        raise ValueError('An experimental challenger cannot serve as the released onset model')
    return bundle


def metadata():
    try:
        return load()['report']
    except FileNotFoundError:
        return {'status': 'not_trained', 'disclaimer': DISCLAIMER}


def predict(values):
    bundle = load()
    # Select by measured input availability, never by test performance.
    name = 'clinical_activity' if all(values.get(k) is not None for k in ACTIVITY) else 'clinical'
    entry = bundle['models'][name]
    x = np.array([[np.nan if values.get(k) is None else values[k] for k in entry['features']]], dtype=float)
    warnings = []
    for c, value in zip(entry['features'], x[0]):
        if np.isnan(value):
            warnings.append(f'{c} is missing; prediction with missing predictors is not separately validated.')
        elif not bundle['training_ranges'][c][0] <= value <= bundle['training_ranges'][c][1]:
            warnings.append(f'{c} is outside the fitting cohort range; extrapolation is unreliable.')
    if name == 'clinical':
        warnings.append('Activity model requires all five measured weekly activity fields; clinical model used.')
    missing = np.isnan(x).any()
    model = entry.get('missing_model', entry['model']) if missing else entry['model']
    if missing and entry.get('algorithm') != 'fixed_hgb_incumbent':
        warnings.append('A separately calibrated native-missing HGB fallback is used; no measurement is imputed.')
    return {'probability': round(float(model.predict_proba(x)[0, 1]), 4),
            'horizon_years': 5, 'endpoint': bundle['report']['endpoint'], 'model': name,
            'algorithm': ('native_missing_hgb_fallback' if missing and entry.get('algorithm') != 'fixed_hgb_incumbent'
                          else entry.get('algorithm', 'fixed_hgb_incumbent')),
            'model_version': bundle['report']['model_version'], 'warnings': warnings,
            'disclaimer': DISCLAIMER, 'individual_probability_interval': None}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--search', action='store_true', help='Save a challenger; requires --out distinct from the released model')
    parser.add_argument('--out', type=Path)
    args = parser.parse_args()
    print(json.dumps(train(out=args.out, search=args.search), indent=2))
