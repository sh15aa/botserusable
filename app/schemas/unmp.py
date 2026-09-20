from enum import Enum
from typing import Optional, Dict, Any, List
from pydantic import BaseModel, Field
import uuid
import time


class ChannelType(str, Enum):
    WHATSAPP = "whatsapp"
    TELEGRAM = "telegram"
    DISCORD = "discord"
    SLACK = "slack"


class MessageContentType(str, Enum):
    TEXT = "text"
    INTERACTIVE_BUTTON = "interactive_button"
    INTERACTIVE_LIST = "interactive_list"
    IMAGE = "image"
    AUDIO = "audio"
    DOCUMENT = "document"
    LOCATION = "location"
    CONTACT = "contact"


class MessageContent(BaseModel):
    text: Optional[str] = None
    action_payload: Optional[str] = None
    media_url: Optional[str] = None
    mime_type: Optional[str] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None


class UnifiedMessage(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    channel: ChannelType
    channel_message_id: str
    sender_id: Optional[str] = None  # Internal unified User UUID
    channel_user_id: str             # Phone number (E.164) or Telegram User ID
    conversation_id: Optional[str] = None
    timestamp: int = Field(default_factory=lambda: int(time.time() * 1000))
    type: MessageContentType
    content: MessageContent
    metadata: Dict[str, Any] = Field(default_factory=dict)


class ButtonAction(BaseModel):
    id: str
    title: str


class ListMenuRow(BaseModel):
    id: str
    title: str
    description: Optional[str] = None


class ListMenuSection(BaseModel):
    title: str
    rows: List[ListMenuRow]


class ListMenu(BaseModel):
    title: str
    button_text: str
    sections: List[ListMenuSection]


class MediaContent(BaseModel):
    type: str  # image, document, audio
    url: str
    caption: Optional[str] = None
    file_name: Optional[str] = None


class UnifiedResponse(BaseModel):
    recipient_channel_user_id: str
    channel: ChannelType
    conversation_id: Optional[str] = None
    text: Optional[str] = None
    buttons: Optional[List[ButtonAction]] = None
    list_menu: Optional[ListMenu] = None
    media: Optional[MediaContent] = None
