import asyncio
from collections.abc import AsyncGenerator
import uuid
from fastapi import HTTPException, status
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
    Tier-1 Distributed Concurrency Lock with spin-wait retry loop and Lua release.
    Serializes concurrent requests across workers to prevent race conditions.
    """

    def __init__(
        self,
        redis: aioredis.Redis,
        lock_key: str,
        ttl_seconds: int = 10,
        timeout_seconds: float = 5.0,
        retry_interval: float = 0.05,
    ) -> None:
        self.redis = redis
        self.lock_key = f"lock:{lock_key}" if not lock_key.startswith("lock:") else lock_key
        self.ttl = ttl_seconds
        self.timeout = timeout_seconds
        self.retry_interval = retry_interval
        self.token = str(uuid.uuid4())
        self.acquired = False

    async def acquire(self) -> bool:
        loop = asyncio.get_running_loop()
        deadline = loop.time() + self.timeout

        while True:
            # Atomic acquisition setting a unique token ownership ID
            result = await self.redis.set(self.lock_key, self.token, nx=True, ex=self.ttl)
            if result:
                self.acquired = True
                return True

            if loop.time() >= deadline:
                return False

            await asyncio.sleep(self.retry_interval)

    async def release(self) -> None:
        if not self.acquired:
            return

        # Atomic Lua script: release key only if the token matches owner
        release_script = """
        if redis.call('get', KEYS[1]) == ARGV[1] then
            return redis.call('del', KEYS[1])
        else
            return 0
        end
        """
        try:
            await self.redis.eval(release_script, 1, self.lock_key, self.token)
        except Exception:
            pass
        finally:
            self.acquired = False

    async def __aenter__(self) -> "DistributedLock":
        acquired = await self.acquire()
        if not acquired:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Resource {self.lock_key} lock acquisition timeout: currently held by another worker.",
            )
        return self

    async def __aexit__(self, exc_type: object, exc_val: object, exc_tb: object) -> None:
        await self.release()