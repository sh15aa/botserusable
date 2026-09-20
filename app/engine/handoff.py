import logging
from typing import Optional
from redis.asyncio import Redis
from app.adapters.chatwoot import ChatwootClient
from app.engine.fsm import ConversationContext, ConversationEngine
from app.schemas.unmp import UnifiedMessage, UnifiedResponse, ButtonAction

logger = logging.getLogger(__name__)


class HumanHandoffManager:
    def __init__(
        self,
        redis: Redis,
        chatwoot_client: ChatwootClient,
        conversation_engine: ConversationEngine,
    ):
        self.redis = redis
        self.chatwoot = chatwoot_client
        self.engine = conversation_engine

    async def trigger_handoff(
        self,
        context: ConversationContext,
        message: UnifiedMessage,
        reason: str = "User requested live human agent"
    ) -> UnifiedResponse:
        """
        Switches bot session to Human Handoff mode and provisions Chatwoot conversation.
        """
        context.is_human_takeover = True
        context.current_state = "HUMAN_HANDOFF"
        context.state_data["handoff_reason"] = reason

        # 1. Ensure contact exists in Chatwoot
        phone = message.channel_user_id if message.channel == "whatsapp" else None
        contact_id = await self.chatwoot.get_or_create_contact(
            identifier=f"{message.channel}:{message.channel_user_id}",
            phone_number=phone,
        )

        if contact_id:
            # 2. Get or create conversation in Chatwoot
            conv_id = await self.chatwoot.get_or_create_conversation(
                contact_id=contact_id,
                custom_attributes={
                    "channel": message.channel.value,
                    "channel_user_id": message.channel_user_id,
                    "handoff_reason": reason,
                },
            )
            context.chatwoot_conversation_id = conv_id

            # 3. Post note and user message into Chatwoot
            if conv_id:
                # Post private note explaining handoff trigger
                await self.chatwoot.create_message(
                    conversation_id=conv_id,
                    content=f"🤖 [System Notice] Handoff triggered. Reason: {reason}",
                    message_type="outgoing",
                    private=True,
                )
                # Post the actual user's message
                user_text = message.content.text or "[Non-text message]"
                await self.chatwoot.create_message(
                    conversation_id=conv_id,
                    content=user_text,
                    message_type="incoming",
                )

                # Map Chatwoot conversation ID back to user_id for inbound agent webhooks
                await self.redis.set(
                    f"chatwoot:conv_to_user:{conv_id}",
                    context.user_id,
                    ex=604800
                )

        return UnifiedResponse(
            recipient_channel_user_id=message.channel_user_id,
            channel=message.channel,
            text="🤝 I have connected you with a human representative. An agent will respond to you shortly.",
        )

    async def forward_user_message_to_agent(
        self,
        context: ConversationContext,
        message: UnifiedMessage
    ) -> None:
        """
        While in handoff, relay incoming user messages directly to Chatwoot.
        """
        if not context.chatwoot_conversation_id:
            logger.error(f"No Chatwoot conversation ID associated with user {context.user_id}")
            return

        text = message.content.text or "[User sent media or attachment]"
        await self.chatwoot.create_message(
            conversation_id=context.chatwoot_conversation_id,
            content=text,
            message_type="incoming",
        )

    async def release_handoff_by_chatwoot_id(self, chatwoot_conv_id: int) -> Optional[str]:
        """
        Triggered when agent resolves the conversation in Chatwoot.
        Reverts user session back to AI Assistant mode.
        """
        user_id = await self.redis.get(f"chatwoot:conv_to_user:{chatwoot_conv_id}")
        if not user_id:
            logger.warning(f"No user found for Chatwoot conversation {chatwoot_conv_id}")
            return None

        user_id_str = user_id.decode("utf-8") if isinstance(user_id, bytes) else str(user_id)
        context = await self.engine.get_context(user_id_str)
        context.is_human_takeover = False
        context.current_state = "IDLE"
        context.chatwoot_conversation_id = None
        await self.engine.save_context(context)

        logger.info(f"Released human handoff for user {user_id_str}")
        return user_id_str
