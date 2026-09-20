import json
import logging
from fastapi import APIRouter, Request, Header, HTTPException, Query, Response, status
from typing import Optional
from arq import create_pool
from arq.connections import RedisSettings, ArqRedis
from redis.asyncio import Redis

from app.config import settings
from app.gateway.security import WebhookSecurityService
from app.adapters.whatsapp import WhatsAppAdapter
from app.adapters.telegram import TelegramAdapter
from app.engine.fsm import ConversationEngine
from app.engine.handoff import HumanHandoffManager
from app.adapters.chatwoot import ChatwootClient
from app.schemas.chatwoot import ChatwootWebhookPayload

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/webhooks", tags=["Webhooks"])

# Shared resources initialized on app startup
redis_client: Optional[Redis] = None
arq_pool: Optional[ArqRedis] = None
security_svc: Optional[WebhookSecurityService] = None
whatsapp_adapter: Optional[WhatsAppAdapter] = None
telegram_adapter: Optional[TelegramAdapter] = None
chatwoot_client: Optional[ChatwootClient] = None
handoff_manager: Optional[HumanHandoffManager] = None


async def init_gateway_dependencies():
    global redis_client, arq_pool, security_svc, whatsapp_adapter, telegram_adapter, chatwoot_client, handoff_manager
    redis_client = Redis.from_url(settings.REDIS_URL, decode_responses=False)
    arq_pool = await create_pool(RedisSettings.from_dsn(settings.REDIS_URL))
    security_svc = WebhookSecurityService(redis_client)

    whatsapp_adapter = WhatsAppAdapter(
        phone_number_id=settings.WHATSAPP_PHONE_NUMBER_ID or "",
        access_token=settings.WHATSAPP_ACCESS_TOKEN or "",
        api_version=settings.WHATSAPP_API_VERSION,
    )
    telegram_adapter = TelegramAdapter(
        bot_token=settings.TELEGRAM_BOT_TOKEN or ""
    )
    chatwoot_client = ChatwootClient(
        base_url=settings.CHATWOOT_BASE_URL,
        api_access_token=settings.CHATWOOT_API_ACCESS_TOKEN or "",
        account_id=settings.CHATWOOT_ACCOUNT_ID,
        inbox_id=settings.CHATWOOT_INBOX_ID,
    )
    fsm_engine = ConversationEngine(redis_client)
    handoff_manager = HumanHandoffManager(redis_client, chatwoot_client, fsm_engine)


# ---------------------------------------------------------
# WhatsApp Webhooks
# ---------------------------------------------------------

@router.get("/whatsapp")
async def verify_whatsapp_webhook(
    hub_mode: Optional[str] = Query(None, alias="hub.mode"),
    hub_challenge: Optional[str] = Query(None, alias="hub.challenge"),
    hub_verify_token: Optional[str] = Query(None, alias="hub.verify_token"),
):
    """WhatsApp webhook challenge verification."""
    if hub_mode == "subscribe" and hub_verify_token == settings.WHATSAPP_VERIFY_TOKEN:
        return Response(content=hub_challenge, media_type="text/plain")
    raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Verification failed")


@router.post("/whatsapp")
async def handle_whatsapp_webhook(
    request: Request,
    x_hub_signature_256: Optional[str] = Header(None, alias="X-Hub-Signature-256"),
):
    raw_body = await request.body()

    # 1. Constant-time Signature Verification
    if settings.WHATSAPP_APP_SECRET:
        if not security_svc.verify_whatsapp_signature(
            raw_body, x_hub_signature_256, settings.WHATSAPP_APP_SECRET
        ):
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid HMAC signature")

    payload = await request.json()

    # 2. Parse Inbound
    msg = whatsapp_adapter.parse_inbound(payload)
    if not msg:
        return {"status": "ignored"}

    # 3. Distributed Replay / Idempotency Check
    if await security_svc.is_duplicate_event("whatsapp", msg.channel_message_id):
        return {"status": "duplicate_ignored"}

    # 4. Asynchronously enqueue for background processing (< 200ms ACK)
    await arq_pool.enqueue_job("process_inbound_message", msg.model_dump())
    return {"status": "queued"}


# ---------------------------------------------------------
# Telegram Webhooks
# ---------------------------------------------------------

@router.post("/telegram")
async def handle_telegram_webhook(
    request: Request,
    x_telegram_bot_api_secret_token: Optional[str] = Header(None, alias="X-Telegram-Bot-Api-Secret-Token"),
):
    # 1. Constant-time Secret Token Verification
    if settings.TELEGRAM_SECRET_TOKEN:
        if not security_svc.verify_telegram_secret(
            x_telegram_bot_api_secret_token, settings.TELEGRAM_SECRET_TOKEN
        ):
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid secret token")

    payload = await request.json()

    # 2. Parse Inbound
    msg = telegram_adapter.parse_inbound(payload)
    if not msg:
        return {"status": "ignored"}

    # 3. Distributed Replay / Idempotency Check
    if await security_svc.is_duplicate_event("telegram", msg.channel_message_id):
        return {"status": "duplicate_ignored"}

    # 4. Asynchronously enqueue for background processing
    await arq_pool.enqueue_job("process_inbound_message", msg.model_dump())
    return {"status": "queued"}


# ---------------------------------------------------------
# Chatwoot Webhooks (Agent Desk Sync & Handoff Release)
# ---------------------------------------------------------

@router.post("/chatwoot")
async def handle_chatwoot_webhook(
    request: Request,
    x_chatwoot_signature: Optional[str] = Header(None, alias="X-Chatwoot-Signature"),
):
    raw_body = await request.body()

    # 1. Optional Signature Verification
    if settings.CHATWOOT_WEBHOOK_SECRET:
        if not security_svc.verify_chatwoot_webhook(
            raw_body, x_chatwoot_signature, settings.CHATWOOT_WEBHOOK_SECRET
        ):
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid Chatwoot signature")

    payload_dict = await request.json()
    payload = ChatwootWebhookPayload.model_validate(payload_dict)

    # Event 1: Agent sent an outgoing message to the user
    if (
        payload.event == "message_created"
        and payload.message_type == "outgoing"
        and not payload.private
        and payload.conversation
    ):
        conv_id = payload.conversation.id
        custom_attrs = payload.conversation.custom_attributes or {}
        channel = custom_attrs.get("channel")
        channel_user_id = custom_attrs.get("channel_user_id")

        if channel and channel_user_id and payload.content:
            await arq_pool.enqueue_job(
                "dispatch_agent_reply_to_user",
                channel,
                channel_user_id,
                payload.content,
            )
            return {"status": "agent_reply_dispatched"}

    # Event 2: Agent resolved conversation -> release handoff back to bot
    elif payload.event == "conversation_status_changed" and payload.conversation:
        if payload.conversation.status == "resolved":
            conv_id = payload.conversation.id
            released_user_id = await handoff_manager.release_handoff_by_chatwoot_id(conv_id)
            if released_user_id:
                parts = released_user_id.split(":")
                if len(parts) == 2:
                    channel, channel_user_id = parts[0], parts[1]
                    await arq_pool.enqueue_job(
                        "dispatch_agent_reply_to_user",
                        channel,
                        channel_user_id,
                        "🤝 Your conversation with our support agent has ended. Feel free to ask me anything else!",
                    )
            return {"status": "handoff_released"}

    return {"status": "event_acknowledged"}
