# Benchmarks and source-paper context

The numerical model-vs-baseline comparison is in [MODEL_CARD.md](MODEL_CARD.md)
and its linked generated metrics JSON. Carry-forward retains the current SE/AL;
Ridge is a regularized linear baseline; Random Forest is the additional nonlinear
comparison. All use the same untouched patient holdout. No result from a generated
cohort is reported as performance.

The [Dryad three-year dataset abstract](https://datadryad.org/dataset/doi:10.5061/dryad.d4mb3pn)
reports 452 children, non-cycloplegic refraction and mean three-year changes of
0.89 +/- 0.51 mm AL and -0.95 +/- 1.41 D SE. It reports R-squared 0.009 for the
association of baseline AL with three-year AL elongation. The linked source paper
is [Li, Jiang and Zhou, BMJ Open 2019](https://doi.org/10.1136/bmjopen-2019-029896).
These numbers were verified in the repository's published abstract; the paper
page itself could not be retrieved here. The workbook has not been used.

That explanatory association is NOT a held-out forecast score. Its outcome,
horizon, population and measurement protocol differ from Iiris's DIMS-treated
SE/AL level forecasts. Therefore no numerical superiority comparison or shared
leaderboard is justified. The Zenodo DIMS metadata supplies no source-paper
forecast benchmark; no such result is invented. The excluded Shanghai source
compares school samples in 2014/2018 and supplies no verified within-child forecast
benchmark for this implementation.

A [January 2026 npj Digital Medicine paper](https://www.nature.com/articles/s41746-025-02308-4)
already describes a large Transformer for personalized myopia progression and
interventions. Iiris makes no first-predictor or better-than-that-paper claim.
The software contribution is the integration of versioned history, uncertainty,
capability-gated scenarios, cited agent tools, monitoring and an API.
