# Model improvement and the 95% target

Updated 16 October 2026. **Overall accuracy above 95% has not been achieved.**
Continuous SE/AL forecasts have MAE in D/mm, RMSE and R-squared; R-squared is not
percent accuracy. Onset classification has threshold-dependent accuracy,
sensitivity and specificity. Combining these different endpoints into one
accuracy percentage would conceal errors.

## Progression changes

Previously the HGB model forecast absolute eye measurements from only eight
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

## What this evaluation establishes

These are **previously reported fixed benchmarks**, reused for this comparison.
Candidates/CV settings were fixed before evaluating challengers; test subjects
never enter fitting or calibration. The onset deployment decision nevertheless
considered this benchmark, so it is not an untouched prospective evaluation.
Post-selection development CV is not nested unbiased validation. No external
performance, generalization or clinical-utility claim is supported.

The full candidate scores, confusion matrices, CIs and before/after results are
in [MODEL_IMPROVEMENT.json](MODEL_IMPROVEMENT.json). Current generated reports are
in [progression metrics](../backend/artifacts/progression_model.metrics.json) and
[onset metrics](../backend/artifacts/onset_model.metrics.json). Data/source links
are in [CURRENT_DATASETS.md](CURRENT_DATASETS.md).

A defensible next improvement needs a larger linked longitudinal cohort with
measured predictors and an independent evaluation cohort. Optimizing displayed
numbers, joining unrelated subjects, synthetic exposures or choosing a favorable
test split cannot establish the requested accuracy.

## Rebuild and application refresh

`make model` rebuilds both released models from verified licensed data. The onset
search is separate: `python -m app.ml.onset --search --out artifacts/onset_challenger.joblib`.
Set OMP_NUM_THREADS=1 for training. From backend, run
`python scripts/refresh_model_predictions.py` after replacing the model to append
new snapshots without altering observations or prior versions. Repeating refresh
with the same model skips those records.
