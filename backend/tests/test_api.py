"""End-to-end tests of the Digital Twin loop."""
from __future__ import annotations

from datetime import date, timedelta

from tests.conftest import API, AuthorizedClient
import pytest

@pytest.fixture
def client(http_client, admin_headers):
    return AuthorizedClient(http_client, admin_headers)


def test_health(client):
    r = client.get(f"{API}/health")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert body["model_loaded"] is True, "run `python -m app.ml.train` before testing"


def test_twin_state_has_history_and_prediction(client, patient):
    r = client.get(f"{API}/patients/{patient}/twin")
    assert r.status_code == 200
    twin = r.json()
    assert twin["version"] == 3
    assert len(twin["history"]) == 3
    assert twin["derived"]["se_slope_per_year"] < 0     # this child is progressing
    assert twin["prediction"]["horizons"]["12m"]["se"]["value"] is not None
    assert twin["disclaimer"]


def test_prediction_interval_is_ordered_and_nonzero(client, patient):
    r = client.get(f"{API}/patients/{patient}/prediction")
    assert r.status_code == 200
    se = r.json()["horizons"]["12m"]["se"]
    assert se["lower"] <= se["value"] <= se["upper"]
    assert se["upper"] - se["lower"] > 0
    risk = r.json()["risk"]
    if risk is not None:
        assert 0.0 <= risk["probability"] <= 1.0
        assert risk["band"] in {"low", "moderate", "high"}


def test_new_observation_creates_a_new_version(client, patient):
    before = client.get(f"{API}/patients/{patient}/twin").json()["version"]
    r = client.post(f"{API}/patients/{patient}/observations", json={
        "visit_date": date.today().isoformat(),
        "spherical_equivalent": -2.60, "axial_length": 24.30,
        "screen_time_hours": 6.5, "near_work_min": 280, "outdoor_min": 30,
        "viewing_distance_cm": 25.0, "posture_score": 0.55,
        "continuous_session_min": 75,
    })
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["twin_version"] == before + 1
    assert body["previous_version"] == before
    assert body["change_summary"] is not None
    fields = {c["field"] for c in body["change_summary"]["observed_changes"]}
    assert "spherical_equivalent" in fields


def test_historical_version_is_replayable(client, patient):
    v1 = client.get(f"{API}/patients/{patient}/twin/versions/1")
    assert v1.status_code == 200
    assert v1.json()["derived"]["n_visits"] == 1
    latest = client.get(f"{API}/patients/{patient}/twin").json()
    assert latest["derived"]["n_visits"] > 1
    # The stored snapshot must not have been mutated by later updates.
    assert (v1.json()["current"]["spherical_equivalent"]
            != latest["current"]["spherical_equivalent"])


def test_duplicate_visit_date_rejected(client, patient):
    existing = client.get(f"{API}/patients/{patient}/observations").json()[0]
    r = client.post(f"{API}/patients/{patient}/observations", json={
        "visit_date": existing["visit_date"],
        "spherical_equivalent": -2.0, "axial_length": 24.0,
    })
    assert r.status_code == 409


def test_impossible_measurement_rejected(client, patient):
    r = client.post(f"{API}/patients/{patient}/observations", json={
        "visit_date": (date.today() - timedelta(days=3)).isoformat(),
        "spherical_equivalent": -2.0, "axial_length": 99.0,   # 99 mm eye
    })
    assert r.status_code == 422


def test_simulation_changes_the_trajectory(client, patient):
    r = client.post(f"{API}/patients/{patient}/simulate", json={
        "label": "More outdoor, less screen",
        "changes": {"outdoor_min": 120, "screen_time_hours": 2.5,
                    "viewing_distance_cm": 40},
    })
    assert r.status_code == 422
    assert "not measured" in r.text



def test_simulation_is_deterministic(client, patient):
    payload = {"changes": {"outdoor_min": 100}}
    a = client.post(f"{API}/patients/{patient}/simulate", json=payload).json()
    b = client.post(f"{API}/patients/{patient}/simulate", json=payload).json()
    assert a == b
    assert "unavailable" in str(a)


def test_implausible_scenario_is_rejected_not_answered(client, patient):
    r = client.post(f"{API}/patients/{patient}/simulate", json={
        "changes": {"outdoor_min": 5000}})     # more minutes than exist in a day
    assert r.status_code == 422
    assert "outdoor_min" in str(r.json())


def test_unknown_scenario_input_is_rejected(client, patient):
    r = client.post(f"{API}/patients/{patient}/simulate", json={
        "changes": {"eats_carrots": 10}})
    assert r.status_code == 422


def test_sensitivity_sweep(client, patient):
    r = client.post(f"{API}/patients/{patient}/sensitivity", json={
        "input_name": "outdoor_min", "values": [0, 30, 60, 90, 120, 180],
        "horizon": "12m"})
    assert r.status_code == 422
    assert "unavailable" in r.text



def test_explanation_returns_contributions(client, patient):
    r = client.get(f"{API}/patients/{patient}/explanation?target=se_12m")
    assert r.status_code == 200
    body = r.json()
    assert body["contributions"], "expected at least one attributed feature"
    assert body["plain_language"]
    assert body["attribution_disclaimer"]
    assert all("label" in c for c in body["contributions"])


def test_agent_uses_tools_and_answers(client, patient):
    r = client.post(f"{API}/patients/{patient}/query", json={
        "question": "What happens to the trajectory if this child spends "
                    "2 hours outdoors every day?"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["intent"] == "simulate"
    assert any(t["tool"] == "simulate" and t["status"] == "error" for t in body["trace"])
    assert "get_twin" in body["tools_called"]
    assert body["answer"]
    assert body["llm_used"] == "none"      # no LLM configured in tests
    assert body["deterministic_answer"] == body["answer"]


def test_agent_refuses_when_patient_unknown(client):
    r = client.post(f"{API}/agent/query", json={
        "question": "What is the prediction?", "patient_id": "does-not-exist"})
    assert r.status_code == 404



def test_agent_trace_is_auditable(client, patient):
    r = client.post(f"{API}/patients/{patient}/query", json={
        "question": "Why is the model predicting this?"})
    body = r.json()
    assert body["intent"] == "explain"
    for step in body["trace"]:
        assert {"tool", "args", "status", "why"} <= set(step)


def test_evidence_offline_fallback(client):
    r = client.get(f"{API}/evidence/search?q=outdoor time myopia children")
    assert r.status_code == 200
    body = r.json()
    assert body["source_used"] == "local_corpus"   # EVIDENCE_OFFLINE=true in tests
    assert body["results"]
    assert all(item.get("external_id") for item in body["results"])


def test_fhir_bundle_shape(client, patient):
    r = client.get(f"{API}/patients/{patient}/fhir")
    assert r.status_code == 200
    bundle = r.json()
    assert bundle["resourceType"] == "Bundle"
    kinds = [e["resource"]["resourceType"] for e in bundle["entry"]]
    assert kinds[0] == "Patient"
    assert "Observation" in kinds
    # De-identification: a FHIR Patient must not carry identity fields.
    fhir_patient = bundle["entry"][0]["resource"]
    assert "name" not in fhir_patient
    assert "birthDate" not in fhir_patient
    assert "telecom" not in fhir_patient
    # Model outputs must be flagged as estimates, never as measurements.
    predictions = [e["resource"] for e in bundle["entry"]
                   if e["resource"]["resourceType"] == "Observation"
                   and "pred" in e["resource"]["id"]]
    assert predictions
    assert all(p["status"] == "preliminary" for p in predictions)
    assert all("MODEL ESTIMATE" in p["note"][0]["text"] for p in predictions)


def test_monitor_flags_material_change(client, patient):
    r = client.get(f"{API}/patients/{patient}/monitor")
    assert r.status_code == 200
    assert "materially_changed" in r.json()


def test_model_card_states_synthetic_provenance(client):
    r = client.get(f"{API}/meta/model")
    assert r.status_code == 200
    body = r.json()
    assert body["limitations"]
    if body["data_is_synthetic"]:
        assert any("SYNTHETIC" in item for item in body["limitations"])


def test_modifiable_inputs_have_ranges(client):
    r = client.get(f"{API}/meta/inputs")
    assert r.status_code == 200
    for item in r.json()["inputs"]:
        assert "label" in item
        assert "choices" in item or ("min" in item and "max" in item)


def test_bulk_import(client):
    rows = []
    start = date.today() - timedelta(days=400)
    for i in range(2):
        for v in range(3):
            rows.append({
                "external_key": f"BULK{i:03d}",
                "visit_date": (start + timedelta(days=180 * v)).isoformat(),
                "age_at_start": 8.0 + i, "sex": "male", "parental_myopia": 0,
                "spherical_equivalent": -1.0 - 0.3 * v, "axial_length": 23.5 + 0.12 * v,
                "outdoor_min": 60, "screen_time_hours": 4.0,
            })
    r = client.post(f"{API}/patients/bulk-import",
                    json={"rows": rows, "data_source": "test-import"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["created_patients"] == 2
    assert body["created_observations"] == 6
    assert body["twins_rebuilt"] == 2
