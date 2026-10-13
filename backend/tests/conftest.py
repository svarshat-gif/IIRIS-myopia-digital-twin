from __future__ import annotations

import os
import sys
from datetime import date, timedelta
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

# Point the app at a throwaway database BEFORE anything imports settings.
TEST_DB = ROOT / "artifacts" / "test_myopia_twin.db"
os.environ["DATABASE_URL"] = f"sqlite:///{TEST_DB}"
os.environ["EVIDENCE_OFFLINE"] = "true"   # tests must never depend on the network
os.environ["LLM_PROVIDER"] = "none"

from fastapi.testclient import TestClient  # noqa: E402

from app.db.database import Base, engine  # noqa: E402
from app.main import app  # noqa: E402

API = "/api/v1"


@pytest.fixture(scope="session", autouse=True)
def _fresh_db():
    if TEST_DB.exists():
        TEST_DB.unlink()
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)
    engine.dispose()
    if TEST_DB.exists():
        TEST_DB.unlink()


@pytest.fixture(scope="session")
def client():
    with TestClient(app) as c:
        yield c


@pytest.fixture(scope="session")
def patient(client):
    """A patient with three visits, so trends and versions exist."""
    r = client.post(f"{API}/patients", json={
        "external_key": "TEST0001", "age_at_start": 9.0, "sex": "female",
        "parental_myopia": 1, "consent_status": "test", "data_source": "test",
    })
    assert r.status_code == 201, r.text
    pid = r.json()["patient_id"]

    start = date.today() - timedelta(days=365)
    visits = [
        (start, -1.50, 23.80, 5.0, 240, 45, 28.0),
        (start + timedelta(days=182), -1.85, 23.95, 5.5, 260, 40, 27.0),
        (start + timedelta(days=364), -2.20, 24.12, 6.0, 270, 35, 26.0),
    ]
    for d, se, al, screen, near, outdoor, dist in visits:
        r = client.post(f"{API}/patients/{pid}/observations", json={
            "visit_date": d.isoformat(),
            "spherical_equivalent": se, "axial_length": al,
            "visual_acuity": 0.05, "treatment": "none",
            "screen_time_hours": screen, "near_work_min": near, "outdoor_min": outdoor,
            "sleep_hours": 8.0, "viewing_distance_cm": dist, "posture_score": 0.6,
            "continuous_session_min": 60,
        })
        assert r.status_code == 201, r.text
    return pid
