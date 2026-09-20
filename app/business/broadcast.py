import asyncio
import logging
from typing import List, Dict, Any, Optional
from redis.asyncio import Redis
from app.schemas.unmp import UnifiedResponse, ChannelType
from app.adapters.whatsapp import WhatsAppAdapter
from app.adapters.telegram import TelegramAdapter

logger = logging.getLogger(__name__)


class BroadcastCampaign:
    def __init__(
        self,
        redis: Redis,
        whatsapp_adapter: WhatsAppAdapter,
        telegram_adapter: TelegramAdapter,
        rate_limit_per_second: int = 20
    ):
        self.redis = redis
        self.whatsapp = whatsapp_adapter
        self.telegram = telegram_adapter
        self.rate_limit = rate_limit_per_second

    async def opt_out_user(self, user_identifier: str):
        """Records user opt-out to prevent compliance violations."""
        await self.redis.set(f"broadcast:optout:{user_identifier}", "1")

    async def is_opted_out(self, user_identifier: str) -> bool:
        return await self.redis.exists(f"broadcast:optout:{user_identifier}") == 1

    async def send_broadcast(
        self,
        recipients: List[Dict[str, str]],  # [{"channel": "whatsapp", "user_id": "+1234567890"}]
        message_text: str
    ) -> Dict[str, int]:
        """
        Dispatches broadcast campaign with rate-limiting throttling and opt-out checks.
        """
        stats = {"total": len(recipients), "sent": 0, "opted_out": 0, "failed": 0}
        delay_between_messages = 1.0 / self.rate_limit

        for item in recipients:
            channel_str = item["channel"]
            user_id = item["user_id"]
            user_ident = f"{channel_str}:{user_id}"

            if await self.is_opted_out(user_ident):
                stats["opted_out"] += 1
                continue

            response = UnifiedResponse(
                recipient_channel_user_id=user_id,
                channel=ChannelType(channel_str),
                text=message_text,
            )

            try:
                success = False
                if response.channel == ChannelType.WHATSAPP:
                    success = await self.whatsapp.render_and_send(response)
                elif response.channel == ChannelType.TELEGRAM:
                    success = await self.telegram.render_and_send(response)

                if success:
                    stats["sent"] += 1
                else:
                    stats["failed"] += 1
            except Exception as e:
                logger.error(f"Broadcast failed for {user_ident}: {e}")
                stats["failed"] += 1

            await asyncio.sleep(delay_between_messages)

        return stats
