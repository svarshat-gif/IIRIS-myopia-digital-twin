# Current datasets and model roles

Updated 17 October 2026. Iiris keeps each source's endpoint and purpose separate; the cohorts below are not pooled into one generic accuracy score.

| Dataset | Data in the project | Model role | License |
|---|---:|---|---|
| [Zenodo DIMS 36-month dataset](https://zenodo.org/records/18166476) | 20 subjects / 140 visits | Source for the existing fixed-horizon SE and AL models and the selectable-horizon SE/AL model. It is also the de-identified demo cohort. | CC BY 4.0 |
| [PLOS GOAL and RELS supplement](https://journals.plos.org/plosmedicine/article/file?type=supplementary&id=10.1371/journal.pmed.1002674.s002) | GOAL: 1,610 subjects / 6,440 scheduled rows; RELS: 2,042 subjects / 12,252 scheduled rows | GOAL trains and calibrates the 12-month and selectable-horizon SE models. RELS is held out for cross-cohort evaluation. A separate SE-change risk challenger failed RELS validation and was not released. The workbook contains annual cycloplegic SE, not AL or treatment assignment. | CC BY 4.0 |
| [Kinoshita two-year orthokeratology/atropine trial](https://data.mendeley.com/datasets/y58rh8bfkv/7), [study](https://www.nature.com/articles/s41598-020-69710-8) | 73 children / 438 right-eye visits | Ingested for selectable-horizon AL development and patient-grouped evaluation. Enrollment months are 0, 3, 9, 15, 21, 27; training anchors start at month 3. SE and age are recorded only at enrollment; follow-up SE and age remain missing. Allowed target: AL only. | CC BY 4.0 |
| [OLSM / `aplore3` CRAN package](https://cran.r-project.org/src/contrib/aplore3_0.9.tar.gz), matching the [Kaggle Myopia Study](https://www.kaggle.com/datasets/mscgeorges/myopia-study) | 618 subjects / 81 five-year onset outcomes | Separate five-year onset association model. Training uses the license-verified CRAN source; the Kaggle copy was used only for row-by-row source comparison. | GPL-3 upstream |
| [Aier-SERI adult high-myopia cohort](https://www.kaggle.com/datasets/panwei052117/ivi-questionnaire-responses-aier-seri) | 431 baseline subjects | Reference table only; no future target. | CC0 |
| [Miopia medical-student dataset](https://www.kaggle.com/datasets/manueldepradogarcia/miopia) | 132 labeled and 24 unlabeled rows | Noncommercial research table only. Subject linkage and outcome protocol are insufficient for longitudinal model training. | CC BY-NC 4.0 |
| [Jinshan three-year cohort (Dryad)](https://datadryad.org/dataset/doi:10.5061/dryad.d4mb3pn), [verified Zenodo copy](https://zenodo.org/records/4987818) | 2,024 measurements; no subject IDs | Reference only. Row order and demographic combinations do not establish repeat-person linkage, so it is excluded from longitudinal training. | CC0 |

The PLOS paper reports GOAL and RELS as distinct population cohorts and evaluates longitudinal SE forecasts across multiple resources. The source supplement and paper are openly available under CC BY 4.0 ([paper and methods](https://journals.plos.org/plosmedicine/article?id=10.1371/journal.pmed.1002674)). GOAL's intervention assignment is absent from the workbook, so Iiris makes no treatment-effect estimate. Neither PLOS cohort contains axial length; those cohorts contribute only to SE development or evaluation.

Kinoshita's original trial baseline is three months after orthokeratology enrollment, once the corneal response has stabilized. Atropine starts at that time in the combination arm. The normalized table preserves the original enrollment month labels; trajectory training excludes anchors before month 3. The two treatment groups have 38 combination and 35 orthokeratology-only completers. Original patient IDs and right-eye source cells are retained, and the raw workbook checksum is verified before normalization. This treated cohort supplies no untreated-control or future SE labels. The selectable-horizon model learns from measured visit pairs; unmeasured intervals inside the observed range are interpolation, and intervals below or above that range are extrapolation with unverified accuracy. See [forecast support and evaluation](FORECAST_HORIZONS.md).

The provided [Human Lifestyle and Daily Habits Kaggle dataset](https://www.kaggle.com/datasets/neevvv/human-lifestyle-and-daily-habits-dataset) is explicitly synthetic and contains no ocular outcomes, so it is not model training data. Other screened data with unknown licensing, static measurements, or no reliable subject linkage remain excluded. The UI dataset catalog records these roles, source links, licenses, counts, checksums, and limitations.

## Access-gated datasets to pursue

The strongest identified candidate for improving five-year onset estimation is
the Fudan Eye & ENT Hospital 15-year refractive cohort: 88,250 people and
408,255 cycloplegic refraction records collected from 2005-2019. The authors say
the records are not publicly accessible and must be requested. The [Anyang
Childhood Eye Study](https://atlaslongitudinaldatasets.ac.uk/datasets/aces)
has 5,160 children at baseline and annual follow-up for 3-5 years, but its data
also require contact with the study team. Neither is included in Iiris. We need
explicit data-use terms and a de-identified, linked patient-visit table before
either can be used. See [the acquisition checklist](DATA_ACQUISITION_PLAN.md).

## Rebuild and access

`make model` verifies and rebuilds the DIMS baseline, onset model, expanded 12-month SE model, and selectable-horizon trajectory model. The Docker model stage follows the same sequence. Host commands:

```sh
cd backend
python scripts/build_research_datasets.py
OMP_NUM_THREADS=1 python -m app.ml.onset
OMP_NUM_THREADS=1 python -m app.ml.expanded --without-catboost --promote
OMP_NUM_THREADS=1 python -m app.ml.trajectory
```

Generated tables and the catalog are under `backend/data/research`; source fingerprints are in `backend/data/open/research_sources.json`. `GET /api/v1/meta/datasets` exposes dataset roles and restrictions. `GET /api/v1/meta/model` exposes the released model version, sources, held-out metrics, and limitations.

The Kaggle Myopia Study mirror itself has no verified redistribution grant; Iiris uses the matching, explicitly licensed upstream CRAN package. Miopia's noncommercial license blocks commercial reuse unless it is removed or separately authorized.
