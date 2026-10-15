# Data onboarding contract

One row per de-identified subject/visit. Never invent absent measurements.

| Field | Units / contract |
|---|---|
| patient_key | Stable de-identified study key; group splits by this key, not eye/visit |
| visit_date | Actual YYYY-MM-DD, not in the future; null when unpublished |
| followup_month | Source-recorded elapsed months when calendar dates are absent |
| spherical_equivalent | Dioptres; sphere + cylinder/2; negative means myopic; -30 to +15 |
| axial_length | Millimetres; 15 to 35 |
| age | Recorded age in years at that visit; missing remains missing |
| sex | male/female/other/unknown only when supported by a reviewed codebook |
| treatment | Recorded treatment; never treat unknown as untreated |
| parental_myopia | Recorded count 0/1/2 |
| visual_acuity | logMAR, -0.3 to 2.0 |
| corneal_curvature | Millimetres |
| screen_time_hours / sleep_hours | Hours/day or night; leave absent columns missing |
| near_work_min / outdoor_min | Minutes/day |
| viewing_distance_cm | Centimetres, non-medical-grade exposure |
| posture_score | 0 to 1; higher means better; scale must be documented |
| continuous_session_min | Minutes of uninterrupted near work |
| source | Verified source label |

Use a single time convention per subject. Relative months are NOT a licence to
invent a baseline date. No duplicate subject/time pairs. Loaders reject missing
keys/time and out-of-range numeric values; target building drops visits missing
SE or AL and never uses future metadata in an earlier feature row. Document
all dropped records. An eye-level dataset must retain the original subject as
the split group; two eyes are not independent patients.

`fetch_datasets.py --sources dims --offline` verifies the bundled CC BY 4.0 input.
`build_training_table.py` accepts the reviewed DIMS structure and writes the
normalized table, content hash, source provenance and DATA_CARD. Training refuses
missing/invalid provenance or generated sources. The reviewed adapter leaves B/G
sex codes unknown rather than inferring a mapping, and retains baseline age only.

Dryad d4mb3pn and c2fqz615c metadata/licenses/checksums were fetched, but workbook
responses were HTML. They are not admitted to training. Exact download locations
and expected checksums are in DEPLOYMENT.md. Review actual headers, timing,
cycloplegia, subject/eye linkage and units before adding an adapter. Shanghai's
independent 2014/2018 school samples do not establish within-child follow-up.

Before introducing private institutional data: approved data-use/consent scope,
de-identification at source, a lawful private storage location and institutional
security review are required. Keep the identity/key mapping outside Iiris. No real
patient data goes to free/public hosts. The public release training path currently
accepts verified open-source research only; hospital adapters require a separate
reviewed pipeline and private deployment.

FHIR maps actual dates only; relative months are a project extension. Ocular
codes are explicitly project-local, not guessed LOINC/SNOMED. The read facade is
not a terminology-validated EHR integration or a complete FHIR server.

See [the Kaggle candidate review](KAGGLE_DATASET_REVIEW.md) for inspected onset,
cross-sectional, imaging and synthetic sources. Discovery does not admit a
source to training; verify its license, endpoint and subject/time linkage first.

## Additional datasets and separate onset endpoint

See [CURRENT_DATASETS.md](CURRENT_DATASETS.md) and [ONSET_MODEL_CARD.md](ONSET_MODEL_CARD.md)
for the newly integrated OLSM onset model, Aier-SERI baseline reference and
Miopia noncommercial research tables. The progression metrics/cohort above are
unchanged. Make/Docker now build both models offline from bundled licensed inputs.
