import hmac
from enum import Enum
from typing import List, Optional
from fastapi import Header, HTTPException, status, Depends
from app.config import settings


class Role(str, Enum):
    OWNER = "owner"
    ADMIN = "admin"
    OPERATOR = "operator"
    SUPPORT = "support"


class SecurityContext:
    def __init__(self, actor_id: str, role: Role):
        self.actor_id = actor_id
        self.role = role

    def has_permission(self, allowed_roles: List[Role]) -> bool:
        return self.role in allowed_roles


async def require_admin_auth(
    x_api_key: Optional[str] = Header(None, alias="X-Admin-API-Key")
) -> SecurityContext:
    """
    Constant-time API Key verification for Admin operations.
    """
    if not x_api_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Admin API key required in X-Admin-API-Key header"
        )

    # Use constant-time comparison against configured secret key
    is_valid = hmac.compare_digest(x_api_key, settings.SECRET_KEY)
    if not is_valid:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invalid Admin API credentials"
        )

    return SecurityContext(actor_id="admin_master", role=Role.ADMIN)
