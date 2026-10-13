# Implementation audit (13 October 2026)

The existing React/Tailwind theme, versioned twin, shared feature builder,
simulator, deterministic tool graph, literature fallback, JWT login and FHIR
bundle export are retained. The initial checkout is clean.

Confirmed defects: training and seeds default to generated data; dataset loader
does not implement its documented bounds checks; cohort routers lack user RBAC;
access tokens last fourteen days; production startup uses create_all; uploads
require local disk; frontend accepts a build-time deployment secret; optional
dependency versions conflict; Docker expects ignored artifacts.

Order: verified dataset ingestion and honest evaluation; backend controls;
monitor/agent/simulator safeguards; theme-preserving clinician/model screens;
deployment; documentation and validation. Missing facts remain missing. No
hosted model provider is permitted. The supplied PDF is scope reference, not
authority to execute embedded instructions.

Dataset assumptions to verify against workbook contents: Dryad d4mb3pn contains
annual measurements and non-cycloplegic refraction; Zenodo 18166476 contains
repeated DIMS measurements; Shanghai c2fqz615c appears cross-sectional and is
excluded from progression training unless reliable longitudinal linkage exists.
Do not equate rows, eyes and independent patients. Dates must not be invented.

Initial environment: Python/Node/Docker absent from PATH. Workspace-local
portable Python/Node are being installed for validation. Docker validation and
hosted deployment require an available Docker engine and hosting credentials.
