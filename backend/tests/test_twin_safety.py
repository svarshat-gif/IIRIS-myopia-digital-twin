from app.agents import llm
from app.agents.tools import tool_schemas
from app.core.config import settings


def test_guide_tool_set_is_exact():
    assert {x["name"] for x in tool_schemas()} == {"get_twin", "predict", "simulate", "explain",
        "retrieve_evidence", "compare_scenarios", "flag_changes"}


def test_generated_small_hallucinated_number_is_rejected(monkeypatch):
    monkeypatch.setattr(settings, "llm_provider", "ollama")
    monkeypatch.setattr(llm, "_call_ollama", lambda _: "The expected change is 7 D.")
    result = llm.narrate("What is expected?", {"se": -1.5}, "Known estimate only")
    assert result["answer"] == "Known estimate only"
    assert result["guardrail"]["passed"] is False


def test_local_narration_keeps_supported_numbers(monkeypatch):
    monkeypatch.setattr(settings, "llm_provider", "ollama")
    monkeypatch.setattr(llm, "_call_ollama", lambda _: "The estimate is -1.5 D.")
    result = llm.narrate("Expected?", {"se": -1.5}, "fallback")
    assert result["guardrail"]["passed"] is True


def test_relative_research_twin_versions_monitor_and_fhir(client, admin_headers):
    h = admin_headers
    pid = client.post("/api/v1/patients", headers=h, json={"age_at_start": 9,
        "consent_status": "open_research", "data_source": "test-fixture"}).json()["patient_id"]
    for month, se, al in [(0, -1, 24), (12, -1.5, 24.3)]:
        r = client.post(f"/api/v1/patients/{pid}/observations", headers=h,
            json={"followup_month": month, "spherical_equivalent": se, "axial_length": al})
        assert r.status_code == 201, r.text
        assert "monitor" in r.json()["twin"]
    twin = client.get(f"/api/v1/patients/{pid}/twin", headers=h).json()
    assert twin["version"] == 2
    assert twin["current"]["visit_date"] is None
    replay = client.get(f"/api/v1/patients/{pid}/twin/versions/1", headers=h).json()
    assert replay["current"]["followup_month"] == 0
    assert "monitor" in replay
    facade = client.get(f"/api/v1/fhir/Observation?patient={pid}", headers=h)
    assert facade.status_code == 200, facade.text
    assert all("effectiveDateTime" not in e["resource"] for e in facade.json()["entry"])
    assert client.get(f"/fhir/Patient/{pid}", headers=h).json()["resourceType"] == "Patient"
    r = client.post(f"/api/v1/patients/{pid}/observations", headers=h,
        json={"visit_date": "2021-01-01", "spherical_equivalent": -1.75, "axial_length": 24.4})
    assert r.status_code == 400
