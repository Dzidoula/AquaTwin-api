import os
import time

from tests.test_fields import _login
from app.jobs import emitter_flow_env

FAKE_OCTAVE = os.path.join(os.path.dirname(__file__), "fixtures", "fake_octave.sh")
FAKE_OCTAVE_WITH_ANIMATION = os.path.join(
    os.path.dirname(__file__), "fixtures", "fake_octave_with_animation.sh"
)
FAKE_OCTAVE_ALWAYS_FAILS = os.path.join(
    os.path.dirname(__file__), "fixtures", "fake_octave_always_fails.sh"
)


def _run_simulation_and_wait(client, token, payload):
    job_id = client.post(
        "/simulations/run",
        json=payload,
        headers={"Authorization": f"Bearer {token}"},
    ).json()["job_id"]

    for _ in range(50):
        poll = client.get(
            f"/simulations/jobs/{job_id}",
            headers={"Authorization": f"Bearer {token}"},
        )
        if poll.json()["status"] in ("done", "failed"):
            return poll.json()
        time.sleep(0.1)
    raise AssertionError("simulation job never completed")


def test_run_requires_a_token(client):
    response = client.post(
        "/simulations/run",
        json={"culture": "mais", "lat": 6.37, "lon": 2.39},
    )
    assert response.status_code == 401


def test_simulation_produces_a_recommendation_shaped_result(client, monkeypatch):
    monkeypatch.setenv("ENGINE_OCTAVE_CMD", FAKE_OCTAVE)
    monkeypatch.setenv("ENGINE_SCRIPT_PATH", "unused-by-fake")

    token = _login(client, phone="+22990000040")
    body = _run_simulation_and_wait(
        client, token, {"culture": "mais", "lat": 6.37, "lon": 2.39, "size_hectares": 0.8}
    )

    assert body["status"] == "done"
    result = body["result"]
    assert result["should_irrigate"] is True
    assert 0 <= result["soil_moisture_percent"] <= 100
    assert result["explanation"]
    assert result["has_animation"] is False


def test_simulation_without_size_hectares_still_succeeds(client, monkeypatch):
    monkeypatch.setenv("ENGINE_OCTAVE_CMD", FAKE_OCTAVE)
    monkeypatch.setenv("ENGINE_SCRIPT_PATH", "unused-by-fake")

    token = _login(client, phone="+22990000041")
    body = _run_simulation_and_wait(
        client, token, {"culture": "tomate", "lat": 6.37, "lon": 2.39}
    )

    assert body["status"] == "done"


def test_simulation_includes_animation_when_the_engine_produces_one(client, monkeypatch):
    monkeypatch.setenv("ENGINE_OCTAVE_CMD", FAKE_OCTAVE_WITH_ANIMATION)
    monkeypatch.setenv("ENGINE_SCRIPT_PATH", "unused-by-fake")

    token = _login(client, phone="+22990000042")
    body = _run_simulation_and_wait(
        client, token, {"culture": "mais", "lat": 6.37, "lon": 2.39}
    )

    assert body["status"] == "done"
    result = body["result"]
    assert result["has_animation"] is True
    assert result["animation"]["grid_res"] == 2
    assert len(result["animation"]["frames"]) == 2


def test_simulation_job_failure_is_reported(client, monkeypatch):
    monkeypatch.setenv("ENGINE_OCTAVE_CMD", FAKE_OCTAVE_ALWAYS_FAILS)
    monkeypatch.setenv("ENGINE_SCRIPT_PATH", "unused-by-fake")

    token = _login(client, phone="+22990000043")
    job_id = client.post(
        "/simulations/run",
        json={"culture": "mais", "lat": 6.37, "lon": 2.39},
        headers={"Authorization": f"Bearer {token}"},
    ).json()["job_id"]

    for _ in range(50):
        poll = client.get(
            f"/simulations/jobs/{job_id}",
            headers={"Authorization": f"Bearer {token}"},
        )
        if poll.json()["status"] == "failed":
            assert poll.json()["error"]
            return
        time.sleep(0.1)
    raise AssertionError("simulation job never failed as expected")


def test_run_rejects_out_of_range_latitude(client):
    token = _login(client, phone="+22990000045")
    response = client.post(
        "/simulations/run",
        json={"culture": "mais", "lat": 999, "lon": 2.39},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 422


def test_unknown_simulation_job_is_404(client):
    token = _login(client, phone="+22990000044")
    response = client.get(
        "/simulations/jobs/does-not-exist",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 404


def test_emitter_flow_env_converts_lh_to_m3s():
    env = emitter_flow_env(4.0)
    assert set(env.keys()) == {"Q_IRR_OVERRIDE_M3S"}
    # 4 L/h = 4e-3 m^3 / 3600 s
    assert abs(float(env["Q_IRR_OVERRIDE_M3S"]) - (4.0 * 1e-3 / 3600)) < 1e-12


def test_emitter_flow_env_is_empty_when_not_given():
    assert emitter_flow_env(None) == {}
