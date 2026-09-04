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


def _engine_explanation(result: dict) -> str:
    moisture_pct = float(result.get("soil_moisture", 0) or 0) * 100
    if result.get("severe_stress"):
        return (
            f"Humidité du sol à {moisture_pct:.0f}% (moteur physique) : stress "
            "hydrique sévère détecté, arrosage recommandé sans délai."
        )
    if result.get("should_irrigate"):
        duration_min = round((result.get("duration_s", 0) or 0) / 60)
        volume = float(result.get("volume", 0) or 0)
        return (
            f"Humidité du sol à {moisture_pct:.0f}% (moteur physique) : un "
            f"arrosage de {duration_min} min ({volume:.0f} L) est recommandé aujourd'hui."
        )
    return f"Humidité du sol à {moisture_pct:.0f}% (moteur physique) : pas d'arrosage nécessaire aujourd'hui."


def build_recommendation_dict(result: dict, finished_at: datetime) -> dict:
    """Shapes a raw engine result (theta fractions, seconds) into the
    farmer-facing units the app expects (percent, minutes) — shared by the
    field-scoped recommendation endpoint (app/main.py) and the ad-hoc
    simulation job (execute_simulation_job, added in Task 2)."""
    return {
        "date": finished_at.date().isoformat(),
        "should_irrigate": bool(result.get("should_irrigate", False)),
        "duration_minutes": round((result.get("duration_s", 0) or 0) / 60),
        "volume_liters": round(float(result.get("volume", 0) or 0), 1),
        "severe_stress_alert": bool(result.get("severe_stress", False)),
        "soil_moisture_percent": round(float(result.get("soil_moisture", 0) or 0) * 100, 1),
        "explanation": _engine_explanation(result),
        "has_animation": bool(result.get("animation")),
    }


def engine_config() -> tuple[str, str]:
    octave_cmd = os.environ.get("ENGINE_OCTAVE_CMD", "octave")
    script_path = os.environ.get("ENGINE_SCRIPT_PATH", "run_recommendation.m")
    return octave_cmd, script_path


def emitter_flow_env(emitter_flow_lh: float | None) -> dict[str, str]:
    """Farmer-chosen emitter flow rate (L/h, from a dropdown), converted to
    the m^3/s parameterGoutteur.m expects and passed as an environment
    variable to the Octave subprocess — see Q_IRR_OVERRIDE_M3S there. Empty
    dict (no override) when the farmer didn't pick one, so the engine keeps
    its own hardcoded default."""
    if emitter_flow_lh is None:
        return {}
    q_irr_m3s = emitter_flow_lh * 1e-3 / 3600
    return {"Q_IRR_OVERRIDE_M3S": repr(q_irr_m3s)}


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
            # Farmer-supplied at onboarding; None ("je ne sais pas") makes
            # the engine fall back to classifySoilType (ISRIC) as before.
            "type_sol": field.soil_type,
            "jour_julien": field.engine_last_julian_day or date.today().timetuple().tm_yday,
            "psi_old": field.engine_psi_state,
            "theta_infiltre": field.engine_theta_infiltre,
        }
        try:
            result = await run_engine(
                params,
                octave_cmd=octave_cmd,
                script_path=script_path,
                extra_env=emitter_flow_env(field.emitter_flow_lh),
            )
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
            # Optional: absent when the engine had nothing to irrigate today
            # (nothing to animate), or on older engine versions without it.
            if result.get("animation"):
                job.result["animation"] = result["animation"]
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


async def execute_simulation_job(job_id: str, params: dict, extra_env: dict[str, str] | None = None) -> None:
    from .database import SessionLocal

    db: Session = SessionLocal()
    try:
        job = db.query(models.SimulationJobModel).filter_by(id=job_id).first()
        if job is None:
            return
        job.status = "running"
        db.commit()

        octave_cmd, script_path = engine_config()
        try:
            result = await run_engine(
                params, octave_cmd=octave_cmd, script_path=script_path, extra_env=extra_env
            )
        except EngineRunError as exc:
            job.status = "failed"
            job.error = exc.message
            job.finished_at = datetime.now(timezone.utc)
            db.commit()
            return

        try:
            missing = [
                key
                for key in ("should_irrigate", "duration_s", "volume", "soil_moisture", "severe_stress")
                if result.get(key) is None
            ]
            if missing:
                raise ValueError(f"Champs manquants dans le resultat du moteur: {', '.join(missing)}")

            finished_at = datetime.now(timezone.utc)
            shaped = build_recommendation_dict(result, finished_at)
            if result.get("animation"):
                shaped["animation"] = result["animation"]
            job.result = shaped
            job.status = "done"
            job.finished_at = finished_at
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
