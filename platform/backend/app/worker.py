import logging

from redis import Redis

from app.config import settings
from app.db import SessionLocal
from app.models import SyncJob
from app.sync.runner import run_sync_job

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("aftertime.worker")


def main() -> None:
    redis = Redis.from_url(settings.redis_url, decode_responses=True)
    logger.info("sync worker ready")
    while True:
        item = redis.blpop("aftertime:sync", timeout=settings.sync_poll_seconds)
        if not item:
            continue
        _, job_id = item
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
