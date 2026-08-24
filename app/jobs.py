"""Recommendation-job execution — shared by the interactive `/recommendation/run`
endpoint (app/main.py) and the autonomous daily scheduler (app/scheduler.py).

Kept in its own module so both callers run the exact same engine-invocation
and result-validation logic — one place to fix if the engine's behavior
changes.
"""

import os
from datetime import date, datetime, timezone

from sqlalchemy.orm import Session

from . import models
from .engine_runner import EngineRunError, run_engine


def engine_config() -> tuple[str, str]:
    octave_cmd = os.environ.get("ENGINE_OCTAVE_CMD", "octave")
    script_path = os.environ.get("ENGINE_SCRIPT_PATH", "run_recommendation.m")
    return octave_cmd, script_path


async def execute_job(job_id: str, field_id: str) -> None:
    from .database import SessionLocal

    db: Session = SessionLocal()
    try:
        job = db.query(models.RecommendationJobModel).filter_by(id=job_id).first()
        field = db.query(models.FieldModel).filter_by(id=field_id).first()
        if job is None or field is None:
            return
        job.status = "running"
        db.commit()

        octave_cmd, script_path = engine_config()
        params = {
            "culture": field.crop,
            "lat": field.latitude,
            "lon": field.longitude,
            "size_hectares": field.size_hectares,
            "jour_julien": field.engine_last_julian_day or date.today().timetuple().tm_yday,
            "psi_old": field.engine_psi_state,
            "theta_infiltre": field.engine_theta_infiltre,
        }
        try:
            result = await run_engine(params, octave_cmd=octave_cmd, script_path=script_path)
        except EngineRunError as exc:
            job.status = "failed"
            job.error = exc.message
            job.finished_at = datetime.now(timezone.utc)
            db.commit()
            return

        try:
            # The engine can return a technically-valid JSON response (exit
            # code 0) where a numeric field is nonetheless `null` — e.g. a
            # NaN from a known unresolved unit-conversion issue in
            # dailyIrrigationRecommendation.m (see its comments). Treat that
            # as a failed run instead of silently persisting a "done" job
            # with missing data — the app must never show a incomplete
            # result as if it were a real recommendation.
            missing = [
                key
                for key in ("should_irrigate", "duration_s", "volume", "soil_moisture", "severe_stress")
                if result.get(key) is None
            ]
            if missing:
                raise ValueError(f"Champs manquants dans le resultat du moteur: {', '.join(missing)}")

            job.result = {
                "should_irrigate": result["should_irrigate"],
                "duration_s": result["duration_s"],
                "volume": result["volume"],
                "soil_moisture": result["soil_moisture"],
                "severe_stress": result["severe_stress"],
            }
            field.engine_psi_state = result.get("psi_old")
            field.engine_theta_infiltre = result.get("theta_infiltre", field.engine_theta_infiltre)
            field.engine_last_julian_day = result.get("jour_julien", field.engine_last_julian_day)
            job.status = "done"
            job.finished_at = datetime.now(timezone.utc)
            db.commit()
        except Exception as exc:
            db.rollback()
            job.status = "failed"
            job.error = f"Résultat du moteur invalide: {exc}"
            job.finished_at = datetime.now(timezone.utc)
            db.commit()
            return
    finally:
        db.close()
