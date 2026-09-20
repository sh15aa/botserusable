from typing import Optional, Dict, Any, List
from pydantic import BaseModel, Field


class ChatwootSender(BaseModel):
    id: int
    name: Optional[str] = None
    email: Optional[str] = None
    type: str  # "user" (agent) or "contact" (end user)


class ChatwootConversation(BaseModel):
    id: int
    status: str  # "open", "resolved", "pending"
    channel: Optional[str] = None
    custom_attributes: Dict[str, Any] = Field(default_factory=dict)


class ChatwootWebhookPayload(BaseModel):
    event: str  # "message_created", "conversation_status_changed", etc.
    id: Optional[int] = None
    content: Optional[str] = None
    message_type: Optional[str] = None  # "incoming", "outgoing"
    private: Optional[bool] = False
    sender: Optional[ChatwootSender] = None
    conversation: Optional[ChatwootConversation] = None
    account: Optional[Dict[str, Any]] = None
