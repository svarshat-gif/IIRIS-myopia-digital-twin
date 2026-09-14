"""Accounts, isolation between users, appointments, and the public simulator."""
from __future__ import annotations

from datetime import date, timedelta

from tests.conftest import API

PW = "irisdemo2026"


def register(client, email, name="Test Person", **extra):
    r = client.post(f"{API}/auth/signup", json={
        "email": email, "password": PW, "full_name": name, **extra})
    assert r.status_code == 201, r.text
    return r.json()


def auth(tok):
    return {"Authorization": f"Bearer {tok}"}


def test_signup_creates_account_and_empty_record(client):
    body = register(client, "alice@example.com", "Alice A", age=10.0, sex="female",
                    parental_myopia=1)
    assert body["access_token"]
    assert body["user"]["email"] == "alice@example.com"
    assert body["user"]["patient_id"]          # a record is created immediately
    assert body["user"]["has_record"] is False  # but it holds no results yet


def test_duplicate_email_rejected(client):
    register(client, "dupe@example.com")
    r = client.post(f"{API}/auth/signup", json={
        "email": "dupe@example.com", "password": PW, "full_name": "Someone Else"})
    assert r.status_code == 409


def test_weak_password_rejected(client):
    r = client.post(f"{API}/auth/signup", json={
        "email": "weak@example.com", "password": "12345678", "full_name": "W"})
    assert r.status_code == 422


def test_login_and_wrong_password(client):
    register(client, "bob@example.com")
    ok = client.post(f"{API}/auth/login",
                     json={"email": "bob@example.com", "password": PW})
    assert ok.status_code == 200
    bad = client.post(f"{API}/auth/login",
                      json={"email": "bob@example.com", "password": "wrongwrong"})
    assert bad.status_code == 401
    # The same message either way: never reveal whether an email is registered.
    unknown = client.post(f"{API}/auth/login",
                          json={"email": "nobody@example.com", "password": PW})
    assert unknown.status_code == 401
    assert unknown.json()["detail"] == bad.json()["detail"]


def test_protected_routes_need_a_token(client):
    for path in ["/me/summary", "/me/records", "/me/twin", "/me/appointments"]:
        assert client.get(f"{API}{path}").status_code == 401


def test_garbage_token_rejected(client):
    r = client.get(f"{API}/me/summary", headers=auth("not-a-real-token"))
    assert r.status_code == 401


def test_full_record_lifecycle(client):
    tok = register(client, "carol@example.com", "Carol C", age=9.0)["access_token"]
    h = auth(tok)

    start = date.today() - timedelta(days=370)
    for i, (se, al) in enumerate([(-1.0, 23.5), (-1.4, 23.7), (-1.9, 23.95)]):
        r = client.post(f"{API}/me/records", headers=h, json={
            "visit_date": (start + timedelta(days=182 * i)).isoformat(),
            "spherical_equivalent": se, "axial_length": al,
            "outdoor_min": 60, "screen_time_hours": 4.0,
            "viewing_distance_cm": 30,
        })
        assert r.status_code == 201, r.text
        assert r.json()["twin_version"] == i + 1

    summary = client.get(f"{API}/me/summary", headers=h).json()
    assert summary["n_visits"] == 3
    assert summary["twin_version"] == 3
    assert summary["latest"]["spherical_equivalent"] == -1.9
    assert summary["change_since_previous"]["spherical_equivalent"] == -0.5
    assert "days" in summary["change_since_previous"]
    assert summary["category"]["label"] in {"Low myopia", "Moderate myopia"}
    assert summary["prediction"]["horizons"]["12m"]["se"]["value"] is not None

    records = client.get(f"{API}/me/records", headers=h).json()
    assert records["n_visits"] == 3
    assert records["records"][0]["visit_date"] > records["records"][1]["visit_date"]


def test_users_cannot_see_each_others_records(client):
    a = register(client, "dan@example.com", "Dan D")
    b = register(client, "erin@example.com", "Erin E")
    ha, hb = auth(a["access_token"]), auth(b["access_token"])

    client.post(f"{API}/me/records", headers=ha, json={
        "visit_date": date.today().isoformat(),
        "spherical_equivalent": -2.0, "axial_length": 24.0})

    assert client.get(f"{API}/me/records", headers=ha).json()["n_visits"] == 1
    assert client.get(f"{API}/me/records", headers=hb).json()["n_visits"] == 0

    # Dan's record must not be reachable through the generic patient endpoints.
    listed = client.get(f"{API}/patients").json()
    assert a["user"]["patient_id"] not in {p["patient_id"] for p in listed}

    # Nor may Erin delete one of Dan's results.
    obs = client.get(f"{API}/me/records", headers=ha).json()["records"][0]
    assert client.delete(f"{API}/me/records/{obs['observation_id']}",
                         headers=hb).status_code == 404


def test_appointments_are_per_user(client):
    a = register(client, "fay@example.com")["access_token"]
    b = register(client, "gus@example.com")["access_token"]
    ha, hb = auth(a), auth(b)

    r = client.post(f"{API}/me/appointments", headers=ha, json={
        "scheduled_for": (date.today() + timedelta(days=30)).isoformat(),
        "clinic": "City Eye Centre", "reason": "Review", "status": "scheduled"})
    assert r.status_code == 201
    appt_id = r.json()["appointment_id"]

    assert len(client.get(f"{API}/me/appointments", headers=ha).json()) == 1
    assert len(client.get(f"{API}/me/appointments", headers=hb).json()) == 0
    assert client.delete(f"{API}/me/appointments/{appt_id}",
                         headers=hb).status_code == 404
    assert client.delete(f"{API}/me/appointments/{appt_id}",
                         headers=ha).status_code == 204

    summary_appt = client.post(f"{API}/me/appointments", headers=ha, json={
        "scheduled_for": (date.today() + timedelta(days=10)).isoformat(),
        "status": "scheduled"})
    assert summary_appt.status_code == 201


def test_projection_extends_and_widens(client):
    tok = register(client, "hana@example.com", age=9.0)["access_token"]
    h = auth(tok)
    start = date.today() - timedelta(days=370)
    for i, (se, al) in enumerate([(-1.0, 23.5), (-1.5, 23.75), (-2.0, 24.0)]):
        client.post(f"{API}/me/records", headers=h, json={
            "visit_date": (start + timedelta(days=182 * i)).isoformat(),
            "spherical_equivalent": se, "axial_length": al,
            "outdoor_min": 30, "screen_time_hours": 6.0})

    r = client.post(f"{API}/me/project", headers=h, json={"years": 5})
    assert r.status_code == 200, r.text
    pts = r.json()["baseline"]["points"]
    assert len(pts) == 5
    # Uncertainty must grow with each rollout step, never shrink.
    # For SE the "lower" bound is the more negative one, so take the magnitude.
    widths = [abs(p["se_upper"] - p["se_lower"]) for p in pts]
    assert all(b > a for a, b in zip(widths, widths[1:])), widths
    # Confidence must be labelled honestly further out.
    assert pts[0]["confidence"] == "modelled"
    assert pts[-1]["confidence"] == "indicative"


def test_projection_scenario_beats_baseline(client):
    tok = register(client, "ivan@example.com", age=9.0)["access_token"]
    h = auth(tok)
    client.post(f"{API}/me/records", headers=h, json={
        "visit_date": date.today().isoformat(),
        "spherical_equivalent": -2.0, "axial_length": 24.0,
        "outdoor_min": 20, "screen_time_hours": 8.0, "viewing_distance_cm": 22,
        "near_work_min": 300, "continuous_session_min": 120, "posture_score": 0.4})

    r = client.post(f"{API}/me/project", headers=h, json={
        "years": 5, "changes": {"outdoor_min": 120, "screen_time_hours": 2,
                                "viewing_distance_cm": 40}})
    assert r.status_code == 200, r.text
    body = r.json()
    base = body["baseline"]["summary"]["final_se"]
    scen = body["scenario"]["summary"]["final_se"]
    # Better habits should not project a worse outcome than the baseline.
    assert scen >= base, (scen, base)


def test_public_simulator_needs_no_account(client):
    r = client.post(f"{API}/simulator/project", json={
        "age": 10, "spherical_equivalent": -1.5, "years": 3})
    assert r.status_code == 200, r.text
    body = r.json()
    assert len(body["baseline"]["points"]) == 3
    assert body["not_a_diagnosis"]
    # With one time point it must say the estimate rests on little.
    assert body["baseline"]["input_quality"]["notes"]


def test_public_simulator_rejects_impossible_values(client):
    r = client.post(f"{API}/simulator/project", json={
        "age": 10, "spherical_equivalent": -1.5, "years": 3,
        "compare_with": {"outdoor_min": 9000}})
    assert r.status_code == 422


def test_profile_update_rebuilds_the_twin(client):
    tok = register(client, "jo@example.com", "Jo J", age=8.0)["access_token"]
    h = auth(tok)
    client.post(f"{API}/me/records", headers=h, json={
        "visit_date": date.today().isoformat(),
        "spherical_equivalent": -1.2, "axial_length": 23.6})

    before = client.get(f"{API}/me/prediction", headers=h).json()
    r = client.patch(f"{API}/auth/me", headers=h,
                     json={"parental_myopia": 2, "age": 8.5})
    assert r.status_code == 200
    after = client.get(f"{API}/me/prediction", headers=h).json()
    # Family history feeds the model, so the estimate must be recomputed.
    assert after["twin_version"] > before["twin_version"]


def test_password_change(client):
    tok = register(client, "kim@example.com")["access_token"]
    h = auth(tok)
    bad = client.post(f"{API}/auth/change-password", headers=h,
                      json={"current_password": "nope", "new_password": "brandnew2026"})
    assert bad.status_code == 401
    ok = client.post(f"{API}/auth/change-password", headers=h,
                     json={"current_password": PW, "new_password": "brandnew2026"})
    assert ok.status_code == 204
    assert client.post(f"{API}/auth/login", json={
        "email": "kim@example.com", "password": "brandnew2026"}).status_code == 200


def test_risk_consistency_flag_is_reported(client):
    tok = register(client, "lee@example.com", age=10.0)["access_token"]
    h = auth(tok)
    client.post(f"{API}/me/records", headers=h, json={
        "visit_date": date.today().isoformat(),
        "spherical_equivalent": -2.0, "axial_length": 24.0})
    risk = client.get(f"{API}/me/prediction", headers=h).json()["risk"]
    # The regression and the classifier are trained separately, so the API must
    # always say whether they agree for this record.
    assert "consistent_with_interval" in risk
    assert "interval_implied_probability" in risk
