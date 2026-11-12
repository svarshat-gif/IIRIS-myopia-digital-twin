# Myopia model data acquisition plan

Updated 17 October 2026. The immediate priority is improving selectable-month
SE and axial-length forecasts. The separate five-year incident-myopia model
remains an additional endpoint. These tasks retain separate data and metrics.

## SE and axial-length priority

The app supports 1–120 months, but the current training intervals cover 3–36
months. More static or unrelated lifestyle rows cannot validate new horizons.
We need independently linked pediatric visits with measured cycloplegic SE,
axial length, actual examination times, age, eye side, site, treatment and
treatment changes. Both treated and untreated children are needed; most of the
new AL source received orthokeratology. Follow-up beyond three years is required
to test longer forecasts rather than extending a short-term rate assumption.

Retain study/site identifiers for a genuinely separate external test, and keep
all visits from a child in the same partition. Freeze the model and engineering
error tolerances before evaluating that test. Report SE within ±0.50 D and AL
within ±0.10 mm separately, with MAE, patient-level uncertainty and results by
elapsed horizon, age and treatment. The current model does not reach 90% under
these tolerances. Access to a larger cohort may help; it cannot guarantee a
passing result. See [current horizon results](FORECAST_HORIZONS.md).

## Priority access requests

1. **Fudan Eye & ENT Hospital 15-year refractive cohort.** The published study
   reports 88,250 people and 408,255 cycloplegic refraction records from
   2005-2019, including longitudinal onset outcomes. The authors say the data
   are not public and may be requested from the corresponding authors. Ask for
   the de-identified person-visit file, age at visit, cycloplegic SE, stable
   subject key, outcome definition, data dictionary, ethics/data-use terms, and
   permission for model development and external evaluation. The published
   aggregate metrics are not a substitute for evaluating Iiris on shared data.
   Source: [study and data availability](https://translational-medicine.biomedcentral.com/articles/10.1186/s12967-024-05075-0).

2. **Anyang Childhood Eye Study (ACES).** The cohort profile reports 5,160
   children at baseline and annual follow-up over 3-5 years. Its data access
   listing says researchers must contact the study team. Request the same
   linked-visit and outcome fields, with axial length, cycloplegic SE, parental
   myopia, age, sex, and exposure/treatment measurements if collected.
   Source: [cohort profile and access information](https://atlaslongitudinaldatasets.ac.uk/datasets/aces).

3. **CLEERE.** This large multi-site onset study is clinically relevant to
   baseline risk. The published onset analysis reports cohort-level modeling,
   but a machine-readable person-level dataset is not provided with the article.
   Consider a separate access request if Fudan/ACES access is unavailable.
   Source: [CLEERE onset study](https://pmc.ncbi.nlm.nih.gov/articles/PMC11060695/).

No request has been sent and none of these datasets is included in Iiris yet.
Data access, permitted use, identifiers, and schemas must be confirmed before
download or training.

## Intake requirements

Before onboarding a cohort, verify the dataset license/data-use agreement and
retain its source, version, file hashes, data dictionary, and preprocessing
record. Each person must have a stable de-identified key so every visit stays
in one split. The onset endpoint requires an initially nonmyopic baseline and
dated follow-up sufficient to determine incident onset within five years.
Measurements recorded after onset must never be predictors for that outcome.
Treatment and study site should be retained for subgroup checks, not used to
infer causal treatment effects.

The primary onset report will give raw accuracy, sensitivity, specificity,
and patient-level confidence intervals. Probability calibration and operating-
threshold selection will use separate development data; the research operating
point will have a provisional minimum sensitivity of 80%. The test cohort will
not select a model or threshold. The 90% raw-accuracy target
must also meet that sensitivity floor and be confirmed on a distinct cohort.
The current 618-person OLSM sample, with only 16 onset cases in its fixed test
partition, cannot establish that target.

For continuous outcomes, report MAE/RMSE in diopters or millimeters and
pre-specified tolerance rates. Do not combine SE and AL errors into a single
classification-accuracy claim. Keep onset cohorts, refraction cohorts, and
treatment-specific progression cohorts as separate evaluations until their
protocols and patient identities can be verified.

## Draft access request

> Subject: Request for de-identified longitudinal myopia data for external model evaluation
>
> Dear study team,
>
> We are evaluating a research prototype that predicts five-year myopia onset
> and near-term refraction change in children. Would you consider sharing a
> de-identified, person-linked visit table from your cohort for independent
> model evaluation? We would need the data dictionary, outcome and measurement
> protocols, follow-up dates or ages, and any restrictions on storage,
> redistribution, publication, or model training. We can provide a short
> analysis plan and comply with required ethics or data-use approvals.
>
> We would not use aggregate published scores as model training data, infer
> missing measurements, or make treatment-effect claims. Please let us know
> whether a formal application or collaboration agreement is required.
>
> Sincerely,
>
> Iiris research team
