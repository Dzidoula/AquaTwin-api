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
        fields = db.query(models.FieldModel).order_by(models.FieldModel.id).all()
        due = [f for f in fields if not _has_job_today(db, f.id)]
        logger.info("%d/%d fields due for today's run", len(due), len(fields))

        for field in due:
            job = models.RecommendationJobModel(field_id=field.id, status="pending")
            db.add(job)
            db.commit()
            db.refresh(job)
            logger.info("field %s: job %s starting", field.id, job.id)
            await execute_job(job.id, field.id)
            db.refresh(job)
            logger.info("field %s: job %s finished with status=%s", field.id, job.id, job.status)
    finally:
        db.close()


def main() -> None:
    asyncio.run(run_daily_batch())


if __name__ == "__main__":
    main()
