import pytest
from pydantic import ValidationError
from app.core.config import Settings, settings
from app.core.auth import create_access_token, hash_password
from app.db.database import SessionLocal
from app.db.models import User


def account(role):
    import uuid
    with SessionLocal() as db:
        user = User(email=f"{uuid.uuid4().hex}@example.org", full_name="Test", role=role,
                    password_hash=hash_password("test-password-2026"))
        db.add(user)
        db.commit()
        return user.user_id, {"Authorization": "Bearer " + create_access_token(user.user_id, user.email)[0]}


def test_production_refuses_unsafe_defaults():
    with pytest.raises(ValidationError, match="JWT_SECRET"):
        Settings(_env_file=None, environment="production")


def test_production_accepts_explicit_jwt_gate_and_persistent_storage():
    value = Settings(_env_file=None, environment="production", jwt_secret="x" * 40,
                     auth_gate="jwt", database_url="postgresql+psycopg://u:p@localhost/d",
                     cors_origins="https://example.org", storage_backend="s3",
                     s3_endpoint_url="https://s3.example.org", s3_bucket="test",
                     s3_access_key_id="test", s3_secret_access_key="test")
    assert value.jwt_expire_minutes == 30


@pytest.mark.parametrize("kwargs", [{"llm_provider": "openai_compatible"},
                                    {"llm_provider": "ollama", "llm_base_url": "https://example.org"}])
def test_hosted_ai_configuration_rejected(kwargs):
    with pytest.raises(ValidationError):
        Settings(_env_file=None, **kwargs)


def test_every_patient_path_requires_authenticated_assigned_staff(client, patient, admin_headers):
    _, ph = account("patient")
    clinician_id, ch = account("clinician")
    paths = [f"/patients/{patient}", f"/patients/{patient}/twin",
             f"/patients/{patient}/observations", f"/patients/{patient}/prediction",
             f"/patients/{patient}/explanation", f"/patients/{patient}/monitor",
             f"/patients/{patient}/fhir", f"/patients/{patient}/simulations"]
    for path in paths:
        assert client.get("/api/v1" + path).status_code == 401
        assert client.get("/api/v1" + path, headers=ph).status_code == 403
        assert client.get("/api/v1" + path, headers=ch).status_code == 403
    for suffix, body in [("simulate", {"changes": {}}), ("query", {"question": "Show current twin"}),
                          ("observations", {"visit_date": "2020-01-01", "spherical_equivalent": -1, "axial_length": 24})]:
        assert client.post(f"/api/v1/patients/{patient}/{suffix}", headers=ch, json=body).status_code == 403
    assert client.get("/api/v1/patients", headers=ch).json() == []
    assert client.post("/api/v1/admin/assignments", headers=admin_headers,
                       json={"clinician_id": clinician_id, "patient_id": patient}).status_code == 201
    assert client.get(f"/api/v1/patients/{patient}/twin", headers=ch).status_code == 200
    assert len(client.get("/api/v1/patients", headers=ch).json()) == 1
    assert client.delete(f"/api/v1/patients/{patient}", headers=ch).status_code == 403
    assert client.post("/api/v1/patients/bulk-import", headers=ch, json={"rows": []}).status_code == 403
    assert client.post("/api/v1/agent/query", headers=ch,
                       json={"question": "Show current twin", "patient_id": "unassigned"}).status_code == 404
    assert client.get("/api/v1/agent/runs", headers=ch).status_code == 403
    assert client.get("/api/v1/admin/audit", headers=ph).status_code == 403
    events = client.get("/api/v1/admin/audit", headers=admin_headers).json()["events"]
    assert any(e["actor_id"] == clinician_id and e["action"] == "GET" for e in events)
    assert all(len(e["ip_hash"]) == 64 for e in events)


def test_rate_limit_and_security_headers(client, monkeypatch):
    from app.core.middleware import ControlsMiddleware
    ControlsMiddleware.buckets.clear()
    monkeypatch.setattr(settings, "rate_limit_enabled", True)
    for _ in range(21):
        response = client.post("/api/v1/auth/login", json={"email": "unknown@example.org", "password": "incorrect"})
    assert response.status_code == 429
    assert int(response.headers["Retry-After"]) > 0
    assert response.headers["X-Content-Type-Options"] == "nosniff"
    assert response.headers["X-Request-ID"]
    ControlsMiddleware.buckets.clear()


def test_chunked_request_size_is_bounded(client, monkeypatch):
    monkeypatch.setattr(settings, "max_request_bytes", 5)
    r = client.post("/api/v1/auth/login", content=iter([b"123", b"456"]))
    assert r.status_code == 413


def test_lockout_is_persistent(client):
    uid, _ = account("patient")
    with SessionLocal() as db:
        email = db.get(User, uid).email
    for _ in range(5):
        assert client.post("/api/v1/auth/login", json={"email": email, "password": "wrong"}).status_code == 401
    r = client.post("/api/v1/auth/login", json={"email": email, "password": "test-password-2026"})
    assert r.status_code == 429


def test_local_storage_rejects_path_escape():
    from app.core.storage import local_path
    with pytest.raises(ValueError, match="outside"):
        local_path("../outside.pdf")


def test_s3_storage_roundtrip_without_network(monkeypatch):
    from app.core import storage
    import io
    objects = {}
    class FakeS3:
        def put_object(self, **kw): objects[kw["Key"]] = kw["Body"]
        def get_object(self, **kw): return {"Body": io.BytesIO(objects[kw["Key"]])}
        def delete_object(self, **kw): objects.pop(kw["Key"], None)
    monkeypatch.setattr(settings, "storage_backend", "s3")
    monkeypatch.setattr(storage, "s3_client", lambda: FakeS3())
    key = storage.put("test/file.pdf", b"%PDF-test")
    assert storage.read(key).read() == b"%PDF-test"
    storage.remove(key)
    assert not objects
