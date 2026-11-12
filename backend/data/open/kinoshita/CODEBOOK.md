# Kinoshita 2020 two-year orthokeratology trial

Dataset: https://data.mendeley.com/datasets/y58rh8bfkv/7

Article: https://www.nature.com/articles/s41598-020-69710-8

License: CC BY 4.0. Attribution: Kinoshita N, Konno Y, Hamada N, Kanda Y,
Shimmura-Tomita M, Kaburaki T, Kakehashi A (2020), Mendeley Data V7,
doi:10.17632/y58rh8bfkv.7. Associated article: Scientific Reports 10:12750,
doi:10.1038/s41598-020-69710-8.

The workbook has one sheet, `OK and 0.01% atropine`. It contains 73 study
completers: 38 assigned to orthokeratology plus 0.01% atropine, and 35 to
orthokeratology alone. Each original Study ID spans two rows, right eye then
left eye. Normalization retains right eyes only and namespaces original IDs
by treatment group. Registration dates are not retained in the model table.

| Source column | Meaning |
| --- | --- |
| A | Original Study ID, unique within treatment group |
| C | Age at original enrollment, years |
| D | Sex (`M` or `F`) |
| E | Cycloplegic spherical equivalent at original enrollment, diopters |
| H | Eye (`R` or `L`) |
| I, K, N, Q, T, W | Measured axial length in mm at enrollment months 0, 3, 9, 15, 21, 27 |
| AX, AY | Compliance percentages over the study, excluded from forecast predictors |

Enrollment month 3 is the randomized trial baseline after orthokeratology
stabilization. Trial follow-up months 0, 6, 12, 18, 24 therefore correspond to
enrollment months 3, 9, 15, 21, 27. The normalized `followup_month` preserves
the enrollment labels. Atropine starts at enrollment month 3. Combination-arm
enrollment month 0 is pre-atropine, so this interval must not be treated as
continuous combination treatment.

SE is available only at original enrollment. It is left missing at every
follow-up. No future SE targets, corrected-refraction targets or carried-forward
SE labels are created. Follow-up age is also left missing; the separately named
`age_at_enrollment_years` is an explicit repeated baseline covariate. Nominal
month labels are preserved because exact follow-up examination dates are absent.

The raw file SHA256 is
`423771baddd91a25356603c750b78dc45b8d6fdb3c0b18788eb21a72d6e011b5`.
Run `python scripts/normalize_kinoshita.py` from the backend directory to reproduce
the 438-row right-eye visit table and its provenance. This source is suitable
for separately labeled AL development/evaluation in its treatment population.
It provides no evidence about untreated natural history or future SE.
