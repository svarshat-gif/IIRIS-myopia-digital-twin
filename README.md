# Iiris - Myopia Digital Twin

Iiris extends the existing FastAPI + React/Tailwind prototype into a versioned,
uncertainty-aware research twin with a clinician portal, audited access, a
capability-gated simulator, cited deterministic agent tools and a FHIR read facade.
The original warm-paper theme, fonts, tokens and component system are preserved.

**Current status:** working local research application. 99 backend tests passed
with 88.89% coverage across twin/simulator/ML/core, four frontend unit tests and two
browser smoke flows passed. Lighthouse accessibility: sign-in 100, simulator 95.
Docker/Compose, live Postgres/S3, remote CI and free-host deployment are not yet
verified on this machine (Docker/WSL/cloud accounts are absent). See
[verification and remaining work](docs/VERIFICATION.md) and the
[workstream report](docs/IMPLEMENTATION_REPORT.md).

## Real data and honest results

The progression model is trained on the unmodified, openly licensed
[Zenodo DIMS 36-month workbook](https://doi.org/10.5281/zenodo.18166476), CC BY 4.0:
20 independent subjects, 140 visits, repeated SE/AL at baseline and 3/6/9/12/24/36
months. Calendar dates and exposure data are absent and remain missing. The
original workbook, metadata and attribution are in backend/data/open; download
checksums and the normalized table's hash are verified by the pipeline.

Dryad d4mb3pn and Shanghai c2fqz615c metadata were inspected, but their downloads
returned HTML and failed verification. They are not silently used. The Dryad
longitudinal adapter needs actual workbook inspection; Shanghai appears to compare
independent cross-sectional school samples. See [data card](docs/DATA_CARD.md).

| Existing benchmark target | Model MAE | Carry-forward MAE | Ridge MAE | Model RMSE | R-squared | Measured interval coverage |
|---|---|---|---|---|---|---|
| SE 6 months (D) | 0.1258 | 0.1675 | 0.2589 | 0.1551 | 0.9877 | 100% |
| SE 12 months (D) | 0.3204 | 0.335 | 0.2851 | 0.3604 | 0.9399 | 100% |
| AL 6 months (mm) | 0.0363 | 0.0633 | 0.6807 | 0.0404 | 0.9995 | 100% |
| AL 12 months (mm) | 0.04 | 0.1333 | 0.6302 | 0.0457 | 0.9994 | 100% |

Only two independent test patients. Training/calibration/test are 8/10/2 patients.
The new point models forecast change from observed measurements and are selected
using training-only patient-grouped CV. All four targets beat carry-forward on
this **previously reported benchmark**; SE at six months still trails RF; at 12 months it trails Ridge/RF.
These scores and patient-bootstrap intervals are highly unstable. R-squared and
coverage are not percent prediction accuracy. Overall accuracy above 95% has not
been achieved. The retained onset model has 87.9% activity-model accuracy at the
fixed .5 threshold, versus 87.1% for predicting no onset for everyone; its
sensitivity is only 6.25%. See [model improvement report](docs/MODEL_IMPROVEMENT.md).
There is no demonstrated clinical utility. No risk classifier is released because
independent labels are insufficient. Behaviour/ergonomics ablations are marked
unevaluable and numeric exposure/treatment what-ifs are refused.

The [current dataset list](docs/CURRENT_DATASETS.md) now includes a separate
GPL-3 OLSM five-year onset model (618 children), CC0 Aier-SERI baseline reference
(431 adults), and Miopia noncommercial research tables (156 rows). These are not
additional progression visits. The [onset model card](docs/ONSET_MODEL_CARD.md)
reports its independent held-out evaluation. The earlier
[Kaggle review](docs/KAGGLE_DATASET_REVIEW.md) records the source audit.

See [model card](docs/MODEL_CARD.md) for repeated patient-grouped CV, cluster
bootstrap intervals, measured calibration coverage and benchmark limitations.

## First run

Install Docker Desktop with Compose and Python 3.12. From this repository root:

```sh
pip install -r backend/requirements-dev.txt
cp .env.example .env
# Set JWT_SECRET, ADMIN_EMAIL and ADMIN_PASSWORD in .env. No default credentials.
make bootstrap
docker compose up -d
```

Open http://localhost:8080. Windows without Make can run
`python backend/scripts/bootstrap.py` then `docker compose up -d`.
[Deployment instructions](docs/DEPLOYMENT.md) cover exact secrets, account setup,
TLS, free-tier limits, artifact strategy and pending Docker checks. Public free
hosts may contain only de-identified open research records, never actual patient
records or attachments. The Docker model stage trains from the bundled verified
workbook; it does not require a git-ignored model file.

Host-only development: `make model`, then from backend run
`python -m alembic upgrade head`, `python scripts/seed_demo.py --patients 20`, and
`uvicorn app.main:app --reload`. From frontend run `npm ci && npm run dev`.
Default SQLite/local storage are for development. Production requires Postgres,
S3-compatible private uploads, explicit HTTPS CORS and a strong JWT secret.

## What is included

- Patient-owned /me records, files and appointments; clinician/admin cohort views
  with assignment checks. Admin account bootstrap, assignment API and access audit.
- Observation -> immutable twin version -> prediction/interval -> persisted monitor
  loop; replay and diff. Shared history-aware feature building avoids future leakage.
- Seven agent tools: get_twin, predict, simulate, explain, retrieve_evidence,
  compare_scenarios, flag_changes. Deterministic by default; optional loopback-only
  Ollama narration rejects any unsupported number. No hosted AI provider path.
- Europe PMC -> PubMed -> bundled corpus with citation IDs/cache. FHIR Patient and
  Observation reads plus the existing Bundle export; project-local ocular codes.
- Request IDs/JSON logs, health/readiness probes, password policy, login lockout,
  short-lived JWTs, request/upload caps, security headers, rate limits and migrations.
- React route splitting; role-gated cohort/detail; version/monitor, trajectory bands,
  attribution, evidence trace and honest model-card screens using existing tokens.
- CI definitions for ruff, tests/coverage, leakage guards, frontend build, browser
  smoke, container build and health checks. These have not run remotely yet.

The seven core API operations remain under /api/v1/patients:
POST /patients, POST /patients/{id}/observations, GET /patients/{id}/twin,
GET /patients/{id}/prediction, POST /patients/{id}/simulate,
GET /patients/{id}/explanation and POST /patients/{id}/query. Visit /docs for OpenAPI.
Clinician access is assignment-scoped; patients use /api/v1/me/*.

## Limits and novelty

Observational data support association, not causation. Iiris is not a medical
device and provides no diagnosis, prescribing or autonomous treatment decisions.
Behaviour/ergonomics are non-medical-grade and absent from this model. Multi-year
rollouts feed predictions back into the model; their bands are heuristic beyond
the first step. No clinical validation or generalization claim is made.

A January 2026 [npj Digital Medicine paper](https://www.nature.com/articles/s41746-025-02308-4)
already reports a large Transformer for personalized myopia progression and
interventions. We make no "first AI myopia predictor" claim. The contribution is
the integration of a versioned twin, history, uncertainty, simulator capability
checks, cited tools, monitoring and an API. See [architecture](docs/ARCHITECTURE.md),
[security controls and gaps](docs/SECURITY.md), [onboarding](docs/DATA_ONBOARDING.md)
and the [eight-step demo](docs/DEMO_SCRIPT.md).

Generated data lives only in backend/tests/fixtures and cannot be used by the
release training/seed entrypoints. Do not quote its metrics. The bundled workbook
is CC BY 4.0; credit and original metadata are retained in backend/data/open/SOURCES.md.
