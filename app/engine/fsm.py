import json
import uuid
import logging
from typing import Optional, Dict, Any, Callable, Awaitable
from redis.asyncio import Redis
from app.schemas.unmp import UnifiedMessage, UnifiedResponse

logger = logging.getLogger(__name__)

LUA_RELEASE_LOCK = """
if redis.call("get", KEYS[1]) == ARGV[1] then
    return redis.call("del", KEYS[1])
else
    return 0
end
"""


class ConversationContext:
    def __init__(
        self,
        user_id: str,
        current_state: str = "IDLE",
        state_data: Optional[Dict[str, Any]] = None,
        is_human_takeover: bool = False,
        chatwoot_conversation_id: Optional[int] = None,
        last_active: Optional[int] = None,
    ):
        self.user_id = user_id
        self.current_state = current_state
        self.state_data = state_data or {}
        self.is_human_takeover = is_human_takeover
        self.chatwoot_conversation_id = chatwoot_conversation_id
        self.last_active = last_active

    def to_dict(self) -> Dict[str, Any]:
        return {
            "user_id": self.user_id,
            "current_state": self.current_state,
            "state_data": self.state_data,
            "is_human_takeover": self.is_human_takeover,
            "chatwoot_conversation_id": self.chatwoot_conversation_id,
            "last_active": self.last_active,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ConversationContext":
        return cls(
            user_id=data["user_id"],
            current_state=data.get("current_state", "IDLE"),
            state_data=data.get("state_data", {}),
            is_human_takeover=data.get("is_human_takeover", False),
            chatwoot_conversation_id=data.get("chatwoot_conversation_id"),
            last_active=data.get("last_active"),
        )


class ConversationEngine:
    def __init__(self, redis: Redis):
        self.redis = redis

    async def get_context(self, user_id: str) -> ConversationContext:
        key = f"session:context:{user_id}"
        raw = await self.redis.get(key)
        if raw:
            try:
                data = json.loads(raw)
                return ConversationContext.from_dict(data)
            except Exception:
                pass
        return ConversationContext(user_id=user_id)

    async def save_context(self, context: ConversationContext, ttl_seconds: int = 604800):
        key = f"session:context:{context.user_id}"
        await self.redis.set(key, json.dumps(context.to_dict()), ex=ttl_seconds)

    async def process_with_lock(
        self,
        user_id: str,
        message: UnifiedMessage,
        handler: Callable[[ConversationContext, UnifiedMessage], Awaitable[Optional[UnifiedResponse]]]
    ) -> Optional[UnifiedResponse]:
        """
        Acquires a distributed lock per user session to serialize messages and prevent race conditions.
        """
        lock_key = f"lock:user:{user_id}"
        lock_token = str(uuid.uuid4())
        # 5 second distributed lock
        acquired = await self.redis.set(lock_key, lock_token, px=5000, nx=True)

        if not acquired:
            logger.warning(f"Concurrent message ignored for user {user_id}; lock active.")
            return None

        try:
            context = await self.get_context(user_id)
            response = await handler(context, message)
            await self.save_context(context)
            return response
        finally:
            await self.redis.eval(LUA_RELEASE_LOCK, 1, lock_key, lock_token)
