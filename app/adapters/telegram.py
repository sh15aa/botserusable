import httpx
import logging
from typing import Optional, Dict, Any, List
from app.adapters.base import BaseChannelAdapter
from app.schemas.unmp import (
    UnifiedMessage,
    UnifiedResponse,
    ChannelType,
    MessageContentType,
    MessageContent,
)

logger = logging.getLogger(__name__)


class TelegramAdapter(BaseChannelAdapter):
    def __init__(self, bot_token: str):
        self.bot_token = bot_token
        self.base_url = f"https://api.telegram.org/bot{self.bot_token}"

    def parse_inbound(self, raw_payload: Dict[str, Any]) -> Optional[UnifiedMessage]:
        try:
            if "message" in raw_payload:
                msg = raw_payload["message"]
                sender = msg.get("from", {})
                chat = msg.get("chat", {})
                channel_user_id = str(chat.get("id"))
                msg_id = str(msg.get("message_id"))
                timestamp = int(msg.get("date", 0)) * 1000

                content = MessageContent()
                unified_type = MessageContentType.TEXT

                if "text" in msg:
                    content.text = msg.get("text", "")
                    unified_type = MessageContentType.TEXT
                elif "photo" in msg:
                    unified_type = MessageContentType.IMAGE
                    photos = msg.get("photo", [])
                    content.media_url = photos[-1].get("file_id") if photos else None
                    content.text = msg.get("caption", "")
                elif "location" in msg:
                    unified_type = MessageContentType.LOCATION
                    content.latitude = msg.get("location", {}).get("latitude")
                    content.longitude = msg.get("location", {}).get("longitude")

                return UnifiedMessage(
                    channel=ChannelType.TELEGRAM,
                    channel_message_id=msg_id,
                    channel_user_id=channel_user_id,
                    timestamp=timestamp,
                    type=unified_type,
                    content=content,
                    metadata={"raw_payload": msg, "sender": sender},
                )

            elif "callback_query" in raw_payload:
                cb = raw_payload["callback_query"]
                sender = cb.get("from", {})
                channel_user_id = str(sender.get("id"))
                msg_id = str(cb.get("message", {}).get("message_id", cb.get("id")))

                return UnifiedMessage(
                    channel=ChannelType.TELEGRAM,
                    channel_message_id=msg_id,
                    channel_user_id=channel_user_id,
                    timestamp=int(cb.get("message", {}).get("date", 0)) * 1000,
                    type=MessageContentType.INTERACTIVE_BUTTON,
                    content=MessageContent(
                        text=cb.get("data", ""),
                        action_payload=cb.get("data", ""),
                    ),
                    metadata={"raw_payload": cb, "callback_id": cb.get("id")},
                )

            return None
        except Exception as e:
            logger.error(f"Error parsing Telegram update: {e}", exc_info=True)
            return None

    async def render_and_send(self, response: UnifiedResponse) -> bool:
        url = f"{self.base_url}/sendMessage"
        payload: Dict[str, Any] = {
            "chat_id": response.recipient_channel_user_id,
            "text": response.text or "",
            "parse_mode": "HTML",
        }

        if response.buttons and len(response.buttons) > 0:
            keyboard: List[List[Dict[str, str]]] = [
                [{"text": b.title, "callback_data": b.id} for b in response.buttons]
            ]
            payload["reply_markup"] = {"inline_keyboard": keyboard}

        elif response.list_menu:
            # Map hierarchical list menus to multi-row Telegram inline keyboards
            keyboard = []
            for sec in response.list_menu.sections:
                for row in sec.rows:
                    keyboard.append([{"text": row.title, "callback_data": row.id}])
            payload["reply_markup"] = {"inline_keyboard": keyboard}

        async with httpx.AsyncClient(timeout=10.0) as client:
            try:
                res = await client.post(url, json=payload)
                res.raise_for_status()
                return True
            except httpx.HTTPStatusError as err:
                logger.error(f"Telegram API HTTP error {err.response.status_code}: {err.response.text}")
                return False
            except Exception as e:
                logger.error(f"Telegram API request failed: {e}", exc_info=True)
                return False
