# Additional SE / AL accuracy search

Protocol fixed 17 October 2026 before calibration-gate or reused-test evaluation
of the new candidates. Incumbent: `trajectory-79d72ad57c4c`.

The aim is to improve the fraction of genuinely future measurements predicted
within **±0.50 D for SE** and **±0.10 mm for AL**. These existing primary error
limits stay fixed. Neither R-squared, interval coverage, training scores nor
classification of existing myopia can satisfy the point-forecast target.

## Development

Each measure uses only the existing fitting patients for feature/model selection.
Candidate families, feature sets, grouped folds and ensemble weights are fixed
before their CV scores are calculated and saved with the experiment report.
All visits and pairs belonging to a child stay in one fold. Development reports
include patient-balanced MAE and tolerance hit rates for all observed horizons,
12 months separately, and each source. Missing clinical outcomes remain missing.

New features may use measured SE/AL, history ending at the index visit, current
recorded treatment, and explicitly identified elapsed-time calculations from a
previously observed age. They may not use future age/SE/AL, source identifiers,
future treatment or synthetic targets. A history feature must use the identical
calculation at training and serving time. Optional CatBoost 1.2.10 supplements
the fixed sklearn candidate families.

An eligible challenger must improve development tolerance performance while
not worsening development MAE under its declared selection rule. Each search
exports one frozen candidate; unsuccessful searches remain research reports.

## Calibration promotion gate

After selection, compare the frozen candidate to the incumbent on the existing
calibration patients. The candidate must meet all of these conditions:

1. Patient-balanced MAE does not increase and the primary hit rate does not
   decrease, for both all observed horizons and 12 months.
2. Overall patient-balanced MAE does not increase within either source having
   at least five calibration patients.
3. There is a material overall improvement: at least 0.005 D MAE for SE,
   0.002 mm MAE for AL, or one percentage point in the primary hit rate.

Paired patient-bootstrap uncertainty accompanies these comparisons; passing
this development gate is not a claim of a statistically established clinical
improvement. The gate may reject both candidates. No weaker gate or wider error
tolerance will be substituted after seeing its results.

If a point model passes, refit its quantile models on fitting patients with the
same feature matrix and recalculate patient-grouped range correction using
calibration patients. Never reuse incompatible old-feature quantile models.
Do not fit the point model on the calibration or test patients.

## Reporting

Only after the gate is frozen and applied, evaluate each challenger once on
the existing internal benchmark and, for SE, RELS. These test sets have already
been inspected in earlier work; a new score is a **reused benchmark**, not a fresh
independent confirmation. Do not select another candidate after seeing it.
There is still no external AL cohort. A 90% claim requires independent measured
outcomes, fixed error limits, adequate patient-level precision and validation
at the claimed horizon/population. It cannot extend to unobserved months/years.

Preserve the incumbent artifact if its challenger fails the gate. Keep software
checks and model performance separate. Search reports record failures and
unavailable datasets as well as improvements.
