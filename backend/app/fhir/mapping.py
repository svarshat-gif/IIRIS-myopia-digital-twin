"""HL7 FHIR R4 mapping layer (Patient + Observation).

Scope: this demonstrates that the twin's internal canonical format can be
projected onto standard FHIR resources for exchange. It is a mapping layer, not a
conformant FHIR server -- there is no search, no capability statement and no
terminology validation.

CODES -- READ BEFORE USING THIS WITH A REAL SYSTEM
--------------------------------------------------
Ocular biometry codes are NOT hard-coded to guessed LOINC identifiers here.
Inventing a plausible-looking LOINC code is worse than having none, because a
receiving system would silently mis-file the value. Instead:

  * Codes we are confident about (body height/weight style vitals) are omitted --
    we do not send them.
  * Every ocular measure uses a PROJECT-LOCAL CodeSystem URI. That is legal FHIR
    and it is unambiguous: a receiver can see it is a local code and ask for a
    mapping instead of guessing.
  * Before exchanging with a real EHR, replace `LOCAL_CODE_SYSTEM` entries with
    verified LOINC/SNOMED CT codes from the official browsers and record the
    verification in docs/DATA_ONBOARDING.md.

Behaviour and ergonomics are mapped as Observations with a `survey` category,
since they are self-reported/app-derived exposures rather than clinical
measurements.
"""
from __future__ import annotations

from typing import Any

from app.db.models import Observation, Patient

LOCAL_CODE_SYSTEM = "http://myopia-twin.local/CodeSystem/ocular-measure"
UCUM = "http://unitsofmeasure.org"

# field -> (local code, display, UCUM unit, unit display, category)
MEASURE_MAP: dict[str, tuple[str, str, str, str, str]] = {
    "spherical_equivalent": ("se", "Spherical equivalent refraction", "[diop]", "D", "exam"),
    "axial_length": ("al", "Axial length", "mm", "mm", "exam"),
    "visual_acuity": ("va-logmar", "Visual acuity (logMAR)", "1", "logMAR", "exam"),
    "corneal_curvature": ("k-mean", "Mean corneal curvature radius", "mm", "mm", "exam"),
    "screen_time_hours": ("screen-time", "Daily screen time", "h", "h/day", "survey"),
    "near_work_min": ("near-work", "Daily near-work duration", "min", "min/day", "survey"),
    "outdoor_min": ("outdoor-time", "Daily outdoor time", "min", "min/day", "survey"),
    "sleep_hours": ("sleep", "Nightly sleep duration", "h", "h/night", "survey"),
    "viewing_distance_cm": ("viewing-distance", "Habitual viewing distance", "cm", "cm",
                            "survey"),
    "posture_score": ("posture-score", "Posture score (0-1, non-medical-grade)", "1",
                      "score", "survey"),
    "continuous_session_min": ("session-length", "Continuous near-work session length",
                               "min", "min", "survey"),
}

CATEGORY_DISPLAY = {"exam": "Exam", "survey": "Survey"}


def patient_to_fhir(patient: Patient) -> dict[str, Any]:
    """De-identified FHIR Patient. No name, no telecom, no address, no birthDate.

    Age is carried as an extension rather than a birth date so the resource stays
    de-identified.
    """
    resource: dict[str, Any] = {
        "resourceType": "Patient",
        "id": patient.patient_id,
        "meta": {
            "profile": ["http://hl7.org/fhir/StructureDefinition/Patient"],
            "security": [{
                "system": "http://terminology.hl7.org/CodeSystem/v3-Confidentiality",
                "code": "R", "display": "Restricted",
            }],
            "tag": [{
                "system": "http://terminology.hl7.org/CodeSystem/v3-ObservationValue",
                "code": "ANONYED", "display": "anonymized",
            }],
        },
        "identifier": [{
            "system": "http://myopia-twin.local/patient-id",
            "value": patient.patient_id,
        }],
        "active": True,
        "extension": [{
            "url": "http://myopia-twin.local/StructureDefinition/age-at-first-visit",
            "valueDecimal": patient.age_at_start,
        }],
    }
    if patient.sex:
        mapped = {"male": "male", "female": "female", "m": "male", "f": "female"}
        resource["gender"] = mapped.get(patient.sex.lower(), "unknown")
    if patient.parental_myopia is not None:
        resource["extension"].append({
            "url": "http://myopia-twin.local/StructureDefinition/parental-myopia-count",
            "valueInteger": patient.parental_myopia,
        })
    return resource


def _observation_resource(obs: Observation, field: str, value: float) -> dict[str, Any]:
    code, display, ucum, unit_display, category = MEASURE_MAP[field]
    return {
        "resourceType": "Observation",
        "id": f"{obs.observation_id}-{code}",
        "status": "final",
        "category": [{
            "coding": [{
                "system": "http://terminology.hl7.org/CodeSystem/observation-category",
                "code": category,
                "display": CATEGORY_DISPLAY[category],
            }]
        }],
        "code": {
            "coding": [{
                "system": LOCAL_CODE_SYSTEM,
                "code": code,
                "display": display,
            }],
            "text": display,
        },
        "subject": {"reference": f"Patient/{obs.patient_id}"},
        "effectiveDateTime": obs.visit_date.isoformat(),
        "valueQuantity": {
            "value": round(float(value), 4),
            "unit": unit_display,
            "system": UCUM,
            "code": ucum,
        },
        **({"note": [{"text": "Self-reported or app-derived exposure, "
                              "non-medical-grade."}]} if category == "survey" else {}),
    }


def observation_to_fhir(obs: Observation) -> list[dict[str, Any]]:
    """One visit becomes several FHIR Observations (one per measured value)."""
    resources = []
    for field in MEASURE_MAP:
        value = getattr(obs, field, None)
        if value is None:
            continue  # never emit a resource for a value we do not have
        resources.append(_observation_resource(obs, field, value))

    if obs.treatment and obs.treatment != "none":
        resources.append({
            "resourceType": "Observation",
            "id": f"{obs.observation_id}-treatment",
            "status": "final",
            "category": [{
                "coding": [{
                    "system": "http://terminology.hl7.org/CodeSystem/observation-category",
                    "code": "therapy", "display": "Therapy",
                }]
            }],
            "code": {
                "coding": [{"system": LOCAL_CODE_SYSTEM, "code": "myopia-control",
                            "display": "Myopia control intervention in use"}],
                "text": "Myopia control intervention in use",
            },
            "subject": {"reference": f"Patient/{obs.patient_id}"},
            "effectiveDateTime": obs.visit_date.isoformat(),
            "valueCodeableConcept": {
                "coding": [{"system": f"{LOCAL_CODE_SYSTEM}/treatment",
                            "code": obs.treatment, "display": obs.treatment}],
                "text": obs.treatment,
            },
        })
    return resources


def prediction_to_fhir(patient_id: str, twin_version: int,
                       prediction: dict[str, Any]) -> list[dict[str, Any]]:
    """Model outputs as Observations, explicitly derived and clearly labelled.

    They carry `derived-from` provenance and a note stating they are model
    estimates, so a downstream system can never confuse them with measurements.
    """
    resources: list[dict[str, Any]] = []
    for key, entry in prediction.get("horizons", {}).items():
        for measure, unit, ucum in (("se", "D", "[diop]"), ("al", "mm", "mm")):
            item = entry.get(measure)
            if not item:
                continue
            resources.append({
                "resourceType": "Observation",
                "id": f"{patient_id}-v{twin_version}-pred-{measure}-{key}",
                "status": "preliminary",
                "category": [{
                    "coding": [{
                        "system":
                            "http://terminology.hl7.org/CodeSystem/observation-category",
                        "code": "survey", "display": "Survey",
                    }]
                }],
                "code": {
                    "coding": [{
                        "system": LOCAL_CODE_SYSTEM,
                        "code": f"predicted-{measure}-{key}",
                        "display": f"Model-predicted {measure.upper()} at {key}",
                    }],
                    "text": f"Model-predicted {measure.upper()} at {key}",
                },
                "subject": {"reference": f"Patient/{patient_id}"},
                "issued": None,
                "valueQuantity": {"value": item["value"], "unit": unit,
                                  "system": UCUM, "code": ucum},
                "component": [
                    {"code": {"text": "prediction interval lower bound"},
                     "valueQuantity": {"value": item["lower"], "unit": unit}},
                    {"code": {"text": "prediction interval upper bound"},
                     "valueQuantity": {"value": item["upper"], "unit": unit}},
                ],
                "derivedFrom": [{
                    "reference": f"Patient/{patient_id}",
                    "display": f"Myopia Digital Twin v{twin_version}, model "
                               f"{prediction.get('model_version')}",
                }],
                "note": [{"text":
                          "MODEL ESTIMATE, not a measurement and not a diagnosis. "
                          f"Produced by {prediction.get('model_version')}."}],
            })
    return resources


def build_bundle(patient: Patient, observations: list[Observation],
                 prediction: dict[str, Any] | None = None,
                 twin_version: int | None = None) -> dict[str, Any]:
    """A FHIR `collection` Bundle: the Patient, every Observation, and optionally
    the current model predictions."""
    entries: list[dict[str, Any]] = [
        {"resource": patient_to_fhir(patient),
         "fullUrl": f"urn:uuid:{patient.patient_id}"}
    ]
    for obs in observations:
        for resource in observation_to_fhir(obs):
            entries.append({"resource": resource, "fullUrl": f"urn:uuid:{resource['id']}"})

    if prediction and twin_version is not None:
        for resource in prediction_to_fhir(patient.patient_id, twin_version, prediction):
            entries.append({"resource": resource, "fullUrl": f"urn:uuid:{resource['id']}"})

    return {
        "resourceType": "Bundle",
        "id": f"myopia-twin-{patient.patient_id}",
        "type": "collection",
        "meta": {"tag": [{"system": "http://myopia-twin.local/tag",
                          "code": "digital-twin-export"}]},
        "entry": entries,
        "total": len(entries),
    }
