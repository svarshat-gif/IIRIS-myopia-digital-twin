# Model accuracy and cohort expansion

Updated 17 October 2026. **A defensible overall accuracy above 90% has not been
established.** Continuous SE/AL forecasts use errors in D/mm; R-squared and the
fraction within an error tolerance are not generic accuracy. Binary onset
accuracy depends on its threshold and class prevalence. Results are reported by
endpoint, with sensitivity and balanced accuracy beside raw accuracy.

The app now provides an experimental **1–120-month selectable forecast** for SE
and AL, including year inputs. It uses real observed visit pairs and adds the
73-child Kinoshita AL trial. See [selectable horizons and measured results](FORECAST_HORIZONS.md)
for interpolation/extrapolation limits and the separate model's evaluation.
The 90% point-accuracy target remains unmet; the fixed 6/12-month snapshot model
and the selectable model have distinct reports.

## Original DIMS-only progression check

This table records the original DIMS-only model before the PLOS expansion. The
current released 12-month SE model and its separate cohort evaluation follow
below. Previously the HGB model forecast absolute eye measurements from only eight
fitting patients. The new protocol compares six fixed point models per target
using 12 training-only patient-grouped CV folds. It selects smooth change-HGB for
SE and simple training mean change for AL. Each adds the measured baseline.
Anchored quantile models retain separate ten-patient conformal calibration.
No source values, targets, patient split, candidate grid or test threshold were
changed in response to benchmark results. No unrelated cohorts are joined.

| Target | Previous MAE | Current MAE | MAE reduction | Carry-forward MAE | Current R-squared |
|---|---|---|---|---|---|
| SE 6 months (D) | 0.1421 | 0.1258 | 11.5% | 0.1675 | 0.9877 |
| SE 12 months (D) | 0.371 | 0.3204 | 13.6% | 0.335 | 0.9399 |
| AL 6 months (mm) | 0.977 | 0.0363 | 96.3% | 0.0633 | 0.9995 |
| AL 12 months (mm) | 0.823 | 0.04 | 95.1% | 0.1333 | 0.9994 |

All four targets improve MAE and beat carry-forward on the existing benchmark.
SE 6-month RMSE/R-squared are slightly worse than before; MAE is the training-only
selection objective. Six-month SE still trails RF; 12-month SE trails Ridge/RF on this test set. AL's simple
mean-change model should not be described as personalized biological prediction.
The cohort is still only 20 children, with two test children/six rows per target.
Observed 100% interval coverage on those children is not 95% prediction accuracy.

## PLOS cohorts and the expanded 12-month SE model

The licensed PLOS GOAL cohort (1,610 children) is now included for 12-month SE
training. The separate RELS cohort (2,042 children) is held out for study-level
evaluation. Annual right-eye refraction supports SE forecasting only; neither
cohort supplies axial length or treatment assignment. The app's released model
is `mdt-expanded-20261016-cc73de06`; its selected point model is a change-anchored
HGB. At inference, it anchors each forecast to the patient's current measured SE;
the 12-month model is trained on pooled DIMS and GOAL development partitions.

The fixed four-model leave-one-cohort-out experiment selected a simple
change-anchored Ridge model in both directions. It uses only current and prior
SE. Selection used patient-grouped three-fold CV within the training cohort;
the other cohort was not used for fitting or selection.

| Train to test | Test patients / transitions | MAE (D) | RMSE (D) | Within 0.75 D | Patient-bootstrap 95% CI |
|---|---:|---:|---:|---:|---|
| RELS to GOAL | 1,580 / 4,573 | 0.4439 | 0.6155 | 82.02% | 80.74-83.09% |
| GOAL to RELS | 1,901 / 8,758 | 0.5229 | 0.7384 | 77.45% | 76.46-78.37% |

These tolerance hit rates are not overall classification accuracy. The PLOS
paper treats MAE at or below 0.75 D as clinically acceptable and reports
cross-resource refraction errors; the app reports the hit rate only to make the
error scale concrete ([paper](https://journals.plos.org/plosmedicine/article?id=10.1371/journal.pmed.1002674)).
The independently held-out RELS check of the promoted pooled model has 5,520
common-support transitions from 1,900 subjects, MAE 0.5578 D (patient-bootstrap
95% CI 0.5429-0.5749), RMSE 0.7906 D and R-squared 0.6269. Carry-forward MAE is
0.5853 D. Its error is within 0.50 D for 56.96% of transitions; the nominal 90%
interval covers 93.59% of transitions but 83.53% of patients at every measured
transition. Intervals average 2.46 D wide.

At a -0.50 D cut point, the same RELS predictions classify **future myopic
status**, including children already myopic at baseline, with 75.80% accuracy,
77.59% balanced accuracy, 85.93% sensitivity and 69.25% specificity. This is
not incident-myopia onset. The carry-forward status baseline is 78.86% accurate
and 74.78% balanced accurate. The held-out GOAL subset reached 90.43% raw
accuracy and 82.13% balanced accuracy for the same status endpoint, but the
independent RELS result is lower and is the stronger transfer check. This derived
status metric is not the app's five-year onset model.

The new SE-change risk classifier was selected using training-only grouped CV
(best ROC AUC 0.6873), then evaluated on RELS. Its RELS AUC was 0.4957 and Brier
score 0.2690, worse than the training-prevalence Brier baseline 0.2499. Its
threshold accuracy was 44.18% (balanced accuracy 45.64%). It failed the fixed
external gate and was not promoted; the released app still has no fast-
progression probability. GOAL's internal result does not transfer to RELS.

The promotion gate was fixed to require lower GOAL calibration MAE than the
previous DIMS model and no more than +0.05 D degradation on DIMS calibration
patients. It passed: GOAL 0.4589 to 0.4097 D; DIMS 0.2770 to 0.2998 D. The tiny
reused DIMS test contains only two patients, so it cannot establish transfer to
the original treatment cohort. The RELS report is presented separately, and
no axial-length claim changes.

## Onset search and retained model

Thirteen fixed configurations per feature set: four scaled logistic models,
four scaled RBF SVMs, three HGB settings and two random forests. Ten training-only
stratified CV folds select by ROC AUC; scaling fits inside each fold. The selected
model fits only 370 subjects and sigmoid calibration uses a separate 124. The
fixed test set has 124 subjects and 16 positive outcomes.

| Inputs | Incumbent AUC | Challenger AUC | Incumbent Brier | Challenger Brier | Incumbent accuracy at .5 | Incumbent sensitivity |
|---|---|---|---|---|---|---|
| clinical | 0.7914 | 0.8032 | 0.0934 | 0.0967 | 87.10% | 0.00% |
| clinical_activity | 0.8067 | 0.8056 | 0.092 | 0.0952 | 87.90% | 6.25% |

The logistic challengers were not promoted: they did not consistently improve
probability quality. Both have 87.1% test accuracy and zero sensitivity at .5.
The incumbent activity model has 87.9% accuracy, only one of 16 onsets detected,
and 53.12% balanced accuracy. Always predicting no onset gives 87.1% accuracy.
The app now displays these metrics and the baseline together. The API continues
to return research probabilities, not validated screening decisions.

An additional biometry challenger used anterior chamber depth, lens thickness
and vitreous chamber depth from OLSM. It was evaluated on the same 124-subject
holdout and was not promoted. The activity-only challenger reached 88.71%
accuracy, 69.56% balanced accuracy and 43.75% sensitivity at a calibration-set
threshold, but its AUC (0.7986) and Brier score (0.0929) did not improve on the
incumbent activity model (0.8067 and 0.0920). It detected 7 of 16 onsets. This
does not meet the 90% target and does not provide external validation. The
four-biometry feature sets and their scores are in
[MODEL_IMPROVEMENT.json](MODEL_IMPROVEMENT.json); serving continues to use the
released OLSM model.

### Sensitivity-constrained operating-point check

A separate challenger experiment fit sigmoid calibration from training-only
out-of-fold predictions, selected the decision threshold on a separate
124-person threshold-selection partition to meet a pre-specified **80% minimum
sensitivity**, then evaluated it on the locked 124-person test partition. The
threshold-selection partition had only 16 positive cases, so the floor required
detecting at least 13 of 16. Test sensitivity fell to 50-56.25%; no feature set
reached 90% accuracy. This is not external validation and did not replace the
released probability model.

| Inputs | Test accuracy | Balanced accuracy | Sensitivity | Specificity | Threshold-selection sensitivity |
|---|---:|---:|---:|---:|---:|
| Clinical | 75.81% | 64.81% | 50.00% | 79.63% | 81.25% |
| Clinical + activity | 79.84% | 69.79% | 56.25% | 83.33% | 81.25% |
| Clinical + biometry | 79.03% | 66.67% | 50.00% | 83.33% | 81.25% |
| Clinical + activity + biometry | 83.06% | 68.98% | 50.00% | 87.96% | 81.25% |

The threshold-selection-to-test drop shows the operating point is unstable with
so few onset cases. Thresholds were not selected on test labels. Stratified subject-bootstrap
95% intervals are recorded in [MODEL_IMPROVEMENT.json](MODEL_IMPROVEMENT.json).
The test partition has only 16 positive outcomes, so the intervals are broad
and do not support clinical use.

## What this evaluation establishes

The DIMS and OLSM test results reuse previously reported fixed benchmarks. The
GOAL/RELS tests are separate cohort evaluations, but both cohorts are from the
same published research program and region. The PLOS external results apply to
SE only and do not establish 90% accuracy for all Iiris predictions. No
prospective clinical-utility claim is supported.

The full candidate scores, confusion matrices, CIs and before/after results are
in [MODEL_IMPROVEMENT.json](MODEL_IMPROVEMENT.json). Current generated reports are
in [progression metrics](../backend/artifacts/progression_model.metrics.json) and
[onset metrics](../backend/artifacts/onset_model.metrics.json). Data/source links
are in [CURRENT_DATASETS.md](CURRENT_DATASETS.md).

Rebuild the separate 80%-sensitivity onset challenger from `backend` with
`python scripts/train_expanded_onset.py --without-catboost --minimum-sensitivity 0.8 --out artifacts/onset_sensitivity80_challenger.joblib`.

A defensible next improvement needs a larger linked longitudinal cohort with
measured predictors and an independent evaluation cohort. Optimizing displayed
numbers, joining unrelated subjects, synthetic exposures or choosing a favorable
test split cannot establish the requested accuracy.

## Rebuild and application refresh

`make model` rebuilds the DIMS baseline, verifies the research datasets, trains
the onset model, and runs the GOAL expansion with its calibration gate. Set
OMP_NUM_THREADS=1 for training. From backend, run
`python scripts/refresh_model_predictions.py` after replacing the model to append
new snapshots without altering observations or prior versions. Repeating refresh
with the same model skips those records.
