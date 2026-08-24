import os

import app.database as database_module
import app.scheduler as scheduler_module
from app import models
from app.scheduler import run_daily_batch

FAKE_OCTAVE = os.path.join(os.path.dirname(__file__), "fixtures", "fake_octave.sh")


def _login(client, phone="+22990000040"):
    client.post("/auth/otp/request", json={"phone": phone})
    resp = client.post("/auth/otp/verify", json={"phone": phone, "code": "1234"})
    return resp.json()["token"]


def _make_field(client, token, **overrides):
    payload = {
        "crop": "mais", "size_hectares": 1.0, "latitude": 9.3,
        "longitude": 2.6, "planting_date": "2026-06-01",
    }
    payload.update(overrides)
    resp = client.post("/fields", headers={"Authorization": f"Bearer {token}"}, json=payload)
    return resp.json()["id"]


async def test_run_daily_batch_creates_and_runs_a_job_per_field(client, monkeypatch):
    monkeypatch.setenv("ENGINE_OCTAVE_CMD", FAKE_OCTAVE)
    monkeypatch.setenv("ENGINE_SCRIPT_PATH", "unused-by-fake")

    token = _login(client)
    field_id = _make_field(client, token)

    await run_daily_batch()

    history = client.get(
        f"/fields/{field_id}/history",
        headers={"Authorization": f"Bearer {token}"},
    ).json()
    assert len(history) == 1


async def test_run_daily_batch_skips_a_field_that_already_has_a_job_today(client, monkeypatch):
    monkeypatch.setenv("ENGINE_OCTAVE_CMD", FAKE_OCTAVE)
    monkeypatch.setenv("ENGINE_SCRIPT_PATH", "unused-by-fake")

    token = _login(client)
    field_id = _make_field(client, token)

    client.post(
        f"/fields/{field_id}/recommendation/run",
        headers={"Authorization": f"Bearer {token}"},
    )

    await run_daily_batch()

    db = database_module.SessionLocal()
    try:
        job_count = db.query(models.RecommendationJobModel).filter_by(field_id=field_id).count()
    finally:
        db.close()
    # Only the manually-triggered job — run_daily_batch must not queue a
    # second one for a field that already has one today.
    assert job_count == 1


async def test_run_daily_batch_continues_after_one_field_fails(client, monkeypatch):
    monkeypatch.setenv("ENGINE_OCTAVE_CMD", "/bin/false")
    monkeypatch.setenv("ENGINE_SCRIPT_PATH", "unused")

    token = _login(client)
    field_id = _make_field(client, token, latitude=1.0, longitude=1.0)

    await run_daily_batch()

    history = client.get(
        f"/fields/{field_id}/history",
        headers={"Authorization": f"Bearer {token}"},
    ).json()
    assert history == []


async def test_run_daily_batch_survives_a_field_deleted_mid_batch(client, monkeypatch):
    # Regression test: run_daily_batch used to hold ORM FieldModel objects
    # across db.commit() calls. SQLAlchemy expires every loaded object on
    # commit, so touching field.id again later re-queries it — if that row
    # was deleted in the meantime (as happened for real when test fields
    # were cleaned up mid-run), that raised ObjectDeletedError and killed
    # the whole batch, leaving every later field unprocessed for the day.
    monkeypatch.setenv("ENGINE_OCTAVE_CMD", FAKE_OCTAVE)
    monkeypatch.setenv("ENGINE_SCRIPT_PATH", "unused-by-fake")

    token = _login(client)
    field_a = _make_field(client, token, latitude=1.0, longitude=1.0)
    field_b = _make_field(client, token, latitude=2.0, longitude=2.0)

    real_execute_job = scheduler_module.execute_job

    async def execute_job_and_delete_field_b(job_id, field_id):
        await real_execute_job(job_id, field_id)
        if field_id == field_a:
            db = database_module.SessionLocal()
            try:
                db.query(models.FieldModel).filter_by(id=field_b).delete()
                db.commit()
            finally:
                db.close()

    monkeypatch.setattr(scheduler_module, "execute_job", execute_job_and_delete_field_b)

    await run_daily_batch()  # must not raise

    history_a = client.get(
        f"/fields/{field_a}/history",
        headers={"Authorization": f"Bearer {token}"},
    ).json()
    assert len(history_a) == 1
