import httpx
import logging
from typing import Optional, Dict, Any
from app.adapters.base import BaseChannelAdapter
from app.schemas.unmp import (
    UnifiedMessage,
    UnifiedResponse,
    ChannelType,
    MessageContentType,
    MessageContent,
)

logger = logging.getLogger(__name__)


class WhatsAppAdapter(BaseChannelAdapter):
    def __init__(
        self,
        phone_number_id: str,
        access_token: str,
        api_version: str = "v19.0"
    ):
        self.phone_number_id = phone_number_id
        self.access_token = access_token
        self.api_version = api_version
        self.base_url = f"https://graph.facebook.com/{self.api_version}/{self.phone_number_id}/messages"

    def parse_inbound(self, raw_payload: Dict[str, Any]) -> Optional[UnifiedMessage]:
        try:
            entry = raw_payload.get("entry", [{}])[0]
            change = entry.get("changes", [{}])[0].get("value", {})
            messages = change.get("messages", [])

            if not messages:
                # Status updates (delivered, read) or unsupported events
                return None

            msg = messages[0]
            channel_user_id = msg.get("from")
            msg_id = msg.get("id")
            timestamp = int(msg.get("timestamp", 0)) * 1000
            msg_type = msg.get("type")

            content = MessageContent()
            unified_type = MessageContentType.TEXT

            if msg_type == "text":
                content.text = msg.get("text", {}).get("body", "")
                unified_type = MessageContentType.TEXT

            elif msg_type == "interactive":
                interactive = msg.get("interactive", {})
                reply = interactive.get("button_reply") or interactive.get("list_reply") or {}
                content.text = reply.get("title", "")
                content.action_payload = reply.get("id", "")
                unified_type = (
                    MessageContentType.INTERACTIVE_BUTTON
                    if "button_reply" in interactive
                    else MessageContentType.INTERACTIVE_LIST
                )

            elif msg_type == "image":
                unified_type = MessageContentType.IMAGE
                content.media_url = msg.get("image", {}).get("id")  # Media ID
                content.mime_type = msg.get("image", {}).get("mime_type")
                content.text = msg.get("image", {}).get("caption")

            elif msg_type == "location":
                unified_type = MessageContentType.LOCATION
                loc = msg.get("location", {})
                content.latitude = loc.get("latitude")
                content.longitude = loc.get("longitude")

            else:
                content.text = f"[Unsupported message type: {msg_type}]"

            return UnifiedMessage(
                channel=ChannelType.WHATSAPP,
                channel_message_id=msg_id,
                channel_user_id=channel_user_id,
                timestamp=timestamp,
                type=unified_type,
                content=content,
                metadata={"raw_payload": msg}
            )
        except Exception as e:
            logger.error(f"Error parsing WhatsApp inbound message: {e}", exc_info=True)
            return None

    async def render_and_send(self, response: UnifiedResponse) -> bool:
        headers = {
            "Authorization": f"Bearer {self.access_token}",
            "Content-Type": "application/json",
        }

        body: Dict[str, Any] = {
            "messaging_product": "whatsapp",
            "recipient_type": "individual",
            "to": response.recipient_channel_user_id,
        }

        if response.buttons and len(response.buttons) > 0:
            body["type"] = "interactive"
            body["interactive"] = {
                "type": "button",
                "body": {"text": response.text or ""},
                "action": {
                    "buttons": [
                        {
                            "type": "reply",
                            "reply": {"id": b.id, "title": b.title[:20]},
                        }
                        for b in response.buttons[:3]  # WhatsApp max 3 quick-reply buttons
                    ]
                },
            }
        elif response.list_menu:
            body["type"] = "interactive"
            body["interactive"] = {
                "type": "list",
                "header": {"type": "text", "text": response.list_menu.title[:60]},
                "body": {"text": response.text or "Please select an option:"},
                "action": {
                    "button": response.list_menu.button_text[:20],
                    "sections": [
                        {
                            "title": s.title[:24],
                            "rows": [
                                {
                                    "id": r.id[:200],
                                    "title": r.title[:24],
                                    "description": r.description[:72] if r.description else None,
                                }
                                for r in s.rows[:10]
                            ],
                        }
                        for s in response.list_menu.sections[:10]
                    ],
                },
            }
        elif response.media:
            body["type"] = response.media.type
            body[response.media.type] = {
                "link": response.media.url,
                "caption": response.media.caption,
            }
        else:
            body["type"] = "text"
            body["text"] = {"preview_url": False, "body": response.text or ""}

        async with httpx.AsyncClient(timeout=10.0) as client:
            try:
                res = await client.post(self.base_url, json=body, headers=headers)
                res.raise_for_status()
                return True
            except httpx.HTTPStatusError as err:
                logger.error(f"WhatsApp API HTTP error {err.response.status_code}: {err.response.text}")
                return False
            except Exception as e:
                logger.error(f"WhatsApp API request failed: {e}", exc_info=True)
                return False
