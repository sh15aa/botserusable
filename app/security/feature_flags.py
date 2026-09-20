import hashlib
from redis.asyncio import Redis


class FeatureFlagService:
    def __init__(self, redis: Redis):
        self.redis = redis

    async def is_enabled(self, flag_name: str, user_id: str = "") -> bool:
        """
        Evaluates boolean or percentage rollout feature flag.
        Also checks global emergency kill switches.
        """
        # 1. Emergency Kill Switch Check
        kill_switch = await self.redis.get(f"killswitch:{flag_name}")
        if kill_switch == b"1" or kill_switch == "1":
            return False

        # 2. Check Global Flag
        val = await self.redis.get(f"flag:{flag_name}")
        if not val:
            return False

        val_str = val.decode("utf-8") if isinstance(val, bytes) else str(val)

        if val_str.lower() in ("true", "1", "enabled"):
            return True
        if val_str.lower() in ("false", "0", "disabled"):
            return False

        # 3. Percentage Rollout (e.g. "25" for 25% of users)
        if val_str.isdigit() and user_id:
            percentage = int(val_str)
            hash_val = int(hashlib.md5(f"{flag_name}:{user_id}".encode("utf-8")).hexdigest()[:4], 16)
            return (hash_val % 100) < percentage

        return False

    async def set_flag(self, flag_name: str, value: str):
        await self.redis.set(f"flag:{flag_name}", value)

    async def set_kill_switch(self, flag_name: str, active: bool):
        if active:
            await self.redis.set(f"killswitch:{flag_name}", "1")
        else:
            await self.redis.delete(f"killswitch:{flag_name}")
