import os
import time

from tests.test_fields import _login

FAKE_OCTAVE = os.path.join(os.path.dirname(__file__), "fixtures", "fake_octave.sh")
FAKE_OCTAVE_WITH_ANIMATION = os.path.join(
    os.path.dirname(__file__), "fixtures", "fake_octave_with_animation.sh"
)


def _run_job_and_wait(client, token, field_id):
    job_id = client.post(
        f"/fields/{field_id}/recommendation/run",
        headers={"Authorization": f"Bearer {token}"},
    ).json()["job_id"]

    for _ in range(50):
        poll = client.get(
            f"/fields/{field_id}/recommendation/jobs/{job_id}",
            headers={"Authorization": f"Bearer {token}"},
        )
        if poll.json()["status"] == "done":
            return
        time.sleep(0.1)
    raise AssertionError("engine job never completed")


def _make_field(client, token):
    return client.post(
        "/fields",
        json={"crop": "mais", "size_hectares": 0.8, "latitude": 9.34, "longitude": 2.63, "planting_date": "2026-03-01"},
        headers={"Authorization": f"Bearer {token}"},
    ).json()["id"]


def test_recommendation_is_404_with_no_completed_engine_run(client):
    token = _login(client)
    field_id = _make_field(client, token)

    response = client.get(
        f"/fields/{field_id}/recommendation",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 404


def test_history_is_empty_with_no_completed_engine_run(client):
    token = _login(client)
    field_id = _make_field(client, token)

    response = client.get(
        f"/fields/{field_id}/history",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    assert response.json() == []


def test_recommendation_and_history_reflect_a_completed_engine_run(client, monkeypatch):
    monkeypatch.setenv("ENGINE_OCTAVE_CMD", FAKE_OCTAVE)
    monkeypatch.setenv("ENGINE_SCRIPT_PATH", "unused-by-fake")

    token = _login(client, phone="+22990000030")
    field_id = _make_field(client, token)

    job_id = client.post(
        f"/fields/{field_id}/recommendation/run",
        headers={"Authorization": f"Bearer {token}"},
    ).json()["job_id"]

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
    )
    assert reco.status_code == 200
    body = reco.json()
    assert 0 <= body["soil_moisture_percent"] <= 100
    assert body["explanation"]

    history = client.get(
        f"/fields/{field_id}/history",
        headers={"Authorization": f"Bearer {token}"},
    ).json()
    assert len(history) == 1
    assert history[0]["date"] == body["date"]
    assert isinstance(history[0]["severe_stress_alert"], bool)


def test_recommendation_has_animation_false_and_animation_404_without_frames(client, monkeypatch):
    monkeypatch.setenv("ENGINE_OCTAVE_CMD", FAKE_OCTAVE)
    monkeypatch.setenv("ENGINE_SCRIPT_PATH", "unused-by-fake")

    token = _login(client, phone="+22990000031")
    field_id = _make_field(client, token)
    _run_job_and_wait(client, token, field_id)

    reco = client.get(
        f"/fields/{field_id}/recommendation", headers={"Authorization": f"Bearer {token}"}
    )
    assert reco.json()["has_animation"] is False

    animation = client.get(
        f"/fields/{field_id}/recommendation/animation", headers={"Authorization": f"Bearer {token}"}
    )
    assert animation.status_code == 404


def test_recommendation_animation_is_served_when_present(client, monkeypatch):
    monkeypatch.setenv("ENGINE_OCTAVE_CMD", FAKE_OCTAVE_WITH_ANIMATION)
    monkeypatch.setenv("ENGINE_SCRIPT_PATH", "unused-by-fake")

    token = _login(client, phone="+22990000032")
    field_id = _make_field(client, token)
    _run_job_and_wait(client, token, field_id)

    reco = client.get(
        f"/fields/{field_id}/recommendation", headers={"Authorization": f"Bearer {token}"}
    )
    assert reco.json()["has_animation"] is True

    animation = client.get(
        f"/fields/{field_id}/recommendation/animation", headers={"Authorization": f"Bearer {token}"}
    )
    assert animation.status_code == 200
    body = animation.json()
    assert body["grid_res"] == 2
    assert len(body["frames"]) == 2
    assert body["r_emitter"] == 0.005
    assert len(body["trace_debut"]["frames"]) == 2
    assert body["trace_debut"]["frame_times_s"] == [0, 0.5]
    assert len(body["trace_fin"]["frames"]) == 2
    assert body["trace_fin"]["frame_times_s"] == [130.5, 131.0]
