import os

FAKE_OCTAVE = os.path.join(os.path.dirname(__file__), "fixtures", "fake_octave_season.sh")


def _make_field(client, token):
    resp = client.post(
        "/fields",
        headers={"Authorization": f"Bearer {token}"},
        json={"crop": "mais", "size_hectares": 1.0, "latitude": 9.3,
              "longitude": 2.6, "planting_date": "2026-06-01"},
    )
    return resp.json()["id"]


def _login(client, phone="+22990000020"):
    client.post("/auth/otp/request", json={"phone": phone})
    resp = client.post("/auth/otp/verify", json={"phone": phone, "code": "1234"})
    return resp.json()["token"]


def test_season_simulation_returns_points_and_appreciation(client, monkeypatch):
    monkeypatch.setenv("ENGINE_OCTAVE_CMD", FAKE_OCTAVE)
    monkeypatch.setenv("SEASON_SCRIPT_PATH", "unused-by-fake")

    token = _login(client)
    field_id = _make_field(client, token)

    resp = client.post(
        f"/fields/{field_id}/season-simulation",
        headers={"Authorization": f"Bearer {token}"},
        json={"irrigation_coverage": 0.7},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["final_rendement"] == 1.5
    assert body["appreciation"] == "Faible"
    assert body["points"] == [
        {"day": 1, "biomass": 1.5, "rendement": 0.75},
        {"day": 2, "biomass": 3.0, "rendement": 1.5},
    ]


def test_season_simulation_requires_auth(client):
    resp = client.post("/fields/anything/season-simulation", json={"irrigation_coverage": 0.7})
    assert resp.status_code == 401


def test_season_simulation_rejects_other_owners_field(client):
    token_a = _login(client, phone="+22990000021")
    field_id = _make_field(client, token_a)
    token_b = _login(client, phone="+22990000022")

    resp = client.post(
        f"/fields/{field_id}/season-simulation",
        headers={"Authorization": f"Bearer {token_b}"},
        json={"irrigation_coverage": 0.7},
    )
    assert resp.status_code == 403


def test_season_simulation_surfaces_engine_failure(client, monkeypatch):
    failing_octave = os.path.join(os.path.dirname(__file__), "fixtures", "fake_octave_always_fails.sh")
    monkeypatch.setenv("ENGINE_OCTAVE_CMD", failing_octave)
    monkeypatch.setenv("SEASON_SCRIPT_PATH", "unused-by-fake")

    token = _login(client, phone="+22990000023")
    field_id = _make_field(client, token)

    resp = client.post(
        f"/fields/{field_id}/season-simulation",
        headers={"Authorization": f"Bearer {token}"},
        json={"irrigation_coverage": 0.7},
    )
    assert resp.status_code == 502
