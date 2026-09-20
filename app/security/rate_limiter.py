import time
from typing import Tuple
from redis.asyncio import Redis

LUA_SLIDING_WINDOW_RATE_LIMIT = """
local key = KEYS[1]
local now = tonumber(ARGV[1])
local clear_before = tonumber(ARGV[2])
local limit = tonumber(ARGV[3])
local window = tonumber(ARGV[4])

-- Remove items older than current window
redis.call('ZREMRANGEBYSCORE', key, 0, clear_before)

-- Count current items in window
local current_requests = redis.call('ZCARD', key)

if current_requests < limit then
    redis.call('ZADD', key, now, now)
    redis.call('EXPIRE', key, window)
    return { 1, limit - current_requests - 1 }
else
    return { 0, 0 }
end
"""


class DistributedRateLimiter:
    def __init__(self, redis: Redis):
        self.redis = redis

    async def check_limit(
        self,
        identifier: str,
        limit: int = 30,
        window_seconds: int = 60
    ) -> Tuple[bool, int]:
        """
        Sliding-window rate limiter executed atomically via Lua script in Redis.
        Returns (is_allowed, remaining_requests).
        """
        now = int(time.time() * 1000)
        clear_before = now - (window_seconds * 1000)
        key = f"ratelimit:{identifier}"

        result = await self.redis.eval(
            LUA_SLIDING_WINDOW_RATE_LIMIT,
            1,
            key,
            now,
            clear_before,
            limit,
            window_seconds
        )

        allowed = bool(result[0] == 1)
        remaining = int(result[1])
        return allowed, remaining
