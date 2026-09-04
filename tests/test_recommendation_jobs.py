import os
import time

FAKE_OCTAVE = os.path.join(os.path.dirname(__file__), "fixtures", "fake_octave.sh")


def _make_field(client, token):
    resp = client.post(
        "/fields",
        headers={"Authorization": f"Bearer {token}"},
        json={"crop": "mais", "size_hectares": 1.0, "latitude": 9.3,
              "longitude": 2.6, "planting_date": "2026-06-01"},
    )
    return resp.json()["id"]


def _login(client, phone="+22990000010"):
    client.post("/auth/otp/request", json={"phone": phone})
    resp = client.post("/auth/otp/verify", json={"phone": phone, "code": "1234"})
    return resp.json()["token"]


def test_run_and_poll_job_reaches_done(client, monkeypatch):
    monkeypatch.setenv("ENGINE_OCTAVE_CMD", FAKE_OCTAVE)
    monkeypatch.setenv("ENGINE_SCRIPT_PATH", "unused-by-fake")

    token = _login(client)
    field_id = _make_field(client, token)

    run_resp = client.post(
        f"/fields/{field_id}/recommendation/run",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert run_resp.status_code == 202
    job_id = run_resp.json()["job_id"]
    assert run_resp.json()["status"] == "pending"

    status = None
    for _ in range(50):
        poll = client.get(
            f"/fields/{field_id}/recommendation/jobs/{job_id}",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert poll.status_code == 200
        status = poll.json()["status"]
        if status == "done":
            assert poll.json()["result"]["should_irrigate"] is True
            break
        time.sleep(0.1)
    assert status == "done"

    reco = client.get(
        f"/fields/{field_id}/recommendation",
        headers={"Authorization": f"Bearer {token}"},
    ).json()
    assert reco["eto_mm_jour"] == 4.1
    assert reco["pluie_48h_mm"] == 16.7


def test_run_job_requires_auth(client):
    resp = client.post("/fields/anything/recommendation/run")
    assert resp.status_code == 401


def test_poll_unknown_job_is_404(client):
    token = _login(client, phone="+22990000011")
    field_id = _make_field(client, token)
    resp = client.get(
        f"/fields/{field_id}/recommendation/jobs/does-not-exist",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 404


def test_recommendation_uses_latest_completed_engine_run(client, monkeypatch):
    monkeypatch.setenv("ENGINE_OCTAVE_CMD", FAKE_OCTAVE)
    monkeypatch.setenv("ENGINE_SCRIPT_PATH", "unused-by-fake")

    token = _login(client, phone="+22990000012")
    field_id = _make_field(client, token)

    run_resp = client.post(
        f"/fields/{field_id}/recommendation/run",
        headers={"Authorization": f"Bearer {token}"},
    )
    job_id = run_resp.json()["job_id"]

    for _ in range(50):
        poll = client.get(
            f"/fields/{field_id}/recommendation/jobs/{job_id}",
            headers={"Authorization": f"Bearer {token}"},
        )
        if poll.json()["status"] == "done":
            break
        time.sleep(0.1)
    else:
        raise AssertionError("engine job never completed")

    reco = client.get(
        f"/fields/{field_id}/recommendation",
        headers={"Authorization": f"Bearer {token}"},
    ).json()

    # fake_octave.sh's canned result: soil_moisture=0.31, duration_s=131.79,
    # volume=0.0, should_irrigate=true, severe_stress=false.
    assert reco["should_irrigate"] is True
    assert reco["severe_stress_alert"] is False
    assert reco["soil_moisture_percent"] == 31.0
    assert reco["duration_minutes"] == round(131.79 / 60)
    assert "moteur physique" in reco["explanation"]

    history = client.get(
        f"/fields/{field_id}/history",
        headers={"Authorization": f"Bearer {token}"},
    ).json()
    todays_point = next(p for p in history if p["date"] == reco["date"])
    assert todays_point["soil_moisture_percent"] == 31.0
    assert todays_point["severe_stress_alert"] is False
