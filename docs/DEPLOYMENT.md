# Deployment: local verification first, free research demo second

Status on 15 October 2026: the Python/React app, tests, browser smoke flows,
SQLite migration and health endpoints were exercised locally. Docker/Compose,
Postgres integration, S3 against a real account and a hosted deployment were NOT
executed: this computer has no Docker engine or WSL. CI includes these container
checks, but no remote CI run has been observed. Do not call deployment verified.

## Local prerequisites and first run

Install Docker Desktop (Linux containers/Compose), Python 3.12 and Make. On
Windows, use WSL/Git Bash for Make, or invoke the Python bootstrap directly.
Install `pip install -r backend/requirements-dev.txt` for host training/tests.
From the repository root:

```sh
cp .env.example .env
# Edit .env: JWT_SECRET >=32 random characters, ADMIN_EMAIL,
# ADMIN_PASSWORD >=12 characters. DEMO_PASSWORD is optional, never bundled.
python -c "import secrets; print(secrets.token_urlsafe(48))"
make bootstrap
docker compose up -d
curl --fail http://localhost:8000/healthz
curl --fail http://localhost:8000/readyz
```

Windows without Make: `python backend/scripts/bootstrap.py` followed by
`docker compose up -d`. Bootstrap loads the root .env. It builds the images,
waits for Postgres, migrates, seeds 20 actual open-research subjects through month
24, and creates the requested admin. Optional demo login attaches an existing
research record; it creates no fictitious person, visits, exposures or appointments.
Admin bootstrap refuses to promote an existing account implicitly. Re-running
it after a successful first run will report that the admin exists; use compose
up directly for ordinary restarts. Database and local uploads have named volumes.
Open http://localhost:8080. Sign in as admin and assign research records to a
clinician. Create a clinician with:

```sh
docker compose run --rm api python scripts/bootstrap_admin.py --email clinician@example.org --role clinician
```

This uses ADMIN_PASSWORD from your local .env; use a separate password in a real
multi-account setup. Assign via authenticated `POST /api/v1/admin/assignments`
with `clinician_id` and `patient_id`. An admin can inspect the whole cohort.

## Reproducible model artifact

The Docker model stage trains inside the image from the bundled, unmodified
CC BY 4.0 DIMS workbook. It verifies the repository MD5 and local SHA256, builds
the table/provenance, trains and copies only the model, metrics and normalized
research table into the runtime. No download is needed during that stage and no
ignored host artifact is required. `make model` reproduces the same pipeline on
the host. Model version includes data and training-code fingerprints.

The source input is 20 subjects/140 visits, not a clinically validated cohort.
The runtime refuses a missing or synthetic artifact. Never load an untrusted
joblib file. CI archives the real model/metrics/table as a release artifact;
archive the associated source/code commit together. Synthetic fixtures and raw
unverified downloads are excluded from Docker contexts.

## Free hosted research stack

Verified official plan descriptions on 13 October 2026:

- Static frontend: Cloudflare Pages Free (or Render static hosting). Build from
  `frontend` with `npm ci && npm run build`; publish `dist`. `_redirects` provides
  SPA routing. Set VITE_API_BASE_URL to the HTTPS API origin. This is a public URL,
  not a secret. No deployment key is sent by browser code.
- API: [Render Free web service](https://render.com/docs/free), Docker, repository
  Dockerfile `backend/Dockerfile`, build context `backend`, health check `/readyz`.
  The Docker model stage solves the artifact problem on Git-based deploys. Free
  services sleep after 15 minutes idle; first request can take about a minute.
  The filesystem is ephemeral. Render says these plans are not production
  application hosting. This is a research demo only.
- Database: [Neon Free](https://neon.com/pricing), Postgres with its TLS-enabled
  connection string. The current page lists 1 GB/project and 100 CU-hours monthly.
  Set DATABASE_URL, using postgresql+psycopg. Render's own free database expires
  after 30 days, so do not use it as durable demo storage.
- Uploads: a private [Cloudflare R2 bucket](https://developers.cloudflare.com/r2/pricing/)
  within its Standard storage free allowance, or an S3-compatible private
  Supabase Storage bucket. Set S3_ENDPOINT_URL, S3_BUCKET, S3_ACCESS_KEY_ID,
  S3_SECRET_ACCESS_KEY and S3_REGION. Use a bucket-scoped credential. The API
  streams authenticated downloads; no public object ACL is needed.
- CI: GitHub Actions subject to the account's included minutes/storage. Keep
  within the free quotas; no paid tier is required for this small demo. Free
  allowances and billing activation requirements can change; check the linked
  providers at account creation. No auto-deploy credentials are included.

Required API environment: ENVIRONMENT=production, JWT_SECRET (>=32 characters),
JWT_EXPIRE_MINUTES=30, AUTH_GATE=jwt, explicit HTTPS CORS_ORIGINS, Postgres
DATABASE_URL, STORAGE_BACKEND=s3 and all S3 settings above, LLM_PROVIDER=none.
The frontend never receives any of these secrets. The API's production guard
refuses unsafe defaults. `AUTH_GATE=api_key` is an optional extra server/reverse
proxy gate; never put that key in VITE_ variables.

`start.py` runs Alembic before serving, with one worker because rate limits are
in process. For release tooling with a shell, run `python -m alembic upgrade head`
explicitly. On free Render, which lacks shell/release commands, startup migrations
provide the equivalent path. Provision the admin by running the same Docker image
locally against the approved demo database with injected environment secrets;
do not add a public bootstrap endpoint. Seed only the bundled research records.

Use the provider's managed HTTPS/TLS URL, configure CORS to the exact static site
origin, and keep Postgres TLS enabled. HSTS is enabled in production. Access tokens
expire after 30 minutes and require signing in again. No auth cookies are used.

## Checks and recovery

`/healthz` is a lightweight liveness ping; `/readyz` verifies DB connectivity and
model loading. `/api/v1/health` includes model version and source. A failed DB or
model check returns 503. Logs are JSON and responses carry request IDs.

Migrations were tested on a fresh SQLite database. Existing pre-migration installs
need a backup/export and explicit schema migration review; do not stamp an old DB
as current or delete it to make an error disappear. Postgres and the container
healthchecks must still be run on a Docker-equipped host using the CI commands.

**Public-demo privacy:** only de-identified, openly licensed research records.
Never upload actual patient records, prescriptions, names or attachments to a
free public host. The personal-entry features are for local/approved private
installations. Free demo hosting is not clinical infrastructure.

## Dryad downloads still pending

- https://doi.org/10.5061/dryad.d4mb3pn : Data3.xlsx (155656 bytes).
  Expected SHA256 1072365a4fd398061fac3ef5221ae10e222e4e95b77029b05b6ddc58b4cfe0df.
- https://doi.org/10.5061/dryad.c2fqz615c : DATA.xls (2306560 bytes) and README.docx.
  DATA.xls SHA256 355785f24c8f56ae2dfbdd3cb89bd8a4025694a8326acfe6398e183df124508d.

Use the normal repository download in your browser. Put files under
backend/data/raw/dryad_3year/ and backend/data/raw/shanghai/. Run fetch_datasets.py
with `--sources dryad_3year shanghai` to retrieve metadata and verify checksums,
or use --offline with cached metadata.json and files.json. HTML responses are
rejected. The Dryad longitudinal adapter remains deliberately unimplemented
until actual headers, eye linkage and visit timing can be reviewed. Shanghai is
excluded from progression training unless a reliable longitudinal linkage is
established. The DIMS-only release remains reproducible while that review is pending.

## Additional datasets and separate onset endpoint

See [CURRENT_DATASETS.md](CURRENT_DATASETS.md) and [ONSET_MODEL_CARD.md](ONSET_MODEL_CARD.md)
for the newly integrated OLSM onset model, Aier-SERI baseline reference and
Miopia noncommercial research tables. Progression data remain separate; current retraining results are in MODEL_CARD.md. Make/Docker now build both models offline from bundled licensed inputs.
