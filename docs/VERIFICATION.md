# Verification and remaining work

Local verification on 15 October 2026. This report distinguishes executed checks
from prepared infrastructure. The full deployment definition of done remains open.

## Executed checks

| Check | Result |
|---|---|
| Verified workbook -> normalization -> real training | Passed; 20 subjects, 140 visits; no generated fallback |
| Backend pytest | 94 passed; 10 upstream/deprecated-name warnings |
| Requested aggregate coverage | 89.81% |
| Coverage by requested module | core 88.17%, ML 90.34%, simulator 91.23%, twin 89.19% |
| Ruff | Passed |
| Installed Python dependency consistency | pip check: no broken requirements |
| Frontend Vitest/Testing Library | Four tests passed |
| Frontend production build | Passed; initial JS 214.39 kB / 70.54 kB gzip; charts loaded separately |
| Playwright/Chrome smoke | Two flows passed on an isolated SQLite test database |
| Last Lighthouse 12.8.2 accessibility run (before onset UI addition) | Sign-in 100; public simulator 95 |
| SQLite Alembic upgrade + schema check | Passed on fresh databases; no pending operations |
| Postgres initial migration SQL generation | Passed in offline mode; not a live Postgres test |
| Production browser dependencies | npm audit --omit=dev: zero advisories |
| Theme files | tailwind.config.js and src/index.css unchanged from baseline commit 66930a2 |

Backend coverage is line coverage across the four requested packages, not a claim
that every production failure mode is tested. The suite exercises ownership and
staff assignments, unauthorized reads/writes, audit events, rate limits, lockout,
production guards, upload sniffing/storage mocks, FHIR, immutable versions, persisted
monitor flags, leakage, actual-data training, scenario refusals and numeric narration
guards. Synthetic measurements in test fixtures never seed the shipped demo/model.

Browser flows cover signup, record entry, a version update, public baseline
simulation, patient role denial, clinician cohort/detail, adding the actual D1
month-36 observation (v6 -> v7), a recalculated prediction, persisted monitor,
version diff, unsupported scenario messaging, evidence/tool trace, model card and
390-pixel mobile overflow. Clinician axe checks cover WCAG A/AA rules except
color-contrast. Lighthouse reports a color-contrast issue on the simulator; the
existing palette remains frozen, and the score still exceeds the requested 90.
No claim is made that every screen is fully WCAG conformant.

Local QA reports are ignored in .tools/final-coverage.json,
.tools/lighthouse-login.json and .tools/lighthouse-simulator.json. Browser
screenshots/traces are ignored under frontend/test-results. These are local
verification evidence, not release inputs.

## Legacy data and current demo

The original default database contained 27 synthetic records, 216 observations,
two accounts and 18 appointments. It was moved intact to the ignored local archive
backend/tests/fixtures/legacy/prototype_myopia_twin.db. This preserves the prior
accounts/data without using them in the current application. Do not publish this
archive or use it for training, metrics or demonstrations.

A fresh default SQLite database was migrated and seeded with 20 verified DIMS
subjects and 120 observations/versions through month 24, withholding the real
month-36 measurements for the demo loop. It contains no invented appointments or
default accounts/passwords. Create an admin explicitly using bootstrap_admin.py
and a password you supply. The complete 140 visits are used in model training.
Smoke-test accounts/data are isolated in ignored databases ending smoke_test.db.

## Not executed / still required

- Docker and WSL are unavailable on this machine. Container builds, Compose
  healthchecks and live Postgres migrations must run on a Docker-equipped host.
- S3/R2 integration is covered with interface mocks only; configure a private
  bucket and perform a real upload/download/ownership check before hosting.
- GitHub Actions definitions are prepared; no remote CI run has been observed.
- No hosting account, cloud secrets, public URL or live deployment was created.
- The two Dryad workbooks remain unverified. Download Data3.xlsx and
  DATA.xls/README.docx via their normal repository pages; inspect headers, timing,
  subject/eye linkage and units before implementing the longitudinal adapter.
- Optional SHAP, XGBoost, LightGBM and LangGraph pins resolve in a dependency dry
  run but those optional libraries were not installed/exercised. Default runtime
  uses deterministic tools and ablation attribution; optional Ollama was not run.
- Development tooling retains npm advisories associated with the frozen Tailwind 3
  toolchain. Do not equate the zero runtime audit with a zero development audit.
- The 20-subject model has no demonstrated clinical utility; two test patients
  cannot establish generalization or coverage. Behaviour/treatment contrasts are
  unavailable. Larger data and external evaluation are substantive remaining work.

Start with [DEPLOYMENT.md](DEPLOYMENT.md), then run the prepared CI/container checks.
The larger-data, container, storage, hosted-deployment and clinical-validation
items must not be marked complete on the basis of this local verification.

New dataset integration: source hash/license guards, 618-subject independent onset
training, missingness preservation and authenticated domain checks are included
in the 94 passing tests. The browser Model Card smoke also exercises the separate
five-year estimate form. See CURRENT_DATASETS.md. Docker/cloud remain unverified.
