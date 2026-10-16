# Five-year onset research model

Version: `onset5y-e8e0b40d33`. Trained at `2026-10-16T03:14:02.373756+00:00`.

This is a separate incident-myopia endpoint for initially nonmyopic children aged
5-9. It does not replace Iiris's 6/12-month SE/AL progression models or their risk
definition. It is exploratory association, not diagnosis, treatment advice,
clinical validation or a causal behavioural effect.

## Data and rights

618 real OLSM/textbook subjects, 81 five-year onsets. The explicitly GPL-3 licensed
[aplore3 0.9 upstream archive](https://cran.r-project.org/src/contrib/aplore3_0.9.tar.gz)
was verified against CRAN's published MD5 21812a5e3837d10d46cd32f5e0333ddf. Original
R data, package source, DESCRIPTION, codebook, full license and a CSV serialization
are retained in backend/data/open/olsm. The original and decoded Kaggle CSV match
all 618 rows/18 columns numerically. The Kaggle file's Unknown license is not used
as a redistribution basis; upstream GPL-3 attribution/terms are retained.

Conversion used rdata 1.0.0, retaining categorical labels and source values. Runtime
and container builds use the bundled verified CSV; no R/conversion dependency or
network download is required. To reproduce serialization separately, install
rdata==1.0.0, read myopia.rda with rdata.read_rda, select myopia, cast column names
to str, and write CSV with index=False and LF line endings. The source manifest
records exact file hashes. Research normalization recodes verified No/Yes and
Male/Female categories to original 0/1 values; all absent measurements stay absent.

## Fixed protocol and predictors

One row per independent subject; fixed stratified split into 370 fitting, 124
calibration and 124 fixed test subjects, with 49/16/16 positive outcomes.
The trainer asserts subject disjointness. Features/settings are not tuned on test subjects.
This is the previously reported benchmark, not new external validation. HGB classifier: 100 iterations, five leaves,
minimum leaf 15, learning rate .05, L2 10, no early stopping, seed 42. A separate
sigmoid calibrator fits only the calibration subjects.

Clinical inputs: age, recorded gender, SE, AL, mother/father myopia. The additional
activity model uses five weekly-hour fields: sports/outdoor, pleasure reading,
computer/games, school study and TV. ID/entry year, weighted duplicate composites
and future labels are excluded from features. Activity inputs are not mapped to
modern smartphone or pure outdoor measures. No ergonomic or treatment effects
are inferred.

| Inputs | ROC AUC | 95% subject-bootstrap CI | Average precision | Brier | Log loss |
|---|---:|---|---:|---:|---:|
| clinical | 0.7914 | [0.6813, 0.8993] | 0.4482 | 0.0934 | 0.3189 |
| clinical_activity | 0.8067 | [0.7013, 0.9031] | 0.5052 | 0.092 | 0.3135 |

The constant training-prevalence baseline has test ROC AUC .5, AP .1290,
Brier .1124 and log loss .3846. Confidence intervals use 500 bootstrap resamples
of independent test subjects; one-class samples are skipped. Only 16 test onsets
and a historical single cohort limit precision. The activity-model difference is
not proof of a reliable improvement, generalization or intervention effect.
There is no external validation or validated individual probability interval.

## Classification accuracy and challenger experiment

| Inputs | Accuracy at .5 | Balanced accuracy | Sensitivity | Specificity | Confusion matrix [[TN,FP],[FN,TP]] |
|---|---|---|---|---|---|
| clinical | 87.10% | 50.00% | 0.00% | 100.00% | [[108, 0], [16, 0]] |
| clinical_activity | 87.90% | 53.12% | 6.25% | 100.00% | [[108, 0], [15, 1]] |

The majority/prevalence baseline is **87.10% accuracy, 50% balanced accuracy,
0% sensitivity**. Overall accuracy above 95% has not been achieved. The .5
threshold is fixed and is not optimized on test labels. This endpoint returns a
research probability, not a clinical screening decision.

An opt-in search compared 13 fixed logistic, RBF SVM, HGB and random-forest
configurations with ten training-only stratified CV folds per feature set,
selecting by ROC AUC before test evaluation. Selected logistic challengers did
not consistently improve test probability quality (clinical Brier .0967 vs .0934;
activity .0952 vs .0920). They were **not promoted**. The retained model and its
predictions are unchanged apart from version/expanded reporting. The deployment
decision considered this reused benchmark; independent validation remains needed.
See [MODEL_IMPROVEMENT.md](MODEL_IMPROVEMENT.md) and its full candidate scores.

To reproduce the experiment without overwriting the release:

```sh
OMP_NUM_THREADS=1 python -m app.ml.onset --search --out artifacts/onset_challenger.joblib
```

The default command rebuilds the incumbent. Challenger search requires a separate
path; a bundle explicitly marked challenger_only is refused by the serving loader.
Source NaNs are never imputed; experimental models use a separately calibrated
native-missing fallback if needed. Missing-pattern validity is not established.

## API and UI

Authenticated `POST /api/v1/research/onset/predict` takes age, spheq (D), measured
al (mm), optional original-coded gender/mommy/dadmy, and optional sporthr/readhr/
comphr/studyhr/tvhr in hours/week. Ages outside 5-9 and already-myopic baseline
SE <= -.75 D are rejected. All five activity measurements are required to select
the activity model; otherwise the clinical model is used with a visible warning.
Missing inputs remain NaN and produce an unvalidated-missing-pattern warning;
extrapolation beyond fitting ranges is also reported. Native missing handling
does not establish clinical validity for missing-pattern predictions.

The Model Card shows dataset roles, separate onset metrics and a blank-input
research form. The response explicitly says horizon_years=5 and returns no
progression horizons or invented probability interval. Rate limits, JWT auth and
access auditing cover the endpoint. No patient lookup/join or hosted AI call occurs.
