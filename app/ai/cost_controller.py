import time
import logging
from redis.asyncio import Redis

logger = logging.getLogger(__name__)


class AICostController:
    def __init__(self, redis: Redis, default_daily_token_limit: int = 50000):
        self.redis = redis
        self.daily_limit = default_daily_token_limit

    @staticmethod
    def get_today_key(user_id: str) -> str:
        date_str = time.strftime("%Y-%m-%d")
        return f"ai:tokens:{user_id}:{date_str}"

    async def can_consume(self, user_id: str, estimated_tokens: int = 500) -> bool:
        """
        Checks if the user has remaining token allowance for today.
        """
        key = self.get_today_key(user_id)
        current = await self.redis.get(key)
        used = int(current) if current else 0
        return (used + estimated_tokens) <= self.daily_limit

    async def record_consumption(self, user_id: str, prompt_tokens: int, completion_tokens: int):
        """
        Records token usage and sets 48h TTL on the daily key.
        """
        total = prompt_tokens + completion_tokens
        key = self.get_today_key(user_id)
        await self.redis.incrby(key, total)
        await self.redis.expire(key, 172800)  # 48 hours retention

        # Also increment global monthly billing meter
        month_str = time.strftime("%Y-%m")
        await self.redis.incrby(f"ai:meter:global:{month_str}", total)

    async def get_usage(self, user_id: str) -> int:
        key = self.get_today_key(user_id)
        current = await self.redis.get(key)
        return int(current) if current else 0
