from collections.abc import AsyncGenerator
import redis.asyncio as aioredis
from app.core.config import settings

# Global connection pool for Redis operations
redis_pool = aioredis.ConnectionPool.from_url(
    settings.REDIS_URL,
    max_connections=50,
    decode_responses=True,
)


def get_redis_client() -> aioredis.Redis:
    """Instantiate a Redis client bounded to the connection pool."""
    return aioredis.Redis(connection_pool=redis_pool)


async def get_redis() -> AsyncGenerator[aioredis.Redis, None]:
    """FastAPI dependency for accessing the async Redis store."""
    client = get_redis_client()
    try:
        yield client
    finally:
        await client.aclose()


class DistributedLock:
    """
    Asynchronous distributed lock context manager using Redis SET NX EX.
    Guarantees atomic lock acquisition and release with TTL safety nets.
    """

    def __init__(
        self,
        redis: aioredis.Redis,
        lock_key: str,
        ttl_seconds: int = 10,
    ) -> None:
        self.redis = redis
        self.lock_key = f"lock:{lock_key}"
        self.ttl = ttl_seconds
        self.acquired = False

    async def acquire(self) -> bool:
        # SET key value NX EX ttl ensures atomic acquisition with automatic expiration
        result = await self.redis.set(self.lock_key, "LOCKED", nx=True, ex=self.ttl)
        self.acquired = bool(result)
        return self.acquired

    async def release(self) -> None:
        if self.acquired:
            await self.redis.delete(self.lock_key)
            self.acquired = False

    async def __aenter__(self) -> "DistributedLock":
        acquired = await self.acquire()
        if not acquired:
            from fastapi import HTTPException, status
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Resource {self.lock_key} is currently locked by another operation.",
            )
        return self

    async def __aexit__(self, exc_type: object, exc_val: object, exc_tb: object) -> None:
        await self.release()