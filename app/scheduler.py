"""Autonomous daily trigger for the recommendation engine.

Run once a day (see the systemd timer unit shipped alongside this repo) by
`python3 -m app.scheduler`. For every field with no job created today, it
starts one and runs it to completion before moving to the next — the engine
can only run one calculation at a time (see engine_runner.ENGINE_LOCK), so
there is nothing to gain from doing this any other way.

One field's failure (a convergence error, ISRIC being down, ...) never stops
the run for the others: `execute_job` already marks that job "failed" and
returns normally. Tomorrow's run will simply try that field again.
"""

import asyncio
import logging
from datetime import date, datetime, timezone

from . import models
from .jobs import execute_job

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("aquatwin.scheduler")


def _has_job_today(db, field_id: str) -> bool:
    today_start = datetime.combine(date.today(), datetime.min.time(), tzinfo=timezone.utc)
    return (
        db.query(models.RecommendationJobModel)
        .filter(
            models.RecommendationJobModel.field_id == field_id,
            models.RecommendationJobModel.created_at >= today_start,
        )
        .first()
        is not None
    )


async def run_daily_batch() -> None:
    # Imported lazily (not at module import time) so tests that monkeypatch
    # database_module.SessionLocal to an in-memory engine are respected —
    # same reason app/jobs.py does this inside execute_job rather than at
    # its own module top.
    from .database import SessionLocal

    db = SessionLocal()
    try:
        all_ids = [f.id for f in db.query(models.FieldModel.id).order_by(models.FieldModel.id).all()]
        # Plain strings, not ORM objects: a batch can span hours (up to 30
        # min per field), and every db.commit() in the loop below expires
        # every object already loaded in this session (SQLAlchemy's
        # expire_on_commit default) — touching a FieldModel after that
        # re-queries it, which raises ObjectDeletedError if that field was
        # deleted in the meantime. Plain IDs sidestep that entirely.
        due_ids = [field_id for field_id in all_ids if not _has_job_today(db, field_id)]
        logger.info("%d/%d fields due for today's run", len(due_ids), len(all_ids))

        for field_id in due_ids:
            try:
                if db.query(models.FieldModel).filter_by(id=field_id).first() is None:
                    logger.info("field %s: no longer exists, skipping", field_id)
                    continue
                job = models.RecommendationJobModel(field_id=field_id, status="pending")
                db.add(job)
                db.commit()
                job_id = job.id
                logger.info("field %s: job %s starting", field_id, job_id)
                await execute_job(job_id, field_id)
                # execute_job commits through its own separate session — this
                # session's identity map still holds the `job` object from
                # right above (non-expired, since accessing `.id` after our
                # own commit already reloaded it), so a plain requery here
                # would just hand back that same stale object instead of
                # reflecting the row execute_job actually wrote. db.refresh()
                # forces a real re-SELECT.
                db.refresh(job)
                logger.info("field %s: job %s finished with status=%s", field_id, job_id, job.status)
            except Exception:
                # One field's DB/engine trouble must never stop the rest of
                # the batch — log and move on, same spirit as execute_job
                # already marking a failed run without raising.
                db.rollback()
                logger.exception("field %s: unexpected error, skipping", field_id)
    finally:
        db.close()


def main() -> None:
    asyncio.run(run_daily_batch())


if __name__ == "__main__":
    main()
