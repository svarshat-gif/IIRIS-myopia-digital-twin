"""Expand the 12-month SE/progression endpoints with licensed GOAL; hold RELS aside."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingRegressor
from sklearn.metrics import (accuracy_score, balanced_accuracy_score, recall_score, precision_score,
                             f1_score, confusion_matrix)
from sklearn.model_selection import GroupShuffleSplit

from app.core.config import settings
from app.ml import onset, train as original
from app.ml.dataset import load_visits, build_supervised_table
from app.ml.features import ALL_FEATURES
from app.ml.research_models import (regressors, classifiers, select, ChangeRegressor,
                                    SigmoidProbabilityModel, calibration_threshold)

ROOT = Path(__file__).resolve().parents[2]
TARGET = 'y_se_12m'


def patient_bootstrap_metrics(y, prediction, groups, repeats=300):
    groups = np.asarray(groups)
    keys, inverse = np.unique(groups, return_inverse=True)
    group_indices = [np.flatnonzero(inverse == i) for i in range(len(keys))]
    rng = np.random.default_rng(42)
    values = {'mae': [], 'rmse': [], 'r2': []}
    for _ in range(repeats):
        take = np.concatenate([group_indices[i] for i in rng.integers(0, len(keys), len(keys))])
        scores = original.regression_metrics(y[take], prediction[take])
        for key in values:
            if np.isfinite(scores[key]):
                values[key].append(scores[key])
    return {key: [round(float(v), 4) for v in np.quantile(scores, [.025, .975])]
            for key, scores in values.items() if scores}


def checked_table(name):
    catalog = onset.catalog()
    entry = next(d for d in catalog['datasets'] if d['id'] == name)
    path = ROOT / f'data/research/{name}_visits.csv'
    if entry['license'] != 'CC-BY-4.0' or entry['data_is_synthetic'] is not False:
        raise ValueError('Only the reviewed real, licensed PLOS cohorts are accepted')
    if hashlib.sha256(path.read_bytes()).hexdigest() != entry['table_sha256']:
        raise ValueError('Longitudinal table checksum mismatch')
    return load_visits(path), entry


def split_goal(table):
    groups = table.patient_key.to_numpy()
    fitcal, test = next(GroupShuffleSplit(test_size=.2, random_state=42).split(table, groups=groups))
    fit, cal = next(GroupShuffleSplit(test_size=.25, random_state=43).split(table.iloc[fitcal], groups=groups[fitcal]))
    result = [table.iloc[fitcal[fit]].copy(), table.iloc[fitcal[cal]].copy(), table.iloc[test].copy()]
    sets = [set(x.patient_key) for x in result]
    assert all(not sets[i] & sets[j] for i in range(3) for j in range(i))
    return result


def decision_scores(y, p, threshold):
    y = np.asarray(y, dtype=int)
    predicted = p >= threshold
    has_negative = bool(np.any(y == 0))
    has_positive = bool(np.any(y == 1))
    return {'accuracy': float(accuracy_score(y, predicted)),
        'balanced_accuracy': (float(balanced_accuracy_score(y, predicted)) if has_negative and has_positive else None),
        'sensitivity': (float(recall_score(y, predicted, zero_division=0)) if has_positive else None),
        'specificity': (float(recall_score(y, predicted, pos_label=0, zero_division=0)) if has_negative else None),
        'precision': float(precision_score(y, predicted, zero_division=0)),
        'f1': float(f1_score(y, predicted, zero_division=0)),
        'confusion_matrix': confusion_matrix(y, predicted, labels=[0, 1]).tolist(), 'threshold': float(threshold)}


def evaluate(table, point, lower, upper, delta, risk, threshold):
    sub = table.dropna(subset=[TARGET, 'se'])
    if sub.empty:
        return {'status': 'not_evaluable'}
    x, y = sub[ALL_FEATURES].to_numpy(float), sub[TARGET].to_numpy(float)
    pred = point.predict(x)
    lo, hi = lower.predict(x), upper.predict(x)
    lc, hc = np.minimum(np.minimum(lo, hi) - delta, pred), np.maximum(np.maximum(lo, hi) + delta, pred)
    result = original.regression_metrics(y, pred)
    result.update(n_patients=sub.patient_key.nunique(), bootstrap_95ci=patient_bootstrap_metrics(y, pred, sub.patient_key),
        within_025D=float(np.mean(np.abs(y-pred) <= .25)), within_050D=float(np.mean(np.abs(y-pred) <= .5)),
        interval_coverage=float(np.mean((y>=lc)&(y<=hc))), mean_interval_width=float(np.mean(hc-lc)),
        interval_patient_coverage=float(pd.Series((y>=lc)&(y<=hc)).groupby(sub.patient_key.to_numpy()).all().mean()),
        baselines={'carry_forward': original.regression_metrics(y, sub.se.to_numpy())})
    # Future status includes prevalent myopes. It must never be presented as incidence or overall app accuracy.
    status = (y <= -.5).astype(int)
    result['future_myopic_status'] = {'definition': 'Future SE <= -0.50D, including already-myopic subjects; not onset',
        'model': decision_scores(status, -(pred + .5), 0),
        'carry_forward': decision_scores(status, -(sub.se.to_numpy() + .5), 0)}
    labeled = sub.dropna(subset=['y_fast_progression'])
    if labeled.empty or risk is None:
        result['fast_progression'] = {'status': 'not_evaluable',
            'reason': ('This cohort has no annual refraction pairs for the SE-change label.'
                if labeled.empty else 'No SE-change classifier is available.')}
    else:
        fast = labeled.y_fast_progression.to_numpy(int)
        p = risk.predict_proba(labeled[ALL_FEATURES].to_numpy(float))[:, 1]
        if np.unique(fast).size < 2:
            result['fast_progression'] = {'status': 'not_evaluable',
                'reason': 'Evaluation subset contains only one outcome class.'}
        else:
            result['fast_progression'] = {**onset.scores(fast, p),
                'at_calibration_threshold': decision_scores(fast, p, threshold),
                'prevalence_baseline': onset.scores(fast,
                    np.repeat(risk.training_prevalence_, len(fast)))}
    return result


def run(out, include_catboost=True, promote=False):
    if Path(out).resolve() == settings.model_path.resolve() and not promote:
        raise ValueError('Explicit promotion mode is required for the released progression path')
    base = joblib.load(settings.model_path)
    if base['data_is_synthetic'] is not False:
        raise ValueError('A real DIMS baseline artifact is required')
    if base.get('expanded_training'):
        raise ValueError('Rebuild the DIMS baseline before expanding; do not recursively retrain an expanded bundle')
    dims = build_supervised_table(load_visits(ROOT / 'data/training_visits.csv'))
    dims_sets = original.split_by_patient(dims)
    goal_visits, goal_meta = checked_table('goal')
    rels_visits, rels_meta = checked_table('rels')
    goal = build_supervised_table(goal_visits)
    rels = build_supervised_table(rels_visits)
    goal_sets = split_goal(goal)
    sets = [pd.concat([a,b],ignore_index=True).dropna(subset=[TARGET,'se']) for a,b in zip(dims_sets,goal_sets)]
    fit, cal, test = sets
    x, y = fit[ALL_FEATURES].to_numpy(float), fit[TARGET].to_numpy(float)
    xc, yc = cal[ALL_FEATURES].to_numpy(float), cal[TARGET].to_numpy(float)
    print('Selecting 12-month SE change model', flush=True)
    point, selection = select(regressors(ALL_FEATURES, include_catboost), x, y, fit.patient_key.to_numpy(), regression=True)
    point.fit(x,y)
    anchor = ALL_FEATURES.index('se')
    qargs = dict(max_iter=300,max_leaf_nodes=7,min_samples_leaf=20,learning_rate=.03,
                 l2_regularization=10,early_stopping=False,random_state=42)
    lower = ChangeRegressor(HistGradientBoostingRegressor(loss='quantile',quantile=.05,**qargs),anchor).fit(x,y)
    upper = ChangeRegressor(HistGradientBoostingRegressor(loss='quantile',quantile=.95,**qargs),anchor).fit(x,y)
    delta = original.conformal_delta(lower.predict(xc),upper.predict(xc),yc,groups=cal.patient_key)
    # Fast progression is labeled from annual SE change, so GOAL contributes
    # labeled rows even though its released workbook has no axial length.
    risk_fit = fit.dropna(subset=['y_fast_progression'])
    risk_cal = cal.dropna(subset=['y_fast_progression'])
    xr = risk_fit[ALL_FEATURES].to_numpy(float)
    yr = risk_fit.y_fast_progression.to_numpy(int)
    xrc = risk_cal[ALL_FEATURES].to_numpy(float)
    yrc = risk_cal.y_fast_progression.to_numpy(int)
    print('Selecting SE fast-progression classifier', flush=True)
    risk_base, risk_selection = select(classifiers(include_catboost), xr, yr,
                                       risk_fit.patient_key.to_numpy())
    risk_base.fit(xr, yr)
    risk = SigmoidProbabilityModel(risk_base).fit(xrc, yrc)
    risk.training_prevalence_ = float(yr.mean())
    threshold = calibration_threshold(yrc, risk.predict_proba(xrc)[:, 1])
    # Promotion uses only separate calibration subjects, before any benchmark calculation.
    old_point = base['models']['se_12m']['median']
    gates = {}
    for name, frame in [('goal', goal_sets[1]),('dims',dims_sets[1])]:
        sub = frame.dropna(subset=[TARGET, 'se'])
        xx = sub[ALL_FEATURES].to_numpy(float)
        yy = sub[TARGET].to_numpy(float)
        gates[name]={'previous_mae':original.regression_metrics(yy,old_point.predict(xx))['mae'],
            'candidate_mae':original.regression_metrics(yy,point.predict(xx))['mae']}
    accepted = (gates['goal']['candidate_mae'] < gates['goal']['previous_mae'] and
                gates['dims']['candidate_mae'] <= gates['dims']['previous_mae'] + .05)
    print('CALIBRATION GATE',gates,'accepted',accepted,flush=True)
    # All choices, thresholds and the calibration promotion gate are fixed before this evaluation.
    evaluations = {}
    for name, frame in [('goal_internal',goal_sets[2]),('dims_reused',dims_sets[2]),
                        ('rels_common_support',rels[rels.months_since_baseline<=24]),
                        ('rels_later_extrapolation',rels[rels.months_since_baseline>24])]:
        evaluations[name] = evaluate(frame,point,lower,upper,delta,risk,threshold)
        m=evaluations[name]
        print('BENCHMARK',name,{k:m.get(k) for k in ('n','n_patients','mae','rmse','r2','within_050D','future_myopic_status','fast_progression')},flush=True)
    combined = evaluate(test,point,lower,upper,delta,risk,threshold)
    rels_risk = evaluations['rels_common_support'].get('fast_progression', {})
    risk_baseline = rels_risk.get('prevalence_baseline', {})
    risk_accepted = (rels_risk.get('status') != 'not_evaluable' and
        rels_risk.get('roc_auc', 0) > .5 and
        rels_risk.get('brier', 1) < risk_baseline.get('brier', 0))
    stamp = datetime.now(timezone.utc)
    protocol = Path(__file__).read_bytes()+Path(__file__).with_name('research_models.py').read_bytes()
    version = f'mdt-expanded-{stamp:%Y%m%d}-'+hashlib.sha256(protocol+str(goal_meta).encode()+base['model_version'].encode()).hexdigest()[:8]
    report = {'model_version':version,'trained_at':stamp.isoformat(),'data_is_synthetic':False,
        'catboost_included':include_catboost,'regression_selection':selection,'risk_selection':risk_selection,
        'calibration_gate':gates,'promotion_accepted':accepted,
        'risk_external_gate':{'accepted':risk_accepted,
            'rule':'RELS ROC AUC > 0.50 and Brier score below the training-prevalence baseline.',
            'candidate_auc':rels_risk.get('roc_auc'),'candidate_brier':rels_risk.get('brier'),
            'prevalence_baseline_brier':risk_baseline.get('brier')},
        'calibration_threshold':threshold,'evaluation':evaluations,
        'split':{k:{'patients':int(s.patient_key.nunique()),'rows':len(s)} for k,s in zip(['fit','calibration','test'],sets)},
        'limitations':['Only 12-month SE and SE-change risk gain GOAL data; 6-month SE and all AL endpoints remain DIMS-only.',
            'RELS is held out as a PLOS study cohort; overlap with the separately sourced DIMS cohort cannot be checked from available files.',
            'GOAL/DIMS differ in population and treatment; pooled calibration is not group-specific clinical validation.',
            'Future myopic-status accuracy includes existing cases; it is not incident-myopia sensitivity or overall app accuracy.',
            'RELS index months above24 are later than fitting support; reported separately as extrapolation.',
            'No invented dates, age, AL, exposure or treatment allocation; nominal annual timing is retained.']}
    candidate = {'report':report,'point':point,'lower':lower,'upper':upper,'conformal_delta':delta,'risk':risk}
    out = Path(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump(candidate,out)
    out.with_suffix('.metrics.json').write_text(json.dumps(report,indent=2,allow_nan=False),encoding='utf-8')
    if promote and accepted:
        base['models']['se_12m']={'median':point,'lower':lower,'upper':upper,'conformal_delta':delta,
            'selection':selection,'anchored_point':True}
        if risk_accepted:
            base['models']['risk'] = risk
        base['expanded_training']=report
        base.update(model_version=version,trained_at=stamp.isoformat(),data_source=base['data_source']+'; PLOS GOAL annual cycloplegic refraction')
        base['metrics']['regression']['y_se_12m']={**combined,'model_selection':selection,
            'calibration_patients':cal.patient_key.nunique(),'nominal_coverage':.9,'conformal_delta':delta,
            'evaluation_by_cohort':evaluations,'endpoint':'12-month future measured SE from observed history'}
        if risk_accepted:
            base['metrics']['risk']={'definition':base['risk_definition'],'model_selection':risk_selection,
                'calibration_selected_threshold':threshold,
                'evaluation_by_cohort':{k:v.get('fast_progression') for k,v in evaluations.items()}}
        # Retain the original Ridge/RF comparison only under its original DIMS report, never mix split results.
        base['metrics']['expanded_training']=report
        base['metrics']['n_patients']=20+goal_visits.patient_key.nunique()
        base['metrics']['n_visits']=140+len(goal_visits)
        base['provenance']={**base['provenance'],'additional_sources':[goal_meta],
            'external_evaluation_sources':[rels_meta],'n_patients':20+goal_visits.patient_key.nunique(),
            'limitations':base['provenance']['limitations']+report['limitations']}
        joblib.dump(base,settings.model_path)
        settings.model_path.with_suffix('.metrics.json').write_text(json.dumps({**base['metrics'],
            'provenance':base['provenance'],'model_version':version,'trained_at':stamp.isoformat()},indent=2,allow_nan=False),encoding='utf-8')
        print('PROMOTED',version,'risk_promoted',risk_accepted,flush=True)
    elif promote:
        print('NOT PROMOTED: calibration gate failed; DIMS release retained',flush=True)
    return report


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out',type=Path,default=settings.artifacts_dir/'expanded_candidate.joblib')
    parser.add_argument('--without-catboost',action='store_true')
    parser.add_argument('--promote',action='store_true')
    args=parser.parse_args()
    run(args.out,not args.without_catboost,args.promote)
