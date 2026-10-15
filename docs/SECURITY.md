# Security and privacy

This is an exploratory research decision-support application, not a medical
device or an approved clinical record system. Public free hosts may contain only
licensed, de-identified open research records. Actual patient data must never be
uploaded to a free public deployment.

## Implemented and locally tested

- JWT signature/expiry checks; 30-minute access tokens; re-login on expiry.
- PBKDF2 password hashing, 12-character minimum and common/numeric rejection.
- Persistent 15-minute lockout after five failed account logins.
- Patient/clinician/admin roles and explicit clinician-patient assignments.
  Self-signup always creates a patient role; roles cannot be submitted via profile.
- Ownership on /me records, appointments and attachments; generic cohort,
  simulation, explanation, version and agent access requires assigned staff.
- Admin-only assignments and audit query; read/write/denied access events include
  actor, resource, timestamp, status, request ID and keyed IP hash. No raw IPs or
  request bodies are stored in access audit. Audit persistence failure returns 503.
- In-process per-IP and verified-user auth/compute/evidence limits; 429 includes
  Retry-After. The process is intentionally deployed with one worker. A trusted
  reverse proxy can cause clients to share an IP limit; scale-out needs shared limits.
- Streamed request-size cap, upload size/type sniffing, generated storage keys,
  sanitized filenames and ownership validation of linked observations on updates.
- Private local/S3 storage interface. Production requires S3 configuration;
  authenticated API downloads avoid public object URLs.
- Production config refuses weak/missing JWT secrets, wildcard/non-HTTPS CORS,
  SQLite, missing persistent upload config and an invalid optional API-key gate.
- Synthetic training inputs are refused; source licenses/checksums are preserved.
  Runtime images refuse missing/synthetic artifacts.
- Optional narration is loopback Ollama only. Unsupported numbers, including
  small integers, cause the deterministic answer to replace generated prose.
- Security headers and request IDs; HSTS in production. No frontend deployment
  key or default demo password. No auth cookies are used.

Evidence APIs are Europe PMC and PubMed, with a bundled offline fallback. Do not
put patient identifiers in literature queries. Cache inspection is admin-only.
AgentRun records do store question/answer/tool traces; apply private-installation
retention controls before use with actual records. Local SHAP is optional;
feature-ablation attribution is labeled accurately when it is unavailable.

## Not yet verified or implemented

- Docker/Compose runtime, live Postgres and live S3: configuration exists but this
  host has no Docker engine, WSL or cloud credentials. CI jobs are added, not run remotely.
- No clinical validation, external clinical test cohort or medical-device approval.
- No MFA, refresh-token rotation, external identity provider, immutable external
  audit sink, malware scanning, backups/restore drill or institutional retention
  workflow. Access tokens remain valid until their short expiry after a password
  change. A disabled account is rejected on each request.
- No database row-level security; API RBAC is the enforcement boundary.
- Free-host quotas/cold starts preclude clinical availability guarantees.
- Tailwind 3 retains development-only dependency advisories. The frozen theme
  prevents a blind Tailwind 4 migration. Run npm audit, use only trusted build
  inputs, and plan a separately reviewed compatible patch/migration. Production
  browser dependencies are checked separately with npm audit --omit=dev.

Alembic initial-schema migration is intended for new installs. Back up existing
prototype DBs and review an upgrade/export plan; never stamp an old schema as
migrated. Joblib artifacts execute Python on load: accept only artifacts built
from this repository's verified pipeline. Put TLS at the host/reverse proxy and
keep DB/object credentials server-side. Never commit .env files or private data.
