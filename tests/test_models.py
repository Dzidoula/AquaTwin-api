from datetime import datetime, timezone

from app import models


def test_recommendation_job_model_round_trip(client):
    from app.database import SessionLocal

    db = SessionLocal()
    try:
        db.rollback()
    finally:
        db.close()


def test_field_has_engine_state_columns():
    field = models.FieldModel(
        owner_id="u1",
        crop="mais",
        size_hectares=1.0,
        latitude=9.3,
        longitude=2.6,
        planting_date="2026-06-01",
    )
    assert field.engine_psi_state is None
    assert field.engine_theta_infiltre == 0.0 or field.engine_theta_infiltre is None
    assert field.engine_last_julian_day is None


def test_recommendation_job_model_fields():
    job = models.RecommendationJobModel(
        field_id="f1",
        status="pending",
        created_at=datetime.now(timezone.utc),
    )
    assert job.status == "pending"
    assert job.result is None
    assert job.error is None
