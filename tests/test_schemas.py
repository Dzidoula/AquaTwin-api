from app import schemas


def test_recommendation_job_out_serializes():
    job = schemas.RecommendationJobOut(
        id="j1",
        field_id="f1",
        status="done",
        created_at="2026-08-19T10:00:00",
        finished_at="2026-08-19T10:13:00",
        result={"should_irrigate": True, "duration_s": 131.79, "volume": 0.0,
                "soil_moisture": 0.31, "severe_stress": False},
        error=None,
    )
    assert job.status == "done"
    assert job.result["should_irrigate"] is True


def test_run_job_response_serializes():
    resp = schemas.RunJobResponse(job_id="j1", status="pending")
    assert resp.job_id == "j1"
    assert resp.status == "pending"
