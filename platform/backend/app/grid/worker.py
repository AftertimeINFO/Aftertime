"""Worker for grid runs: computes queued scenario runs, ensembles and N-1 screenings.

Grid runs are computed in full (not paced in real time like Model Lab runs) and the UI
plays the stored frames back, so they get their own queue and process.
"""

import logging
import time

from redis import Redis
from redis.exceptions import RedisError
from sqlalchemy import text

from app.config import settings
from app.db import engines
from app.grid.runner import execute_run
from app.layers import split_queue_item

GRID_QUEUE = "aftertime:grid"

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("aftertime.grid")


def main() -> None:
    redis = Redis.from_url(settings.redis_url, decode_responses=True)
    logger.info("grid worker ready")
    while True:
        try:
            item = redis.blpop([GRID_QUEUE], timeout=10)
        except RedisError:
            logger.warning("queue unavailable; grid worker will retry", exc_info=True)
            time.sleep(5)
            continue
        if not item:
            continue
        layer, run_id = split_queue_item(item[1])
        engine = engines[layer]
        try:
            execute_run(engine, run_id, log=logger.info)
        except Exception as exc:
            logger.exception("grid run %s failed", run_id)
            with engine.begin() as connection:
                connection.execute(
                    text("UPDATE odbl.grid_runs SET status = 'failed', error = :e, finished_at = now() WHERE id = :id"),
                    {"e": str(exc)[:4000], "id": run_id},
                )


if __name__ == "__main__":
    main()
