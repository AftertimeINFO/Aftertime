import logging
import time
from datetime import UTC, datetime, timedelta
from redis import Redis
from redis.exceptions import RedisError

from app.config import settings
from app.db import SessionLocal
from app.models import LabRun, SyncJob
from app.services.model_lab import prepare_run, process_next
from app.services.run_queue import SimulationQueueUnavailable, enqueue_simulation
from app.sync.runner import run_sync_job

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("aftertime.worker")


def main() -> None:
    redis = Redis.from_url(settings.redis_url, decode_responses=True)
    logger.info("sync and Model Lab worker ready")
    while True:
        try:
            item = redis.blpop(["aftertime:simulation", "aftertime:sync"], timeout=settings.sync_poll_seconds)
        except RedisError:
            logger.warning("queue unavailable; worker will retry", exc_info=True)
            time.sleep(min(max(settings.sync_poll_seconds, 1), 10))
            continue
        if not item:
            continue
        queue, job_id = item
        if queue == "aftertime:simulation":
            with SessionLocal() as db:
                run = db.get(LabRun, job_id)
                if not run:
                    continue
                try:
                    if run.status in {"completed", "failed", "stopped", "paused"}:
                        continue
                    was_queued = run.status == "queued"
                    if not run.state:
                        prepare_run(db, run)
                    if was_queued:
                        run.status = "running"; db.commit()
                    db.refresh(run)
                    now = datetime.now(UTC)
                    event_mode = bool(run.event_speed_until and run.event_speed_until > now)
                    effective_speed = run.event_speed if event_mode else run.idle_speed
                    step_speed = effective_speed
                    previous_time = run.current_time
                    iteration_started = time.perf_counter()
                    result = process_next(db, run, max_step_seconds=max(.001, effective_speed))
                    if result.get("event") in set(run.event_speed_event_types or []):
                        run.event_speed_until = datetime.now(UTC) + timedelta(seconds=max(0, run.event_speed_duration_seconds))
                    if run.run_until and run.current_time >= run.run_until:
                        run.current_time = min(run.current_time, run.run_until)
                        run.run_until = None
                        run.status = "paused"
                    db.commit()
                    model_seconds = max(0.0, (run.current_time - previous_time).total_seconds())
                    if run.status == "running":
                        if model_seconds:
                            desired_wall_seconds = model_seconds / max(step_speed, .001)
                            time.sleep(max(0, desired_wall_seconds - (time.perf_counter() - iteration_started)))
                        enqueue_simulation(run.id)
                except SimulationQueueUnavailable as exc:
                    logger.warning("simulation run %s is waiting for queue recovery", run.id)
                    run.status = "queue_waiting"; run.error = str(exc); db.commit()
                except Exception as exc:
                    logger.exception("simulation run %s failed", run.id)
                    run.status = "failed"; run.error = str(exc); db.commit()
            continue
        with SessionLocal() as db:
            job = db.get(SyncJob, job_id)
            if not job:
                logger.warning("sync job %s no longer exists", job_id)
                continue
            try:
                run_sync_job(db, job)
                logger.info("sync job %s succeeded", job_id)
            except Exception:
                logger.exception("sync job %s failed", job_id)


if __name__ == "__main__":
    main()
