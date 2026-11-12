"""Run the frozen additional-biometry experiment; never overwrite the released onset model."""
import sys
from pathlib import Path
import json
import hashlib

import joblib
import numpy as np
import pandas as pd
from sklearn.metrics import confusion_matrix
from sklearn.model_selection import train_test_split

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.ml import onset  # noqa: E402
from app.ml.research_models import (classifiers, select, SigmoidProbabilityModel,
                                    sensitivity_threshold)  # noqa: E402


def bootstrap_threshold_ci(y, p, threshold, repeats=500, seed=42):
    """Stratified subject bootstrap CIs for threshold metrics (one row per subject)."""
    y = np.asarray(y, dtype=int)
    predicted = np.asarray(p) >= threshold
    groups = {label: np.flatnonzero(y == label) for label in (0, 1)}
    if any(len(indices) == 0 for indices in groups.values()):
        return {}
    rng = np.random.default_rng(seed)
    values = {key: [] for key in ('accuracy', 'balanced_accuracy', 'sensitivity', 'specificity')}
    for _ in range(repeats):
        take = np.concatenate([rng.choice(indices, len(indices), replace=True)
                               for indices in groups.values()])
        yy, pp = y[take], predicted[take]
        sensitivity = float(np.mean(pp[yy == 1]))
        specificity = float(np.mean(~pp[yy == 0]))
        values['accuracy'].append(float(np.mean(yy == pp)))
        values['balanced_accuracy'].append((sensitivity + specificity) / 2)
        values['sensitivity'].append(sensitivity)
        values['specificity'].append(specificity)
    return {key: [round(float(v), 4) for v in np.quantile(scores, [.025, .975])]
            for key, scores in values.items()}


def run(out, include_catboost=True, minimum_sensitivity=0.80):
    df = pd.read_csv(onset.ROOT / 'data/research/olsm_onset.csv')
    source = next(d for d in onset.catalog()['datasets'] if d['id'] == 'olsm')
    if hashlib.sha256((onset.ROOT / 'data/research/olsm_onset.csv').read_bytes()).hexdigest() != source['table_sha256']:
        raise ValueError('Onset source checksum mismatch')
    fit_threshold, test = train_test_split(np.arange(len(df)), test_size=.2, stratify=df.myopic, random_state=42)
    fit, threshold_set = train_test_split(fit_threshold, test_size=.25,
        stratify=df.iloc[fit_threshold].myopic, random_state=43)
    sets = {'clinical': onset.CLINICAL, 'clinical_activity': onset.CLINICAL + onset.ACTIVITY,
            'clinical_biometry': onset.CLINICAL + ['acd', 'lt', 'vcd'],
            'clinical_activity_biometry': onset.CLINICAL + onset.ACTIVITY + ['acd', 'lt', 'vcd']}
    bundle = {'models': {}, 'metrics': {}, 'data_is_synthetic': False, 'source': source,
              'test_status': 'Reused original 124-subject benchmark; not external validation',
              'release_status': 'challenger_only', 'catboost_included': include_catboost}
    y = df.myopic.to_numpy()
    for name, cols in sets.items():
        print('FEATURES', name, flush=True)
        x = df[cols].to_numpy(float)
        base, selection = select(classifiers(include_catboost), x[fit], y[fit])
        model = SigmoidProbabilityModel(base).fit_oof(x[fit], y[fit])
        threshold_probabilities = model.predict_proba(x[threshold_set])[:, 1]
        threshold = sensitivity_threshold(y[threshold_set], threshold_probabilities,
                                          minimum_sensitivity=minimum_sensitivity)
        p = model.predict_proba(x[test])[:, 1]
        fixed = onset.scores(y[test], p)
        decision = onset.scores(y[test], p)  # ranking/probability scores do not depend on threshold
        from sklearn.metrics import accuracy_score, balanced_accuracy_score, recall_score, precision_score, f1_score
        predicted = p >= threshold
        decision.update(accuracy=float(accuracy_score(y[test], predicted)),
            balanced_accuracy=float(balanced_accuracy_score(y[test], predicted)),
            sensitivity=float(recall_score(y[test], predicted)), specificity=float(recall_score(y[test], predicted, pos_label=0)),
            precision=float(precision_score(y[test], predicted, zero_division=0)), f1=float(f1_score(y[test], predicted, zero_division=0)),
            confusion_matrix=confusion_matrix(y[test], predicted, labels=[0, 1]).tolist(),
            bootstrap_95ci=bootstrap_threshold_ci(y[test], p, threshold))
        bundle['models'][name] = {'model': model, 'features': cols, 'decision_threshold': threshold}
        bundle['metrics'][name] = {'model_selection': selection, 'fixed_threshold_05': fixed,
            'threshold_policy': {'minimum_threshold_selection_sensitivity': minimum_sensitivity,
                'threshold_selection_sensitivity': float(recall_score(
                    y[threshold_set], threshold_probabilities >= threshold, zero_division=0)),
                'threshold_selection_positive_count': int(y[threshold_set].sum()),
                'threshold_selection_subject_count': int(len(threshold_set)),
                'selection': 'Highest threshold meeting the pre-specified sensitivity floor; maximizes threshold-selection specificity'},
            'threshold_selection_threshold': threshold, 'test_at_threshold_selection': decision}
        print('TEST', name, json.dumps(bundle['metrics'][name]), flush=True)
        out = Path(out)
        out.parent.mkdir(exist_ok=True, parents=True)
        joblib.dump(bundle, out)
        out.with_suffix('.metrics.json').write_text(json.dumps({k:v for k,v in bundle.items() if k!='models'}, indent=2),encoding='utf-8')
    return bundle


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--without-catboost', action='store_true')
    parser.add_argument('--minimum-sensitivity', type=float, default=0.80,
                        help='Pre-specified minimum sensitivity on threshold-selection subjects (default: 0.80)')
    args = parser.parse_args()
    if args.out.resolve() == onset.MODEL_PATH.resolve():
        raise ValueError('Experimental output must not overwrite the released onset model')
    run(args.out, not args.without_catboost, args.minimum_sensitivity)
