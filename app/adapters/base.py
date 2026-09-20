from abc import ABC, abstractmethod
from typing import Optional, Any, Dict
from app.schemas.unmp import UnifiedMessage, UnifiedResponse


class BaseChannelAdapter(ABC):
    @abstractmethod
    def parse_inbound(self, raw_payload: Dict[str, Any]) -> Optional[UnifiedMessage]:
        """Parse native channel webhook payload into UnifiedMessage."""
        pass

    @abstractmethod
    async def render_and_send(self, response: UnifiedResponse) -> bool:
        """Render UnifiedResponse into native channel payload and dispatch."""
        pass
