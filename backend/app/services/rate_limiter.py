from fastapi import HTTPException

from app.core.redis import redis_client


RATE_LIMIT_REQUESTS = 30
RATE_LIMIT_WINDOW_SECONDS = 60


def check_schedule_rate_limit(user_id: int) -> None:
    key = f"rate_limit:schedule:{user_id}"

    current_count = redis_client.incr(key)

    if current_count == 1:
        redis_client.expire(
            key,
            RATE_LIMIT_WINDOW_SECONDS,
        )

    if current_count > RATE_LIMIT_REQUESTS:
        raise HTTPException(
            status_code=429,
            detail="Too many email scheduling requests. Please try again later.",
            headers={
                "Retry-After": str(RATE_LIMIT_WINDOW_SECONDS),
            },
        )