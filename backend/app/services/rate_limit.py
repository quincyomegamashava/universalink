from __future__ import annotations

import logging
import time

import redis.asyncio as redis

from app.core.config import get_settings

logger = logging.getLogger(__name__)


class RateLimiter:
    """Fixed-window per-key rate limiter backed by Redis."""

    def __init__(self) -> None:
        self._redis: redis.Redis | None = None

    async def connect(self) -> None:
        settings = get_settings()
        self._redis = redis.from_url(settings.redis_url, decode_responses=True)

    async def close(self) -> None:
        if self._redis is not None:
            await self._redis.aclose()
            self._redis = None

    @property
    def client(self) -> redis.Redis:
        if self._redis is None:
            raise RuntimeError("Redis not connected")
        return self._redis

    async def ping(self) -> bool:
        try:
            return bool(await self.client.ping())
        except Exception as exc:  # noqa: BLE001
            logger.warning("Redis ping failed: %s", exc)
            return False

    async def allow(self, key: str, limit: int, window_seconds: int = 60) -> tuple[bool, int]:
        """Return (allowed, remaining). Fail-open if Redis is down."""
        try:
            r = self.client
            now_window = int(time.time() // window_seconds)
            redis_key = f"rl:{key}:{now_window}"
            count = await r.incr(redis_key)
            if count == 1:
                await r.expire(redis_key, window_seconds)
            remaining = max(0, limit - int(count))
            return int(count) <= limit, remaining
        except Exception as exc:  # noqa: BLE001
            logger.warning("Rate limiter error (fail-open): %s", exc)
            return True, limit


rate_limiter = RateLimiter()
