# Iiris

**A personal eye-health digital twin.** Iiris keeps every eye-test result a person has ever
had, shows how their short-sightedness is actually changing, projects the years ahead **with
an honest uncertainty range**, and lets them test what a different set of habits would do to
that projection.

Underneath it is a patient-specific, **stateful** computational twin: it remembers the
history, updates itself when a new result arrives, predicts with uncertainty, runs
counterfactual scenarios, explains every prediction, grounds discussion in retrieved
literature, and exposes all of it through its own API.

> **The contribution is not another myopia classifier.** It is a versioned twin that
> updates over time and can simulate alternative exposure trajectories while showing
> uncertainty and evidence. The ML model is one component *inside* the twin.

---

## ⚠️ Read this first

| | |
|---|---|
| **Clinical scope** | Decision support only. The system does **not** diagnose, does **not** prescribe, and does **not** establish causal treatment effects. |
| **Current data** | The repository ships with **synthetic data only**. No real patient data is included, and none should be added without institutional approval. See [Connecting real hospital data](#1-real-hospital-data-the-big-one). |
| **Current metrics** | Every number the app currently shows was produced from a generated cohort. `GET /api/v1/health` returns `data_is_synthetic: true`, and the UI shows an amber banner while that is the case. **Do not quote these metrics as clinical performance.** |
| **What-if results** | Produced by re-running a predictive model on modified inputs. They show how the model's expectation changes — not what would happen to the eye. |

---

## Table of contents

- [Quick start](#quick-start)
- [What is actually built](#what-is-actually-built)
- [Architecture](#architecture)
- [The API](#the-api)
- [What still needs to be connected](#what-still-needs-to-be-connected)
- [Configuration reference](#configuration-reference)
- [Project layout](#project-layout)
- [Testing](#testing)
- [Deployment](#deployment)
- [The demo script](#the-demo-script)
- [Limitations](#limitations)
- [Further docs](#further-docs)

---

## Quick start

Requirements: **Python 3.11+** and **Node 18+**. Nothing else — no database server, no
LLM, no API keys.

```bash
# 1. Install everything
make setup

# 2. Synthetic data -> trained model -> seeded database -> demo accounts
make demo

# 3. Two terminals
make api      # http://localhost:8000/docs
make ui       # http://localhost:5173
```

Then open **http://localhost:5173** and sign in with the demo account, which already has
four years of history in it:

| | |
|---|---|
| **Email** | `demo@iiris.health` |
| **Password** | `irisdemo2026` |

(The sign-in page has a one-click button for it. A second account,
`clear@iiris.health`, has only two results — useful for seeing the early-stage view.)

> Use `localhost`, not `127.0.0.1` — Vite binds to IPv6 on macOS.

### The app

| Page | What it does |
|---|---|
| `/` | Landing page |
| `/try` | **The simulator, with no account.** Type in an age and a prescription, get a projection |
| `/signup`, `/login` | Create an account or sign in |
| `/app` | Home: current status, trend, forecast, next appointment |
| `/app/records` | Every eye test, newest first, plus prescription photo uploads |
| `/app/appointments` | Past visits and upcoming reviews |
| `/app/simulator` | Project years ahead, and compare habit scenarios |
| `/app/insights` | Why the model says what it says, plus record version history |
| `/app/profile` | Details, password, and a FHIR export of the whole record |

<details>
<summary>Without <code>make</code></summary>

```bash
# backend
python3 -m venv backend/.venv
backend/.venv/bin/pip install -r backend/requirements.txt
cd backend
.venv/bin/python scripts/generate_synthetic.py     # synthetic cohort -> data/
.venv/bin/python -m app.ml.train                   # models -> artifacts/
.venv/bin/python scripts/seed_demo.py --patients 40 --reset
.venv/bin/uvicorn app.main:app --reload --port 8000

# frontend (new terminal)
cd frontend && npm install && npm run dev
```
</details>

You should now see 40 patients, each with 8 visits and a real 8-version twin history.

---

## What is actually built

Everything in this table runs today, against synthetic data, with no external service.

| Layer | Status | Where |
|---|---|---|
| **Evolving twin** — immutable versioned state, full replay of any past version | ✅ | [`app/twin/service.py`](backend/app/twin/service.py) |
| **Patient-adaptive prediction** — population model + this patient's own trajectory features | ✅ | [`app/ml/features.py`](backend/app/ml/features.py) |
| **Uncertainty** — quantile models, **conformally calibrated** so 90% means 90% | ✅ | [`app/ml/train.py`](backend/app/ml/train.py) |
| **Counterfactual engine** — multi-input scenarios, plausibility gate, dose-response sweeps | ✅ | [`app/simulator/`](backend/app/simulator/) |
| **Ergonomic digital phenotype** — structured exposure features + composite load index | ✅ | `ERGONOMIC_FEATURES` in `features.py` |
| **Explainability** — SHAP when installed, marginal-ablation fallback otherwise | ✅ | [`app/explain/explainer.py`](backend/app/explain/explainer.py) |
| **Tool-using agent** — explicit graph, full audit trace, works with **no LLM** | ✅ | [`app/agents/`](backend/app/agents/) |
| **Evidence / RAG** — Europe PMC → PubMed → bundled corpus, cached with citations | ✅ | [`app/evidence/`](backend/app/evidence/) |
| **FHIR R4 mapping** — Patient + Observation + flagged model outputs | ✅ | [`app/fhir/mapping.py`](backend/app/fhir/mapping.py) |
| **Digital Twin API** — 20+ endpoints, OpenAPI docs, optional API-key auth | ✅ | [`app/routers/`](backend/app/routers/) |
| **Dashboard** — trajectory + band, simulator, attribution, agent console, version diff | ✅ | [`frontend/src/`](frontend/src/) |
| **Ablation experiment** — clinical vs +behaviour vs +ergonomics on identical splits | ✅ | `make train`, shown on the Model card tab |
| **Real clinical data** | ❌ not connected | [see below](#1-real-hospital-data-the-big-one) |

### Design decisions worth defending in a viva

- **Missing means missing.** Behaviour and ergonomics are nullable everywhere. The models
  are `HistGradientBoosting`, which handles `NaN` natively, so a value is never invented to
  fill a gap. The UI shows per-layer data completeness so you can see what was actually
  collected.
- **Uncertainty that is honest.** Raw quantile regression under-covered badly here (0.72–0.77
  against a nominal 0.90). A split-conformal correction is fitted on a **held-out set of
  patients** and the calibrated intervals now cover 0.91–0.93. The model card reports both.
- **Splits by patient, never by row.** `GroupShuffleSplit` on `patient_key`, asserted in code.
  A patient's visits cannot straddle train and test.
- **The baseline that matters.** Every regression metric is reported next to a
  *carry-forward* baseline ("assume the next measurement equals the current one"). A
  progression model that cannot beat that column is not worth deploying.
- **The simulator refuses bad questions.** Values outside physiological range are rejected
  with `422`, not answered. Values that are possible but far from the patient's own baseline
  are answered *with a warning that the model is extrapolating*.
- **Differences smaller than the uncertainty are labelled as such.** The scenario table says
  "smaller than the prediction interval — not a meaningful separation" rather than letting a
  0.02 D difference look like a finding.
- **Accounts are separated from clinical data.** Identity (email, name) lives in `users`;
  measurements live in `patients` + `observations` with no name, MRN or contact column in the
  schema at all. A research export is de-identified by construction — you simply never join
  `users`. Passwords are PBKDF2-HMAC-SHA256 with a per-password salt and 480,000 iterations;
  sessions are signed JWTs.
- **The multi-year projection admits what it costs.** Beyond the first year the model is fed
  its own output, so errors compound. The interval is widened in quadrature at every step,
  and each year is labelled `modelled` → `projected` → `indicative` so a five-year number is
  never presented with the confidence of a one-year number.
- **Two models that disagree say so.** The regression and the progression-risk classifier are
  trained independently and can conflict on a record unlike the training cohort. The API
  computes the risk implied by the calibrated interval, compares it with the classifier, and
  when they diverge by more than 0.25 it returns `consistent_with_interval: false` and the UI
  shows the caution instead of a confident number that contradicts the range beside it.
- **Uploaded files are identified by their bytes, not their name.** A file's real
  type comes from its magic bytes; the client's `Content-Type` is ignored entirely. An
  HTML file renamed `.png` is refused, which closes the obvious path to storing something
  executable and serving it back inline. Downloads carry `nosniff` and a restrictive CSP,
  files are stored outside the repo under a generated name, and only the owning account
  can read them (404 to anyone else, never 403 — which would confirm the file exists).
- **The form and the API cannot disagree about what is valid.** Field bounds live in one
  table on each side, a test asserts every published range round-trips, and errors are
  rewritten to name the field as the interface labels it — a user who fills in "Eye length"
  should never be told something about `axial_length`.
- **The agent cannot hallucinate a number.** It obtains facts only through declared tools,
  and the answer is composed deterministically from tool output. If an LLM is attached, its
  prose is checked: every number must trace back to tool output or **the generated text is
  discarded** and the deterministic answer is returned. See `verify_numbers` in
  [`app/agents/llm.py`](backend/app/agents/llm.py).

---

## Architecture

```
                    ┌──────────────────────────────────────────┐
   New observation  │            React dashboard               │
        │           │  trajectory · simulator · attribution    │
        │           │  agent console · version diff · FHIR     │
        ▼           └────────────────────┬─────────────────────┘
 ┌──────────────┐                        │ HTTP (own API)
 │  FastAPI     │◄───────────────────────┘
 │  /api/v1     │
 └──────┬───────┘
        │
        ├──► Twin service ──► build state ──► store IMMUTABLE version (v1, v2, v3…)
        │         │
        │         ├──► Feature builder ──┬──► Prediction model (median + quantiles
        │         │   (one shared        │     + conformal calibration)
        │         │    implementation)   ├──► Risk classifier
        │         │                      └──► Explainer (SHAP / ablation)
        │         │
        │         └──► Simulator: clone twin → apply changes → SAME feature builder
        │                        → SAME model → compare vs baseline
        │
        ├──► Agent graph: route → plan → execute tools → check → compose
        │         tools: get_twin · predict · simulate · explain ·
        │                retrieve_evidence · compare_versions · flag_changes …
        │
        ├──► Evidence: Europe PMC → PubMed → bundled corpus (cached + cited)
        │
        └──► FHIR R4 export (Patient · Observation · flagged model outputs)

  Storage: patients · observations · twin_versions · predictions ·
           simulations · evidence · agent_runs      (SQLite → PostgreSQL)
```

**The loop that makes it a twin, not a dashboard:**

```
new observation → twin rebuilds → NEW VERSION stored → prediction recomputed
      → what-if scenarios → explanation → evidence → UI → next observation
```

---

## The API

Interactive docs at **http://localhost:8000/docs** once the server is running.

### Core seven (from the project guide)

| Endpoint | Purpose |
|---|---|
| `POST /api/v1/patients` | Create a de-identified patient record |
| `POST /api/v1/patients/{id}/observations` | **Add a visit → advances the twin to a new version** |
| `GET /api/v1/patients/{id}/twin` | Current twin state + history + derived trend |
| `GET /api/v1/patients/{id}/prediction` | 6/12-month SE + AL with prediction intervals, and risk |
| `POST /api/v1/patients/{id}/simulate` | Run a what-if scenario |
| `GET /api/v1/patients/{id}/explanation` | Per-prediction attribution |
| `POST /api/v1/patients/{id}/query` | Ask the tool-using agent |

### Accounts and personal records

Each account owns exactly one clinical record. Personal records are reachable **only**
through `/me/...`, by their owner — they are excluded from the generic `/patients` list, and
the tests assert that one user cannot read or delete another's data.

| Endpoint | Purpose |
|---|---|
| `POST /api/v1/auth/signup` | Create an account and an empty eye record |
| `POST /api/v1/auth/login` | Sign in, returns a bearer token |
| `GET /api/v1/auth/me` | The signed-in account |
| `PATCH /api/v1/auth/me` | Update name, age, sex, family history (rebuilds the twin) |
| `POST /api/v1/auth/change-password` | Change password |
| `GET /api/v1/me/summary` | **Everything the home screen needs, in one call** |
| `GET /api/v1/me/records` | Eye-test history with the change between visits |
| `POST /api/v1/me/records` | Add a result — advances the twin a version |
| `GET /api/v1/me/prediction` | Prediction with uncertainty and progression risk |
| `GET /api/v1/me/explanation` | Why the prediction looks like this |
| `POST /api/v1/me/project` | **Project years ahead, with an optional habit change** |
| `POST /api/v1/me/simulate` | Single what-if scenario at 6/12 months |
| `GET /api/v1/me/appointments` | Past and upcoming appointments (full CRUD) |
| `GET /api/v1/me/fhir` | Export the whole record as a FHIR R4 Bundle |
| `POST /api/v1/me/attachments` | **Upload a prescription photo or scan report** |
| `GET /api/v1/me/attachments` | List uploaded files |
| `GET /api/v1/me/attachments/{id}/file` | Download one (owner only) |
| `DELETE /api/v1/me/attachments/{id}` | Delete one |
| `POST /api/v1/simulator/project` | **Public** — project from typed-in values, no account |
| `GET /api/v1/simulator/inputs` | Fields the public simulator accepts, with ranges |

### Everything else

| Endpoint | Purpose |
|---|---|
| `GET /api/v1/health` | Liveness, model version, **`data_is_synthetic`** flag |
| `GET /api/v1/meta/model` | Full model card: metrics, ablation, importance, limitations |
| `GET /api/v1/meta/inputs` | Modifiable inputs + plausible ranges (the UI builds its sliders from this) |
| `GET /api/v1/meta/stats` | Row counts by table and data source |
| `GET /api/v1/patients` | Patient list with latest values and risk band |
| `POST /api/v1/patients/bulk-import` | **Load a whole cohort** — the real-data entry point |
| `GET /api/v1/patients/{id}/twin/versions` | Every stored version |
| `GET /api/v1/patients/{id}/twin/versions/{v}` | Replay one historical version exactly |
| `GET /api/v1/patients/{id}/twin/compare` | Diff two versions (observed + predicted) |
| `GET /api/v1/patients/{id}/monitor` | Did the latest update materially change the outlook? |
| `POST /api/v1/patients/{id}/simulate/batch` | Several scenarios at once |
| `POST /api/v1/patients/{id}/sensitivity` | Dose-response sweep of one input |
| `GET /api/v1/patients/{id}/simulations` | Stored scenario history |
| `GET /api/v1/patients/{id}/fhir` | FHIR R4 Bundle export |
| `GET /api/v1/agent/tools` | The tools the agent may call, with JSON schemas |
| `GET /api/v1/agent/graph` | The agent graph, introspected from the running code |
| `GET /api/v1/agent/runs` | Audit trail of past agent answers |
| `GET /api/v1/evidence/search` | Literature search (Europe PMC / PubMed / corpus) |
| `GET /api/v1/evidence/cached` | Previously retrieved citations |

**Why this is a Digital Twin API and not a `/predict` wrapper:** a normal ML API answers
*"what is the prediction?"*. This one answers *what is the patient's current state, how has
it changed, what does the model predict, what happens under a scenario, why did the model
say that, and what evidence relates to it* — and every new observation advances a stored,
replayable version.

---

## What still needs to be connected

This is the checklist for turning the working prototype into the full project. Items are
ordered by how much they matter.

### 1. Real hospital data (the big one)

Everything else already works. **This is the only piece that changes what the numbers mean.**

**Before any data moves:**

- [ ] Institutional ethics / IRB approval, with the data-use scope written down
- [ ] A signed data-use agreement covering storage location and retention
- [ ] De-identification **at source** — no names, MRNs, dates of birth, addresses or contact
      details ever leave the hospital system. Only a study key (`external_key`) travels.
- [ ] Confirm where the data may legally be stored, and keep it off any public host
- [ ] Decide whether behaviour/ergonomics will be collected at all — if the hospital does
      not record them, do **not** invent them. The system is built to run on clinical
      fields alone.

**Then the technical part is one CSV and one command.** The required column contract is
identical to the synthetic file, so nothing else changes:

```csv
patient_key,visit_date,age,sex,parental_myopia,spherical_equivalent,axial_length,...
```

Required: `patient_key`, `visit_date`, `spherical_equivalent`, `axial_length`.
Everything else optional — missing stays missing.

```bash
cd backend
.venv/bin/python -m app.ml.train --data data/hospital_cohort.csv     # retrain
.venv/bin/python scripts/seed_demo.py --data data/hospital_cohort.csv \
    --patients 0 --reset --consent-status approved --data-source hospital
```

Or push it through the API with `POST /api/v1/patients/bulk-import`.

`data_is_synthetic` flips to `false` automatically, the UI's amber banner disappears, and
the model card stops disclaiming the metrics.

👉 **Full column dictionary, unit conventions, validation rules and a QA checklist:
[`docs/DATA_ONBOARDING.md`](docs/DATA_ONBOARDING.md).**

**Expect the metrics to get worse, and say so.** The synthetic cohort is generated by a
deterministic equation, so the model can nearly invert it (R² ≈ 0.99). Real progression data
is noisier and partly unpredictable. A real 12-month SE MAE in the 0.25–0.50 D range that
beats the carry-forward baseline would be a genuinely good result. Report the honest number.

**Public datasets to start with, if hospital data is delayed** (all longitudinal, all
require checking the licence before use):

| Dataset | Contents | DOI |
|---|---|---|
| Dryad 3-year cohort | 452 children, repeated AL + SE | `10.5061/dryad.d4mb3pn` |
| Dryad Shanghai | AL, SE, myopia prevalence, 2014–2018 | `10.5061/dryad.c2fqz615c` |
| Zenodo DIMS raw data | Repeated SE, peripheral refraction, AL over 36 months | `10.5281/zenodo.18166476` |

### 2. PostgreSQL instead of SQLite

SQLite is the zero-setup default and is fine through development. Switch when you have
concurrent users or real data.

```bash
pip install "psycopg[binary]"
export DATABASE_URL="postgresql+psycopg://myopia:myopia@localhost:5432/myopia_twin"
```

Tables are created automatically on startup. `docker compose up` brings up Postgres wired
in already. Nothing in the application code changes — SQLAlchemy handles it.

> For a real deployment, add **Alembic** migrations rather than relying on
> `create_all()`, so schema changes do not require dropping tables.

### 3. A local LLM for the agent (optional)

**The agent is fully functional with no LLM.** Attaching one only makes the prose nicer.

```bash
# install from https://ollama.com
ollama pull llama3.2:3b
ollama serve

# backend/.env
LLM_PROVIDER=ollama
LLM_BASE_URL=http://localhost:11434
LLM_MODEL=llama3.2:3b
```

Local keeps prompts and patient context on your machine and costs nothing. The numeric
guardrail runs on every generated answer regardless of provider.

> Never send real patient data to a hosted LLM unless your institution has approved that
> specific vendor and its data-processing terms.

### 4. Exact SHAP values

The explainer already works — it falls back to marginal-ablation attribution and says so in
the response. For exact Shapley values:

```bash
pip install shap
```

No code change. `explanation.method` switches from `marginal_ablation` to
`shap.TreeExplainer` (or `shap.Permutation`), and the UI reflects it.

### 5. XGBoost / LightGBM comparison

The training script already benchmarks Ridge, Random Forest and carry-forward against the
gradient-boosting model. To add XGBoost and LightGBM to the comparison table:

```bash
pip install xgboost lightgbm
```

then add them to the `baselines` block in
[`app/ml/train.py`](backend/app/ml/train.py) (`train_regressors`), following the existing
Ridge/RF pattern. Keep the same `_xy()` split so the comparison stays fair.

### 6. LangGraph runtime

The agent is written as an explicit node/edge graph (`NODES`, `EDGES`, `AgentState` in
[`app/agents/graph.py`](backend/app/agents/graph.py)) precisely so it maps 1:1 onto
LangGraph. `GET /api/v1/agent/graph` reports `runtime: "builtin"` today.

```bash
pip install langgraph langchain-core
```

then build a `StateGraph` over the same node functions — they are the single source of
truth, so behaviour does not change and the tests still apply.

### 7. Semantic RAG instead of keyword retrieval

Live retrieval from Europe PMC already works. The **offline corpus** currently uses keyword
scoring. To make it semantic:

```bash
pip install faiss-cpu sentence-transformers
```

Replace `search()` in [`app/evidence/corpus.py`](backend/app/evidence/corpus.py) — keep the
return shape and nothing else needs touching. Drop additional open-access papers into
`backend/data/corpus/*.json` using the same fields.

> Do not build a huge knowledge base before the twin itself works. A curated folder of
> open-access papers plus live Europe PMC is enough for a strong demo.

### 8. PubMed API key

Optional. Raises the NCBI rate limit from 3 to 10 requests/second.

```bash
# backend/.env
NCBI_API_KEY=your_key
EVIDENCE_CONTACT_EMAIL=you@university.edu
```

Get one free at <https://www.ncbi.nlm.nih.gov/account/>.

### 9. Verify the FHIR codes ⚠️

The FHIR layer deliberately uses a **project-local CodeSystem** for ocular measures rather
than guessed LOINC codes, because a plausible-but-wrong LOINC code would cause a receiving
system to silently mis-file a value.

Before exchanging with any real EHR:

- [ ] Look up real LOINC/SNOMED CT codes for spherical equivalent, axial length, visual
      acuity and keratometry in the official browsers
- [ ] Replace the entries in `MEASURE_MAP` in
      [`app/fhir/mapping.py`](backend/app/fhir/mapping.py)
- [ ] Record which codes you verified, and when, in `docs/DATA_ONBOARDING.md`
- [ ] Validate output against the HL7 FHIR validator

Model-derived Observations are already emitted with `status: "preliminary"`, a
`derivedFrom` provenance reference and a "MODEL ESTIMATE" note, so they can never be
mistaken for measurements. Keep that.

### 10. Authentication and access control ⚠️

There is a working API-key gate, **off by default** for local development.

```bash
# backend/.env
API_KEY=$(python3 -c "import secrets; print(secrets.token_urlsafe(32))")
# frontend/.env
VITE_API_KEY=the_same_value
```

**Before real clinical data, this is not enough.** You need at minimum:

- [ ] Per-user accounts instead of one shared key (OAuth2 / OIDC against the institution's IdP)
- [ ] Role-based access — clinician vs researcher vs administrator
- [ ] An access audit log (the `agent_runs` table is a start; extend it to all reads)
- [ ] TLS everywhere, enforced
- [ ] Encryption at rest for the database
- [ ] Rate limiting and request size limits

See [`docs/SECURITY.md`](docs/SECURITY.md).

### 11. Camera-based ergonomics (stretch)

`viewing_distance_cm` and `posture_score` are currently entered manually or imported. To
estimate them from a webcam, add a **separate** MediaPipe/OpenCV service that POSTs to
`/api/v1/patients/{id}/observations`. Deliberately kept out of the API so the clinical
service has no camera dependency.

If you build it: label it **non-medical-grade** everywhere it appears, and never let a
camera estimate overwrite a clinician-recorded measurement.

### 12. Deployment

See [Deployment](#deployment) below. Free tiers are fine for a **synthetic-data** demo and
are not suitable for real clinical data.

---

## Configuration reference

All settings are environment variables, read from `backend/.env` (copy `.env.example`).

| Variable | Default | Notes |
|---|---|---|
| `DATABASE_URL` | `sqlite:///./artifacts/myopia_twin.db` | Any SQLAlchemy URL |
| `API_KEY` | *(empty)* | Deployment-wide gate, separate from user sign-in. Empty = off. |
| `JWT_SECRET` | *(random)* | **Set this in production.** Left empty, a random key is generated at startup, so every restart signs users out. |
| `JWT_EXPIRE_MINUTES` | `20160` | Session length (14 days). |

Uploaded files are written to `backend/artifacts/uploads/<user_id>/` (git-ignored) with a
10 MB cap per file. Treat that directory as clinical data once real accounts exist.
| `CORS_ORIGINS` | `http://localhost:5173,…` | Comma-separated |
| `ENVIRONMENT` | `development` | Reported by `/health` |
| `EVIDENCE_OFFLINE` | `false` | `true` = bundled corpus only, no network |
| `NCBI_API_KEY` | *(empty)* | Raises PubMed rate limit |
| `EVIDENCE_CONTACT_EMAIL` | *(empty)* | Polite identification for NCBI |
| `LLM_PROVIDER` | `none` | `none` \| `ollama` \| `openai_compatible` |
| `LLM_BASE_URL` | `http://localhost:11434` | |
| `LLM_MODEL` | `llama3.2:3b` | |

Frontend (`frontend/.env`, baked in at build time):

| Variable | Default | Notes |
|---|---|---|
| `VITE_API_BASE_URL` | *(empty)* | Empty = same origin (dev proxy / nginx). Set to your API URL for a split deployment. |
| `VITE_API_KEY` | *(empty)* | Must match the backend's `API_KEY` if set |

---

## Project layout

```
myopia-digital-twin/
├── backend/
│   ├── app/
│   │   ├── main.py              FastAPI entry point, CORS, router wiring
│   │   ├── core/                config, API-key gate, password hashing + JWT,
│   │   │                        upload storage with magic-byte type detection
│   │   ├── db/                  SQLAlchemy models: the twin's data model
│   │   ├── schemas/             pydantic request/response models -> OpenAPI
│   │   ├── ml/
│   │   │   ├── features.py      ⭐ ONE feature builder, shared by train/predict/simulate
│   │   │   ├── dataset.py       long visit table -> supervised rows, no future leakage
│   │   │   ├── train.py         training, conformal calibration, ablation, metrics
│   │   │   └── registry.py      model loading + prediction
│   │   ├── twin/service.py      ⭐ state, versioning, diffing, material-change flags
│   │   ├── simulator/           counterfactual engine, plausibility constraints,
│   │   │                        multi-year autoregressive projection
│   │   ├── explain/             SHAP with an always-available fallback
│   │   ├── evidence/            Europe PMC / PubMed / bundled corpus
│   │   ├── agents/              tools · graph · optional LLM with numeric guardrail
│   │   ├── fhir/mapping.py      FHIR R4 Patient + Observation + flagged predictions
│   │   └── routers/             the HTTP surface
│   ├── scripts/
│   │   ├── generate_synthetic.py  the synthetic cohort generator
│   │   ├── seed_demo.py           load a cohort + build twin version histories
│   │   └── seed_users.py          demo accounts with real history
│   ├── tests/                   58 tests covering the whole loop
│   ├── data/                    cohort CSVs + offline evidence corpus
│   └── artifacts/               trained bundle, metrics JSON, SQLite db
├── frontend/
│   └── src/
│       ├── lib/api.js           client, token handling, formatters
│       ├── context/AuthContext  session restore, sign-in/out, 401 handling
│       ├── lib/validate.js      field rules mirrored from the API's bounds
│       ├── components/          AppLayout · Logo (blinks/winks) · Attachments ·
│       │                        TrajectoryChart · ProjectionChart · ui
│       ├── pages/               Landing · Auth · Dashboard · Records ·
│       │                        Appointments · Simulator · Insights · Profile
│       └── App.jsx              routing and route guards
├── docs/                        onboarding · architecture · security · demo script
├── docker-compose.yml           Postgres + API + nginx-served UI
└── Makefile
```

---

## Testing

```bash
make test        # or: cd backend && .venv/bin/python -m pytest tests -q
```

58 tests, no network required (`EVIDENCE_OFFLINE=true`, `LLM_PROVIDER=none` are forced in
`conftest.py`). They cover:

- the full loop: create patient → add visits → twin versions → prediction → simulation
- prediction intervals are ordered and non-degenerate
- a new observation creates a new version and the **old version is not mutated**
- impossible measurements (`axial_length: 99`) are rejected with `422`
- duplicate visit dates are rejected with `409`
- implausible scenarios are **rejected, not answered**
- simulation is deterministic
- overrides affect only the current visit; history is preserved
- missing values stay `NaN` and are never invented
- the agent routes correctly, calls real tools, and produces an auditable trace
- the agent reports failure instead of answering when a patient does not exist
- the LLM numeric guardrail accepts traceable numbers and rejects invented ones
- FHIR patients carry no identity fields; model outputs are flagged as estimates
- signup, sign-in, weak-password rejection, and identical errors for wrong password vs
  unknown email (so the API never reveals which emails are registered)
- **one user cannot read or delete another user's records or appointments**
- personal records never appear in the generic `/patients` listing
- projection intervals widen monotonically and confidence is downgraded year by year
- a healthier-habits scenario never projects a worse outcome than the baseline
- the risk/interval consistency flag is always reported
- uploads: HTML disguised as an image is refused, oversized files are refused, PDFs are
  accepted, download headers are hardened, and **one user cannot read, attach to, or
  delete another user's files**
- every range published by `/simulator/inputs` is accepted by `/simulator/project`, and
  values outside it are refused — so the form can never offer something the API rejects

---

## Deployment

### Docker Compose (recommended for a self-hosted demo)

```bash
cd backend && .venv/bin/python scripts/generate_synthetic.py && .venv/bin/python -m app.ml.train
cd .. && docker compose up --build
# UI  http://localhost:8080
# API http://localhost:8000/docs
```

nginx serves the built UI and proxies `/api` to the API container, so the browser sees one
origin and CORS never applies.

### Render / Railway / Fly free tier

**Backend** — a web service from `backend/`:

- Build: `pip install -r requirements.txt`
- Start: `uvicorn app.main:app --host 0.0.0.0 --port $PORT`
- Commit a trained `artifacts/progression_model.joblib`, or add a build step that runs
  `python scripts/generate_synthetic.py && python -m app.ml.train`
- Set `API_KEY`, `DATABASE_URL`, and `CORS_ORIGINS` to your UI's origin

**Frontend** — a static site from `frontend/`:

- Build: `npm ci && npm run build` · Publish directory: `dist`
- Set `VITE_API_BASE_URL` to the deployed API URL (and `VITE_API_KEY` if you set one)

> **Synthetic data only on any public host.** Free tiers sleep, have no BAA/DPA, and are not
> appropriate for clinical data under any circumstances.

---

## The demo script

A 5–7 minute walkthrough that lands the point. Full version with talking points:
[`docs/DEMO_SCRIPT.md`](docs/DEMO_SCRIPT.md).

1. **Open a patient** — twin state, latest SE/AL, data completeness, twin version, model version
2. **Show the trajectory** — observed history plus the forecast *with its uncertainty band*
3. **Explain the prediction** — top contributing factors in plain language
4. **Run a what-if** — "More outdoor time" → baseline vs counterfactual on both measures
5. **Show the plausibility gate** — try an absurd value; it is *rejected*, not answered
6. **Ask the agent** — a natural-language question; then open the tool trace to show it
   called `get_twin`, `predict`, `simulate`, `retrieve_evidence` rather than guessing
7. **Show evidence** — retrieved citations with identifiers
8. **Add a new visit** — POST to your own API; **the twin version increments and the
   predictions recompute in front of them**
9. **Open Version history** — replay exactly what the system knew before that visit
10. **End on limitations** — model estimates, not diagnosis; synthetic data today

Step 8 is the moment that separates a Digital Twin from a prediction dashboard. Do not skip it.

---

## Limitations

State these plainly rather than being asked about them.

- **The current data is synthetic.** All metrics describe a generated cohort.
- **Observational data supports association, not causation.** A counterfactual here shows
  how the *model's expectation* changes when inputs change. It is not evidence that
  changing the behaviour would change the eye.
- **Attribution explains the model, not the disease.** SHAP values describe which inputs
  moved a prediction.
- **Behaviour and ergonomics are self-reported or app-derived**, and are non-medical-grade.
- **Prediction intervals assume the future resembles the training distribution.** A patient
  unlike the training cohort will get an over-confident interval, which is why the
  simulator warns when a scenario extrapolates.
- **The system is not a medical device** and has not been clinically validated.
- **Related work exists.** A January 2026 *npj Digital Medicine* paper reports a large
  Transformer for personalized myopia progression and intervention prediction. Do not claim
  to be "the first AI myopia predictor." The contribution here is the *integration*: an
  evolving versioned twin, calibrated uncertainty, ergonomic exposure modelling, a
  constrained counterfactual engine, an auditable tool-using agent and a reusable twin API.
  Re-run the novelty search before final submission.

---

## Further docs

| Document | Contents |
|---|---|
| [`docs/DATA_ONBOARDING.md`](docs/DATA_ONBOARDING.md) | Column contract, units, validation rules, de-identification and QA checklist for real data |
| [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) | How the twin, simulator and agent fit together; extension points |
| [`docs/SECURITY.md`](docs/SECURITY.md) | What must be true before real clinical data is connected |
| [`docs/DEMO_SCRIPT.md`](docs/DEMO_SCRIPT.md) | The demo, with talking points and likely questions |

---

## Licence

MIT for the code. The synthetic data is generated and carries no restrictions. Any real
clinical data you connect is governed by your institution's agreements, not by this licence.
