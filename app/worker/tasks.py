import json
import logging
from typing import Dict, Any, Optional
from arq.connections import RedisSettings
from redis.asyncio import Redis

from app.config import settings
from app.schemas.unmp import (
    UnifiedMessage,
    UnifiedResponse,
    ChannelType,
    ButtonAction,
)
from app.adapters.whatsapp import WhatsAppAdapter
from app.adapters.telegram import TelegramAdapter
from app.adapters.chatwoot import ChatwootClient
from app.engine.fsm import ConversationEngine, ConversationContext
from app.engine.handoff import HumanHandoffManager
from app.engine.flows import FlowEngine, FlowDefinition, FlowStep
from app.engine.router import MessageRouter
from app.ai.gateway import LLMGateway
from app.ai.memory import ConversationMemory
from app.ai.cost_controller import AICostController
from app.security.rate_limiter import DistributedRateLimiter
from app.security.loop_detector import BotLoopDetector

logger = logging.getLogger(__name__)


def setup_sample_flow(flow_engine: FlowEngine):
    """Registers a sample production lead-capture multi-step flow."""
    lead_flow = FlowDefinition(
        flow_id="lead_capture",
        initial_step_id="step_name",
        steps={
            "step_name": FlowStep(
                id="step_name",
                prompt_text="📋 Let's get you set up! What is your full name?",
                validation_regex=r"^[A-Za-z\s]{2,50}$",
                error_message="Please enter a valid name (letters only, 2-50 characters):",
                next_step_id="step_interest",
            ),
            "step_interest": FlowStep(
                id="step_interest",
                prompt_text="What service are you interested in?",
                options=[
                    ButtonAction(id="INTEREST_AI_BOT", title="AI Bot Building"),
                    ButtonAction(id="INTEREST_CONSULTING", title="Consulting"),
                ],
                next_step_id="step_confirm",
            ),
            "step_confirm": FlowStep(
                id="step_confirm",
                prompt_text="Great! Would you like our team to reach out via WhatsApp?",
                options=[
                    ButtonAction(id="CONFIRM_YES", title="Yes, please"),
                    ButtonAction(id="CONFIRM_NO", title="No, thanks"),
                ],
            ),
        },
    )
    flow_engine.register_flow(lead_flow)


async def startup(ctx: Dict[Any, Any]):
    redis = Redis.from_url(settings.REDIS_URL, decode_responses=False)
    ctx["redis"] = redis

    # Adapters
    ctx["whatsapp"] = WhatsAppAdapter(
        phone_number_id=settings.WHATSAPP_PHONE_NUMBER_ID or "",
        access_token=settings.WHATSAPP_ACCESS_TOKEN or "",
        api_version=settings.WHATSAPP_API_VERSION,
    )
    ctx["telegram"] = TelegramAdapter(
        bot_token=settings.TELEGRAM_BOT_TOKEN or ""
    )
    ctx["chatwoot"] = ChatwootClient(
        base_url=settings.CHATWOOT_BASE_URL,
        api_access_token=settings.CHATWOOT_API_ACCESS_TOKEN or "",
        account_id=settings.CHATWOOT_ACCOUNT_ID,
        inbox_id=settings.CHATWOOT_INBOX_ID,
    )

    # Conversation & Workflow Engines
    ctx["fsm_engine"] = ConversationEngine(redis)
    ctx["handoff_mgr"] = HumanHandoffManager(redis, ctx["chatwoot"], ctx["fsm_engine"])
    ctx["flow_engine"] = FlowEngine()
    setup_sample_flow(ctx["flow_engine"])
    ctx["message_router"] = MessageRouter(ctx["flow_engine"])

    # AI & Security
    ctx["ai_memory"] = ConversationMemory(redis)
    ctx["ai_gateway"] = LLMGateway(
        api_key=settings.OPENAI_API_KEY,
        default_model=settings.OPENAI_MODEL,
        memory=ctx["ai_memory"],
    )
    ctx["cost_controller"] = AICostController(redis)
    ctx["rate_limiter"] = DistributedRateLimiter(redis)
    ctx["loop_detector"] = BotLoopDetector(redis)

    # Register Router Commands
    async def cmd_start(c: ConversationContext, m: UnifiedMessage, args):
        return UnifiedResponse(
            recipient_channel_user_id=m.channel_user_id,
            channel=m.channel,
            text="👋 Welcome! Choose an option below or type your question:",
            buttons=[
                ButtonAction(id="START_LEAD_FLOW", title="Start Intake Form"),
                ButtonAction(id="ACTION_HUMAN_HANDOFF", title="Talk to Agent"),
            ],
        )

    async def cmd_help(c: ConversationContext, m: UnifiedMessage, args):
        return UnifiedResponse(
            recipient_channel_user_id=m.channel_user_id,
            channel=m.channel,
            text="💡 Available commands:\n/start - Main Menu\n/flow - Intake Form\n/human - Connect to Human Agent\n/cancel - Cancel active form",
        )

    async def action_lead_flow(c: ConversationContext, m: UnifiedMessage):
        return await ctx["flow_engine"].start_flow("lead_capture", c, m)

    async def action_human_handoff(c: ConversationContext, m: UnifiedMessage):
        return await ctx["handoff_mgr"].trigger_handoff(c, m, reason="User clicked Talk to Agent")

    ctx["message_router"].register_command("start", cmd_start)
    ctx["message_router"].register_command("help", cmd_help)
    ctx["message_router"].register_command("flow", lambda c, m, a: action_lead_flow(c, m))
    ctx["message_router"].register_command("human", lambda c, m, a: action_human_handoff(c, m))
    ctx["message_router"].register_action("START_LEAD_FLOW", action_lead_flow)
    ctx["message_router"].register_action("ACTION_HUMAN_HANDOFF", action_human_handoff)


async def shutdown(ctx: Dict[Any, Any]):
    redis: Redis = ctx.get("redis")
    if redis:
        await redis.close()


async def process_inbound_message(ctx: Dict[Any, Any], message_data: Dict[str, Any]):
    message = UnifiedMessage.model_validate(message_data)
    rate_limiter: DistributedRateLimiter = ctx["rate_limiter"]
    loop_detector: BotLoopDetector = ctx["loop_detector"]
    fsm_engine: ConversationEngine = ctx["fsm_engine"]
    handoff_mgr: HumanHandoffManager = ctx["handoff_mgr"]
    message_router: MessageRouter = ctx["message_router"]
    ai_gateway: LLMGateway = ctx["ai_gateway"]
    cost_controller: AICostController = ctx["cost_controller"]
    whatsapp: WhatsAppAdapter = ctx["whatsapp"]
    telegram: TelegramAdapter = ctx["telegram"]

    user_identifier = f"{message.channel.value}:{message.channel_user_id}"

    # 1. Rate Limiting Check
    allowed, _ = await rate_limiter.check_limit(user_identifier, limit=30, window_seconds=60)
    if not allowed:
        logger.warning(f"Rate limit exceeded for {user_identifier}")
        return

    # 2. Bot Loop Prevention
    user_text = message.content.text or message.content.action_payload or ""
    if await loop_detector.is_looping(user_identifier, user_text):
        logger.warning(f"Bot-to-bot loop detected and suppressed for {user_identifier}")
        return

    # 3. Message Processing with Distributed Lock
    async def session_handler(context: ConversationContext, msg: UnifiedMessage) -> Optional[UnifiedResponse]:
        # Case A: User is in Human Handoff mode
        if context.is_human_takeover:
            await handoff_mgr.forward_user_message_to_agent(context, msg)
            return None

        # Case B: AI Brain Fallback Handler
        async def fallback_ai(c: ConversationContext, m: UnifiedMessage) -> Optional[UnifiedResponse]:
            # Token Budget Check
            can_run = await cost_controller.can_consume(user_identifier, estimated_tokens=500)
            if not can_run:
                return UnifiedResponse(
                    recipient_channel_user_id=m.channel_user_id,
                    channel=m.channel,
                    text="⏳ You have reached your daily AI usage limit. Please try again tomorrow or talk to a human agent.",
                    buttons=[ButtonAction(id="ACTION_HUMAN_HANDOFF", title="Talk to Agent")],
                )

            ai_reply = await ai_gateway.generate_response(
                user_id=user_identifier,
                user_text=user_text,
                system_prompt="You are a helpful customer support agent. Answer concisely.",
            )
            # Record estimated token consumption
            await cost_controller.record_consumption(user_identifier, prompt_tokens=250, completion_tokens=250)

            return UnifiedResponse(
                recipient_channel_user_id=m.channel_user_id,
                channel=m.channel,
                text=ai_reply,
                buttons=[ButtonAction(id="ACTION_HUMAN_HANDOFF", title="Talk to Agent")],
            )

        # Route via hierarchical router (Flows -> Commands -> Actions -> Fallback AI)
        return await message_router.route(context, msg, fallback_ai)

    response = await fsm_engine.process_with_lock(user_identifier, message, session_handler)

    # 4. Outbound Delivery
    if response:
        if response.channel == ChannelType.WHATSAPP:
            await whatsapp.render_and_send(response)
        elif response.channel == ChannelType.TELEGRAM:
            await telegram.render_and_send(response)


async def dispatch_agent_reply_to_user(
    ctx: Dict[Any, Any],
    channel_str: str,
    recipient_user_id: str,
    agent_message: str
):
    whatsapp: WhatsAppAdapter = ctx["whatsapp"]
    telegram: TelegramAdapter = ctx["telegram"]

    response = UnifiedResponse(
        recipient_channel_user_id=recipient_user_id,
        channel=ChannelType(channel_str),
        text=agent_message,
    )

    if response.channel == ChannelType.WHATSAPP:
        await whatsapp.render_and_send(response)
    elif response.channel == ChannelType.TELEGRAM:
        await telegram.render_and_send(response)


class WorkerSettings:
    functions = [process_inbound_message, dispatch_agent_reply_to_user]
    on_startup = startup
    on_shutdown = shutdown
    redis_settings = RedisSettings.from_dsn(settings.REDIS_URL)
    max_jobs = 100
