from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from typing import Dict, Any, List, Optional
from redis.asyncio import Redis

from app.config import settings
from app.security.rbac import require_admin_auth, SecurityContext
from app.security.feature_flags import FeatureFlagService
from app.business.broadcast import BroadcastCampaign
from app.adapters.whatsapp import WhatsAppAdapter
from app.adapters.telegram import TelegramAdapter

router = APIRouter(prefix="/admin", tags=["Admin Operations"], dependencies=[Depends(require_admin_auth)])


class FeatureFlagRequest(BaseModel):
    flag_name: str
    value: str


class KillSwitchRequest(BaseModel):
    flag_name: str
    active: bool


class BroadcastRequest(BaseModel):
    recipients: List[Dict[str, str]]
    message: str


class UserBlockRequest(BaseModel):
    user_identifier: str  # "whatsapp:+123456" or "telegram:123456"
    blocked: bool


@router.get("/metrics")
async def get_metrics():
    redis = Redis.from_url(settings.REDIS_URL, decode_responses=True)
    keys = await redis.keys("ratelimit:*")
    active_users = len(keys)
    return {
        "active_users_last_minute": active_users,
        "system_status": "operational",
        "environment": settings.ENVIRONMENT,
    }


@router.post("/feature-flags")
async def update_feature_flag(req: FeatureFlagRequest):
    redis = Redis.from_url(settings.REDIS_URL)
    svc = FeatureFlagService(redis)
    await svc.set_flag(req.flag_name, req.value)
    return {"status": "updated", "flag": req.flag_name, "value": req.value}


@router.post("/kill-switch")
async def toggle_kill_switch(req: KillSwitchRequest):
    redis = Redis.from_url(settings.REDIS_URL)
    svc = FeatureFlagService(redis)
    await svc.set_kill_switch(req.flag_name, req.active)
    return {"status": "updated", "kill_switch": req.flag_name, "active": req.active}


@router.post("/broadcast")
async def dispatch_broadcast(req: BroadcastRequest):
    redis = Redis.from_url(settings.REDIS_URL)
    wa = WhatsAppAdapter(
        phone_number_id=settings.WHATSAPP_PHONE_NUMBER_ID or "",
        access_token=settings.WHATSAPP_ACCESS_TOKEN or "",
    )
    tg = TelegramAdapter(bot_token=settings.TELEGRAM_BOT_TOKEN or "")
    campaign = BroadcastCampaign(redis, wa, tg)
    results = await campaign.send_broadcast(req.recipients, req.message)
    return {"status": "completed", "results": results}
