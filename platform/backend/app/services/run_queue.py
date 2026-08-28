from redis import Redis
from redis.exceptions import RedisError

from app.config import settings


SIMULATION_QUEUE = "aftertime:simulation"


class SimulationQueueUnavailable(RuntimeError):
    """The durable run exists, but Redis cannot accept it yet."""


def enqueue_simulation(run_id: str) -> None:
    try:
        Redis.from_url(settings.redis_url, decode_responses=True).rpush(
            SIMULATION_QUEUE, run_id
        )
    except RedisError as exc:
        raise SimulationQueueUnavailable(
            "Черга симуляції тимчасово недоступна"
        ) from exc
