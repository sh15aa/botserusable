import hashlib
from redis.asyncio import Redis


class BotLoopDetector:
    def __init__(self, redis: Redis):
        self.redis = redis

    async def is_looping(self, user_id: str, message_text: str, max_repeats: int = 4) -> bool:
        """
        Detects bot-to-bot infinite ping-pong loops by tracking message hashes over a sliding window.
        """
        cleaned = message_text.strip().lower()
        msg_hash = hashlib.sha256(cleaned.encode("utf-8")).hexdigest()
        key = f"loop_detector:{user_id}"

        await self.redis.lpush(key, msg_hash)
        await self.redis.ltrim(key, 0, max_repeats - 1)
        await self.redis.expire(key, 60)  # 60s observation window

        recent_hashes = await self.redis.lrange(key, 0, max_repeats - 1)
        if len(recent_hashes) >= max_repeats:
            hashes_str = [h.decode("utf-8") if isinstance(h, bytes) else str(h) for h in recent_hashes]
            if all(h == msg_hash for h in hashes_str):
                return True

        return False
