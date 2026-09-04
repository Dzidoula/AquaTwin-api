import asyncio
import json
import os
import stat

import pytest

from app.engine_runner import run_engine, EngineRunError, ENGINE_LOCK, SEASON_LOCK


FAKE_OCTAVE = os.path.join(os.path.dirname(__file__), "fixtures", "fake_octave.sh")
FAKE_OCTAVE_ECHO_ENV = os.path.join(os.path.dirname(__file__), "fixtures", "fake_octave_echo_env.sh")
FAKE_OCTAVE_NOISY_ERROR = os.path.join(os.path.dirname(__file__), "fixtures", "fake_octave_noisy_error.sh")


@pytest.mark.asyncio
async def test_run_engine_returns_parsed_output():
    result = await run_engine(
        params={"culture": "mais", "lat": 9.3, "lon": 2.6, "jour_julien": 220,
                "psi_old": None, "theta_infiltre": 0.0},
        octave_cmd=FAKE_OCTAVE,
        script_path="unused-by-fake",
    )
    assert result["should_irrigate"] is True
    assert result["duration_s"] == 131.79


@pytest.mark.asyncio
async def test_run_engine_passes_extra_env_to_the_subprocess():
    result = await run_engine(
        params={"culture": "mais", "lat": 9.3, "lon": 2.6},
        octave_cmd=FAKE_OCTAVE_ECHO_ENV,
        script_path="unused-by-fake",
        extra_env={"TEST_ECHO_VAR": "hello-from-extra-env"},
    )
    assert result["echoed"] == "hello-from-extra-env"


@pytest.mark.asyncio
async def test_run_engine_raises_on_nonzero_exit():
    with pytest.raises(EngineRunError):
        await run_engine(
            params={"culture": "mais", "lat": 9.3, "lon": 2.6, "jour_julien": 220,
                    "psi_old": None, "theta_infiltre": 0.0, "force_fail": True},
            octave_cmd=FAKE_OCTAVE,
            script_path="unused-by-fake",
        )


@pytest.mark.asyncio
async def test_run_engine_strips_octave_noise_from_the_error_message():
    with pytest.raises(EngineRunError) as exc_info:
        await run_engine(
            params={"culture": "mais", "lat": 20.0, "lon": 7.4},
            octave_cmd=FAKE_OCTAVE_NOISY_ERROR,
            script_path="unused-by-fake",
        )
    message = exc_info.value.message
    assert "octave:" not in message
    assert "called from" not in message
    assert "SoilGrids_Rosetta" not in message
    assert "Aucune donnee de sol disponible" in message


@pytest.mark.asyncio
async def test_run_engine_serializes_concurrent_calls():
    # Two calls started together must not run their subprocess at the same
    # time — the fake script writes a marker file for the duration of its
    # run, and errors out if it finds another marker file already there.
    results = await asyncio.gather(
        run_engine(
            params={"culture": "mais", "lat": 9.3, "lon": 2.6, "jour_julien": 220,
                    "psi_old": None, "theta_infiltre": 0.0},
            octave_cmd=FAKE_OCTAVE,
            script_path="unused-by-fake",
        ),
        run_engine(
            params={"culture": "mais", "lat": 9.3, "lon": 2.6, "jour_julien": 221,
                    "psi_old": None, "theta_infiltre": 0.0},
            octave_cmd=FAKE_OCTAVE,
            script_path="unused-by-fake",
        ),
    )
    assert len(results) == 2


@pytest.mark.asyncio
async def test_season_lock_is_independent_of_the_recommendation_engine_lock():
    # A long-running recommendation job (holding ENGINE_LOCK) must never
    # block a season-simulation call — they run unrelated scripts with no
    # shared state. Regression test for the bug where both used the same
    # lock and a slow/stuck daily job froze the Predictions tab for
    # everyone until it finished (up to 30 min).
    await ENGINE_LOCK.acquire()
    try:
        result = await asyncio.wait_for(
            run_engine(
                params={"culture": "mais", "irrigation_coverage": 0.7},
                octave_cmd=FAKE_OCTAVE,
                script_path="unused-by-fake",
                lock=SEASON_LOCK,
            ),
            timeout=2,
        )
        assert result["should_irrigate"] is True
    finally:
        ENGINE_LOCK.release()
