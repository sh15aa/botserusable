import httpx
import logging
from typing import Optional, Dict, Any

logger = logging.getLogger(__name__)


class ChatwootClient:
    def __init__(
        self,
        base_url: str,
        api_access_token: str,
        account_id: int,
        inbox_id: int
    ):
        self.base_url = base_url.rstrip("/")
        self.api_access_token = api_access_token
        self.account_id = account_id
        self.inbox_id = inbox_id
        self.headers = {
            "api_access_token": self.api_access_token,
            "Content-Type": "application/json",
        }

    async def get_or_create_contact(
        self,
        identifier: str,
        name: Optional[str] = None,
        phone_number: Optional[str] = None,
        email: Optional[str] = None
    ) -> Optional[int]:
        """
        Searches for an existing contact by identifier or phone; creates one if absent.
        """
        search_url = f"{self.base_url}/api/v1/accounts/{self.account_id}/contacts/search"
        async with httpx.AsyncClient(timeout=10.0) as client:
            try:
                # 1. Try search
                search_res = await client.get(
                    search_url,
                    params={"q": phone_number or identifier},
                    headers=self.headers
                )
                if search_res.status_code == 200:
                    payload = search_res.json().get("payload", [])
                    if payload:
                        return payload[0]["id"]

                # 2. Create if not found
                create_url = f"{self.base_url}/api/v1/accounts/{self.account_id}/contacts"
                contact_body: Dict[str, Any] = {
                    "inbox_id": self.inbox_id,
                    "name": name or f"User {identifier[-4:]}",
                    "identifier": identifier,
                }
                if phone_number:
                    contact_body["phone_number"] = phone_number
                if email:
                    contact_body["email"] = email

                create_res = await client.post(create_url, json=contact_body, headers=self.headers)
                if create_res.status_code in (200, 201):
                    return create_res.json()["payload"]["contact"]["id"]

            except Exception as e:
                logger.error(f"Chatwoot get_or_create_contact failed: {e}", exc_info=True)
        return None

    async def get_or_create_conversation(
        self,
        contact_id: int,
        custom_attributes: Optional[Dict[str, Any]] = None
    ) -> Optional[int]:
        """
        Finds the latest open conversation for the contact or creates a new one.
        """
        async with httpx.AsyncClient(timeout=10.0) as client:
            try:
                # Check for active conversations for this contact
                url = f"{self.base_url}/api/v1/accounts/{self.account_id}/conversations"
                body = {
                    "source_id": str(contact_id),
                    "inbox_id": self.inbox_id,
                    "contact_id": contact_id,
                    "custom_attributes": custom_attributes or {},
                    "status": "open",
                }
                res = await client.post(url, json=body, headers=self.headers)
                if res.status_code in (200, 201):
                    return res.json()["id"]
            except Exception as e:
                logger.error(f"Chatwoot get_or_create_conversation failed: {e}", exc_info=True)
        return None

    async def create_message(
        self,
        conversation_id: int,
        content: str,
        message_type: str = "incoming",
        private: bool = False
    ) -> bool:
        """
        Creates a message in the Chatwoot conversation.
        message_type: 'incoming' (from end-user) or 'outgoing' (from bot/agent).
        """
        url = f"{self.base_url}/api/v1/accounts/{self.account_id}/conversations/{conversation_id}/messages"
        body = {
            "content": content,
            "message_type": message_type,
            "private": private,
        }
        async with httpx.AsyncClient(timeout=10.0) as client:
            try:
                res = await client.post(url, json=body, headers=self.headers)
                return res.status_code in (200, 201)
            except Exception as e:
                logger.error(f"Chatwoot create_message failed: {e}", exc_info=True)
                return False

    async def toggle_status(self, conversation_id: int, status: str = "resolved") -> bool:
        """
        Updates conversation status in Chatwoot (e.g., 'open', 'resolved', 'pending').
        """
        url = f"{self.base_url}/api/v1/accounts/{self.account_id}/conversations/{conversation_id}/toggle_status"
        body = {"status": status}
        async with httpx.AsyncClient(timeout=10.0) as client:
            try:
                res = await client.post(url, json=body, headers=self.headers)
                return res.status_code == 200
            except Exception as e:
                logger.error(f"Chatwoot toggle_status failed: {e}", exc_info=True)
                return False
