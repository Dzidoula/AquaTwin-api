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


FAKE_OCTAVE_DATA_DRIVEN = os.path.join(
    os.path.dirname(__file__), "fixtures", "fake_octave_season_data_driven.sh"
)


def test_season_simulation_data_driven_returns_rendement_and_appreciation(client, monkeypatch):
    monkeypatch.setenv("ENGINE_OCTAVE_CMD", FAKE_OCTAVE_DATA_DRIVEN)
    monkeypatch.setenv("SEASON_DATA_DRIVEN_SCRIPT_PATH", "unused-by-fake")

    token = _login(client, phone="+22990000024")
    field_id = _make_field(client, token)

    resp = client.post(
        f"/fields/{field_id}/season-simulation-data-driven",
        headers={"Authorization": f"Bearer {token}"},
        json={"jours_test": [6, 9, 12], "eto_test": [4.0, 4.2, 3.8]},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["rendement"] == 6611.44
    assert body["biomasse"] == 13222.88
    assert body["appreciation"] == "Bon"


def test_season_simulation_data_driven_requires_matching_lengths(client, monkeypatch):
    monkeypatch.setenv("ENGINE_OCTAVE_CMD", FAKE_OCTAVE_DATA_DRIVEN)
    monkeypatch.setenv("SEASON_DATA_DRIVEN_SCRIPT_PATH", "unused-by-fake")

    token = _login(client, phone="+22990000025")
    field_id = _make_field(client, token)

    resp = client.post(
        f"/fields/{field_id}/season-simulation-data-driven",
        headers={"Authorization": f"Bearer {token}"},
        json={"jours_test": [6, 9], "eto_test": [4.0]},
    )
    assert resp.status_code == 422


def test_season_simulation_data_driven_requires_auth(client):
    resp = client.post(
        "/fields/anything/season-simulation-data-driven",
        json={"jours_test": [6], "eto_test": [4.0]},
    )
    assert resp.status_code == 401


def test_season_simulation_data_driven_surfaces_engine_failure(client, monkeypatch):
    failing_octave = os.path.join(os.path.dirname(__file__), "fixtures", "fake_octave_always_fails.sh")
    monkeypatch.setenv("ENGINE_OCTAVE_CMD", failing_octave)
    monkeypatch.setenv("SEASON_DATA_DRIVEN_SCRIPT_PATH", "unused-by-fake")

    token = _login(client, phone="+22990000026")
    field_id = _make_field(client, token)

    resp = client.post(
        f"/fields/{field_id}/season-simulation-data-driven",
        headers={"Authorization": f"Bearer {token}"},
        json={"jours_test": [6], "eto_test": [4.0]},
    )
    assert resp.status_code == 502


FAKE_OCTAVE_OPTIMAL_HARVEST = os.path.join(
    os.path.dirname(__file__), "fixtures", "fake_octave_optimal_harvest.sh"
)


def test_optimal_harvest_returns_the_best_scenario_found(client, monkeypatch):
    monkeypatch.setenv("ENGINE_OCTAVE_CMD", FAKE_OCTAVE_OPTIMAL_HARVEST)
    monkeypatch.setenv("OPTIMAL_HARVEST_SCRIPT_PATH", "unused-by-fake")

    token = _login(client, phone="+22990000027")
    field_id = _make_field(client, token)

    resp = client.post(
        f"/fields/{field_id}/optimal-harvest",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["rendement"] == 8200.5
    assert body["optimal_eto"] == 4.5
    assert body["appreciation"] == "Exceptionnel"
    assert body["n_iterations"] == 3


def test_optimal_harvest_requires_auth(client):
    resp = client.post("/fields/anything/optimal-harvest")
    assert resp.status_code == 401


def test_optimal_harvest_rejects_other_owners_field(client):
    token_a = _login(client, phone="+22990000028")
    field_id = _make_field(client, token_a)
    token_b = _login(client, phone="+22990000029")

    resp = client.post(
        f"/fields/{field_id}/optimal-harvest",
        headers={"Authorization": f"Bearer {token_b}"},
    )
    assert resp.status_code == 403


def test_optimal_harvest_surfaces_engine_failure(client, monkeypatch):
    failing_octave = os.path.join(os.path.dirname(__file__), "fixtures", "fake_octave_always_fails.sh")
    monkeypatch.setenv("ENGINE_OCTAVE_CMD", failing_octave)
    monkeypatch.setenv("OPTIMAL_HARVEST_SCRIPT_PATH", "unused-by-fake")

    token = _login(client, phone="+22990000030")
    field_id = _make_field(client, token)

    resp = client.post(
        f"/fields/{field_id}/optimal-harvest",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 502
