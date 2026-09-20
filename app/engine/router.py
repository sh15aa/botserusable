import logging
from typing import Dict, Callable, Awaitable, Optional, List
from app.schemas.unmp import UnifiedMessage, UnifiedResponse, ButtonAction
from app.engine.fsm import ConversationContext
from app.engine.flows import FlowEngine

logger = logging.getLogger(__name__)

CommandHandler = Callable[[ConversationContext, UnifiedMessage, List[str]], Awaitable[Optional[UnifiedResponse]]]
ActionHandler = Callable[[ConversationContext, UnifiedMessage], Awaitable[Optional[UnifiedResponse]]]


class MessageRouter:
    def __init__(self, flow_engine: FlowEngine):
        self.flow_engine = flow_engine
        self.commands: Dict[str, CommandHandler] = {}
        self.actions: Dict[str, ActionHandler] = {}

    def register_command(self, command: str, handler: CommandHandler):
        cmd = command.lower().lstrip("/")
        self.commands[cmd] = handler

    def register_action(self, action_id: str, handler: ActionHandler):
        self.actions[action_id] = handler

    async def route(
        self,
        context: ConversationContext,
        message: UnifiedMessage,
        fallback_ai_handler: Callable[[ConversationContext, UnifiedMessage], Awaitable[Optional[UnifiedResponse]]]
    ) -> Optional[UnifiedResponse]:
        """
        Routes incoming unified messages following hierarchical precedence:
        1. Active Flow Step (if user is currently completing a form)
        2. Slash Command (e.g. /start, /cancel, /help)
        3. Interactive Button/Menu Action
        4. Fallback to AI Assistant
        """
        user_text = (message.content.text or "").strip()
        action_payload = message.content.action_payload

        # 1. Active Flow Processing (unless user types /cancel)
        if context.current_state.startswith("FLOW:"):
            if user_text.lower() in ("/cancel", "cancel"):
                context.current_state = "IDLE"
                context.state_data.pop("active_flow_id", None)
                context.state_data.pop("current_step_id", None)
                return UnifiedResponse(
                    recipient_channel_user_id=message.channel_user_id,
                    channel=message.channel,
                    text="Form cancelled. Returning to main menu.",
                    buttons=[ButtonAction(id="MENU_MAIN", title="Main Menu")]
                )
            return await self.flow_engine.handle_flow_input(context, message)

        # 2. Command Dispatch
        if user_text.startswith("/"):
            parts = user_text.split()
            cmd_name = parts[0][1:].lower()
            args = parts[1:]
            if cmd_name in self.commands:
                return await self.commands[cmd_name](context, message, args)

        # 3. Interactive Action Dispatch
        if action_payload and action_payload in self.actions:
            return await self.actions[action_payload](context, message)

        # 4. Fallback to AI Assistant
        return await fallback_ai_handler(context, message)
