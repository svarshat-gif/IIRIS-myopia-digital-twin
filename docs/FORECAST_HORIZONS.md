# Selectable SE and axial-length forecasts

Updated 17 October 2026. The simulator, personal dashboard and clinician patient
view accept **any whole-month horizon from 1 to 120 months**. Examples include
1, 2, 6, 10, 24, 36, 48 and 60 months. Users can enter years instead: 2.5 years
means 30 months. Each response contains monthly estimates through the selected
month, anchored to the latest measured observation.

This is an **experimental forecast**, not a validated 90% accuracy claim. A
measured current axial length is required for an AL forecast; absent AL remains
unavailable. Forecast requests do not create observations or twin versions.
Public manual inputs are not saved.

## Time support

Both measures have observed training intervals ranging from **3 to 36 months**.
Only actual later visit measurements are training labels. No intermediate or
synthetic clinical outcomes are generated for training.

- A measured training horizon means an interval occurred in training; it does
  not establish accuracy for a new patient at that horizon.
- Unmeasured intervals inside 3–36 months, such as 10 months, interpolate the
  learned relationship between elapsed time and change.
- 1–2 months and 37–120 months extrapolate outside the observed interval range.
  Their accuracy and range coverage are unverified. The UI labels this explicitly.

The maximum of 36 months comes from the small DIMS cohort. Most SE observations
are annual school measurements; the additional Kinoshita AL trial supplies at
most 24 months of treatment follow-up from an eligible anchor. Availability of
a 5- or 10-year estimate does not imply validation over that duration.

The model learns annualized change conditioned on the observed history,
treatment flags and elapsed months. It adds predicted change to the measured
anchor. Beyond the training maximum it keeps the learned terminal rate and
scales change by elapsed time; it does not feed invented future visits back
into the history. Prediction ranges widen heuristically beyond that maximum.
This assumption does not model maturation, treatment changes or causal effects.

## Data and evaluation

| Source | Participants / visit rows | Role |
|---|---:|---|
| [DIMS](https://doi.org/10.5281/zenodo.18166476) | 20 / 140 | SE and AL development, calibration and internal test |
| [PLOS GOAL and RELS](https://journals.plos.org/plosmedicine/article?id=10.1371/journal.pmed.1002674) | GOAL 1,610 / 6,440; RELS 2,042 / 12,252 scheduled rows | GOAL SE development; RELS independent study test; missing measurements excluded |
| [Kinoshita trial](https://data.mendeley.com/datasets/y58rh8bfkv/7) | 73 / 438 right-eye visits | AL development, calibration and internal test; no follow-up SE |

Kinoshita supplies orthokeratology with or without atropine. Enrollment precedes
atropine initiation by three months; only month-3-and-later anchors enter
training. Enrollment SE and age are retained only where published. Follow-up
SE and age remain missing. This treatment and missingness pattern limits
generalization to untreated children and complete live records. See the
[trial paper](https://www.nature.com/articles/s41598-020-69710-8) and
[complete dataset inventory](CURRENT_DATASETS.md).

Patients, rather than individual visits, are separated between fitting,
calibration and testing. Candidate selection uses training-only grouped CV.
Each fitting patient has equal total weight despite different pair counts.
RELS does not enter fitting, selection or calibration. There is no independent
study-level AL evaluation. Repeated transitions are correlated; confidence
intervals resample patients. Source tables are never joined into invented people.

The following are results for the selectable-horizon model, separate from the
older fixed 6/12-month snapshot model:

| 12-month evaluation | Test patients / transitions | MAE | Within primary tolerance | Within secondary tolerance |
|---|---:|---:|---:|---:|
| SE internal | 316 / 915 | 0.4261 D | 71.58% within ±0.50 D | 84.70% within ±0.75 D |
| SE external RELS | 1,901 / 8,758 | 0.5451 D | 57.55% within ±0.50 D | 75.74% within ±0.75 D |
| AL internal | 17 / 51 | 0.1097 mm | 54.90% within ±0.10 mm | 84.31% within ±0.20 mm |

**The 90% point-prediction target is unmet.** These are predefined engineering
error tolerances, not clinical acceptance standards. They were fixed before
the benchmark and were not widened to manufacture a passing result. R-squared,
relative error percentages and interval coverage are not substitutes for these
point-error results. The external SE model also trails the earlier standalone
cohort Ridge experiment (MAE 0.5229 D); the new model's benefit is selectable time,
not a demonstrated accuracy improvement at every horizon or in every population.
On the tiny two-patient DIMS SE test, pooled MAE 0.4176 D trails carry-forward
0.1971 D. This is particularly relevant to treated patients.

Ranges target nominal 90% coverage using separate patient-grouped calibration.
They are labeled **Estimated range**. Measured 12-month coverage was 96.50%
internal SE, 95.22% external SE and 100% internal AL, with mean widths 2.5002 D,
2.6342 D and 0.8897 mm respectively. Wide ranges can cover observations while
point predictions remain inaccurate. These measurements establish neither
90% point accuracy nor coverage at unmeasured/extrapolated months.

The full report is
[trajectory_model.metrics.json](../backend/artifacts/trajectory_model.metrics.json).
It includes per-horizon and per-source errors, patient confidence intervals,
carry-forward comparisons and training-only selection records. The prior
[model improvement report](MODEL_IMPROVEMENT.md) documents fixed-horizon and
onset experiments separately.

## API and rebuilding

```text
GET  /api/v1/me/prediction?horizon_months=10
GET  /api/v1/patients/{id}/prediction?horizon_months=60
POST /api/v1/simulator/forecast
     {"age":10,"spherical_equivalent":-1.5,"axial_length":23.9,"horizon_months":24}
```

Personal and cohort routes retain their existing authorization. The public
forecast endpoint requires no account. Responses include requested months,
monthly horizons, model version, support labels and limitations. Invalid or
fractional months return 422. Missing trajectory artifacts return 503.
Omitting the query parameter retains the older stored 6/12-month snapshot,
including historical version replay.

From `backend`, with project dependencies installed and the fixed model built:

```sh
python scripts/build_research_datasets.py
OMP_NUM_THREADS=1 python -m app.ml.trajectory
```

`make model` and the Docker model stage include both steps. Model serialization
uses the importable `app.ml.trajectory.HorizonRateRegressor` class so a new API
process can load the artifact. Local tests cover fresh-process loading, duration
validation, read-only API behavior, missing AL, source integrity and leakage.
Docker deployment has not been verified on this machine.
