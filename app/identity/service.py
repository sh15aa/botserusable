import uuid
import logging
from typing import Optional, Dict, Any, Tuple
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update
from app.models.user import User, ChannelIdentity

logger = logging.getLogger(__name__)


class IdentityResolutionService:
    def __init__(self, db_session: AsyncSession):
        self.db = db_session

    async def resolve_or_create_user(
        self,
        channel: str,
        channel_user_id: str,
        full_name: Optional[str] = None,
        phone_e164: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> Tuple[User, bool]:
        """
        Resolves or creates a unified User from a channel identifier (WhatsApp phone or Telegram ID).
        Returns (User, is_created).
        """
        # 1. Lookup existing channel identity
        stmt = (
            select(ChannelIdentity)
            .where(
                ChannelIdentity.channel == channel,
                ChannelIdentity.channel_user_id == channel_user_id
            )
        )
        res = await self.db.execute(stmt)
        identity = res.scalar_one_or_none()

        if identity:
            user_stmt = select(User).where(User.id == identity.user_id)
            user_res = await self.db.execute(user_stmt)
            user = user_res.scalar_one()
            return user, False

        # 2. If phone_e164 is provided (e.g. from WhatsApp or Telegram contact share), check if User already exists
        user = None
        if phone_e164:
            phone_stmt = select(User).where(User.phone_e164 == phone_e164)
            phone_res = await self.db.execute(phone_stmt)
            user = phone_res.scalar_one_or_none()

        is_created = False
        if not user:
            # 3. Create new User
            user = User(
                id=uuid.uuid4(),
                full_name=full_name,
                phone_e164=phone_e164 if channel == "whatsapp" else None,
                locale="en",
                timezone="UTC",
                is_blocked=False,
            )
            self.db.add(user)
            await self.db.flush()
            is_created = True

        # 4. Link channel identity
        new_identity = ChannelIdentity(
            id=uuid.uuid4(),
            user_id=user.id,
            channel=channel,
            channel_user_id=channel_user_id,
            metadata_=metadata or {},
        )
        self.db.add(new_identity)
        await self.db.commit()
        await self.db.refresh(user)

        return user, is_created

    async def link_accounts(
        self,
        primary_user_id: uuid.UUID,
        secondary_channel: str,
        secondary_channel_user_id: str
    ) -> bool:
        """
        Links a secondary channel (e.g. Telegram ID) to an existing primary user (e.g. WhatsApp user).
        """
        # Ensure identity isn't already assigned elsewhere
        stmt = select(ChannelIdentity).where(
            ChannelIdentity.channel == secondary_channel,
            ChannelIdentity.channel_user_id == secondary_channel_user_id
        )
        res = await self.db.execute(stmt)
        existing = res.scalar_one_or_none()

        if existing:
            if existing.user_id == primary_user_id:
                return True  # Already linked
            # Re-link to primary
            existing.user_id = primary_user_id
        else:
            new_id = ChannelIdentity(
                id=uuid.uuid4(),
                user_id=primary_user_id,
                channel=secondary_channel,
                channel_user_id=secondary_channel_user_id,
            )
            self.db.add(new_id)

        await self.db.commit()
        return True

    async def set_user_blocked_status(self, user_id: uuid.UUID, is_blocked: bool) -> bool:
        """Blocks or unblocks a user across all channels."""
        stmt = update(User).where(User.id == user_id).values(is_blocked=is_blocked)
        await self.db.execute(stmt)
        await self.db.commit()
        return True
