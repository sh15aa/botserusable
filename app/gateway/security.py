import hmac
import hashlib
from typing import Optional
from redis.asyncio import Redis


class WebhookSecurityService:
    def __init__(self, redis: Redis):
        self.redis = redis

    @staticmethod
    def verify_whatsapp_signature(
        raw_body: bytes,
        signature_header: Optional[str],
        app_secret: str
    ) -> bool:
        """
        Verifies WhatsApp webhook signature using constant-time HMAC-SHA256 comparison.
        Header format: sha256={hash}
        """
        if not signature_header or not signature_header.startswith("sha256="):
            return False

        received_sig = signature_header.split("sha256=")[1].strip()
        expected_sig = hmac.new(
            app_secret.encode("utf-8"),
            raw_body,
            hashlib.sha256
        ).hexdigest()

        return hmac.compare_digest(received_sig, expected_sig)

    @staticmethod
    def verify_telegram_secret(
        secret_header: Optional[str],
        configured_secret: str
    ) -> bool:
        """
        Verifies Telegram X-Telegram-Bot-Api-Secret-Token in constant time.
        """
        if not secret_header or not configured_secret:
            return False

        return hmac.compare_digest(secret_header, configured_secret)

    @staticmethod
    def verify_chatwoot_webhook(
        raw_body: bytes,
        signature_header: Optional[str],
        webhook_secret: str
    ) -> bool:
        """
        Verifies Chatwoot webhook signature if configured in Chatwoot settings.
        """
        if not signature_header or not webhook_secret:
            return False

        expected_sig = hmac.new(
            webhook_secret.encode("utf-8"),
            raw_body,
            hashlib.sha256
        ).hexdigest()

        return hmac.compare_digest(signature_header, expected_sig)

    async def is_duplicate_event(
        self,
        channel: str,
        event_id: str,
        ttl_seconds: int = 86400
    ) -> bool:
        """
        Distributed atomic anti-replay / idempotency check.
        Returns True if the event was already processed.
        """
        key = f"idempotency:{channel}:{event_id}"
        # set(..., nx=True, ex=ttl_seconds) returns True if set was successful, False if key already exists
        was_set = await self.redis.set(key, "1", ex=ttl_seconds, nx=True)
        return not was_set
