# Kaggle dataset suitability review

Reviewed 15 October 2026. This is a discovery and schema audit, not a training run.
The release remains trained solely on verified Zenodo DIMS data, model
`mdt-20261015-3e539413`. None of the candidates below was added to the training
manifest, demo records or reported performance.

The supplied Myopia Study is the strongest candidate for a **separate five-year
onset-risk model**, conditional on resolving its reuse terms and source discrepancy.
The supplied lifestyle dataset is explicitly synthetic and must be excluded.
No reviewed Kaggle candidate currently satisfies all requirements for patient-linked
6/12-month SE/AL forecasts with measured behavioural and ergonomic exposures.

## What was actually checked

Public Kaggle API metadata, file listings and downloadable files were inspected
without an account token. Twenty-five cached search responses covered myopia
(pages 1-6), myopic, myopia progression, myopia longitudinal, myopia risk, Orinda,
CLEERE, axial length/elongation, ocular biometry/biometric, spherical equivalent,
refraction/refractive error, near work/nearwork, vision screen time, eye strain
and DIMS. Results contained 185 distinct hits, including irrelevant material,
images and trained model artifacts; this is not a claim that 185 usable cohorts
were inspected. Thirteen shortlisted datasets received metadata review. Seven
small archives were opened, producing ten CSV/workbook-sheet inspections.

[Machine-readable findings](KAGGLE_DATASET_REVIEW.json) retain columns, missingness,
local fingerprints, metadata versions and decisions. Download fingerprints are
locally calculated SHA256 values; Kaggle did not supply repository checksums in
the inspected file-list responses. Cached original metadata/files stay ignored
under backend/data/raw/kaggle_review. The temporary synthetic lifestyle archive
was removed after inspection; no synthetic rows were retained for application use.
Downloaded material was parsed as data, never executed.

## Supplied links

### Human Lifestyle & Daily Habits: exclude

[Dataset](https://www.kaggle.com/datasets/neevvv/human-lifestyle-and-daily-habits-dataset)
| [public metadata](https://www.kaggle.com/api/v1/datasets/view/neevvv/human-lifestyle-and-daily-habits-dataset)

- Actual file: Lifestyle_Habit_Dataset.csv; 25,000 rows and 28 columns; ages 18-65.
- Kaggle declares CC BY 4.0. Its author explicitly describes a generated structural
  causal model, with injected noise/anomalies and missingness. An SCM label does
  not turn generated relationships into observed clinical causal evidence.
- Includes smartphone/laptop/gaming hours and sleep, but no SE, axial length,
  refraction, myopia outcome, subject ID or linked follow-up measurements.
- It cannot train or validate the release model or supply real exposures to DIMS
  subjects. Similar age/sex columns do not establish a cross-dataset patient join.
- At most it is a source for isolated software test fixtures, clearly synthetic;
  there is no need to include it in the research demo or model metrics.

### Myopia Study (OLSM): useful for a different endpoint, pending license

[Dataset](https://www.kaggle.com/datasets/mscgeorges/myopia-study)
| [public metadata](https://www.kaggle.com/api/v1/datasets/view/mscgeorges/myopia-study)
| [uploader's variable dictionary](https://github.com/ggeop/Myopia-Study/blob/master/myopia%20variables.pdf)

The actual semicolon-delimited myopia.csv has **618 rows, 618 unique IDs and 18
columns**, no duplicate IDs/rows and no missing cells. Ages are 5-9; entry years
are 1990-1995. MYOPIC is 1 for 81 children and 0 for 537. The Kaggle prose cites
554 children/45 onsets from a paper, which does not describe the exact file count;
that discrepancy must be resolved rather than copied into a model card.

The uploader's dictionary and [CRAN aplore3 documentation](https://cran.r-project.org/web/packages/aplore3/aplore3.pdf)
identify the endpoint as myopia onset within five years. The CSV has a single
baseline ocular/exposure row per child, not a repeated-visit export. STUDYYEAR is
the entry year, not a sequence of patient visits.

| Available information | Actual fields and semantics |
|---|---|
| Baseline ocular measures | SPHEQ in D; AL, ACD, LT, VCD in mm |
| Activity history | SPORTHR, READHR, COMPHR, STUDYHR, TVHR; hours/week |
| Near-work composite | DIOPTERHR, a weighted activity proxy |
| Demographics/family | AGE, GENDER, MOMMY, DADMY; codebook verifies original 0/1 categories |
| Outcome | MYOPIC: five-year incident myopia, not 12-month fast progression |
| Missing for our forecast | Follow-up SE/AL values, dates, viewing distance, posture, continuous sessions, sleep and treatment history |

Potential use: a separately named and evaluated childhood onset-risk research
model, with clinical-only vs clinical-plus-activity comparisons. It must have its
own target, cohort, calibration, metrics, capability flags and model card. Its
probability cannot replace the existing 12-month progression-risk output.

SPORTHR combines sports/outdoor activity and cannot be silently relabeled as
measured outdoor minutes. Weekly computer/TV activity is not modern smartphone
screen time. Unit conversion may create a clearly labeled daily average, but
cannot create an unmeasured construct. Parent counts can be derived only after
verified coding; preserve the raw columns. All estimates would remain
associational, not intervention effects.

Kaggle's declared license is **Unknown**, and the uploader's GitHub has no explicit
license visible in its file list. CRAN distributes a matching textbook dataset
inside a GPL-3 package, but that package license is not silently assigned to this
Kaggle file. Resolve provenance/terms using an explicitly licensed upstream
source or rights-holder clarification before bundling or deploying it.

## Additional shortlisted Kaggle datasets

| Dataset | Inspected content | Appropriate use / decision |
|---|---|---|
| [Eye sight children](https://www.kaggle.com/datasets/sajvom99/eye-sight-children) | Data3.xlsx; 2,024 rows, 13 columns; examination years 2014-2017; bilateral sphere/cylinder/AL | Most relevant longitudinal lead, but blocked by unknown license/origin and absent subject IDs; details below |
| [Aier-SERI IVI and baseline data](https://www.kaggle.com/datasets/panwei052117/ivi-questionnaire-responses-aier-seri) | 431 unique adult IDs, 45 columns; bilateral SE/AL/VA, family history and 28 IVI responses; codebook included | Real, CC0 confirmed by source paper; useful adult baseline/quality-of-life research, not pediatric progression or exposure effects |
| [Miopia](https://www.kaggle.com/datasets/manueldepradogarcia/miopia) | X_train: 132 rows/49 fields; Y_train: 132 rows/four class labels; X_test: 24 rows/49 fields; ages 20-25 overall | Possible noncommercial adult cross-sectional classification after provenance/codebook review; CC BY-NC 4.0; no linked repeats |
| [Axial Length Prediction](https://www.kaggle.com/datasets/drskprabhakar/axial-length-prediction-dataset) | 108 rows; exactly KH, KV, AL; no missing cells | Static anatomy regression only; no SE, subject/time or exposures. License says Other but description is empty; not admitted |
| [Average Daily Screen Time for Children](https://www.kaggle.com/datasets/ak0212/average-daily-screen-time-for-children) | 198 age/gender/day/type aggregate rows, average hours and sample sizes | Not individual-linked ocular data; source collection unverified; cannot infer myopia effects |
| [Digital Eye Health and Screen Usage](https://www.kaggle.com/datasets/prince7489/digital-eye-health-and-screen-usage-data) | Metadata explicitly says synthetic, survey-inspired | Exclude; symptoms are not quantitative longitudinal myopia outcomes |
| [Indian Kids Screentime 2025](https://www.kaggle.com/datasets/ankushpanday2/indian-kids-screentime-2025) | Metadata explicitly says simulated | Exclude from release training; file not downloaded |
| [Ocular Disease Recognition/ODIR](https://www.kaggle.com/datasets/andrewmvd/ocular-disease-recognition-odir5k) | Fundus photographs and disease labels; metadata only | Different imaging task; uploader says source license unspecified; no progression/exposure export verified |
| [PALM Myopia](https://www.kaggle.com/datasets/fahimaislam1812/myopia) | Pathologic-myopia fundus images/annotations; metadata only | Different imaging task. Kaggle CC0 claim not independently traced to upstream terms; no large download |
| [Dry Eye Disease](https://www.kaggle.com/datasets/dakshnagra/dry-eye-disease) | Adult dry-eye/sleep/symptom dataset; metadata only | Different endpoint; no verified longitudinal SE/AL or source study |
| [MMAC-3 mirror](https://www.kaggle.com/datasets/rithikaa7/mmac-3) | Large archive; empty description; metadata only | No verified patient-linked exposure/progression table; not downloaded or admitted |

### Data3.xlsx: promising filename, insufficient linkage

This may relate to the [pending Dryad cohort](https://doi.org/10.5061/dryad.d4mb3pn):
filename, years and field descriptions overlap. This is an **inference**, not
verified provenance. Kaggle supplies no source description and declares Unknown
license. Its 145,464-byte workbook has SHA256
`6dfec6416c829a453fddd220b75d4fa60a988a72ea30e693fb1947ad2d5a0b58`, whereas
Dryad's 155,656-byte Data3.xlsx has published SHA256
`1072365a4fd398061fac3ef5221ae10e222e4e95b77029b05b6ddc58b4cfe0df`.
It is not a checksum-verified copy of the Dryad artifact.

Actual examination-year row counts: 2014: 513; 2015: 501; 2016: 503; 2017: 507.
The birthday and examination date fields contain **years only**, not full dates.
There is no subject ID. Gender plus birth year yields only six combinations and
cannot identify 2,024 observations' subjects. Neither row order nor height/weight
matching is acceptable proof of linkage. Consequently we cannot count unique
patients, form valid trajectories or enforce patient-disjoint evaluation yet.

Missingness also uses nonnumeric slash tokens: AL has 137 slash entries per eye;
cylinder has five per eye; axis has 198 per eye, in addition to blank cells. Height
and weight each contain four -1 entries. These require a documented missing-value
codebook. SE could be calculated as sphere + cylinder/2 after coding/units are
verified; both eyes must remain grouped by a true subject ID. No behavioural or
ergonomic fields are present. Annual time precision would not supply measured
six-month outcomes. Obtain the original verified source plus its linkage/codebook
before considering this source for progression training.

### Aier-SERI: strongest verified open provenance among new finds

The [primary PLOS One paper](https://pmc.ncbi.nlm.nih.gov/articles/PMC12510582/)
explicitly links this Kaggle dataset, confirms CC0 and describes a cross-sectional
baseline analysis. Our workbook inspection found 431 unique IDs, ages 29-78,
complete SE/AL/VA fields, two missing ages and item-level IVI missingness. There
are no visit dates, repeated IDs, measured activity exposures or future SE/AL.
The codebook's _l/_r labels describe the opposite eye to their suffixes; clarify
that inconsistency before making eye-specific claims or a clinical mapping.

It can support exploration of adult high-myopia measurements or quality of life.
It cannot be presented as external validation of a child's future SE/AL forecast,
and its outcomes cannot fill missing DIMS exposures. Neither its valid license
nor its sample size repairs the endpoint/population mismatch.

### Miopia: inspect the files, not just the description

The description advertises SE and sleep/screen variables, but the actual feature
files contain no spherical-equivalent column, no quantified sleep hours, and no
stable subject ID for linked visits. They do contain bilateral LA (axial length),
keratometry, family history, weekly activity proxies and CUVAF fields. The near-
activity field is entirely blank in both feature files. Dates alone do not prove
repeat visits. Labels describe existing myopia classes, with no future horizon.
Original collection/protocol and numeric scales still need documentation. Do not
reuse label-adjacent disease fields as predictors without a leakage review.

## Recommended next steps

1. Keep the current progression model and its unavailable exposure-effect flags
   unchanged. Do not join unrelated people across cohorts or treat baseline
   cross-sectional measurements as future targets.
2. Prioritize OLSM's verified upstream licensing/provenance for a separate onset
   model. Lock the endpoint/split before analysis; use realistic class-aware
   evaluation and compare clinical vs measured activity features. Do not infer a
   causal behavioural effect from a risk-model response to changed inputs.
3. Prioritize Data3's original artifact and documented patient linkage for the
   progression model. A larger file with no reliable linkage cannot justify
   narrower intervals, better metrics or a larger claimed patient count.
4. Retain Aier-SERI as a verified adult/QoL candidate and Miopia only as a
   conditional noncommercial adult cross-sectional candidate. Keep their metrics
   and populations separate from the deployed pediatric longitudinal model.
5. For the app's exposure/ergonomic progression layer, obtain a cohort measuring
   the same children's serial SE/AL and actual exposures at known times, with
   documented units, eye/subject IDs and clear reuse terms. None of this review's
   Kaggle sources currently fills that complete requirement.
