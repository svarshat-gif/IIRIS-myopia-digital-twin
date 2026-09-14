# Connecting real data

How to replace the synthetic cohort with real, approved, de-identified data. The column
contract is identical to the synthetic file, so **no application code changes** — only the
CSV and one retraining command.

---

## 0. Before any data moves

Complete every item. This is not paperwork you can do afterwards.

- [ ] **Ethics / IRB approval** obtained, with the data-use scope written down
- [ ] **Data-use agreement** signed, covering storage location, retention and deletion
- [ ] **De-identification at source.** Names, MRNs, dates of birth, addresses, phone
      numbers, emails and free-text notes never leave the hospital system. Only a study key
      travels.
- [ ] **The key mapping stays at the hospital**, not in this repository, not in the
      database, not in a spreadsheet on a laptop
- [ ] **Storage location confirmed** to be legally permitted, and confirmed *not* to be a
      public free-tier host
- [ ] **`API_KEY` set** and, for anything beyond a single-user prototype, real
      authentication in place — see [SECURITY.md](SECURITY.md)
- [ ] **`.gitignore` verified.** `backend/data/*.csv` is already ignored. Confirm with
      `git status` before your first commit, every time.

> If behaviour or ergonomics are not recorded by the hospital, **leave those columns out
> entirely**. The system is designed to run on clinical fields alone and reports data
> completeness per layer. Never fabricate an exposure value to make a column look full.

---

## 1. The column contract

One row per **patient-visit**, in a CSV.

### Required

| Column | Type | Units | Notes |
|---|---|---|---|
| `patient_key` | string | — | De-identified study key. Stable across visits. **Never an MRN.** |
| `visit_date` | date | `YYYY-MM-DD` | Must be a real calendar date, not in the future |
| `spherical_equivalent` | float | dioptres (D) | Negative = myopic. `sphere + cylinder/2` |
| `axial_length` | float | millimetres (mm) | Typically 20–30 |

### Optional — clinical

| Column | Type | Units | Notes |
|---|---|---|---|
| `age` | float | years | Age **at this visit** |
| `sex` | string | — | `male` / `female` / `other` / `unknown` |
| `parental_myopia` | int | count | 0, 1 or 2 myopic parents |
| `visual_acuity` | float | logMAR | Convert from Snellen before import |
| `corneal_curvature` | float | mm | Mean keratometry radius |
| `treatment` | string | — | `none`, `single_vision`, `atropine`, `ortho_k`, `dims` |

### Optional — behaviour

| Column | Type | Units |
|---|---|---|
| `screen_time_hours` | float | hours/day |
| `near_work_min` | float | minutes/day |
| `outdoor_min` | float | minutes/day |
| `sleep_hours` | float | hours/night |

### Optional — ergonomics (non-medical-grade)

| Column | Type | Units | Notes |
|---|---|---|---|
| `viewing_distance_cm` | float | cm | Habitual working distance |
| `posture_score` | float | 0–1 | 1 = good posture. Define your scale and document it. |
| `continuous_session_min` | float | minutes | Typical unbroken near-work session |

Any other columns are ignored. Missing values must be **empty**, never `0`, `-1`, `999` or
`"NA"`.

### Example

```csv
patient_key,visit_date,age,sex,parental_myopia,spherical_equivalent,axial_length,visual_acuity,treatment,screen_time_hours,near_work_min,outdoor_min,viewing_distance_cm,posture_score,continuous_session_min
H0001,2023-02-14,8.4,female,1,-0.75,23.41,0.00,none,3.5,180,90,32,0.7,40
H0001,2023-08-22,8.9,female,1,-1.10,23.58,0.02,none,4.0,200,75,30,0.7,45
H0001,2024-02-19,9.4,female,1,-1.45,23.76,0.05,dims,4.5,210,60,29,0.65,50
H0002,2023-03-02,11.1,male,0,-2.20,24.30,0.05,none,,,,,,
```

Note `H0002`: clinical fields only. That is a perfectly valid row.

---

## 2. Unit conventions — get these right

| Quantity | Expected | Common mistakes |
|---|---|---|
| Spherical equivalent | dioptres, **negative for myopia** | Sign flipped; sphere used without the cylinder term |
| Axial length | **mm** | Sent in metres or microns |
| Visual acuity | **logMAR** | Snellen fractions or decimal VA left unconverted |
| Screen time | **hours** per day | Minutes sent as hours |
| Near work / outdoor | **minutes** per day | Hours sent as minutes |
| Viewing distance | **cm** | Inches |
| Posture score | **0–1**, 1 = good | 0–100 scale, or inverted so 1 = bad |

A unit error will not throw an exception. It will produce confident, wrong predictions.
Check the summary statistics after import (step 4).

---

## 3. Validation the system performs for you

`app/ml/dataset.py:load_visits` and the pydantic schemas enforce:

- required columns present, otherwise a clear error naming what is missing
- `visit_date` parses as a date and is not in the future
- `spherical_equivalent` within −30 to +15 D
- `axial_length` within 15 to 35 mm
- `visual_acuity` within −0.3 to 2.0 logMAR
- `posture_score` within 0 to 1
- rows missing SE **or** AL are dropped from training (they cannot be a target)
- duplicate `(patient, visit_date)` pairs are rejected with `409`

**Not** checked automatically, so check them yourself:

- unit correctness (see above)
- sign conventions
- whether a "visit" is one eye or an average of both — **decide and be consistent**
- whether refraction is cycloplegic (it should be, for children)

---

## 4. Import and retrain

```bash
cd backend
cp /secure/path/hospital_cohort.csv data/hospital_cohort.csv

# Retrain on real data. `data_is_synthetic` becomes false automatically.
.venv/bin/python -m app.ml.train --data data/hospital_cohort.csv

# Load into the database, building a twin version per visit.
.venv/bin/python scripts/seed_demo.py \
    --data data/hospital_cohort.csv \
    --patients 0 --reset \
    --consent-status approved \
    --data-source hospital
```

Or, over HTTP, `POST /api/v1/patients/bulk-import` with a `rows` array using the same
field names plus `external_key`.

### Immediately check the summary statistics

```bash
.venv/bin/python - <<'PY'
import pandas as pd
df = pd.read_csv("data/hospital_cohort.csv")
g = df.sort_values(["patient_key","visit_date"]).groupby("patient_key")
print(df[["spherical_equivalent","axial_length"]].describe())
print("visits per patient:", g.size().describe().to_dict())
span = (pd.to_datetime(g["visit_date"].last()) - pd.to_datetime(g["visit_date"].first())).dt.days/365.25
ann = (g["spherical_equivalent"].last() - g["spherical_equivalent"].first()) / span.replace(0, float("nan"))
print("annual SE change: mean %.3f  median %.3f" % (ann.mean(), ann.median()))
PY
```

Sanity ranges for a school-age cohort: axial length mostly 22–26 mm, SE mostly −8 to +2 D,
mean annual SE change roughly −0.2 to −0.8 D/year. **If annual change is positive, your sign
convention is inverted.**

---

## 5. Read the results honestly

The synthetic cohort produces R² ≈ 0.99 because it is generated by a deterministic equation
the model can nearly invert. **Real data will be worse, and that is correct, not a bug.**

What to look at on the Model card tab:

- **MAE against the carry-forward baseline.** Carry-forward means "assume nothing changes".
  If your model does not beat it, the model adds nothing. This is the single most important
  comparison in the project.
- **Interval coverage vs nominal.** Should land near 0.90. Far below means the intervals are
  over-confident; far above means they are uselessly wide.
- **The ablation table.** Does adding behaviour, then ergonomics, actually reduce error?
  **Report the answer either way.** "The ergonomic layer did not improve prediction in this
  cohort" is a legitimate, publishable finding and is much stronger than quietly dropping
  the experiment.
- **Number of patients, not rows.** 4 800 rows from 600 patients is 600 independent units.
  Report patient counts.

---

## 6. Horizons and follow-up intervals

Targets are built by looking forward from each visit for a follow-up near **+6** and **+12**
months, with a ±2.75-month tolerance (`HORIZON_TOLERANCE_MONTHS` in `app/ml/dataset.py`).

If your cohort is followed annually, the 6-month target will be mostly empty and that model
will be skipped with a warning. Adjust `HORIZONS` and the tolerance to match your real
follow-up schedule rather than forcing the data to fit the default.

---

## 7. FHIR code verification

Before exchanging with a real EHR, replace the project-local codes in
`app/fhir/mapping.py:MEASURE_MAP` with verified LOINC/SNOMED CT codes and record them here:

| Measure | Local code | Verified LOINC/SNOMED | Verified by | Date |
|---|---|---|---|---|
| Spherical equivalent | `se` | *(to be filled)* | | |
| Axial length | `al` | *(to be filled)* | | |
| Visual acuity (logMAR) | `va-logmar` | *(to be filled)* | | |
| Corneal curvature | `k-mean` | *(to be filled)* | | |

Behaviour and ergonomics may legitimately stay as local codes — they are project-specific
survey items, not standard clinical observations.

---

## 8. Retiring the synthetic data

Once real data is connected:

```bash
rm backend/data/synthetic_cohort.csv
```

Keep `scripts/generate_synthetic.py` in the repository. It documents exactly what the
synthetic data was and lets anyone reproduce the prototype without access to real data —
which is precisely what a reviewer will want.
