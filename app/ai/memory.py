import json
from typing import List, Dict, Any
from redis.asyncio import Redis


class ConversationMemory:
    def __init__(self, redis: Redis, window_size: int = 10):
        self.redis = redis
        self.window_size = window_size

    async def get_history(self, user_id: str) -> List[Dict[str, str]]:
        """
        Retrieves recent conversation turns formatted for OpenAI Chat Completions.
        """
        key = f"ai:memory:{user_id}"
        items = await self.redis.lrange(key, 0, self.window_size - 1)
        history = []
        for item in reversed(items):
            try:
                history.append(json.loads(item))
            except Exception:
                pass
        return history

    async def append_turn(self, user_id: str, role: str, content: str, ttl_seconds: int = 86400):
        """
        Appends a message turn and trims the list to keep window_size elements.
        """
        key = f"ai:memory:{user_id}"
        payload = json.dumps({"role": role, "content": content})
        await self.redis.lpush(key, payload)
        await self.redis.ltrim(key, 0, self.window_size - 1)
        await self.redis.expire(key, ttl_seconds)

    async def clear_memory(self, user_id: str):
        key = f"ai:memory:{user_id}"
        await self.redis.delete(key)
