from redis import Redis
from redis.exceptions import RedisError

from app.config import settings
from app.layers import DEFAULT_LAYER, Layer, queue_item

SIMULATION_QUEUE = "aftertime:simulation"
SYNC_QUEUE = "aftertime:sync"


class SimulationQueueUnavailable(RuntimeError):
    """The durable run exists, but Redis cannot accept it yet."""


def enqueue_simulation(run_id: str, layer: Layer = DEFAULT_LAYER) -> None:
    try:
        Redis.from_url(settings.redis_url, decode_responses=True).rpush(
            SIMULATION_QUEUE, queue_item(layer, run_id)
        )
    except RedisError as exc:
        raise SimulationQueueUnavailable(
            "Черга симуляції тимчасово недоступна"
        ) from exc


def enqueue_sync(job_id: str, layer: Layer = DEFAULT_LAYER) -> None:
    Redis.from_url(settings.redis_url, decode_responses=True).rpush(
        SYNC_QUEUE, queue_item(layer, job_id)
    )
