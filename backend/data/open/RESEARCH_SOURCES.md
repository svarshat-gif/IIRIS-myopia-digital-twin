# Research source register

The exact SHA256 fingerprints and license identifiers are in `research_sources.json`. Generated research tables are checksum-verified against that register before training.

## Model training and external evaluation

- **Zenodo DIMS 36-month cohort:** [record 18166476](https://zenodo.org/records/18166476), CC BY 4.0. The 20-subject, 140-visit dataset supplies the existing fixed-horizon forecasts and the selectable-horizon SE/AL model. It is combined with GOAL for the 12-month SE model.
- **PLOS GOAL and RELS cohorts:** [PLOS Medicine article](https://journals.plos.org/plosmedicine/article?id=10.1371/journal.pmed.1002674), [S1 data supplement](https://journals.plos.org/plosmedicine/article/file?type=supplementary&id=10.1371/journal.pmed.1002674.s002), CC BY 4.0. The published workbook includes 1,610 GOAL and 2,042 RELS participant IDs with scheduled annual cycloplegic right-eye refraction. GOAL is used for 12-month and selectable-horizon SE training; RELS is held aside for study-level evaluation. No AL, exact exam dates, age, or outdoor-treatment assignment is present in the normalized tables. No treatment effect is estimated. The PLOS paper reports the population cohorts as distinct; DIMS overlap cannot be checked from the available data.
- **Kinoshita 2020 orthokeratology/atropine trial:** [Mendeley Data V7](https://data.mendeley.com/datasets/y58rh8bfkv/7), [Scientific Reports study](https://www.nature.com/articles/s41598-020-69710-8), CC BY 4.0. This verified, ingested source contributes AL labels to selectable-horizon development and patient-grouped evaluation: 73 children (38 orthokeratology plus 0.01% atropine, 35 orthokeratology alone), with 438 normalized right-eye visits at nominal enrollment months 0, 3, 9, 15, 21, 27. Trial baseline and atropine initiation occur at enrollment month 3 after orthokeratology stabilization; training anchors start at month 3 or later. SE and age are available only at enrollment and stay missing at follow-up. Allowed target: AL only. The unchanged raw workbook, repository metadata, source manifest, and codebook are retained under `kinoshita/`; `scripts/normalize_kinoshita.py` verifies its hash, headers, original patient IDs, eye allocation and visit structure before producing the long-format table. These are existing-myopia treatment completers, not incident-onset cases or untreated controls.
- **OLSM / aplore3 0.9:** [CRAN source archive](https://cran.r-project.org/src/contrib/aplore3_0.9.tar.gz), GPL-3. Original R data, package codebook, source archive, and full `COPYING` are retained. The 618 observations match the Kaggle Myopia Study after documented category decoding. Kaggle's copy is not the redistribution source.

## Reference-only datasets

- **Aier-SERI:** [Kaggle source](https://www.kaggle.com/datasets/panwei052117/ivi-questionnaire-responses-aier-seri), CC0. The unmodified 431-person adult baseline workbook is preserved; codebook eye-side ambiguity is not silently resolved. It has no future outcomes.
- **Miopia:** [Kaggle source](https://www.kaggle.com/datasets/manueldepradogarcia/miopia), CC BY-NC 4.0. Original CSVs and derived research table are separate. The 132 labeled and 24 unlabeled rows have no verified longitudinal links or matching follow-up, so they are not model inputs.
- **Jinshan three-year cohort:** [Dryad record](https://datadryad.org/dataset/doi:10.5061/dryad.d4mb3pn), mirrored at [Zenodo record 4987818](https://zenodo.org/records/4987818), CC0. The 2,024-row workbook matches the recorded fingerprints but publishes no stable subject IDs; no repeat-person identity is inferred from row order, birth year, sex, or similar values.

## Screened out

- [Human Lifestyle and Daily Habits](https://www.kaggle.com/datasets/neevvv/human-lifestyle-and-daily-habits-dataset): synthetic and has no eye measurements or outcomes.
- Kaggle Data3 mirror: unknown license/origin and no verified patient identifiers; the matching Dryad data are reference-only for the same linkage issue.
- Axial-prediction dataset: unresolved license and static measurements without follow-up.
- Shandong habits supplement: large cross-sectional table without longitudinal linkage or eye outcomes; its CC BY-NC-ND terms do not permit derived model training here.

## Access-gated candidates (not included)

- **Fudan 15-year refractive cohort:** the [study](https://translational-medicine.biomedcentral.com/articles/10.1186/s12967-024-05075-0) reports 88,250 people and 408,255 records, but its data-availability statement says person-level records are not public and must be requested from the corresponding authors. Strong candidate for a large same-endpoint onset evaluation if access is granted.
- **Anyang Childhood Eye Study:** the [cohort access listing](https://atlaslongitudinaldatasets.ac.uk/datasets/aces) describes 5,160 children with annual 3-5-year follow-up. Access requires contacting the study team; not downloaded or included.
- **CLEERE:** the [onset analysis](https://pmc.ncbi.nlm.nih.gov/articles/PMC11060695/) is relevant to pediatric onset, but machine-readable person-level data are not supplied with the paper. Access would need separate confirmation.

No unrelated cohorts are joined, no missing clinical measures or exposures are invented, and no baseline-only dataset is described as future follow-up. License links: [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/), [CC0](https://creativecommons.org/publicdomain/zero/1.0/), [CC BY-NC 4.0](https://creativecommons.org/licenses/by-nc/4.0/), [GPL-3](https://www.gnu.org/licenses/gpl-3.0.html). The complete GPL-3 license text for OLSM is in `olsm/COPYING`.
