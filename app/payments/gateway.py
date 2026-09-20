import hmac
import hashlib
import time
import logging
from typing import Dict, Any, Optional
from redis.asyncio import Redis

logger = logging.getLogger(__name__)


class PaymentGateway:
    def __init__(self, redis: Redis, stripe_webhook_secret: Optional[str] = None):
        self.redis = redis
        self.webhook_secret = stripe_webhook_secret

    def verify_stripe_signature(
        self,
        payload_bytes: bytes,
        signature_header: Optional[str],
        tolerance_seconds: int = 300
    ) -> bool:
        """
        Verifies Stripe webhook signature: t={timestamp},v1={hash} using constant-time comparison.
        """
        if not signature_header or not self.webhook_secret:
            return False

        try:
            elements = dict(item.split("=") for item in signature_header.split(","))
            timestamp = int(elements.get("t", "0"))
            v1_sig = elements.get("v1", "")

            # Check timestamp freshness to prevent replay attacks
            if abs(time.time() - timestamp) > tolerance_seconds:
                return False

            signed_payload = f"{timestamp}.".encode("utf-8") + payload_bytes
            expected_sig = hmac.new(
                self.webhook_secret.encode("utf-8"),
                signed_payload,
                hashlib.sha256
            ).hexdigest()

            return hmac.compare_digest(v1_sig, expected_sig)
        except Exception as e:
            logger.error(f"Stripe signature verification failed: {e}")
            return False

    async def set_user_subscription(self, user_id: str, tier: str, expires_at: int):
        """Sets subscription tier ('free', 'pro', 'enterprise') in Redis."""
        key = f"billing:tier:{user_id}"
        ttl = max(1, expires_at - int(time.time()))
        await self.redis.set(key, tier, ex=ttl)

    async def get_user_tier(self, user_id: str) -> str:
        key = f"billing:tier:{user_id}"
        tier = await self.redis.get(key)
        return tier.decode("utf-8") if isinstance(tier, bytes) else (tier or "free")

    async def enforce_plan_gate(self, user_id: str, required_tier: str = "pro") -> bool:
        """Enforces plan gate. Returns True if user tier meets or exceeds required tier."""
        tier_levels = {"free": 0, "pro": 1, "enterprise": 2}
        user_tier = await self.get_user_tier(user_id)
        return tier_levels.get(user_tier, 0) >= tier_levels.get(required_tier, 1)
