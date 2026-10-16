# Implementation report

The requested local engineering work is implemented and committed by workstream.
The complete production/deployment definition of done is not yet satisfied;
[VERIFICATION.md](VERIFICATION.md) identifies exactly what ran and what remains.

| Workstream | Delivered | Remaining limitation |
|---|---|---|
| A: data and ML | Checksum/license fetcher with offline path; reviewed DIMS adapter; canonical relative-time data; provenance/hash checks; real grouped fitting/calibration/test and repeated development CV; cluster CIs, baselines, model/data cards; generated data confined to tests; real demo seed | Only DIMS workbook accessible; 20 subjects; no independently supplied units/eye codebook; Dryad adapters await files/review |
| B: backend | Assignment RBAC; audit; auth policy/lockout/short JWT; IP/user limits; headers/body/upload controls; Alembic; private local/S3 abstraction; FHIR facade; logs/health/readiness; installable dependency pins | Live Postgres/S3 not tested; advanced identity/retention/backup controls absent |
| C: twin, simulation, agent | Immutable version/monitor persistence; seven registered tools; cited literature fallback; deterministic default/loopback Ollama only; hallucinated-number rejection; unsupported scenario gate/extrapolation warnings | Numeric exposure/treatment effects unavailable in actual cohort; no local Ollama run |
| D: frontend | Existing theme retained; clinician cohort/detail, history/diff, intervals, attribution, update/monitor, agent trace and honest model card; role routes; loading/errors/validation; route/chart splitting | Accessibility checked on representative routes; existing contrast issue remains |
| E: deployment | Real-model Docker build stage; non-root API/UI; Postgres Compose; migration/bootstrap scripts; env examples; free-stack runbook and Render blueprint; CI gates | Docker/WSL unavailable; no remote CI/cloud/storage verification or hosted URL |
| F: quality/docs/demo | 99 backend tests (88.89% target-module coverage), four UI unit tests, two browser flows, Lighthouse 100/95, migrations, eight-step real-observation demo and honest benchmark note | Full deployment definition of done stays open |

## Data sources and measured results

Used: [Zenodo DIMS](https://zenodo.org/records/18166476),
[direct DataSet.xlsx download](https://zenodo.org/records/18166476/files/DataSet.xlsx?download=1),
CC BY 4.0. Twenty subject rows link SE/AL at 0/3/6/9/12/24/36 months (140 visits).
Baseline age is retained; calendar dates, normalized sex, family history,
VA/keratometry and all exposure variables remain missing. See DATA_CARD.md for
raw column facts, missingness, unit caveats, attribution and checksums.

Not used: [Dryad 452-child three-year cohort](https://doi.org/10.5061/dryad.d4mb3pn)
and [Dryad Shanghai 2014/2018](https://doi.org/10.5061/dryad.c2fqz615c).
CC0 was verified in metadata, but workbook downloads returned HTML/401. Shanghai
has no verified within-child linkage; neither source is part of training or
external validation. Exact manual file locations/checksums are in DEPLOYMENT.md.

| Target | Model MAE | Carry-forward MAE | Ridge MAE | Measured row coverage |
|---|---|---|---|---|
| SE 6 months (D) | 0.1258 | 0.1675 | 0.2589 | 100% |
| SE 12 months (D) | 0.3204 | 0.335 | 0.2851 | 100% |
| AL 6 months (mm) | 0.0363 | 0.0633 | 0.6807 | 100% |
| AL 12 months (mm) | 0.04 | 0.1333 | 0.6302 | 100% |

Only two independent test patients (8 fitting/10 calibration/2 test). All four
change forecasts beat carry-forward on the reused benchmark; Six-month SE still trails RF, and 12-month SE trails
Ridge/RF. R-squared/coverage are not accuracy and 95% overall accuracy is not achieved.
No clinical usefulness claim is justified. Full RMSE/R-squared, bootstrap bounds,
patient-simultaneous coverage, RF baseline and development CV are in MODEL_CARD.md.
BENCHMARKS.md distinguishes the source paper's explanatory association from an
out-of-sample forecast metric.

## First deployment commands and manual setup

Install Docker Desktop/Compose, Python 3.12 and Make (or use the Python bootstrap
on Windows). From the repository root:

```sh
pip install -r backend/requirements-dev.txt
cp .env.example .env
# Set JWT_SECRET (32+ random characters), ADMIN_EMAIL and ADMIN_PASSWORD (12+).
make bootstrap
# Windows without Make: python backend/scripts/bootstrap.py
docker compose up -d
curl --fail http://localhost:8000/readyz
```

Open http://localhost:8080. Bootstrap trains from the bundled licensed workbook
inside the image, migrates and seeds real records, then creates your admin.
No default password is bundled. Run CI/container health checks before calling the
container path verified. For the free research host, create Render, Neon and
Cloudflare Pages/R2 accounts; set exact HTTPS CORS, TLS Postgres connection and
private S3 credentials as documented. These are manual account/secret steps.
Public free hosts may contain only de-identified open research records.

## Additional datasets and separate onset endpoint

See [CURRENT_DATASETS.md](CURRENT_DATASETS.md) and [ONSET_MODEL_CARD.md](ONSET_MODEL_CARD.md)
for the newly integrated OLSM onset model, Aier-SERI baseline reference and
Miopia noncommercial research tables. Progression data remain separate; current retraining results are in MODEL_CARD.md. Make/Docker now build both models offline from bundled licensed inputs.
