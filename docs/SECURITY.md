# Security and data protection

What must be true **before** real clinical data touches this system.

The prototype ships with development defaults chosen for zero-friction local work. Those
defaults are not appropriate for clinical data, and the application says so loudly on
startup and in `GET /api/v1/health`.

---

## Current state, honestly

| Control | Status |
|---|---|
| API-key authentication | ✅ implemented, **disabled by default** (`API_KEY` empty) |
| CORS allow-list | ✅ configurable, defaults to localhost |
| Input validation | ✅ pydantic bounds on every clinical field |
| SQL injection | ✅ SQLAlchemy parameterised queries throughout |
| De-identified-by-design schema | ✅ no name/MRN/DOB/contact columns exist |
| FHIR export omits identity fields | ✅ asserted in tests |
| Model outputs flagged as estimates | ✅ `status: preliminary` + provenance note |
| Agent audit trail | ✅ `agent_runs` records question, tools and answer |
| Per-user accounts | ❌ **not implemented** |
| Role-based access control | ❌ **not implemented** |
| Read-access audit log | ❌ only agent runs are logged |
| Encryption at rest | ❌ depends on your database deployment |
| TLS | ❌ depends on your hosting |
| Rate limiting | ❌ **not implemented** |

Rows marked ❌ must be addressed before real data. Do not skip them because the prototype
"works".

---

## Minimum before real data

### 1. Turn on the API key

```bash
python3 -c "import secrets; print(secrets.token_urlsafe(32))"
# backend/.env
API_KEY=<that value>
# frontend/.env
VITE_API_KEY=<the same value>
```

A shared key is enough for a single-user prototype on a controlled machine. It is **not**
enough for a multi-user deployment: it cannot attribute an action to a person.

### 2. Add real authentication

Use your institution's identity provider (OAuth2 / OIDC). Replace
`app/core/security.py:require_api_key` with a dependency that validates a token and returns
a user principal. Every router already declares that dependency, so the swap is one file.

### 3. Add roles

At minimum: **clinician** (full access to their patients), **researcher** (aggregate and
de-identified only), **administrator** (user management, no clinical data by default).

### 4. Log reads, not just writes

Extend the `agent_runs` pattern to a general access log: who, what patient, which endpoint,
when. Clinical data access is auditable by expectation and often by law.

### 5. Encrypt and transport safely

- TLS enforced, HTTP redirected
- Database encryption at rest
- Backups encrypted, and covered by the same retention rules as the primary data

### 6. Rate limit

Add `slowapi` or an nginx `limit_req` zone. An unauthenticated `/health` is fine; everything
else should be bounded.

---

## Data handling rules

**Never:**

- Commit real data. `backend/data/*.csv` is git-ignored — verify with `git status` anyway,
  every time.
- Deploy real data to a free-tier host. No BAA/DPA, no guarantees about storage location.
- Send real patient data to a hosted LLM. Use local Ollama, or no LLM at all.
- Store the study-key → patient mapping in this system. It stays at the hospital.
- Put identifying information in `external_key`, `notes` or any free-text field.

**Always:**

- De-identify at source, before export.
- Keep a written record of what was approved and by whom.
- Set `CORS_ORIGINS` to exactly your UI's origin. Never `*` with authentication enabled.
- Treat the `artifacts/*.db` file as clinical data once real data is loaded — it contains
  full patient histories.

---

## A note on the trained model

A model trained on real patient data is derived from that data and should be handled under
the same agreement. In particular, do not commit `artifacts/progression_model.joblib` to a
public repository once it has been trained on real records — it embeds the training
distribution, and the bundle also stores a background sample of real feature rows for the
explainer.

`.gitignore` already excludes `backend/artifacts/*.joblib` for this reason.
