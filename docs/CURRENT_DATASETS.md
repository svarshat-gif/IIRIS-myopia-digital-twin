# Current dataset integration

Updated 16 October 2026 after the Kaggle source review. Four datasets now have
explicit roles in Iiris; only two are used for models, with different endpoints.

| Source | Included data | Current role | License |
|---|---|---|---|
| [Zenodo DIMS](https://zenodo.org/records/18166476) | 20 subjects / 140 visits | Existing 6/12-month SE/AL progression training; real demo seeded through month 24 | CC BY 4.0 |
| [OLSM / aplore3](https://cran.r-project.org/web/packages/aplore3/index.html), matching [Kaggle Myopia Study](https://www.kaggle.com/datasets/mscgeorges/myopia-study) | 618 subjects / 81 onsets | New separate five-year onset model: clinical and clinical + weekly activity | GPL-3 upstream source |
| [Aier-SERI](https://www.kaggle.com/datasets/panwei052117/ivi-questionnaire-responses-aier-seri) | 431 unique adult baseline subjects | Included baseline/quality-of-life reference table; no forecasting model or clinical-record seed | CC0 |
| [Miopia](https://www.kaggle.com/datasets/manueldepradogarcia/miopia) | 132 labeled + 24 unlabeled rows | Included noncommercial research table only; unique subjects/linkage unverified | CC BY-NC 4.0 |

The OLSM license barrier was resolved by acquiring the explicitly licensed CRAN
upstream, verifying its repository checksum and comparing every numeric/category-
decoded row against Kaggle. License/source attribution, original R data and full
package source are bundled. The progression patient count is unchanged; the additional subjects are not DIMS
visits. Training-only selection now improves change forecasts on the existing
benchmark; see MODEL_IMPROVEMENT.md. The onset challenger was not promoted.

Aier-SERI's [source publication](https://pmc.ncbi.nlm.nih.gov/articles/PMC12510582/)
confirms the Kaggle release and CC0. Its eye-side codebook ambiguity remains
explicit; original field names are preserved. Miopia remains a noncommercial
research input; source scales/protocol and label-adjacent leakage need review
before training. It is not used to claim additional forecast accuracy.

## Rebuild and access

`make model` now verifies/builds both training paths. The Docker model stage does
the same offline, so bootstrap builds both artifacts automatically. Host commands:

```sh
cd backend
python scripts/build_research_datasets.py
OMP_NUM_THREADS=1 python -m app.ml.onset
```

On PowerShell, set `$env:OMP_NUM_THREADS='1'` before the Python training command.
No rdata/R install is needed for normal rebuilds. Generated tables and catalog
are under backend/data/research; the new model is onset_model.joblib with a tracked
onset_model.metrics.json. All source inputs are verified against research_sources.json.

`GET /api/v1/meta/datasets` reports roles, counts, licenses, limitations and
exclusions. `GET /api/v1/meta/model` includes separate research/onset metadata.
The signed-in Model Card displays the datasets, independent onset scores and
research estimate form. See [ONSET_MODEL_CARD.md](ONSET_MODEL_CARD.md) for inputs,
split, uncertainty and restrictions. Source attribution is in
backend/data/open/RESEARCH_SOURCES.md.

## Still excluded

The supplied Human Lifestyle & Daily Habits data is explicitly synthetic and has
no ocular outcomes. It is not trained, seeded or shipped as research input.
Data3's Kaggle mirror has unknown rights, no subject IDs and differs from the
Dryad artifact; no trajectories are inferred from row order. Axial prediction
has unresolved rights and no follow-up outcomes. Dryad original downloads remain
unverified. These blocks are shown by the catalog rather than bypassed.

No unrelated cohorts are joined by age/sex, no exposures are invented for DIMS,
and no baseline observation is presented as a future target. Behavioural onset
associations do not enable the progression simulator's unavailable what-ifs.
Public free hosting remains limited to de-identified, licensed research data.
Because this research demo includes a CC BY-NC input, Miopia data must be removed
or separately authorized before any commercial distribution/use.
